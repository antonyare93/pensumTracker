from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# La API solo devuelve JSON, así que la CSP puede cerrarlo todo.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
_DEFAULT_CACHE_CONTROL = "no-store"


class SecurityHeadersMiddleware:
    """ASGI puro: BaseHTTPMiddleware bufferiza y rompería el streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                if "cache-control" not in headers:
                    headers["Cache-Control"] = _DEFAULT_CACHE_CONTROL
            await send(message)

        await self.app(scope, receive, send_with_headers)
