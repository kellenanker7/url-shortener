import logging
import boto3

from aws_lambda_powertools.logging import Logger
from aws_lambda_powertools.event_handler.api_gateway import (
    ApiGatewayResolver,
    ProxyEventType,
)
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    InternalServerError,
    NotFoundError,
    ServiceError,
    UnauthorizedError,
)

ddb_table = "url-shortener"

logger = Logger(level=logging.INFO)
app = ApiGatewayResolver(proxy_type=ProxyEventType.APIGatewayProxyEventV2)

ddb_client = boto3.client("dynamodb")


def gen_id(long_url):
    short_url_id = hash(long_url)  # Do things to generate id
    logger.info(short_url_id)

    resp = ddb_client.get_item(
        TableName=ddb_table,
        Key={
            "ShortUrlId": {"S": str(short_url_id)},
        },
    )

    logger.info(resp)

    if resp == "":
        ddb_client.put_item(
            TableName=ddb_table,
            Item={
                "ShortUrlId": {"S": short_url_id},
                "LongUrl": long_url,
                # "TTL": somevalue,
            },
        )

    return short_url_id


@app.get("/shorten")
def shorten():
    long_url = app.current_event.get_query_string_value(
        name="longUrl", default_value=""
    )
    if long_url == "":
        return BadRequestError("Missing longUrl query parameter")

    return {"id": gen_id(long_url)}


@app.get("/s/<sid>")
def redirect(sid):
    long_url = ddb_client.get_item(
        TableName=ddb_table,
        Key={
            "ShortUrlId": {"S": short_url_id},
        },
    )

    logger.info(long_url)

    if long_url == "":
        return BadRequestError("Invalid short URL. Has that short URL expired?")

    return Response(
        status_code=302,
        body="redirecting...",
        content_type="text/plain",
        headers={"Location": long_url},
    )


@app.get("/status")
def status():
    return {"status": "all good"}


def api_handler(event, context):
    return app.resolve(event, context)
