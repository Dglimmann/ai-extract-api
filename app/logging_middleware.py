import time
import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("api")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.time()

        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = int((time.time() - start) * 1000)

        logger.info(
            f"{request.method} {request.url.path} | "
            f"status={response.status_code} | "
            f"time={duration_ms}ms | "
            f"request_id={request_id}"
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = str(duration_ms)

        return response