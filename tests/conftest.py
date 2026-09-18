import asyncio

import httpx
import pytest

from gdex_mcp import client as client_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def mock_gdex(monkeypatch):
    """Route every httpx.AsyncClient the GDEXClient opens through a
    MockTransport. Returns a setter: `mock_gdex(handler)` where handler is
    `(httpx.Request) -> httpx.Response`. Requests seen are appended to
    `mock_gdex.requests`."""
    real = httpx.AsyncClient
    state = {"handler": None}
    requests: list[httpx.Request] = []

    def _transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return state["handler"](request)

    def _factory(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(_transport), **kwargs)

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", _factory)

    def set_handler(handler):
        state["handler"] = handler

    set_handler.requests = requests
    return set_handler
