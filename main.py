# try:
#     import unzip_requirements
# except ImportError:
#     pass

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
app = ApiGatewayResolver(proxy_type=ProxyEventType.APIGatewayProyEventV2)


@app.get("/<short_url>")
def do_stuff(short_url):
    return Response(
        status_code=302, body="redirecting...", headers={Location: "https://google.com"}
    )


@app.get("/status")
def status():
    return status({"status": "All good"})


def api_handler(event, context):
    logger.info(event)
    return app.resolve(event, context)
