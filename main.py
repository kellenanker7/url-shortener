import logging

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


@app.get("/<id>")
def redirect(id):
    long_url = "https://google.com" # Look up real URL in DB based on short URL

    # Simple redirect to real URL
    return Response(
        status_code=302,
        body="redirecting...",
        content_type="text/plain",
        headers={"Location": long_url},
    )


def api_handler(event, context):
    logger.info(event)
    return app.resolve(event, context)
