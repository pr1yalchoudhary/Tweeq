# Public AI allowance rollout — 2026-11-12

## Current rollout status

The protection changes are implemented and deployed. **Public production access is not enabled.**
The owner completed the free-tier startup checks using the real Upstash datastore,
mocked provider transport, isolated fixture keys and an actual Render redeploy between
start/resume. Authentication, quota/estimated-dollar caps, emergency switches and
persistence checks passed; isolated test keys were cleaned up. Production was then
initialized with schema 2, $2 estimated budget, ten global operations, two per visitor/
network, concurrency one, zero use and `enabled=0`.

Live ingress checks observed no header-based identity bypass. The temporary authenticated
health diagnostic wrapper was deactivated, verified absent on both authenticated and
unauthenticated health responses, and removed from source. The ordinary Start Command
now includes `--no-proxy-headers`. Live `/api/public/usage` still reports `mode: demo`.
The UI and Fish model/reference/audio settings are unchanged; no paid tests occurred.
See [PUBLIC_VERIFICATION.md](PUBLIC_VERIFICATION.md) for evidence, scope and remaining
configuration checks. Do not enable public AI until the deliberate final setup is complete.

## Architecture

The existing frontend already supports anonymous public mode: `POST /api/public/session` issues an opaque
random credential, kept in sessionStorage (memory fallback), which is sent as `X-Visitor-Session`.
The password input is absent when the backend reports public mode. There is no public owner-token bypass.
Public limits apply at the Fish adapter, immediately before **every** outbound provider attempt, so direct
HTTP clients cannot bypass them through an alternative application endpoint.

Use a dedicated, durable Upstash Redis database, not Render's ephemeral filesystem. The existing `httpx`
dependency calls its HTTPS REST API; no new runtime package or large database is required. One atomic Lua
script validates enabled state, schema, ledger totals, pending calls, visitor/network quotas, rate,
operation count, and remaining estimated dollars before committing a reservation. Redis serialization
protects multiple backend workers and simultaneous requests. All keys share `tweeq:{public-v1}:`.
Missing/corrupt state, malformed responses or unavailable storage prevent paid dispatch. No automatic
initialization, reset, reservation retry or refund occurs at startup/redeploy.

Schema 2 stores:
- Global operation count, reserved microdollars, budget, enabled flag and active count.
- A nonexpiring debit ledger and pending set; their sums/counts must match global state.
- Nonexpiring per-visitor and HMAC-network operation counts.
- Each reservation's kind, conservative amount, visitor/network digests and terminal/pending state.
- Short-lived per-network rate counters; only these expire.

Reservation amounts and quotas never expire automatically. Success, provider errors, timeouts, cancellation,
client disconnect and backend crashes keep the full debit. Completion frees a concurrency slot but never
returns credit. A crash or ambiguous storage response can leave a paid slot pending indefinitely: this is
intentional. Operators must stop workers and resolve it manually without refunding its cost or operation.

## Estimated $2 budget and pricing audit

Official Fish documentation checked **2026-11-12** lists:
- Drama 3: $50 / million UTF-8 input bytes (temporary $10 promotion through November 30 is ignored).
- S2.1 Pro and S2 Pro: $15 / million UTF-8 bytes; S2.1 Pro Free currently $0.
- File ASR (`transcribe-1-pro`): $0.36 / audio hour, rounded up to a second.

The implementation deliberately reserves **the greater of $0.20 and 2x the documented calculation**
for every provider operation. All supported TTS models use the highest $50/M rate, including currently
free correction models. UTF-8 bytes include the final direction/tag script and any inline reference
transcript. ASR reserves against the configured maximum selected-segment duration (60 seconds by default),
which overestimates shorter selections. All arithmetic uses integer microdollars (1 USD = 1,000,000).

There is **no separately documented saved-voice creation/status price** in the pricing page. The default
$0.20 voice allowance is an operator policy reserve, **not a claimed provider price or proven cost bound**.
Voice status polls are conservatively counted as operations too. Confirm the account's actual voice
creation charges with Fish before setting `PUBLIC_COST_REVIEWED=true`; otherwise paid dispatch stays blocked.
That review flag is required both by the enable CLI and the worker's dispatch guard.

No reliable per-response dollar billing field or account spending-cap API was established in the official
references. Therefore successful responses do not trigger guessed billing reconciliation or refunds.
The ledger tracks **estimated reserved spending**, not an invoice. Ten operations at the default minimum
reserve exhaust $2; longer scripts can exhaust it sooner. Unknown voice pricing and later price changes
mean this is **not a guaranteed provider-enforced $2 invoice cap**. Recheck pricing before enabling or
changing limits. Ask Fish whether your account supports a hard API spend cap; configure one if available.
Use a dedicated prepaid API balance and avoid automatic recharges if your account permits that setup.
No account setting was assumed or changed here. Public accounting does not count authorized demo-mode
internal tests; both can still draw from the same Fish account balance.

## Defaults and backend environment

Keep secrets only in Render/backend environment, never in Vercel or `VITE_` variables.
The actual `FISH_AUDIO_API_KEY` and model settings remain unchanged.

| Variable | Default / purpose |
|---|---|
| `AI_ACCESS_MODE` | `demo` during setup; `public` only after verified rollout |
| `PUBLIC_AI_ENABLED` | `false` during setup; preferred emergency switch |
| `PUBLIC_GENERATIONS_ENABLED` | Legacy switch; if explicitly false it also blocks public AI |
| `PUBLIC_COST_REVIEWED` | `false`; deliberate provider/voice pricing review required |
| `PUBLIC_BUDGET_USD` | `2` lifetime estimated public allowance |
| `PUBLIC_GLOBAL_OPERATIONS` | `10` lifetime provider reservations |
| `PUBLIC_VISITOR_OPERATIONS` | `2` lifetime provider reservations per visitor |
| `PUBLIC_IP_OPERATIONS` | `2` lifetime provider reservations per network |
| `PUBLIC_AI_CONCURRENCY` | `1` concurrent provider operation across all workers |
| `PUBLIC_OPERATION_RESERVE_USD` | `0.20` minimum reserve per operation |
| `PUBLIC_VOICE_RESERVE_USD` | `0.20` unverified voice-create/status policy allowance |
| `PUBLIC_MAX_RECORDING_SECONDS` | `60` uploads/ASR selections |
| `PUBLIC_MAX_UPLOAD_BYTES` | `26214400` (25 MiB); may be lowered |
| `PUBLIC_MAX_TEXT_CHARS` | `200` generated speech characters per request |
| `UPSTASH_REDIS_REST_URL` | Dedicated durable database's HTTPS REST URL |
| `UPSTASH_REDIS_REST_TOKEN` | Standard read/write token, not read-only |
| `PUBLIC_IP_HASH_SECRET` | Independent random secret, at least 32 characters; keep stable |
| `PUBLIC_IP_SOURCE` | `peer` locally; verified `render` in production |
| `PUBLIC_RENDER_IP_VERIFIED` | `false` until actual ingress spoofing checks pass |
| `CORS_ORIGINS` | Exact production frontend/local development origins; no wildcard |
| `DEMO_ACCESS_TOKEN` | Retain only for controlled demo-mode migration/rollback |

Persisted limits constrain environment settings: workers use the smaller of each stored/environment
budget, quota and concurrency limit. A redeploy cannot silently raise the stored allowance.
Use the private `configure` command while disabled to deliberately change persisted limits; no command
resets spending or operation counters. Keep all worker environments consistent.

## Anonymous abuse limits and input validation

The server-issued opaque visitor credential is bound to a server-derived network HMAC. Raw IPs are not
stored. IPv4-mapped IPv6 is normalized; IPv6 is grouped by /64. Local peer mode ignores forwarded headers.
On Render, peer mode is rejected; Render mode requires `RENDER=true`, a verified `CF-Connecting-IP` ingress
and the explicit verification flag. **Never set that flag just to silence a configuration error.**
Run Uvicorn with `--no-proxy-headers` and verify Render overwrites/validates the trusted IP header on all
routes, including direct onrender.com calls. Spoofed `True-Client-IP`, `CF-Connecting-IP`, and
`X-Forwarded-For` must not change an attacker's network identity. If this is not guaranteed by your
actual ingress, leave public AI off and establish a trusted edge before adapting the resolver.

Each network permits two operation attempts/minute and ten visitor token issuances/hour. Each visitor
and network has a lifetime two-operation ceiling. Shared Wi-Fi/NAT users may share an allowance.
Clearing storage does not replenish the network limit; different networks/VPNs can evade individual
limits, but the global operation and estimated-dollar ceilings remain independent and effective.
Bots can exhaust a free public allowance; this is not identity verification or a CAPTCHA system.

Public uploads check extension, MP3/WAV container signature, actual ffprobe audio codec, duration and size
before voice/quality processing. Speech fields exceeding 200 characters are rejected before voice setup.
Simultaneous preview/transcription requests for one recording are rejected while its lock is held.
Existing successful ASR selections and voice models are reused. Public TTS requests have **no automatic
retries**, including 429/5xx/connection errors; explicit retries need new reservations.

Two operations are **not two complete edits**. Voice setup + TTS usually consumes both; Change Delivery
may also require ASR. Voice status polling can consume allowance before a preview is ready. All existing
editing features remain available, but this intentionally strict public quota limits their AI usage.
Apply a saved preview, local cleanup, multiple edits, Undo/Redo, A/B playback and MP3 export do not reserve
Fish operations. Cached/local operations do not reset counters. Audio sessions themselves retain their
existing in-memory/ephemeral lifetime; quotas persist independently.

Public quota errors use:
- "Demo limit reached. You've used your available AI edits."
- "The public demo has reached its usage limit. Please try again later."

Public provider failures omit configuration instructions and raw provider bodies. API keys never leave
the backend. Existing visual design, name, tagline and editing controls have not been redesigned.

## Setup, costs and strict deployment sequence

1. Keep production `AI_ACCESS_MODE=demo`, and both public switches false. Finish active recordings before
   any backend restart; the existing app's audio sessions are not durable.
2. Verify the existing Upstash credentials, database durability/no-eviction/retention and budget contents.
   Do not use an unclaimed temporary database or create a new database to reset historical usage.
   Current Upstash free pricing lists 250 MB and 500,000 commands/month. Pay-as-you-go is $0.20/100,000
   commands; Lua scripts execute multiple commands. A free-tier outage/exhaustion blocks AI rather than
   allowing untracked calls. Plan/retention terms need confirmation in the actual account.
3. Configure Render secrets and public limits from `.env.example`. No new Fish key/provider is required.
   The IP secret and verified ingress configuration are still missing locally. Do not paste secrets in chat.
4. Set Render's existing start command to use `--no-proxy-headers`, preserving its existing app directory,
   host and `$PORT` handling. No Render blueprint or Vercel deployment manifest exists in this repo;
   actual dashboard settings cannot be inferred from local source. Existing CORS defaults include
   `https://tweeq-ruby.vercel.app`; set `CORS_ORIGINS` to your exact intended domain if different.
5. Deploy code with public AI still disabled. Use a separate staging Redis database and mocked Fish
   transport to repeat quota/concurrency/restart tests across actual Render workers. A local emulator
   result does not prove production durability or ingress behavior. Do not call live paid endpoints to
   check whether the guard is installed.
6. Initialize **once**, only if the production budget has never existed. For existing schema 1, disable
   then use `migrate`; migration preserves counters and refuses any nonzero historical usage until
   billing is manually reconciled. Never delete/reinitialize an existing allowance.
7. Verify provider prices/voice fees, then set `PUBLIC_COST_REVIEWED=true`. Enable the Redis budget,
   change Render to public mode and set both public enable switches true. No code/token UI is shown
   in this mode. Keep `DEMO_ACCESS_TOKEN` only for controlled rollback; public mode ignores it.
8. The existing frontend needs only `VITE_API_BASE_URL=https://tweeq-backend.onrender.com` on Vercel.
   It already renders the public usage state without a code; a frontend redesign is unnecessary.
9. Verify incognito access, exact CORS, trusted IP binding, limits, disabled-store failure and emergency
   shutdown with mocked production-shaped provider traffic. This phase has **not** run in production.
   Only remove obsolete rollback demo configuration after rollout is verified.

Local/private operator commands (same production datastore settings; never public HTTP routes):

```powershell
.\.venv\Scripts\python.exe backend/manage_public_usage.py inspect
.\.venv\Scripts\python.exe backend/manage_public_usage.py initialize
# OR, for an existing disabled zero-use schema-1 budget:
.\.venv\Scripts\python.exe backend/manage_public_usage.py migrate
.\.venv\Scripts\python.exe backend/manage_public_usage.py enable
```

## Monitoring, adjustment and emergency stop

`inspect` reports global `used`, `reserved_microusd`, `active`, stored limits, schema and enabled state.
Divide microdollars by 1,000,000 locally for the estimated-dollar reserve. Inspect the nonexpiring ledger,
pending set and reservation records in the private Redis console. Reconcile manually against Fish billing;
no documented reliable automated invoice reconciliation was established. Retain full unknown costs.

For an immediate stop, without waiting for a Render redeploy:

```powershell
.\.venv\Scripts\python.exe backend/manage_public_usage.py disable
```

Also set `PUBLIC_AI_ENABLED=false` on Render. An explicitly false legacy switch blocks calls too.
The datastore flag is checked on every new reservation; already reserved/dispatched provider requests
cannot be recalled. Neither switch resets counters. Local editing/playback/export remain available.

To adjust caps: disable, update backend environment values, run `configure`, inspect, then reenable
only after validation. Raising limits deliberately authorizes a larger allowance. Avoid changing limits
while requests are pending. For interrupted slots, disable and stop **all** backend workers first; verify
no provider operation can still be running, inspect `SMEMBERS tweeq:{public-v1}:pending`, then run
`manage_public_usage.py resolve <reservation-id>`. This releases only the slot; no spend/quota is refunded.
Do not resolve a pending record while its original worker could still dispatch or finish a call.

## Local verification and remaining production checks

The complete 106-test backend suite passed before final refinements; all 36 final budget/security tests
passed afterward, including operator migration/configuration. The earlier targeted editing run passed its
workflow/access checks; two operator-test isolation failures were corrected and rerun successfully.
45 frontend checks passed, including code-free public-mode UI, failure states, two independent edits,
preview/apply, Undo/Redo and export. Tests use the actual Lua scripts in fakeredis and mocked HTTP providers.
The test suite blocks real asynchronous network transports to prevent accidental paid requests.
Production is still gated, datastore authentication failed safely with HTTP 401, and incognito/live ingress/durable
restart tests remain pending. No real Fish Audio credits were consumed.

The current backend secret values were not found in tracked Git history; backend/.env is untracked/ignored.
This exact-value audit is not proof that every historical/unknown credential is absent. Existing audio
retention, per-recording ownership, generic upload/storage DoS protection and anonymous-identity evasion
remain limitations beyond the paid-credit gate.

## Official references

- [Fish API pricing and ASR rounding](https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits)
- [Fish saved voice creation API](https://docs.fish.audio/api-reference/endpoint/model/create-model)
- [Upstash pricing](https://upstash.com/pricing/redis)
- [Upstash REST API](https://upstash.com/docs/redis/features/restapi)
- [Upstash durability](https://upstash.com/docs/redis/features/durability)
- [Redis atomic Lua execution](https://redis.io/docs/latest/develop/programmability/eval-intro/)

## Modified files

- `backend/app/public_usage.py`: atomic dollar/quota ledger, reservations, concurrency and emergency guards.
- `backend/app/fish_audio.py`: operation-specific reservations/finalization and no public TTS retries.
- `backend/app/main.py`: public input limits, duplicate-inflight rejection, generic provider errors and exact configurable CORS.
- `backend/app/audio.py`: optional pre-decode public duration limit, preserving default internal behavior.
- `backend/manage_public_usage.py`: schema initialization/migration, inspect/configure, shutdown and pending-slot recovery.
- `backend/tests/test_public_usage.py`: real-Lua quota, cost, corruption, concurrency, persistence and operator tests.
- `backend/tests/conftest.py`: forbid real async network transports during tests.
- `.env.example`, `README.md`, `PUBLIC_USAGE.md`: configuration, risk and rollout documentation.

All frontend sources, UI styling/wording, Fish model selection and audio splice/Undo/Redo algorithms remain unchanged.
Existing unrelated untracked `migrations/` files were not changed.
