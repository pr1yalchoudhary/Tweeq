# Verify the deployed public allowance without Fish Audio credits

## Current evidence

The latest external checks returned HTTP 200 for the deployed frontend, backend health,
and `/api/public/usage`. That usage response still reports `mode: demo`. In this mode,
the public status endpoint deliberately does not contact Upstash. A successful redeploy
and a healthy FastAPI response do **not** verify Redis authentication or the budget.

Render dashboard credentials and shell access are not available to this local agent.
The corrected Upstash values were entered in Render, not necessarily in local `.env`.
No claim that the previous datastore HTTP 401 is resolved can be made until a check
runs in Render's environment. No production paid endpoint was called during these checks.

Also, this checkout's dollar-budget/reservation changes are still uncommitted relative
to `b16bb6f`. Deploy the current guard code and private verification tool before testing.
A credentials-only redeploy of that older commit is insufficient. This tool does not
push, deploy, initialize the production allowance, or change Render environment settings.

The latest local run passed **117 backend tests**, including the private verifier,
editing regressions, actual Lua executed in a Redis emulator and mocked provider HTTP.
Live CORS preflight allows the intended Vercel origin and rejects an unrelated origin.
These results do not substitute for private authentication or real restart evidence.

If deploying through Git, publish only the prepared Tweeq files (excluding unrelated
untracked `migrations/` and ignored secrets). From the local repository root:

```sh
git add .env.example README.md PUBLIC_USAGE.md PUBLIC_VERIFICATION.md backend/app backend/tests backend/manage_public_usage.py backend/verify_public_usage.py
git diff --cached --stat
git commit -m "Protect public AI budget and add isolated deployment verification"
git push
```

Confirm Render deploys that new commit with public AI still disabled. No commit,
push or production deployment was performed by the agent during this verification.

## First: confirm authentication from Render Shell

Keep `AI_ACCESS_MODE=demo`, `PUBLIC_AI_ENABLED=false` and
`PUBLIC_GENERATIONS_ENABLED=false`. From the repository root in Render Shell:

```sh
python backend/manage_public_usage.py inspect
```

If the configured Render root directory is already `backend`, omit `backend/` from
the script path in these commands. `inspect` is read-only and makes no Fish requests.
A successful Redis hash response (including an empty hash) proves authentication,
but an empty hash means the production budget has not been initialized. A failure
does not justify enabling public AI or recreating/deleting the database.

Do not paste environment variables, API keys, URLs with credentials or REST tokens.
The operator command's budget counters/schema output is safe to share.

## Deploy the current code, then run isolated tests in Render

Ensure Render is running the schema-2 dollar-budget/reservation implementation and
includes `backend/verify_public_usage.py`. This private tool uses only existing
runtime dependencies. It is not an HTTP endpoint, and no application-wide provider
mock switch is added. Keep public AI off while performing these steps.

```sh
python backend/verify_public_usage.py start
```

This command:

- Authenticates to the **actual configured Upstash database** with a read-only PING.
- Creates only `tweeq:{verification-<random-run-id>}:...` fixture keys. Every mutation
  is checked against that isolated prefix. Production allowance keys are never written.
- Executes the actual public Lua and provider adapter with mock Fish HTTP responses.
  Fish URLs never reach a network transport; the process uses an invalid dummy Fish
  key as an additional safeguard. Only the configured Redis HTTPS origin can use
  the real transport. Other outbound requests are blocked.
- Tests two provider operations per visitor, concurrent global ten-operation denial,
  the $2 estimate independently from the operation limit, both emergency switches,
  interrupted requests/no automatic retries, and durable pending concurrency slots.
- Checks that production counters did not change during the test and that retained
  test counters have no expiry. It does not refund or reset production usage.
- Prints a run ID, passed checks, mocked-call count, current guard source hash,
  production budget schema, and `restart_verification: pending`. No secrets are printed.

The isolated process temporarily selects public mode and fixture limits **only within
itself**. It does not test that the live service's environment is configured correctly,
and it does not enable real AI. It makes approximately a few hundred small Redis REST
requests. These consume existing datastore quota and may incur normal Upstash command
charges on a paid plan; **Fish Audio usage is zero**. No account or database is provisioned.

If a step fails, public AI must stay disabled. Test keys may remain for diagnosis.
Do not delete or recreate any production keys to force a pass.

## Restart persistence

Save the printed `run_id`. Restart/redeploy the **actual Render backend service** with
public AI still off; active recordings will expire under the existing session design.
Open a fresh Render Shell afterward and run:

```sh
python backend/verify_public_usage.py resume --run-id YOUR_RUN_ID
```

This new process reads the same Redis fixtures and verifies global, visitor/network,
and pending reservation counters survived unchanged, plus the production budget
snapshot. It refuses missing/corrupt state and does not repair/reset it. The guard
source hash must be unchanged between start and resume.

The command cannot independently prove you clicked Restart in Render; it deliberately
reports `render_restart_independently_verified: false`. Starting a second CLI process
alone is **not** evidence of a backend restart. Confirm the real service restart in
Render's events before interpreting a successful resume as a restart-persistence test.

After collecting the results, remove only the isolated fixtures:

```sh
python backend/verify_public_usage.py cleanup --run-id YOUR_RUN_ID
```

No production keys are deleted. If the live service legitimately changed production
usage between start/resume, the snapshot comparison fails conservatively; investigate
that change before interpreting the report.

## Separate production prerequisites

An isolated pass proves the adapter/Lua behavior against the real datastore, but it
does not prove the live HTTP ingress identifies visitor networks correctly. Before
launch, verify Render's trusted IP header cannot be forged, the actual start command
uses `--no-proxy-headers`, the IP HMAC secret is stable, and exact CORS origins match
the intended frontend. Do not set `PUBLIC_RENDER_IP_VERIFIED=true` merely to unblock
an error. Preserve the original Fish model/reference/audio settings.

The production Redis budget must have valid schema 2, matching ledger/pending totals,
and no unresolved pending operations. `inspect` displays its schema/used/reserved/
active/enabled/cap fields. Initialize only a genuinely new allowance; migrate an
existing disabled zero-use schema-1 budget using the operator CLI. Historical usage
must be reconciled without resetting counters. See `PUBLIC_USAGE.md` for full details.

The production limits must be the requested 2 visitor/network operations, 10 global
operations, $2 estimate, 60-second uploads and 200-character speech. The verifier
uses sandbox limits to isolate failure modes; its pass does not set production values.

## Enable only after all results and ingress checks pass

On Render, retain the existing backend Fish key and configure:

```text
AI_ACCESS_MODE=public
PUBLIC_AI_ENABLED=true
PUBLIC_GENERATIONS_ENABLED=true
PUBLIC_COST_REVIEWED=true
PUBLIC_BUDGET_USD=2
PUBLIC_GLOBAL_OPERATIONS=10
PUBLIC_VISITOR_OPERATIONS=2
PUBLIC_IP_OPERATIONS=2
PUBLIC_AI_CONCURRENCY=1
PUBLIC_MAX_RECORDING_SECONDS=60
PUBLIC_MAX_TEXT_CHARS=200
PUBLIC_IP_SOURCE=render
PUBLIC_RENDER_IP_VERIFIED=true
```

The cost-review flag requires actual review of current provider pricing and the
unverified voice-creation allowance. The $2 accounting is conservative estimation,
not a provider-enforced invoice cap. Two operations may cover only voice setup +
one TTS request, rather than two finished edits.

Enable the **existing, verified** production budget with the private operator CLI:

```sh
python backend/manage_public_usage.py enable
```

The frontend already hides demo-code UI when the backend reports public mode. Keep
Vercel's existing `VITE_API_BASE_URL=https://tweeq-backend.onrender.com`; if that build
setting changes, redeploy the frontend. No backend secret belongs in Vercel or a
`VITE_` variable. No UI redesign or editing feature change is necessary.

Check a private/incognito window for anonymous session creation, no code input,
working upload/local controls and the expected usage display. Do not generate live
speech merely to test access. Untrusted/missing visitor credentials must still be
rejected by the public backend; public mode must not accept a demo bearer bypass.

Immediate shutdown, without waiting for a redeploy:

```sh
python backend/manage_public_usage.py disable
```

Also set `PUBLIC_AI_ENABLED=false` in Render. Already reserved/dispatched requests
cannot be recalled. Playback, applying saved previews, Undo/Redo and export stay local.
