import logging
import random
import boto3
import time
import os

from botocore.exceptions import ClientError
from aws_lambda_powertools.logging import Logger
from aws_lambda_powertools.event_handler.api_gateway import (
    ApiGatewayResolver,
    ProxyEventType,
    Response,
)
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    InternalServerError,
    NotFoundError,
    UnauthorizedError,
)


logger = Logger(level=logging.INFO)
app = ApiGatewayResolver(proxy_type=ProxyEventType.APIGatewayProxyEventV2)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ.get("DDB_TABLE"))
domain_name = os.environ.get("DOMAIN_NAME")

chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
base = len(chars)


# https://stackoverflow.com/a/1119769
def encode(num):
    if num == 0:
        return chars[0]

    res = ""
    _divmod = divmod  # Access to locals is faster.

    while num:
        num, rem = _divmod(num, base)
        res += chars[rem]

    return res[::-1]


def decode(string):
    strlen = len(string)
    num = 0
    idx = 0

    for char in string:
        power = strlen - (idx + 1)
        num += chars.index(char) * (base**power)
        idx += 1

    return num


def clicks_for_value(attr, val):
    items = table.scan(
        ReturnConsumedCapacity="NONE",
        ProjectionExpression=f"{attr},ClickCount",
        FilterExpression=f"#{attr} = :{attr}",
        ExpressionAttributeValues={f":{attr}": val},
        ExpressionAttributeNames={f"#{attr}": attr},
    )["Items"]

    clicks = 0
    for i in items:
        clicks += i["ClickCount"]

    return clicks


def all_clicks_by_attr(items, attr):
    result = {}
    for i in items:
        value = i[attr]
        clicks = i["ClickCount"]

        if value not in result:
            result[value] = clicks
        else:
            result[value] += clicks

    return result


@app.post("/")
def shorten():
    warnings = {}

    try:
        long_url = app.current_event.json_body["longUrl"].strip()
        assert long_url
    except (AssertionError, KeyError) as e:
        logger.error(e)
        raise BadRequestError("Invalid JSON payload")

    try:
        int(long_url)
        raise BadRequestError("Invalid longUrl")
    except ValueError:
        pass

    if len(long_url.split("://")) < 2:
        warnings = {"warnings": "No protocol found, defaulting to http"}
        long_url = f"http://{long_url}"

    # 62^6 - 1 = decode(999999) = max value for ddb_id
    # So, #possible IDs < #possible encodings
    # random.seed(hash(long_url)) + PYTHONHASHSEED=0
    # ensures URL encodes to same suid each time
    random.seed(hash(long_url))
    ddb_id = random.randint(0, base**6 - 1)
    suid = encode(ddb_id)

    now = int(time.time() * 10**6)
    table.put_item(
        Item={
            "Id": ddb_id,
            "LongUrl": long_url,
            "CreateTime": now,
            "ShortUrlId": str(suid),
            "ClickCount": 0,
            "TTL": now + (365 * 24 * 60 * 60),
        },
    )

    logger.info(f"Encoded {long_url} into {suid}")
    return {"short_url": f"https://{domain_name}/{suid}"} | warnings


@app.get("/<suid>")
def redirect(suid):
    ddb_id = decode(suid)

    try:
        item = table.query(
            KeyConditionExpression="#Id = :val",
            ExpressionAttributeNames={"#Id": "Id"},
            ExpressionAttributeValues={":val": ddb_id},
            Limit=1,
        )["Items"][0]

        long_url = item["LongUrl"]

        table.update_item(
            Key={"Id": ddb_id, "CreateTime": item["CreateTime"]},
            ConditionExpression="attribute_exists(LongUrl)",
            UpdateExpression="SET #ClickCount = #ClickCount + :val",
            ExpressionAttributeNames={"#ClickCount": "ClickCount"},
            ExpressionAttributeValues={":val": 1},
        )

        logger.info(f"Decoded {suid} into {long_url}")
        return Response(
            status_code=302,
            body="redirecting...",
            content_type="text/plain",
            headers={"Location": long_url},
        )
    except IndexError as e:
        logger.error(e)
        raise NotFoundError("Could not find short URL")


@app.get("/api/status")
def status():
    return {"status": "alive"}


@app.get("/api/clicks")
def clicks():
    try:
        assert app.current_event.headers["x-kellink-token"] == "let-me-in"
    except (AssertionError, KeyError) as e:
        logger.error(e)
        raise UnauthorizedError("Invalid or missing API token")

    suid = app.current_event.get_query_string_value("suid", default_value="")
    long_url = app.current_event.get_query_string_value("long_url", default_value="")

    if suid or long_url:
        quick_results = {}
        if suid:
            quick_results[suid] = clicks_for_value("ShortUrlId", suid)
        if long_url:
            quick_results[long_url] = clicks_for_value("LongUrl", long_url)
        return quick_results

    items = table.scan(
        ReturnConsumedCapacity="NONE",
        ProjectionExpression="ShortUrlId,LongUrl,ClickCount",
    )["Items"]

    return {
        "clicks_by_suid": all_clicks_by_attr(items, "ShortUrlId"),
        "clicks_by_long_url": all_clicks_by_attr(items, "LongUrl"),
    }


@app.get("/api/search")
def search():
    try:
        assert app.current_event.headers["x-kellink-token"] == "let-me-in"
    except (AssertionError, KeyError) as e:
        logger.error(e)
        raise UnauthorizedError("Invalid or missing API token")

    try:
        days = int(app.current_event.query_string_parameters["days"])
        assert days > 0 and days <= 365
    except (AssertionError, KeyError, ValueError) as e:
        logger.error(e)
        raise BadRequestError("Query must be integer in range [1,365]")

    now = int(time.time() * 10**6)
    then = now - (days * 24 * 60 * 60 * 10**6)

    return table.scan(
        FilterExpression="#CreateTime BETWEEN :then AND :now",
        ExpressionAttributeValues={
            ":then": then,
            ":now": now,
        },
        ExpressionAttributeNames={"#CreateTime": "CreateTime"},
        ReturnConsumedCapacity="NONE",
        ProjectionExpression="CreateTime,LongUrl,ClickCount",
    )["Items"]


def api_handler(event, context):
    logger.debug(event)
    logger.debug(context)
    return True if "warmer" in event else app.resolve(event, context)
