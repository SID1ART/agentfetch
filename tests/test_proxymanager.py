import pytest
from agentfetch.core.proxymanager import ProxyManager


def test_no_proxies_by_default():
    pm = ProxyManager()
    assert pm.is_enabled() is False
    assert pm.count() == 0


@pytest.mark.asyncio
async def test_get_proxy_returns_none_when_empty():
    pm = ProxyManager()
    proxy = await pm.get_proxy()
    assert proxy is None


@pytest.mark.asyncio
async def test_get_proxy_with_proxies(monkeypatch):
    monkeypatch.setenv("AGENTFETCH_PROXY_LIST", "http://proxy1:8080,http://proxy2:8080")
    pm = ProxyManager()
    proxy = await pm.get_proxy()
    assert proxy in ("http://proxy1:8080", "http://proxy2:8080")


@pytest.mark.asyncio
async def test_round_robin_rotation(monkeypatch):
    monkeypatch.setenv("AGENTFETCH_PROXY_LIST", "http://proxy1:8080,http://proxy2:8080")
    pm = ProxyManager()
    first = await pm.get_proxy()
    second = await pm.get_proxy()
    if pm.count() > 1:
        assert first != second


@pytest.mark.asyncio
async def test_mark_failed(monkeypatch):
    monkeypatch.setenv("AGENTFETCH_PROXY_LIST", "http://proxy1:8080")
    pm = ProxyManager()
    await pm.mark_failed("http://proxy1:8080")
    await pm.mark_failed("http://proxy1:8080")
    await pm.mark_failed("http://proxy1:8080")
    proxy = await pm.get_proxy()
    assert proxy is not None


@pytest.mark.asyncio
async def test_mark_success(monkeypatch):
    monkeypatch.setenv("AGENTFETCH_PROXY_LIST", "http://proxy1:8080")
    pm = ProxyManager()
    await pm.mark_failed("http://proxy1:8080")
    await pm.mark_success("http://proxy1:8080")
    proxy = await pm.get_proxy()
    assert proxy == "http://proxy1:8080"


def test_get_all(monkeypatch):
    monkeypatch.setenv("AGENTFETCH_PROXY_LIST", "http://p1:8080,http://p2:8080")
    pm = ProxyManager()
    all_proxies = pm.get_all()
    assert len(all_proxies) == 2
