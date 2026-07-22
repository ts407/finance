from __future__ import annotations

import io
import logging

from fastapi.testclient import TestClient

from standing.logging_config import configure_logging, get_logger, resolve_level
from standing.web.app import create_app


def test_resolve_level_and_configure():
    assert resolve_level("debug") == logging.DEBUG
    assert resolve_level("INFO") == logging.INFO
    stream = io.StringIO()
    root = configure_logging("DEBUG", stream=stream, force=True)
    assert root.level == logging.DEBUG
    log = get_logger("tests")
    log.info("hello-%s", "world")
    text = stream.getvalue()
    assert "standing.tests" in text
    assert "hello-world" in text


def test_client_logs_endpoint():
    configure_logging("INFO", force=True)
    client = TestClient(create_app())
    res = client.post(
        "/api/client-logs",
        json={
            "entries": [
                {
                    "level": "info",
                    "message": "desk boot",
                    "page": "desk",
                    "context": {"view": "standing"},
                },
                {
                    "level": "error",
                    "message": "snapshot load failed",
                    "page": "desk",
                },
            ]
        },
    )
    assert res.status_code == 200
    assert res.json()["accepted"] == 2


def test_static_logger_served():
    client = TestClient(create_app())
    res = client.get("/static/logger.js")
    assert res.status_code == 200
    assert b"client-logs" in res.content
    assert b"export const logger" in res.content


def test_index_and_methodology_reference_logger():
    client = TestClient(create_app())
    index = client.get("/")
    assert index.status_code == 200
    assert b"/static/app.js" in index.content

    method = client.get("/methodology")
    assert method.status_code == 200
    assert b"/static/logger.js" in method.content
