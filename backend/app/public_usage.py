"""Fail-closed public budget. Redis, never browser state, owns all allowances."""
from contextvars import ContextVar
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import math
import logging
import hashlib
import hmac
import ipaddress
import os
import re
import secrets

import httpx
from fastapi import HTTPException, Request

PREFIX = 'tweeq:{public-v1}:'  # Stable across deploys. Never change to reset a budget.
context = ContextVar('public_usage', default=None)

# One script handles status, session creation, and reservation. Redis serializes it.
# Quota keys have NO TTL. Only short-window abuse counters expire.
# Microdollars are integers: no floating point dollar arithmetic in Redis.
SCRIPT = r'''
local function count(key, field)
  local raw = redis.call('HGET', key, field)
  if not raw or not string.match(raw, '^%d+$') then return nil end
  local n = tonumber(raw)
  if n > 1000000000000 then return nil end
  return n
end
local g = count(KEYS[1], 'used')
local spent = count(KEYS[1], 'reserved_microusd')
local active = count(KEYS[1], 'active')
local cap = count(KEYS[1], 'budget_microusd')
if redis.call('HGET', KEYS[1], 'schema') ~= '2' or not g or not spent or not active or not cap
  or active > g or (g > 0 and spent == 0) then return {'storage'} end
-- Environment can tighten persisted limits, never silently expand them.
local limits = {}
for j, field in ipairs({'global_limit', 'visitor_limit', 'ip_limit', 'concurrency'}) do
  local n = count(KEYS[1], field)
  if not n or n < 1 then return {'storage'} end
  limits[j] = math.min(n, tonumber(ARGV[j+5]))
end
cap = math.min(cap, tonumber(ARGV[10]))
local debits = redis.call('HVALS', KEYS[6])
local total = 0
for _, debit in ipairs(debits) do
  if not string.match(debit, '^%d+$') then return {'storage'} end
  total = total + tonumber(debit)
end
if #debits ~= g or total ~= spent or redis.call('SCARD', KEYS[7]) ~= active then return {'storage'} end
if redis.call('HGET', KEYS[1], 'enabled') ~= '1' then return {'disabled'} end
local v = count(KEYS[2], 'used')
local i = 0
if redis.call('EXISTS', KEYS[3]) == 1 then
  i = count(KEYS[3], 'used')
  if not i then return {'storage'} end
end
if ARGV[1] == 'create' then
  if redis.call('EXISTS', KEYS[2]) == 1 then return {'storage'} end
  if g >= limits[1] or spent >= cap then return {'global'} end
  if i >= limits[3] then return {'ip'} end
  local n = tonumber(redis.call('GET', KEYS[4]) or '0')
  if not n then return {'storage'} end
  if n >= 10 then return {'rate'} end
  redis.call('INCR', KEYS[4])
  if n == 0 then redis.call('EXPIRE', KEYS[4], 3600) end
  redis.call('HSET', KEYS[2], 'used', 0, 'ip', ARGV[2])
  return {'ok', 0, g, i, spent, cap, limits[1], limits[2], limits[3]}
end
if not v or redis.call('HGET', KEYS[2], 'ip') ~= ARGV[2] then return {'session'} end
if ARGV[1] == 'reserve' then
  local cost = tonumber(ARGV[3])
  if not cost or cost < 1 or cost > 1000000000000 then return {'storage'} end
  if g >= limits[1] or spent + cost > cap then return {'global'} end
  if v >= limits[2] then return {'visitor'} end
  if i >= limits[3] then return {'ip'} end
  if active >= limits[4] then return {'busy'} end
  if redis.call('EXISTS', KEYS[5]) == 1 then return {'duplicate'} end
  local n = tonumber(redis.call('GET', KEYS[4]) or '0')
  if not n then return {'storage'} end
  if n >= 2 then return {'rate'} end
  -- All checks precede mutations. Pending entries never expire or refund on crash.
  redis.call('HSET', KEYS[6], ARGV[11], cost)
  redis.call('SADD', KEYS[7], ARGV[11])
  redis.call('HINCRBY', KEYS[1], 'used', 1)
  redis.call('HINCRBY', KEYS[1], 'reserved_microusd', cost)
  redis.call('HINCRBY', KEYS[1], 'active', 1)
  redis.call('HINCRBY', KEYS[2], 'used', 1)
  redis.call('HINCRBY', KEYS[3], 'used', 1)
  redis.call('HSET', KEYS[5], 'state', 'pending', 'kind', ARGV[4], 'reserved_microusd', cost,
    'visitor', ARGV[5], 'network', ARGV[2])
  redis.call('INCR', KEYS[4])
  if n == 0 then redis.call('EXPIRE', KEYS[4], 60) end
  v = v + 1; g = g + 1; i = i + 1; spent = spent + cost
end
return {'ok', v, g, i, spent, cap, limits[1], limits[2], limits[3]}
'''

FINISH = r'''
if redis.call('HGET', KEYS[1], 'schema') ~= '2' then return 'storage' end
local active = redis.call('HGET', KEYS[1], 'active')
if not active or not string.match(active, '^%d+$') then return 'storage' end
local state = redis.call('HGET', KEYS[2], 'state')
if not state then return 'storage' end
if state ~= 'pending' then return 'finished' end
if tonumber(active) < 1 then return 'storage' end
redis.call('HSET', KEYS[2], 'state', ARGV[1])
redis.call('HINCRBY', KEYS[1], 'active', -1)
redis.call('SREM', KEYS[3], ARGV[2])
return 'finished'
'''


def positive_int(name, default, maximum=1000000):
    try:
        n = int(os.getenv(name, str(default)))
        if not 0 < n <= maximum: raise ValueError()
        return n
    except ValueError:
        raise HTTPException(503, 'Public AI configuration is unavailable.') from None


def dollars(name, default):
    try:
        n = Decimal(os.getenv(name, default))
        if not n.is_finite() or not 0 < n <= 10000: raise ValueError()
        return int((n * 1000000).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, ValueError):
        raise HTTPException(503, 'Public AI configuration is unavailable.') from None


def limits():
    return [positive_int('PUBLIC_GLOBAL_OPERATIONS', 10), positive_int('PUBLIC_VISITOR_OPERATIONS', 2),
            positive_int('PUBLIC_IP_OPERATIONS', 2), positive_int('PUBLIC_AI_CONCURRENCY', 1),
            dollars('PUBLIC_BUDGET_USD', '2')]


def text_limit(text):
    if mode() == 'public':
        maximum = positive_int('PUBLIC_MAX_TEXT_CHARS', 200, 1000)
        if len(text or '') > maximum:
            raise HTTPException(422, f'Public demo speech is limited to {maximum} characters per request.')


def estimate(kind, *, text='', seconds=0, model=''):
    # 2026-11-12 official LIST prices, ignoring temporary free/discount offers.
    # Policy reserve is a safety allowance, NOT a published voice creation price.
    floor = dollars('PUBLIC_OPERATION_RESERVE_USD', '0.20')
    if kind == 'tts':
        if model not in ('s2.1-pro-free', 's2.1-pro', 's2-pro', 'drama-3'):
            raise HTTPException(503, 'Public AI model is unavailable.')
        # $50/M UTF-8 bytes, 2x headroom; full rendered script includes direction/tags.
        documented = len(text.encode('utf-8')) * 100
    elif kind == 'asr':
        if not math.isfinite(seconds) or seconds <= 0: raise HTTPException(422, 'Invalid audio duration.')
        documented = math.ceil(seconds) * 200  # $0.36/hour = 100 microUSD/s, 2x.
    elif kind in ('voice_create', 'voice_status'):
        documented = dollars('PUBLIC_VOICE_RESERVE_USD', '0.20')
    else:
        raise HTTPException(503, 'Public AI operation is unavailable.')
    return max(floor, documented)



def mode():
    value = os.getenv('AI_ACCESS_MODE', 'demo')
    if value not in ('demo', 'public'):
        raise HTTPException(503, 'AI access configuration is invalid.')
    return value


def enabled():
    if (os.getenv('PUBLIC_AI_ENABLED', os.getenv('PUBLIC_GENERATIONS_ENABLED', 'false')).lower() != 'true'
            or os.getenv('PUBLIC_GENERATIONS_ENABLED', 'true').lower() != 'true'):
        raise HTTPException(503, 'Public AI generation is currently disabled.')


async def command(*args):
    url = os.getenv('UPSTASH_REDIS_REST_URL', '').strip().rstrip('/')
    token = os.getenv('UPSTASH_REDIS_REST_TOKEN', '').strip()
    if not url.startswith('https://') or not token:
        raise HTTPException(503, 'Public usage storage is unavailable. No AI request was sent.')
    try:
        # No automatic retries: an ambiguous response may have committed a reservation.
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.post(url, headers={'Authorization': 'Bearer ' + token}, json=list(args))
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or 'error' in result or 'result' not in result:
                raise ValueError()
            return result['result']
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, 'Public usage storage is unavailable. No AI request was sent.') from None


def normalized_network(raw):
    if '%' in raw:
        raise ValueError()
    address = ipaddress.ip_address(raw)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address) if address.version == 4 else str(ipaddress.ip_network(f'{address}/64', strict=False))


def ip_key(request: Request):
    secret = os.getenv('PUBLIC_IP_HASH_SECRET', '')
    if len(secret) < 32:
        raise HTTPException(503, 'Public AI generation is temporarily unavailable.')
    # Default ignores user-supplied forwarding headers. Behind Render, only opt into
    # an edge-overwritten header after validating the ingress trust boundary.
    source = os.getenv('PUBLIC_IP_SOURCE', 'peer')
    if source == 'peer':
        if os.getenv('RENDER') == 'true':
            raise HTTPException(503, 'Public AI generation is temporarily unavailable.')
        raw = request.client.host if request.client else ''
    elif source == 'render':
        if os.getenv('RENDER') != 'true' or os.getenv('PUBLIC_RENDER_IP_VERIFIED') != 'true':
            raise HTTPException(503, 'Public AI generation is temporarily unavailable.')
        values = request.headers.getlist('cf-connecting-ip')
        if len(values) != 1:
            raise HTTPException(503, 'Cannot verify the visitor network. No AI request was sent.')
        raw = values[0]
    else:
        raise HTTPException(503, 'Public AI generation is temporarily unavailable.')
    try:
        normalized = normalized_network(raw)
    except ValueError:
        raise HTTPException(503, 'Cannot verify the visitor network. No AI request was sent.') from None
    return hmac.new(secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def token_key(token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token or ''):
        raise HTTPException(401, 'Start a new anonymous session to use free AI editing.')
    return hashlib.sha256(token.encode()).hexdigest()


async def evaluate(action, token, ip, *, cost=None, kind='operation', reservation_id=None):
    enabled()
    visitor = token_key(token)
    window = 'issue' if action == 'create' else 'rate'
    reservation_id = reservation_id or secrets.token_hex(16)
    keys = [PREFIX + 'budget', PREFIX + 'visitor:' + visitor, PREFIX + 'ip:' + ip, PREFIX + window + ':' + ip,
            PREFIX + 'reservation:' + reservation_id, PREFIX + 'ledger', PREFIX + 'pending']
    result = await command('EVAL', SCRIPT, len(keys), *keys, action, ip,
                           cost or dollars('PUBLIC_OPERATION_RESERVE_USD', '0.20'), kind, visitor, *limits(), reservation_id)
    if not isinstance(result, list) or not result:
        raise HTTPException(503, 'Public usage storage returned an invalid result.')
    errors = {
        'storage': (503, 'Public usage storage is unavailable. No AI request was sent.'),
        'disabled': (503, 'Public AI generation is currently disabled.'),
        'session': (401, 'Your anonymous session is invalid or your network changed. Start a new session.'),
        'global': (429, "The public demo has reached its usage limit. Please try again later."),
        'visitor': (429, "Demo limit reached. You\'ve used your available AI edits."),
        'ip': (429, "Demo limit reached. You\'ve used your available AI edits."),
        'busy': (429, 'AI is busy. Please try again after the current request finishes.'),
        'duplicate': (409, 'This AI request is already reserved.'),
        'rate': (429, 'Too many AI requests from this network. Please wait before trying again.'),
    }
    if result[0] != 'ok':
        status, message = errors.get(result[0], errors['storage'])
        raise HTTPException(status, message)
    if len(result) != 9 or any(type(n) is not int or n < 0 for n in result[1:]):
        raise HTTPException(503, 'Public usage storage returned an invalid result.')
    if result[4] < result[2] or any(n > 1000000000000 for n in result[1:]):
        raise HTTPException(503, 'Public usage storage returned an invalid result.')
    remaining = max(0, min(result[7]-result[1], result[6]-result[2], result[8]-result[3]))
    budget_remaining = max(0, (result[5] - result[4]) // dollars('PUBLIC_OPERATION_RESERVE_USD', '0.20'))
    remaining = min(remaining, budget_remaining)
    return {'mode': 'public', 'remaining': remaining,
            'visitor_remaining': max(0, result[7]-result[1]), 'global_remaining': max(0, min(result[6]-result[2], budget_remaining)),
            'message': ('The public demo has reached its usage limit. Please try again later.' if result[2] >= result[6] or budget_remaining == 0 else
                        "Demo limit reached. You've used your available AI edits." if remaining == 0 else
                        'Each voice setup, speech detection and generation uses one allowance. Failed attempts count too.')}



async def reserve_operation(kind='operation', **details):
    access = context.get()
    if not access:
        raise HTTPException(403, 'AI operations require a verified access context.')
    if access == 'demo':
        # Only set by the existing backend demo dependency, never a public header.
        if mode() != 'demo':
            raise HTTPException(403, 'Public usage authorization is required.')
        return
    if mode() != 'public':
        raise HTTPException(503, 'Public AI access is unavailable.')
    if os.getenv('PUBLIC_COST_REVIEWED', 'false').lower() != 'true':
        raise HTTPException(503, 'Public AI generation is temporarily unavailable.')
    rid = secrets.token_hex(16)
    await evaluate('reserve', *access, cost=estimate(kind, **details), kind=kind, reservation_id=rid)
    return rid


async def finish_operation(rid, outcome):
    if rid is None: return
    result = await command('EVAL', FINISH, 3, PREFIX + 'budget', PREFIX + 'reservation:' + rid, PREFIX + 'pending', outcome, rid)
    if result != 'finished': raise HTTPException(503, 'Public usage storage is unavailable.')


@asynccontextmanager
async def operation(kind, **details):
    rid = await reserve_operation(kind, **details)
    outcome = 'interrupted'
    try:
        yield
        outcome = 'completed'  # Full reservation retained; no reliable per-response billing field documented.
    except Exception:
        outcome = 'failed_or_unknown'
        raise
    finally:
        try:
            await finish_operation(rid, outcome)
        except Exception:
            # Leave durable pending debit/slot intact on storage failure. Next calls fail closed.
            logging.getLogger('uvicorn.error').warning('Public reservation finalization unavailable; pending allowance retained.')
