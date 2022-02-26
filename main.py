import logging
import boto3
import json
import sys

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
    ServiceError,
)


logger = Logger(level=logging.INFO)
app = ApiGatewayResolver(proxy_type=ProxyEventType.APIGatewayProxyEventV2)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("url-shortener")


def base62encode(db_id):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    suid = ""

    # find corresponding base 62 value for each digit
    while db_id > 0:
        suid += chars[db_id % 62]
        db_id //= 62

    return suid[len(suid) :: -1]


@app.get("/")
def shorten():
    long_url = app.current_event.get_query_string_value(
        name="longUrl", default_value=""
    )
    if not long_url:
        raise BadRequestError("Missing 'longUrl' query param")

    db_id = hash(long_url)
    db_id += sys.maxsize + 1  # Must be positive
    suid = base62encode(db_id)

    item = table.get_item(
        Key={
            "ShortUrlId": suid,
        },
        ProjectionExpression="ShortUrlId",
    )
    logger.info(f"{long_url}: {suid}")

    if "Item" not in item:
        logger.info(f"Putting URL {long_url} in table")
        table.put_item(
            Item={
                "ShortUrlId": str(suid),
                "LongUrl": long_url,
                # "TTL": foo
            }
        )

        return {"suid": suid}

    logger.info(f"URL {long_url} already in table")
    return {"suid": suid}


@app.get("/<suid>")
def redirect(suid):
    item = table.get_item(
        Key={
            "ShortUrlId": suid,
        },
        ProjectionExpression="LongUrl",
    )

    try:
        long_url = item["Item"]["LongUrl"]
        return Response(
            status_code=302,
            body=json.dumps({"redirecting": long_url}),
            content_type="application/json",
            headers={"Location": long_url},
        )
    except KeyError as e:
        raise NotFoundError("Could not find short URL")


def api_handler(event, context):
    logger.info(event)
    return app.resolve(event, context)
