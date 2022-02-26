import logging
import boto3
import json

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
    UnauthorizedError,
)


logger = Logger(level=logging.INFO)
app = ApiGatewayResolver(proxy_type=ProxyEventType.APIGatewayProxyEventV2)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("url-shortener")


def put_item(long_url):
    suid = hash(long_url)
    logger.info(suid)

    response = table.put_item(
        Item={
            "ShortUrlId": str(suid),
            "LongUrl": long_url,
            # "TTL": foo
        }
    )
    logger.info(response["ResponseMetadata"]["HTTPStatusCode"])

    return suid


@app.get("/shorten")
def shorten():
    long_url = app.current_event.get_query_string_value(
        name="longUrl", default_value=""
    )
    if long_url == "":
        raise BadRequestError("Missing longUrl query parameter")

    return Response(
        status_code=200,
        body=json.dumps({"suid": put_item(long_url)}),
        content_type="application/json",
    )


@app.get("/s/<suid>")
def redirect(suid):
    item = table.get_item(
        Key={
            "ShortUrlId": suid,
        },
    )

    try:
        long_url = item["Item"]["LongUrl"]
        logger.info(long_url)

        return Response(
            status_code=302,
            body="redirecting...",
            content_type="text/plain",
            headers={"Location": long_url},
        )
    except KeyError as ignore:
        raise BadRequestError("Bad short URL. Has that short URL expired?")


@app.get("/status")
def status():
    return {"status": "all good"}


def api_handler(event, context):
    return app.resolve(event, context)
