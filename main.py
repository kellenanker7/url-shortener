import logging
import boto3
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
table = dynamodb.Table("url-shortener")

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

    url_hash = hash(long_url)
    if url_hash < 0:
        url_hash += sys.maxsize + 1  # Must be positive
    suid = encode(url_hash)

    try:
        table.put_item(
            Item={"ShortUrlId": str(suid), "LongUrl": long_url, "Clicks": 0},
            ConditionExpression="attribute_not_exists(ShortUrlId)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            pass
        else:
            logger.error(e)
            raise InternalServerError("Unexpected error during PutItem")
    except Exception as e:
        logger.error(e)
        raise InternalServerError("Unexpected error during UpdateItem")

    logger.info(f"{suid}: {long_url}")
    return {"short_url": f"https://{domain_name}/{suid}"}


@app.get("/<suid>")
def redirect(suid):
    try:
        item = table.update_item(
            Key={
                "ShortUrlId": str(suid),
            },
            UpdateExpression="SET Clicks = Clicks + :val",
            ExpressionAttributeValues={":val": {"N": "1"}},
            ReturnValues="ALL_NEW",
        )
        long_url = item["Item"]["LongUrl"]

        return Response(
            status_code=302,
            body=json.dumps({"redirecting": long_url}),
            content_type="application/json",
            headers={"Location": long_url},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise NotFoundError("Could not find short URL")
        else:
            logger.error(e)
            raise InternalServerError("Unexpected error during UpdateItem")
    except Exception as e:
        logger.error(e)
        raise InternalServerError("Unexpected error during UpdateItem")


@app.get("/")
def metrics():
    return {"message": "Metrics coming soon"}


def api_handler(event, context):
    return app.resolve(event, context)
