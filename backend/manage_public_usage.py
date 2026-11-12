"""Private operator CLI. Never exposed as HTTP; never calls Fish Audio."""
import argparse
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / '.env')
from app import public_usage
from app.public_usage import PREFIX, limits, FINISH

INITIALIZE = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 'already_initialized' end
redis.call('HSET', KEYS[1], 'schema', '2', 'enabled', '0', 'used', '0',
  'reserved_microusd', 0, 'active', 0, 'global_limit', ARGV[1], 'visitor_limit', ARGV[2],
  'ip_limit', ARGV[3], 'concurrency', ARGV[4], 'budget_microusd', ARGV[5])
return 'initialized_disabled'
"""
TOGGLE = """
for _, field in ipairs({'used', 'reserved_microusd', 'active', 'global_limit', 'visitor_limit', 'ip_limit', 'concurrency', 'budget_microusd'}) do
  local value = redis.call('HGET', KEYS[1], field)
  if not value or not string.match(value, '^%d+$') then return 'invalid_budget_no_change' end
end
if redis.call('HGET', KEYS[1], 'schema') ~= '2' then return 'invalid_budget_no_change' end
redis.call('HSET', KEYS[1], 'enabled', ARGV[1])
return 'updated'
"""
MIGRATE = """
if redis.call('HGET', KEYS[1], 'schema') ~= '1' or redis.call('HGET', KEYS[1], 'enabled') ~= '0' then return 'disable_legacy_budget_first' end
local used = redis.call('HGET', KEYS[1], 'used')
if not used or not string.match(used, '^%d+$') then return 'invalid_budget_no_change' end
if tonumber(used) > 0 then return 'historical_usage_requires_manual_billing_reconciliation' end
redis.call('HSET', KEYS[1], 'schema', '2', 'reserved_microusd', tonumber(used) > 0 and ARGV[5] or '0',
  'active', '0', 'global_limit', ARGV[1], 'visitor_limit', ARGV[2], 'ip_limit', ARGV[3],
  'concurrency', ARGV[4], 'budget_microusd', ARGV[5])
return 'migrated_disabled_counters_preserved'
"""
CONFIGURE = """
if redis.call('HGET', KEYS[1], 'schema') ~= '2' or redis.call('HGET', KEYS[1], 'enabled') ~= '0' then return 'disable_budget_first' end
redis.call('HSET', KEYS[1], 'global_limit', ARGV[1], 'visitor_limit', ARGV[2], 'ip_limit', ARGV[3],
  'concurrency', ARGV[4], 'budget_microusd', ARGV[5])
return 'limits_updated_counters_preserved'
"""
DISABLE = """
if redis.call('EXISTS', KEYS[1]) == 0 then return 'missing_budget' end
redis.call('HSET', KEYS[1], 'enabled', 0)
return 'updated'
"""

async def manage(action, reservation=None):
    key = PREFIX + 'budget'
    if action in ('initialize', 'migrate', 'configure'):
        script = {'initialize': INITIALIZE, 'migrate': MIGRATE, 'configure': CONFIGURE}[action]
        return await public_usage.command('EVAL', script, 1, key, *limits())
    if action == 'disable':
        return await public_usage.command('EVAL', DISABLE, 1, key)
    if action == 'enable':
        if os.getenv('PUBLIC_COST_REVIEWED', 'false').lower() != 'true':
            return 'review_provider_prices_and_voice_creation_allowance_first'
        return await public_usage.command('EVAL', TOGGLE, 1, key, '1')
    if action == 'resolve':
        import re
        if not re.fullmatch('[0-9a-f]{32}', reservation or ''): return 'invalid_reservation'
        if await public_usage.command('HGET', key, 'enabled') != '0': return 'disable_budget_first'
        return await public_usage.command('EVAL', FINISH, 3, key, PREFIX + 'reservation:' + reservation, PREFIX + 'pending', 'operator_resolved_unknown', reservation)
    return await public_usage.command('HGETALL', key)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('initialize', 'enable', 'disable', 'inspect', 'configure', 'migrate', 'resolve'))
    parser.add_argument('reservation', nargs='?')
    args = parser.parse_args()
    try:
        print(asyncio.run(manage(args.action, args.reservation)))
    except Exception:
        raise SystemExit('Usage storage operation failed; no automatic retry. Check configuration and inspect the budget.') from None
