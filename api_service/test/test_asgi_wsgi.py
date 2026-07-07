import asyncio
import time

import pytest

from api_service.utils.asgi_wsgi import ThreadedWsgiToAsgi


def _wsgi_app(environ, start_response):
    if environ["PATH_INFO"] == "/slow":
        time.sleep(0.4)
        body = b"slow"
    else:
        body = b"fast"
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/plain"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


async def _call_asgi(app, path):
    messages = []
    received = False

    async def receive():
        nonlocal received
        if received:
            await asyncio.sleep(0)
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "http_version": "1.1",
        "scheme": "http",
        "server": ("127.0.0.1", 5000),
        "client": ("127.0.0.1", 12345),
    }

    await app(scope, receive, send)
    return messages


@pytest.mark.asyncio
async def test_threaded_wsgi_adapter_does_not_serialize_requests():
    app = ThreadedWsgiToAsgi(_wsgi_app)

    slow_task = asyncio.create_task(_call_asgi(app, "/slow"))
    await asyncio.sleep(0.05)

    fast_messages = await asyncio.wait_for(_call_asgi(app, "/fast"), timeout=0.25)
    assert any(message.get("body") == b"fast" for message in fast_messages)
    assert not slow_task.done()

    await slow_task
