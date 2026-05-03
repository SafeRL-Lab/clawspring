# Daemon Foundation Roadmap

- **Status:** Tracking
- **Refs:** [#68](https://github.com/SafeRL-Lab/cheetahclaws/issues/68), [RFC 0001 design note](./0001-daemon-design-note.md)
- **Last updated:** 2026-04-30

The "foundation PR" described at the end of [RFC 0001](./0001-daemon-design-note.md) is too big for one reviewable change (~5 KLoC including stdlib HTTP server, auth, JSON-RPC + SSE, SQLite schema, `daemon` CLI, bridges-into-daemon, subprocess-per-agent, and conservative cost defaults). This document splits it into nine stackable PRs and pins the acceptance criteria for each. Implementation follows this index in order; later items can land in parallel once F-1 and F-2 are merged.

## Index

| ID  | Scope                                               | Depends on | Est LoC | Status |
|-----|-----------------------------------------------------|------------|---------|--------|
| F-1 | `daemon/` package skeleton; `serve` + `daemon` CLI  | —          | ~1500   | MERGED #80 |
| F-2 | SQLite schema + originator-tracked permission flow  | F-1        | ~600    | TODO   |
| F-3 | `monitor/scheduler` runs in daemon                  | F-2        | ~500    | TODO   |
| F-4 | `agent_runner` becomes subprocess-per-agent         | F-2        | ~1000   | TODO   |
| F-5 | `proactive` watcher runs in daemon                  | F-2        | ~200    | TODO   |
| F-6 | Telegram bridge in daemon                           | F-2        | ~500    | TODO   |
| F-7 | Slack bridge in daemon                              | F-6        | ~500    | TODO   |
| F-8 | WeChat bridge in daemon                             | F-6        | ~500    | TODO   |
| F-9 | Conservative cost-guardrail defaults under `serve`  | F-1        | ~150    | TODO   |

## F-1 — daemon skeleton

**Scope.** Adopt the `cc_daemon/` reference scaffolding from
[`feature/daemon-spike`](https://github.com/SafeRL-Lab/cheetahclaws/tree/feature/daemon-spike)
(`server`, `auth`, `originator`, `rpc`, `events`, `permission`, `methods`)
**as-is** — those modules encode the contract the maintainer reviewed in
PR #74.  Layer the foundation glue on top:

- `cc_daemon/discovery.py` — atomic `~/.cheetahclaws/daemon.json` so
  REPL / Web / bridge clients can locate the running daemon (transport,
  address, version).  Spike's pid file stays for "is anything running?"
  liveness; discovery answers "where is it?".
- `cc_daemon/system_methods.py` — registers `system.ping` (returns
  `"pong"`) and `system.shutdown` (sets `DaemonState.shutdown_event`,
  giving us cross-platform graceful exit since Windows can't deliver
  SIGTERM cleanly to another Python process).
- `cc_daemon/cli.py` — rewritten `serve_main(argv)` that calls
  `bootstrap()`, pins `log_file` to `<data_dir>/logs/daemon.log`, threads
  the loaded `config` and the `--unauthenticated-metrics` flag through
  `DaemonState`, writes the discovery file on bind, watches the shutdown
  event, and clears discovery on exit.
- `cc_daemon/server.py` — minimal patch: route `/healthz` `/readyz`
  `/metrics` through `health.payload_for(path, config)` instead of
  the spike's stub `{"status": "ok"}`.  Auth-gated by default; opt out
  via `--unauthenticated-metrics`.  Adds Windows guard around
  `socketserver.UnixStreamServer` (unavailable on Windows).
- `commands/daemon_cmd.py` — `cheetahclaws daemon {status, stop, logs,
  rotate-token}` subcommand handlers.  `status` reads discovery + pings
  `system.ping`; `stop` calls `system.shutdown` RPC then falls back to
  SIGTERM / TerminateProcess; `logs` tails `~/.cheetahclaws/logs/daemon.log`;
  `rotate-token` regenerates the token (notes that existing TCP clients
  receive 401 until they re-read the file).
- `health.py` — refactor: extract module-level `healthz_payload(config)`
  / `readyz_payload(config)` / `metrics_payload(config)` /
  `payload_for(path, config)` so both the existing standalone health
  HTTP server and `cc_daemon/server.py` reuse the same
  circuit-breaker / quota / runtime-registry probes.  No behaviour
  change for existing `health_check_port` users.
- `cheetahclaws.py` — main() short-circuit: `cheetahclaws serve`
  dispatches to `cc_daemon.cli.serve_main`; `cheetahclaws daemon
  <action>` dispatches to `commands.daemon_cmd.dispatch`.  Replaces the
  spike's `spike-daemon` shim.

**Acceptance.**
- `cheetahclaws serve` starts; `cheetahclaws daemon status` reports pid,
  transport, address, uptime, ping outcome.
- Unix socket (POSIX): `curl --unix-socket <path> -X POST /rpc
  -H "Cheetahclaws-Api-Version: 0" -d '{"jsonrpc":"2.0","id":1,"method":"system.ping"}'`
  returns `{"jsonrpc":"2.0","id":1,"result":"pong"}`.
- TCP: same call without `Authorization: Bearer <token>` returns 401;
  with valid token returns 200; sustained bad-token attempts trip the
  spike's brute-force throttle (429).
- `curl … GET /events` keeps the stream open; heartbeats arrive at
  spike's 15 s cadence.
- `cheetahclaws daemon stop` → `system.shutdown` RPC → discovery file
  cleared and process exits 0.
- `cheetahclaws daemon rotate-token` regenerates the token; existing TCP
  clients receive 401 on next request until they re-read the file.
- pytest green on Linux, macOS, Windows (TCP-only on Windows; Unix
  socket tests skip on Windows).

## F-2 — SQLite schema + originator-tracked permission flow

**Scope.** Seven additive tables in `~/.cheetahclaws/sessions.db`; `permission.answer` RPC with originator validation.

**Tables (additive — `sessions` schema untouched).** `agent_runs`, `agent_iterations`, `jobs`, `monitor_subscriptions`, `monitor_reports`, `bridges`, `daemon_events`.

**Deliverables.**
- `daemon/schema.py` — table DDL + version table; idempotent `init_schema()`.
- `daemon/events.py` — replay backed by `daemon_events` (replaces F-1's in-memory ring).
- `daemon/permissions.py` — originator record on every `PermissionRequest`; `permission.answer` checks caller's auth identity against originator; non-originators get `403 not_originator`.
- `jobs.py` — one-shot migrate `~/.cheetahclaws/jobs.json` into the `jobs` table; JSON file kept readable for one release.

**Acceptance.**
- Schema migrations run idempotently across daemon restarts.
- `permission.answer` from the originator succeeds; from any other client returns `403 not_originator`.
- Originator disconnect + reconnect within timeout window: pending request replays via SSE scoped to that originator.
- `daemon_events` table caps at configured retention (default 1M rows / 7 days); oldest rows expired.
- Existing `jobs.json` users see a one-time import message; subsequent runs read from SQLite.

## F-3 — monitor in daemon

**Scope.** `monitor/scheduler.py` runs daemon-side; REPL skips its local thread when a daemon is detected.

**RPC methods.** `monitor.subscribe`, `monitor.unsubscribe`, `monitor.list`, `monitor.run`.

**Acceptance.**
- `cheetahclaws serve` running → `/monitor subscribe arxiv --schedule daily --telegram` persists to `monitor_subscriptions`; daemon scheduler fires on cadence even after REPL exit.
- Without daemon: today's behavior unchanged (in-process scheduler thread).
- Reports persist to `monitor_reports` and emit `monitor_report` SSE events.

## F-4 — agent_runner subprocess

**Scope.** Each `AgentRunner` is its own subprocess. From #68: *"subprocess-per-agent rather than threads — one leaking/crashing runner shouldn't take down the scheduler and bridges."*

**Deliverables.**
- `daemon/runner_supervisor.py` — spawn / monitor / restart agent-runner subprocesses.
- `daemon/runner_ipc.py` — line-delimited JSON over stdin/stdout between supervisor and runner.
- `agent_runner.py` — main entry point usable as `python -m agent_runner --pipe …`; iteration-log writes flow back to the daemon and land in `agent_iterations`.
- Permission requests from runners routed through supervisor → `daemon/permissions.py`.

**Acceptance.**
- Runner crash (`kill -9 <runner_pid>`) does not kill the daemon; supervisor logs the crash and emits `agent_runner_crash` event.
- Runner OOM does not affect monitor or bridges.
- Runner subprocess stops within 5 s of `agent.stop` RPC.
- Iteration-log entries match in-process behavior (status, duration, summary, token counts).

## F-5 — proactive watcher in daemon

**Scope.** `_proactive_watcher_loop` from `cheetahclaws.py` becomes a daemon-owned task.

**Acceptance.**
- `/proactive 5m` while daemon is running: setting persists, sentinel runs in daemon, survives REPL exit.
- Without daemon: unchanged.

## F-6 / F-7 / F-8 — bridges in daemon (one PR per bridge)

**Scope per PR.** The named bridge (`telegram`, then `slack`, then `wechat`) runs inside daemon; incoming messages enter via `POST /rpc {"method":"session.send", …}`; outgoing replies come from an SSE subscription to that session's events.

**Per-bridge deliverables.**
- Move `bridges/<kind>.py` poll loop into a daemon-owned worker.
- Drop `RuntimeContext.<kind>_send` / `<kind>_input_event` and friends; replace with the API-mediated path.
- `bridge.start` / `bridge.stop` / `bridge.list` RPC methods.
- Persist bridge state to `bridges` table.

**Acceptance per bridge.**
- Phone message → daemon `session.send` → REPL/Web/another bridge can subscribe to the same session and see events.
- Bridge survives REPL exit; user can keep texting.
- Permission requests originating from a bridge-driven turn route only to that bridge for answer (per RFC 0001 §2).

F-7 depends on F-6 (shared scaffolding); F-8 the same.

## F-9 — cost guardrail defaults under `serve`

**Scope.** When running under `cheetahclaws serve`, the four budget keys default to non-`None`:

```jsonc
{
  "session_token_budget": 200000,
  "session_cost_budget":   2.0,
  "daily_token_budget":   2000000,
  "daily_cost_budget":     20.0
}
```

REPL `--in-process` mode keeps `None` defaults (no surprise for existing users).

**Acceptance.**
- `cheetahclaws serve` started without overrides → `cheetahclaws daemon status` reports the four defaults.
- Agent runner exceeds per-session budget → status moves to `paused_budget`, `quota_warn` event emitted, runner pauses.
- `agent.resume` RPC with a new budget argument unpauses the runner.
- REPL without daemon: budgets still default to `None`.

## Cross-cutting conventions

- **Tests.** Every PR ships unit tests; F-1, F-3, F-4, F-6/7/8 also ship `tests/e2e_daemon_<area>.py`.
- **Docs.** Every PR updates the relevant section in `docs/architecture.md`. The "Daemon" header is created by F-1; subsequent PRs append.
- **Config keys.** New keys go in `cc_config.DEFAULTS`; documented in `docs/architecture.md`.
- **Backwards compatibility.** Users who never run `cheetahclaws serve` see no behavior change until the eventual default flip — that flip is out of scope here and tracked in [#68](https://github.com/SafeRL-Lab/cheetahclaws/issues/68) as the "Phase D" item.

## Updating this document

When a PR lands, change its **Status** in the index from `TODO` to `MERGED #<pr>`. If acceptance criteria evolve during a PR, update the per-PR section in the same PR — do not let this doc drift from the implementation.
