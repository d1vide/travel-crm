class PublicResponsePrivacy:
    """Protect public-link responses and the path used by server access logging."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/public/"):
            return await self.app(scope, receive, send)

        def redact():
            scope["path"] = "/api/public/[redacted]"
            scope["raw_path"] = b"/api/public/[redacted]"
            scope["query_string"] = b""
            if "token" in scope.get("path_params", {}):
                scope["path_params"]["token"] = "[redacted]"

        async def protected_send(message):
            if message["type"] == "http.response.start":
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in (b"cache-control", b"referrer-policy")
                ]
                headers.extend(
                    [(b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer")]
                )
                message = {**message, "headers": headers}
                redact()
            await send(message)

        try:
            await self.app(scope, receive, protected_send)
        finally:
            redact()
