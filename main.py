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
base = len(chars)


def encode(value):
    suid = ""
    while value > 0:
        suid += chars[value % base]
        value //= base

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

    # encode(550731776) = baaaaa (smallest input that generates output length 6)
    # encode(30840979455) = 999999 (largest input that generates output length 6)
    # 30,840,979,455 - 550,731,776 = 30,290,247,679 < 62^6 = 56,800,235,584
    # So, for encode() the number of possible inputs < num of possible outputs
    # We should never hit any collisions. We're also expiring items after 365 days.
    # I hope we don't generate 56,800,235,584 short URLs every year :)
    uid = random.randint(550731776, 30840979455)
    suid = encode(uid)

    try:
        now = int(time.time())
        table.put_item(
            Item={
                "ShortUrlId": str(suid),
                "LongUrl": long_url,
                "Clicks": 0,
                "Timestamp": now,
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
    try:
        # https://stackoverflow.com/a/60064828
        item = table.query(
            KeyConditionExpression="#ShortUrlId = :val",
            ExpressionAttributeNames={"#ShortUrlId": "ShortUrlId"},
            ExpressionAttributeValues={":val": str(suid)},
            Limit=1,
        )["Items"][0]

        long_url = item["LongUrl"]
        table.update_item(
            Key={"ShortUrlId": str(suid), "Timestamp": item["Timestamp"]},
            ConditionExpression="attribute_exists(ShortUrlId)",
            UpdateExpression="SET #Clicks = #Clicks + :val",
            ExpressionAttributeNames={"#Clicks": "Clicks"},
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
    return {"message": "Metrics coming soon"}


def api_handler(event, context):
    return app.resolve(event, context)
