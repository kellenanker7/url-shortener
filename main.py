import logging
import boto3
import json
import sys
import os

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

domain_name = os.environ.get("DOMAIN_NAME")
chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def base62encode(db_id):
    suid = ""

    # find corresponding base 62 value for each digit
    while db_id > 0:
        suid += chars[db_id % 62]
        db_id //= 62

    return suid


@app.post("/")
def shorten():
    try:
        event = app.current_event.json_body
    except:
        raise BadRequestError("Invalid JSON payload")

    try:
        long_url = event["longUrl"]
    except KeyError:
        raise BadRequestError("Missing 'longUrl' attribute in payload")

    if len(long_url.split("://")) < 2:
        logger.warning("No protocol found in 'longUrl' - defaulting to 'https://'")
        long_url = "https://" + long_url

    db_id = hash(long_url)
    db_id += sys.maxsize + 1  # Must be positive
    suid = base62encode(db_id)

    logger.info(f"{suid}: {long_url}")

    item = table.put_item(
        Item={"ShortUrlId": str(suid), "LongUrl": long_url, "Clicks": 0},
        ReturnValues="ALL_OLD",
    )

    logger.info(item)

    return {"short_url": f"https://{domain_name}/{suid}"}


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
    except KeyError:
        raise NotFoundError("Could not find short URL")


@app.get("/")
def metrics():
    return {"message": "Metrics coming soon"}


def api_handler(event, context):
    return app.resolve(event, context)
