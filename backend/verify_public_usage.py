"""Private Render-shell verification. Real Redis, isolated keys, mocked Fish only.

No runtime endpoint or application mock mode is installed. No production budget
is initialized, enabled, charged, reset or otherwise modified by this command.
"""
import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from unittest.mock import patch
import wave

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(Path(__file__).resolve().parent / '.env')
from app import fish_audio, public_usage as usage
from manage_public_usage import INITIALIZE

PRODUCTION_PREFIX = usage.PREFIX
ORIGINAL_CLIENT = httpx.AsyncClient


class VerificationFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise VerificationFailure(message)


def root_for(run_id):
    require(bool(re.fullmatch('[0-9a-f]{32}', run_id)), 'Invalid verification run ID.')
    root = 'tweeq:{verification-' + run_id + '}:'
    require(not root.startswith(PRODUCTION_PREFIX), 'Unsafe verification namespace.')
    return root


def wav_fixture():
    out = io.BytesIO()
    with wave.open(out, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\x00\x01' * 1600)
    return out.getvalue()


class GuardedTransport(httpx.AsyncBaseTransport):
    """Fish hosts NEVER reach the real transport, even with a real account key."""
    def __init__(self, state, redis_url):
        self.state = state
        self.redis_url = httpx.URL(redis_url)
        self.real = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        if request.url.host == 'api.fish.audio':
            self.state['mock_calls'] += 1
            if self.state.get('timeout'):
                raise httpx.ReadTimeout('Mocked interruption', request=request)
            if request.url.path == '/model':
                return httpx.Response(201, json={'_id': 'verification-voice', 'state': 'trained'})
            if request.url.path == '/v1/asr':
                return httpx.Response(200, json={'text': 'Local verification words.'})
            if request.url.path == '/v1/tts':
                return httpx.Response(200, content=wav_fixture())
            raise VerificationFailure('Unexpected mocked provider route.')
        if (request.url.scheme, request.url.host, request.url.port, request.url.path) == (
                'https', self.redis_url.host, self.redis_url.port, self.redis_url.path):
            return await self.real.handle_async_request(request)
        raise VerificationFailure('Unexpected outbound request blocked.')

    async def aclose(self):
        await self.real.aclose()


@contextmanager
def sandbox(root, state):
    redis_url = os.getenv('UPSTASH_REDIS_REST_URL', '').strip().rstrip('/')
    parsed = httpx.URL(redis_url)
    require(parsed.scheme == 'https' and bool(parsed.host) and not parsed.userinfo
            and not parsed.query, 'Configure a valid HTTPS Redis REST URL in Render.')
    # All overrides exist only in this private process, never in Render settings.
    env = {'AI_ACCESS_MODE': 'public', 'PUBLIC_AI_ENABLED': 'true',
           'PUBLIC_GENERATIONS_ENABLED': 'true', 'PUBLIC_COST_REVIEWED': 'true',
           'PUBLIC_BUDGET_USD': '10', 'PUBLIC_GLOBAL_OPERATIONS': '100',
           'PUBLIC_VISITOR_OPERATIONS': '2', 'PUBLIC_IP_OPERATIONS': '2',
           'PUBLIC_AI_CONCURRENCY': '100', 'PUBLIC_OPERATION_RESERVE_USD': '0.20',
           'PUBLIC_VOICE_RESERVE_USD': '0.20', 'PUBLIC_MAX_RECORDING_SECONDS': '60',
           'FISH_AUDIO_API_KEY': 'verification-mock-only-not-a-provider-key'}
    def client(**kwargs):
        require('transport' not in kwargs, 'Unexpected transport override.')
        return ORIGINAL_CLIENT(transport=GuardedTransport(state, redis_url), **kwargs)
    original_command = usage.command
    async def storage(*args):
        verb = str(args[0]).upper()
        if verb == 'EVAL':
            keys = args[3:3 + int(args[2])]
            require(keys and all(k.startswith(root) for k in keys), 'Non-test Lua write blocked.')
        elif verb not in ('PING', 'HGETALL', 'HGET', 'HMGET', 'GET', 'TTL', 'SMEMBERS', 'TYPE', 'SCAN'):
            keys = args[1:] if verb in ('DEL', 'UNLINK') else args[1:2]
            require(keys and all(k.startswith(root) for k in keys), 'Non-test datastore write blocked.')
        return await original_command(*args)
    with patch.dict(os.environ, env), patch.object(usage, 'PREFIX', root), \
            patch.object(usage, 'command', storage), patch.object(httpx, 'AsyncClient', client):
        yield


def as_hash(value):
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    require(isinstance(value, list) and len(value) % 2 == 0, 'Unexpected Redis hash response.')
    return {str(value[i]): str(value[i + 1]) for i in range(0, len(value), 2)}


async def production_state():
    return as_hash(await usage.command('HGETALL', PRODUCTION_PREFIX + 'budget'))


async def authenticate():
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        response = await client.post(os.environ['UPSTASH_REDIS_REST_URL'].strip().rstrip('/'),
            headers={'Authorization': 'Bearer ' + os.environ.get('UPSTASH_REDIS_REST_TOKEN', '').strip()},
            json=['PING'])
    require(response.status_code == 200,
            'Datastore authentication check returned HTTP ' + str(response.status_code) + '.')
    require(response.json().get('result') == 'PONG', 'Invalid Redis authentication response.')


async def initialize(root, name, *, global_limit=10, budget=2000000, concurrency=100):
    usage.PREFIX = root + name + ':'
    key = usage.PREFIX + 'budget'
    result = await usage.command('EVAL', INITIALIZE, 1, key, global_limit, 2, 2, concurrency, budget)
    require(result == 'initialized_disabled', 'Verification state already exists; use a new run.')
    await usage.command('HSET', key, 'enabled', 1)
    return key


async def visitor(network):
    token = secrets.token_urlsafe(32)
    await usage.evaluate('create', token, network)
    return token, network


async def generate(access, reference):
    marker = usage.context.set(access)
    try:
        return await fish_audio.generate('Verification only.', reference,
                                         model='drama-3', reference_id='verification-voice')
    finally:
        usage.context.reset(marker)


async def denied(call, status):
    try:
        await call()
    except HTTPException as exc:
        require(exc.status_code == status, 'Unexpected denial category.')
        return
    raise VerificationFailure('An operation that should be denied was accepted.')


async def start(root, state):
    require(callable(getattr(usage, 'estimate', None)) and hasattr(usage, 'FINISH'),
            'Deploy the current schema-2 dollar-budget safeguards before verifying.')
    await authenticate()
    before = await production_state()
    snapshots = {}
    passed = ['datastore_authentication']
    with tempfile.TemporaryDirectory(prefix='tweeq-verification-') as temp:
        ref = Path(temp) / 'reference.wav'
        ref.write_bytes(wav_fixture())
        key = await initialize(root, 'visitor')
        access = await visitor('verification-network')
        marker = usage.context.set(access)
        try:
            await fish_audio.create_voice(ref, 'verification-only')
        finally:
            usage.context.reset(marker)
        await generate(access, ref)
        calls = state['mock_calls']
        await denied(lambda: generate(access, ref), 429)
        require(state['mock_calls'] == calls == 2, 'Visitor quota allowed extra dispatch.')
        snapshots[key] = as_hash(await usage.command('HGETALL', key))
        for suffix in ('visitor:' + usage.token_key(access[0]), 'ip:' + access[1]):
            test_key = usage.PREFIX + suffix
            snapshots[test_key] = as_hash(await usage.command('HGETALL', test_key))
        passed.append('visitor_two_provider_operations')

        # Separate operation and dollar tests: the other cap cannot mask failure.
        for name, count_cap, dollars_cap in [('global', 10, 10000000), ('dollars', 100, 2000000)]:
            key = await initialize(root, name, global_limit=count_cap, budget=dollars_cap)
            visitors = [await visitor('network-' + str(i)) for i in range(18)]
            async def attempt(access):
                try:
                    await generate(access, ref)
                    return True
                except HTTPException as exc:
                    require(exc.status_code == 429, 'Unexpected concurrent denial.')
                    return False
            outcomes = await asyncio.gather(*(attempt(a) for a in visitors))
            require(sum(outcomes) == 10, 'Concurrent global/dollar quota was bypassed.')
            snapshot = as_hash(await usage.command('HGETALL', key))
            require(snapshot['used'] == '10' and snapshot['reserved_microusd'] == '2000000'
                    and snapshot['active'] == '0', 'Incorrect durable reservation totals.')
            snapshots[key] = snapshot
            passed.append('global_ten_operations' if name == 'global' else 'two_dollar_estimate')

        key = await initialize(root, 'shutdown')
        access = await visitor('shutdown-network')
        calls = state['mock_calls']
        await usage.command('HSET', key, 'enabled', 0)
        await denied(lambda: generate(access, ref), 503)
        await usage.command('HSET', key, 'enabled', 1)
        with patch.dict(os.environ, {'PUBLIC_AI_ENABLED': 'false'}):
            await denied(lambda: generate(access, ref), 503)
        require(state['mock_calls'] == calls, 'Shutdown allowed a provider dispatch.')
        passed.append('datastore_and_environment_shutdown')

        key = await initialize(root, 'interrupted')
        access = await visitor('interrupted-network')
        calls = state['mock_calls']
        state['timeout'] = True
        try:
            await generate(access, ref)
            raise VerificationFailure('Mock interruption unexpectedly succeeded.')
        except fish_audio.FishError:
            pass
        finally:
            state['timeout'] = False
        snapshot = as_hash(await usage.command('HGETALL', key))
        require(snapshot['used'] == '1' and snapshot['reserved_microusd'] == '200000'
                and state['mock_calls'] == calls + 1, 'Interrupted request was refunded/retried.')
        snapshots[key] = snapshot
        passed.append('interrupted_requests_not_refunded_or_retried')

        key = await initialize(root, 'pending', concurrency=1)
        access = await visitor('pending-network')
        marker = usage.context.set(access)
        try:
            rid = await usage.reserve_operation('tts', text='Verification.', model='drama-3')
        finally:
            usage.context.reset(marker)
        await denied(lambda: generate(access, ref), 429)
        snapshots[key] = as_hash(await usage.command('HGETALL', key))
        pending_key = usage.PREFIX + 'reservation:' + rid
        snapshots[pending_key] = as_hash(await usage.command('HGETALL', pending_key))
        passed.append('pending_concurrency_slot_retained')
    require(await production_state() == before, 'Production counters changed during verification; investigate.')
    for key in snapshots:
        require(await usage.command('TTL', key) == -1, 'Durable usage data unexpectedly expires.')
    metadata = {'snapshots': snapshots, 'production_before': before, 'passed': passed,
                'source_sha256': hashlib.sha256(Path(usage.__file__).read_bytes()).hexdigest(),
                'render_instance': os.getenv('RENDER_INSTANCE_ID')}
    await usage.command('SET', root + 'metadata', json.dumps(metadata))
    return {'passed': passed, 'mocked_provider_requests': state['mock_calls'],
            'production_counters_unchanged': True, 'restart_verification': 'pending',
            'guard_source_sha256': metadata['source_sha256'],
            'production_budget_schema': before.get('schema', 'not_initialized')}


async def resume(root):
    saved = await usage.command('GET', root + 'metadata')
    require(isinstance(saved, str), 'No completed verification run with this ID.')
    meta = json.loads(saved)
    for key, expected in meta['snapshots'].items():
        require(key.startswith(root), 'Invalid stored verification key.')
        require(as_hash(await usage.command('HGETALL', key)) == expected,
                'Usage counters/pending records did not persist unchanged.')
        require(await usage.command('TTL', key) == -1, 'Usage state unexpectedly expires.')
    require(await production_state() == meta['production_before'],
            'Production budget changed since start; inspect before enabling.')
    require(hashlib.sha256(Path(usage.__file__).read_bytes()).hexdigest() == meta['source_sha256'],
            'Guard code changed since start; run a fresh verification.')
    return {'passed': ['durable_counters_and_pending_records', 'production_counters_unchanged'],
            'render_restart_independently_verified': False,
            'note': 'Run resume AFTER restarting the actual Render service; a new CLI process alone is not a service restart.'}


async def cleanup(root):
    cursor = '0'
    found = set()
    while True:
        cursor, keys = await usage.command('SCAN', cursor, 'MATCH', root + '*', 'COUNT', 100)
        require(all(key.startswith(root) for key in keys), 'Unsafe cleanup key blocked.')
        found.update(keys)
        require(len(found) < 10000, 'Unexpected verification namespace size; inspect privately.')
        if str(cursor) == '0':
            break
    keys = sorted(found)
    for offset in range(0, len(keys), 100):
        await usage.command('DEL', *keys[offset:offset + 100])
    return {'isolated_test_keys_removed': True, 'production_keys_modified': False}


async def main(action, run_id):
    root = root_for(run_id)
    state = {'mock_calls': 0}
    with sandbox(root, state):
        result = await (start(root, state) if action == 'start' else resume(root) if action == 'resume' else cleanup(root))
    return {'run_id': run_id, **result}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'resume', 'cleanup'))
    parser.add_argument('--run-id')
    args = parser.parse_args()
    if args.action != 'start' and not args.run_id:
        parser.error('--run-id is required for resume/cleanup')
    try:
        print(json.dumps(asyncio.run(main(args.action, args.run_id or secrets.token_hex(16))), indent=2))
    except Exception as exc:
        # No tracebacks/provider bodies/credential-bearing request URLs in output.
        message = str(exc) if isinstance(exc, VerificationFailure) else 'Datastore/tooling verification failed; check the private Render configuration.'
        print(json.dumps({'passed': False, 'reason': message, 'error_category': type(exc).__name__}))
        raise SystemExit(1)
