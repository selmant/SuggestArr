"""ASGI adapter helpers for running the Flask WSGI app under uvicorn."""

import os
from concurrent.futures import ThreadPoolExecutor

from asgiref.sync import sync_to_async
from asgiref.wsgi import WsgiToAsgi, WsgiToAsgiInstance


asgi_wsgi_executor = ThreadPoolExecutor(
    max_workers=int(os.environ.get("SUGGESTARR_WSGI_THREADS", "8"))
)


class ThreadedWsgiToAsgiInstance(WsgiToAsgiInstance):
    """Run WSGI requests in a bounded pool instead of one global thread."""

    async def run_wsgi_app(self, body):
        await sync_to_async(
            self._run_wsgi_app_sync,
            thread_sensitive=False,
            executor=asgi_wsgi_executor,
        )(body)

    def _run_wsgi_app_sync(self, body):
        try:
            environ = self.build_environ(self.scope, body)
        except ValueError:
            self.sync_send(
                {
                    "type": "http.response.start",
                    "status": 400,
                    "headers": [(b"content-type", b"text/plain")],
                }
            )
            self.sync_send(
                {
                    "type": "http.response.body",
                    "body": b"Bad Request: too many duplicate headers",
                }
            )
            return

        bytes_sent = 0
        for output in self.wsgi_application(environ, self.start_response):
            if not self.response_started:
                self.response_started = True
                self.sync_send(self.response_start)
            if self.response_content_length is not None:
                bytes_allowed = self.response_content_length - bytes_sent
                if len(output) > bytes_allowed:
                    output = output[:bytes_allowed]
            self.sync_send(
                {"type": "http.response.body", "body": output, "more_body": True}
            )
            bytes_sent += len(output)
            if bytes_sent == self.response_content_length:
                break
        if not self.response_started:
            self.response_started = True
            self.sync_send(self.response_start)
        self.sync_send({"type": "http.response.body"})


class ThreadedWsgiToAsgi(WsgiToAsgi):
    """WSGI-to-ASGI adapter that does not serialize all Flask requests."""

    def __init__(self, wsgi_application, duplicate_header_limit=100):
        super().__init__(wsgi_application)
        self.duplicate_header_limit = duplicate_header_limit

    async def __call__(self, scope, receive, send):
        await ThreadedWsgiToAsgiInstance(self.wsgi_application)(scope, receive, send)
