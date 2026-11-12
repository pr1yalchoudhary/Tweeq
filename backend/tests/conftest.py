import pytest
from app import public_usage


@pytest.fixture(autouse=True)
def legacy_adapter_access(request, monkeypatch):
    """Old adapter unit tests run in an explicitly authorized demo context.

    Public-budget tests exercise the real guards and real Lua without this fixture.
    """
    if request.node.path.name == 'test_public_usage.py':
        yield
        return
    monkeypatch.setenv('AI_ACCESS_MODE', 'demo')
    marker = public_usage.context.set('demo')
    yield
    public_usage.context.reset(marker)


@pytest.fixture(autouse=True)
def no_real_async_network(monkeypatch):
    """MockTransport and local TestClient remain usable; real provider I/O is forbidden."""
    import httpx
    async def blocked(*args, **kwargs):
        raise AssertionError('Tests must use mocked network transports; no paid requests permitted.')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', blocked)
