import logging

from app.core.logging import RequestIdFilter


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__()
        self.addFilter(RequestIdFilter())
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


def test_request_log_carries_response_request_id(client):
    handler = _Collect()
    logger = logging.getLogger("app.main")
    logger.addHandler(handler)
    try:
        response = client.get("/api/v1/health")
    finally:
        logger.removeHandler(handler)

    request_id = response.headers["X-Request-ID"]
    access = [r for r in handler.records if "/api/v1/health" in r.getMessage()]
    assert len(access) == 1
    assert access[0].request_id == request_id
    assert "-> 200" in access[0].getMessage()
