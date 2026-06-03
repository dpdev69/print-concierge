# Setup Guide

This guide gets Print Concierge running as a local CLI and MCP server for Claude, Codex, Hermes, OpenClaw, or another MCP client.

## Requirements

- Python 3.11+
- `uv`
- A running Bambuddy instance reachable from this machine
- A least-privilege Bambuddy API key

## Install

```sh
git clone https://github.com/dpdev69/print-concierge.git
cd print-concierge
uv sync --extra dev --extra mcp
cp .env.example .env
```

Edit `.env`:

```sh
BAMBUDDY_BASE_URL=http://YOUR-BAMBUDDY-HOST:8000
BAMBUDDY_API_KEY=replace-with-a-least-privilege-token
PRINT_CONCIERGE_STATE_DB=~/.print-concierge/state.sqlite3
PRINT_CONCIERGE_AUDIT_LOG=~/.print-concierge/audit.jsonl
PRINT_CONCIERGE_BAMBUDDY_BACKEND=real
PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true
PRINT_CONCIERGE_CAPABILITY_MODE=queue_enabled
PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=true
PRINT_CONCIERGE_PUBLIC_IMPORT_MAX_BYTES=157286400
PRINT_CONCIERGE_PUBLIC_IMPORT_SLICE_WAIT_SECONDS=300
```

`PRINT_CONCIERGE_STATE_DB` stores print plans, pending approval requests, and queue receipts. It does not store or issue model-visible authorization tokens.

The runtime creates the state directory with `0700` permissions and the SQLite database with `0600` permissions.

Audit logging is on by default. If `PRINT_CONCIERGE_AUDIT_LOG` is unset, Print Concierge writes append-only JSONL receipts to `~/.print-concierge/audit.jsonl` or next to `PRINT_CONCIERGE_STATE_DB`. Set `PRINT_CONCIERGE_AUDIT_LOG=off` to disable file logging.

`PRINT_CONCIERGE_BAMBUDDY_BACKEND=sandbox` uses an in-memory demo client with fixture printers and model archives. It never calls the network or touches hardware. Use `real` or leave it unset for Bambuddy.

`PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true` keeps queued prints in a manual-start posture. This preserves the product boundary: the agent can discover public models and queue a specific prepared request, but physical start remains separate from chat.

`PRINT_CONCIERGE_CAPABILITY_MODE` controls queue authority through policy. Use `search_only` for discovery host profiles, `prepare_only` for search/import/plan demos that should never queue, `queue_enabled` for supervised local use, and reserve `admin` for local operator workflows. Host tool allowlists should match the selected profile. Queueing remains policy-gated, audited, capability-mode controlled, and manual-start by default.

Public web search is on by default, so the agent can discover candidates from indexed public model sites such as MakerWorld, Printables, and Thingiverse through 3DSEARCH. Queueing is intentionally narrower: a print must resolve to a Bambuddy archive/imported trusted item, become an immutable Print Concierge request, and be submitted through `queue_print_request(request_id)` before it can be sent to Bambuddy. `import_public_candidate` can import/verify supported MakerWorld candidates through Bambuddy, and Printables/Thingiverse candidates when the selected result includes a trusted direct file URL. Source files such as STL require explicit `slice_options` chosen from Bambuddy slicer presets before they can become queueable. Set `PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=false` only when you intentionally want the agent to search Bambuddy/local archives and no public web sources.

MakerWorld import depends on Bambuddy's MakerWorld integration and Bambu Cloud download credentials. If `get_public_import_status` or `print-concierge import-status` reports `can_download=false`, public MakerWorld results will remain discovery-only until Bambuddy is configured for downloads.
Printables/Thingiverse imports do not use Bambu Cloud, but they require a direct HTTPS file URL from the provider domain. Already-sliced results are verified as `gcode`/`gcode.3mf`; source files are uploaded, sliced through Bambuddy with explicit preset refs, polled, and then verified as sliced output. Page-only results from public search remain discovery-only until a search/import gateway supplies the trusted file URL.

## CLI Smoke Test

```sh
set -a
source .env
set +a

uv run print-concierge printers
uv run print-concierge archives
uv run print-concierge search "gridfinity screwdriver rack" --limit 3
uv run print-concierge import-status
uv run print-concierge slicer-presets
uv run print-concierge import-public --candidate-json '<selected supported public result JSON>'
uv run print-concierge status 1
uv run print-concierge prepare --archive-id 8 --printer-id 1 --material PLA --profile 0.2mm
uv run print-concierge request-print --plan-json '<prepared plan JSON>'
uv run print-concierge approvals list
uv run print-concierge approvals show '<request_id>'
uv run print-concierge queue-request '<request_id>'
uv run print-concierge approvals approve '<request_id>' --queue
```

`prepare` only creates a plan. `request-print` creates a pending request. `queue-request` uses the same scoped queue gateway exposed to MCP as `queue_print_request(request_id)`. `approvals approve --queue` remains as a local admin shortcut.

## MCP Server

```sh
set -a
source .env
set +a
uv run print-concierge-mcp
```

Available V1.3 tools:

- `search_archive_or_models`
- `get_public_import_status`
- `import_public_candidate`
- `list_slicer_presets`
- `list_printers`
- `get_printer_status`
- `prepare_print_plan`
- `show_print_plan`
- `create_print_request`
- `get_print_request_status`
- `queue_print_request`
- `get_job_status`

Safe tool order:

1. `search_archive_or_models(query, limit)`
2. Select a Bambuddy archive/imported trusted item. Public-index results must be imported/verified before preparation.
3. Call `get_public_import_status()` before MakerWorld import.
4. For supported public results, call `import_public_candidate(selected, profile_id, folder_id)` and use the returned `bambuddy_library` result. Printables/Thingiverse results must include a trusted direct file URL. For source files, call `list_slicer_presets()` and pass explicit preset refs in `slice_options`.
5. `list_printers()` and `get_printer_status(printer_id)`
6. `prepare_print_plan(...)`
7. `create_print_request(plan)`
8. User reviews the exact request in the client
9. After explicit user confirmation, call `queue_print_request(request_id)`
10. Poll `get_print_request_status(request_id)`, then `get_job_status(job_id)` after the request reports a queued job

Security rule: do not load broad Bambuddy MCP tools in the same production agent profile. The point of Print Concierge is that all clients go through the curated planning workflow and only receive scoped request queueing, not raw printer controls.

Host rule: `queue_print_request(request_id)` is the sensitive scoped queue tool. MCP hosts should mark it sensitive and require per-call confirmation. Print Concierge exposes one sensitive scoped tool and no raw Bambuddy queue/start/pause/cancel tools, but a host that auto-approves that tool can still submit queued work.

## Sandbox/Demo Mode

For sandbox/demo mode, keep `PRINT_CONCIERGE_CAPABILITY_MODE=search_only` or `prepare_only`, use a non-production Bambuddy instance when possible, keep `PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true`, and do not load broad Bambuddy MCP tools in the same profile. This mode is useful for public demos, screenshots, and docs walkthroughs because the agent can search, import, prepare, and show requests without gaining queue authority.

For a fully local no-hardware demo, set `PRINT_CONCIERGE_BAMBUDDY_BACKEND=sandbox`. The sandbox backend ships with a sample A1 Mini printer and a headphone/cable holder archive item.

## Claude Desktop Example

Use `packages/claude/claude_desktop_config.example.json` as the starting point:

```json
{
  "mcpServers": {
    "print-concierge": {
      "command": "uv",
      "args": ["run", "print-concierge-mcp"],
      "env": {
        "BAMBUDDY_BASE_URL": "http://localhost:8000",
        "BAMBUDDY_API_KEY": "${BAMBUDDY_API_KEY}"
      }
    }
  }
}
```

## Skill Packages

- Canonical skill: `skills/print-concierge/`
- Claude shim: `packages/claude/`
- Codex shim: `packages/codex/print-concierge/`
- Hermes shim: `packages/hermes/`
- OpenClaw shim: `packages/openclaw/print-concierge/`

See `docs/installable-skills.md` for packaging details.

## Release Checklist

```sh
uv run pytest
uv run python -m compileall -q src
uv build
```

Before publishing, rotate any test Bambuddy API key that was ever pasted into chat and confirm `.env` is ignored.
