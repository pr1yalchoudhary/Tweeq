"""TEMPORARY demo-code-authenticated health-header diagnostics. Remove after testing.

Opt in only via the temporary Start Command: uvicorn ip_verification_app:app.
Normal app.main:app never imports this wrapper. No new HTTP route is added.
No Redis access, provider calls, raw IP output, or environment mutation.
"""
import hashlib
import hmac
import json
import os
import secrets

from starlette.datastructures import Headers
from app.main import app as application
from app.public_usage import normalized_network

_EPHEMERAL_HASH_KEY = secrets.token_bytes(32)
HEADER = b'x-tweeq-ip-check'
TEST_IPS = {'203.0.113.31', '203.0.113.32', '2001:db8::31'}


def authenticated(headers):
    secret = os.getenv('DEMO_ACCESS_TOKEN', '').strip().encode()
    values = headers.getlist('authorization')
    if len(secret) < 32 or len(values) != 1:
        return False
    scheme, _, supplied = values[0].partition(' ')
    return scheme.lower() == 'bearer' and hmac.compare_digest(supplied.encode(), secret)


def result(headers):
    values = headers.getlist('cf-connecting-ip')
    normalized = None
    if len(values) == 1:
        try:
            normalized = normalized_network(values[0])
        except ValueError:
            pass
    return {
        'cf_single_valid': normalized is not None,
        'cf_is_spoof_test_address': len(values) == 1 and values[0] in TEST_IPS,
        'network_fingerprint': hmac.new(_EPHEMERAL_HASH_KEY, normalized.encode(), hashlib.sha256).hexdigest() if normalized else None,
        'ip_secret_configured': len(os.getenv('PUBLIC_IP_HASH_SECRET', '')) >= 32,
        'demo_mode': os.getenv('AI_ACCESS_MODE', 'demo') == 'demo',
        'public_switches_disabled': os.getenv('PUBLIC_AI_ENABLED', 'false').lower() != 'true'
                                   and os.getenv('PUBLIC_GENERATIONS_ENABLED', 'false').lower() != 'true',
    }


async def app(scope, receive, send):
    if scope.get('type') != 'http' or scope.get('method') != 'GET' or scope.get('path') != '/api/health':
        return await application(scope, receive, send)
    headers = Headers(scope=scope)
    if not authenticated(headers):
        return await application(scope, receive, send)
    diagnostic = json.dumps(result(headers), separators=(',', ':')).encode('ascii')
    async def owner_send(message):
        if message['type'] == 'http.response.start':
            message = {**message, 'headers': [
                (key, value) for key, value in message.get('headers', [])
                if key.lower() not in (HEADER, b'cache-control')
            ] + [(HEADER, diagnostic), (b'cache-control', b'no-store')]}
        await send(message)
    return await application(scope, receive, owner_send)
