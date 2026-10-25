"""Bounded HTTP transport without database, account, or settings dependencies."""

import asyncio
import time

import httpx


class ModelDeadlineExceeded(Exception):
    pass


def deadline_post(url, headers, payload, timeout, *, transport=None, deadline=None):
    """Cancel the actual async HTTP stream, close it, then return to the sync loop.

    No abandoned worker or background HTTP request survives a timeout. The lease is
    released only after asyncio.run has completed cancellation and transport cleanup.
    """

    async def send():
        remaining = min(timeout, deadline - time.monotonic()) if deadline else timeout
        if remaining <= 0:
            raise ModelDeadlineExceeded("模型请求超时")
        async with (
            asyncio.timeout(remaining),
            httpx.AsyncClient(
                timeout=remaining, transport=transport, trust_env=False, follow_redirects=False
            ) as client,
        ):
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 1048576:
                        raise ModelDeadlineExceeded("模型响应超出限制")
                    chunks.append(chunk)
                # aiter_bytes already decoded the body; discard wire encoding/framing.
                decoded_headers = response.headers.copy()
                for name in ("content-encoding", "content-length", "transfer-encoding"):
                    decoded_headers.pop(name, None)
                return httpx.Response(
                    response.status_code, headers=decoded_headers, content=b"".join(chunks)
                )

    try:
        return asyncio.run(send())
    except TimeoutError as exc:
        raise ModelDeadlineExceeded("模型请求超时") from exc
