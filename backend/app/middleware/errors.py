"""Unexpected errors as the standard JSON error response, inside CORS.

FastAPI handles `Exception` in its outermost middleware, which runs outside CORSMiddleware
(and, with DEBUG on, returns a traceback instead of calling the handler). Browsers then block
the response without CORS headers and the frontend cannot show the error. This middleware is
registered inside CORS and turns any unhandled exception into the usual 500 envelope via
`unhandled_exception_handler` (which logs the traceback server-side; nothing leaks to clients).
"""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.exceptions.handlers import unhandled_exception_handler


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def send_tracking(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking)
        except Exception as exc:
            if response_started:  # part of a response was already sent: nothing safe to add
                raise
            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send)
