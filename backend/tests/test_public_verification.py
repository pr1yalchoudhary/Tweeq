"""Private live-Redis probe itself is tested with a mocked Redis REST transport."""
import asyncio
import json

import fakeredis
import httpx
import pytest

from app import public_usage as usage
import verify_public_usage as probe


@pytest.fixture
def datastore(monkeypatch):
    store = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv('UPSTASH_REDIS_REST_URL', 'https://redis-verification.invalid')
    monkeypatch.setenv('UPSTASH_REDIS_REST_TOKEN', 'test-rest-secret-never-printed')
    def rest(request):
        # Any Fish request reaching the real transport would fail this assertion.
        assert request.url.host == 'redis-verification.invalid'
        assert request.headers['Authorization'] == 'Bearer test-rest-secret-never-printed'
        command = json.loads(request.content)
        try:
            result = store.execute_command(*command)
            # redis-py normalizes raw PONG to True; REST returns the Redis string.
            if command[0] == 'PING' and result is True:
                result = 'PONG'
            return httpx.Response(200, json={'result': result})
        except Exception:
            return httpx.Response(200, json={'error': 'fixture Redis error'})
    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', lambda **kwargs: httpx.MockTransport(rest))
    return store


def test_isolated_live_probe_start_resume_and_safe_cleanup(datastore):
    original_prefix = usage.PREFIX
    datastore.hset(original_prefix + 'budget', mapping={'schema': '2', 'used': '7', 'enabled': '0'})
    before = datastore.hgetall(original_prefix + 'budget')
    result = asyncio.run(probe.main('start', 'a' * 32))
    assert result['production_counters_unchanged'] is True
    assert result['mocked_provider_requests'] == 23  # setup/TTS + 10 global + 10 dollars + interruption.
    assert 'two_dollar_estimate' in result['passed']
    assert usage.PREFIX == original_prefix
    resumed = asyncio.run(probe.main('resume', 'a' * 32))
    assert 'durable_counters_and_pending_records' in resumed['passed']
    assert resumed['render_restart_independently_verified'] is False
    assert datastore.hgetall(original_prefix + 'budget') == before
    assert asyncio.run(probe.main('cleanup', 'a' * 32))['production_keys_modified'] is False
    assert not list(datastore.scan_iter(match=probe.root_for('a' * 32) + '*'))
    assert datastore.hgetall(original_prefix + 'budget') == before


def test_changed_counters_fail_resume_without_repair_or_reset(datastore):
    asyncio.run(probe.main('start', 'b' * 32))
    key = probe.root_for('b' * 32) + 'visitor:budget'
    datastore.hset(key, 'used', '0')
    with pytest.raises(probe.VerificationFailure, match='did not persist'):
        asyncio.run(probe.main('resume', 'b' * 32))
    assert datastore.hget(key, 'used') == '0'  # A check never silently repairs counters.


def test_bad_credentials_report_http_401_without_provider_access(datastore, monkeypatch):
    monkeypatch.setattr(httpx, 'AsyncHTTPTransport',
                        lambda **kwargs: httpx.MockTransport(lambda request: httpx.Response(401)))
    with pytest.raises(probe.VerificationFailure, match='HTTP 401'):
        asyncio.run(probe.main('start', 'c' * 32))
    assert not list(datastore.scan_iter())


@pytest.mark.parametrize('run_id', ['public-v1', '../public-v1', '', 'x' * 32])
def test_production_or_invalid_namespace_is_never_accepted(run_id):
    with pytest.raises(probe.VerificationFailure):
        probe.root_for(run_id)


def test_unexpected_network_is_blocked(datastore):
    async def check():
        transport = probe.GuardedTransport({'mock_calls': 0}, 'https://redis-verification.invalid')
        try:
            with pytest.raises(probe.VerificationFailure, match='blocked'):
                await transport.handle_async_request(httpx.Request('GET', 'https://other.invalid'))
        finally:
            await transport.aclose()
    asyncio.run(check())
