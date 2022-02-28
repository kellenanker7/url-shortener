import logging
import random
import boto3
import time
import json
import sys
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
)


logger = Logger(level=logging.INFO)
app = ApiGatewayResolver(proxy_type=ProxyEventType.APIGatewayProxyEventV2)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ.get("DDB_TABLE"))
domain_name = os.environ.get("DOMAIN_NAME")

chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


# https://stackoverflow.com/a/1119769
def encode(num):
    if num == 0:
        return chars[0]

    arr = []
    arr_append = arr.append  # Extract bound-method for faster access.
    _divmod = divmod  # Access to locals is faster.

    while num:
        num, rem = _divmod(num, 62)
        arr_append(chars[rem])

    arr.reverse()
    return "".join(arr)


def decode(string):
    strlen = len(string)
    num = 0
    idx = 0

    for char in string:
        power = strlen - (idx + 1)
        num += chars.index(char) * (62**power)
        idx += 1

    return num


@app.post("/")
def shorten():
    try:
        long_url = app.current_event.json_body["longUrl"]
    except:
        raise BadRequestError("Invalid JSON payload")

    if len(long_url.split("://")) < 2:
        long_url = f"http://{long_url}"

    # encode(550731776) = baaaaa (smallest input that generates output length 6)
    # encode(30840979455) = 999999 (largest input that generates output length 6)
    # 30,840,979,455 - 550,731,776 = 30,290,247,679 < 62^6 = 56,800,235,584
    # So, for encode() the number of possible inputs < num of possible outputs
    # We're also expiring items after 365 days.
    # I hope we don't generate 56,800,235,584 short URLs every year :)
    ddb_id = random.randint(550731776, 30840979455)
    suid = encode(ddb_id)

    try:
        now = int(time.time() * 10**6)
        table.put_item(
            Item={
                "Id": ddb_id,
                "LongUrl": long_url,
                "CreateTime": now,
                "ShortUrlId": str(suid),
                "ClickCount": 0,
                "TTL": now + (365 * 24 * 60 * 60),  # one year from now
            },
        )
    except Exception as e:
        logger.error(e)
        raise InternalServerError("Unexpected error during PutItem")

    logger.info(f"{suid}: {long_url}")
    return {"short_url": f"https://{domain_name}/{suid}"}


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

        return Response(
            status_code=302,
            body=json.dumps({"redirecting": long_url}),
            content_type="application/json",
            headers={"Location": long_url},
        )
    except IndexError as e:
        raise NotFoundError("Could not find short URL")
        logger.error(e)
    except Exception as e:
        logger.error(e)
        raise InternalServerError("Unexpected error during UpdateItem")


@app.get("/")
def metrics():
    try:
        days = int(app.current_event.get_query_string_value("days"))
    except:
        raise BadRequestError("Missing or invalid 'days' query parameter")

    limit = app.current_event.get_query_string_value("limit", default_value=100)
    if limit > 1000:
        limit = 1000

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
        Limit=limit,
        ProjectionExpression="LongUrl,CreateTime,ClickCount",
    )["Items"]


def api_handler(event, context):
    logger.debug(event)
    logger.debug(context)
    return app.resolve(event, context)
