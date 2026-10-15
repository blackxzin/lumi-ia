import secrets
import time
from collections import deque


class AccessBoundary:
    """Native clients only: reject browser origins, unexpected Host and oversized bodies."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token
        self.requests: deque[float] = deque()

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
        host = headers.get("host", "").split(":")[0]
        allowed = host in {"127.0.0.1", "localhost"}
        if headers.get("origin") or not allowed:
            return await self.reject(scope, send, 403)
        if scope["type"] == "websocket":
            return await self.app(scope, receive, send)
        supplied = headers.get("authorization", "")
        if not secrets.compare_digest(supplied.encode(), f"Bearer {self.token}".encode()):
            return await self.reject(scope, send, 401)
        now = time.monotonic()
        while self.requests and now - self.requests[0] > 60:
            self.requests.popleft()
        if len(self.requests) >= 120:
            return await self.reject(scope, send, 429)
        self.requests.append(now)
        # Buffer at most 64 KiB, including chunked requests, before parsing JSON.
        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > 65536:
                return await self.reject(scope, send, 413)
            chunks.append(message)
            if not message.get("more_body"):
                break

        async def replay():
            return chunks.pop(0) if chunks else await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def reject(scope, send, status):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"detail":"Request rejected"}'})
