# Print Concierge for Bambuddy

Print Concierge is a safety-first workflow layer for agent-assisted 3D printing with Bambuddy and Bambu Lab printers.

It gives Claude, Codex, Hermes, OpenClaw, and other MCP-capable clients a narrow set of tools to search for models, import and verify printable files, prepare print plans, create request-bound queue actions, and report status. The MCP server does not expose raw Bambuddy queue or start-print authority to the agent.

## Overview

Print Concierge sits between an agent client and Bambuddy:

```text
Agent client -> Print Concierge MCP/CLI -> Bambuddy -> Printer
```

The agent can help with discovery and planning, but Print Concierge enforces the production boundary:

- only trusted Bambuddy archive/library files can be prepared for queueing;
- public model results must be imported and verified first;
- every print plan becomes a pending request before queueing;
- queueing is limited to a scoped `queue_print_request(request_id)` action for an existing request;
- queueing defaults to Bambuddy manual-start behavior.

This keeps the assistant useful without giving it direct, unchecked control over a physical machine.

## Features

- Bambuddy archive search
- Public model discovery through 3DSEARCH
- MakerWorld import through Bambuddy
- Printables and Thingiverse direct-file import
- Bambuddy source-file slicing with explicit slicer presets
- File hash and sliced-file verification before planning
- Curated MCP server for agent clients
- CLI for setup, smoke tests, and local use
- Scoped MCP/CLI queueing for existing print requests
- Local SQLite runtime state
- Installable skill packages for Claude, Codex, Hermes, and OpenClaw

## Requirements

- Python 3.11 or newer
- `uv`
- A running Bambuddy server reachable from this machine
- A Bambuddy API key

The Bambuddy API key should use the least privileges needed for:

- archive/library reads
- public import/library upload
- source-file slicing, if you want STL/source imports
- printer status
- locally approved queueing

## Installation

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
PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true
PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=true
```

Keep `.env` local. The file is ignored by git. Do not put Bambuddy credentials in skill files, agent memory, screenshots, logs, or chat history.

## CLI Smoke Test

Load your local environment:

```sh
set -a
source .env
set +a
```

Check connectivity:

```sh
uv run print-concierge printers
uv run print-concierge archives
uv run print-concierge status 1
```

Search for models:

```sh
uv run print-concierge search "headphone holder" --limit 5
```

Check public import readiness:

```sh
uv run print-concierge import-status
uv run print-concierge slicer-presets
```

Prepare a plan from a trusted Bambuddy archive item:

```sh
uv run print-concierge prepare \
  --archive-id 8 \
  --printer-id 1 \
  --material PLA \
  --profile 0.2mm
```

`prepare` does not queue a print. It only creates a plan.

Create a pending request from the plan JSON, inspect it, then queue that specific request:

```sh
PLAN_JSON="$(uv run print-concierge prepare --archive-id 8 --printer-id 1 --material PLA --profile 0.2mm)"
REQUEST_JSON="$(uv run print-concierge request-print --plan-json "$PLAN_JSON")"
REQUEST_ID="$(python -c 'import json,sys; print(json.load(sys.stdin)["request_id"])' <<< "$REQUEST_JSON")"

uv run print-concierge approvals show "$REQUEST_ID"
uv run print-concierge queue-request "$REQUEST_ID"
```

The older local admin shortcut still exists for manual workflows:

```sh
uv run print-concierge approvals approve "$REQUEST_ID" --queue
```

## MCP Server

Start the MCP server from the repository:

```sh
set -a
source .env
set +a

uv run print-concierge-mcp
```

Example MCP client configuration:

```json
{
  "mcpServers": {
    "print-concierge": {
      "command": "uv",
      "args": ["run", "print-concierge-mcp"],
      "env": {
        "BAMBUDDY_BASE_URL": "http://YOUR-BAMBUDDY-HOST:8000",
        "BAMBUDDY_API_KEY": "${BAMBUDDY_API_KEY}"
      }
    }
  }
}
```

For host-specific skill packages, see [`docs/installable-skills.md`](docs/installable-skills.md).

## Agent Workflow

A typical agent flow should use the tools in this order:

1. `search_archive_or_models(query, limit)`
2. User selects a candidate.
3. If the candidate is public, call `import_public_candidate(...)` first.
4. `list_printers()` and `get_printer_status(printer_id)`
5. `prepare_print_plan(...)`
6. `create_print_request(plan)`
7. The user reviews the exact plan/request in the client.
8. After explicit user confirmation, call `queue_print_request(request_id)`.
9. Poll `get_print_request_status(request_id)`, then `get_job_status(job_id)` after the request reports a queued job.

Do not load broad Bambuddy MCP tools into the same production agent profile. The safety value of Print Concierge comes from keeping all agent actions inside the curated workflow.

## Public Model Imports

Public search results are discovery candidates until they resolve to a verified Bambuddy library item.

Supported import paths:

- MakerWorld: uses Bambuddy's MakerWorld import integration.
- Printables and Thingiverse: require a trusted direct file URL from the provider domain.
- Already-sliced files: verified directly as `gcode` or `gcode.3mf`.
- STL/source files: uploaded to Bambuddy, sliced with explicit preset refs from `list_slicer_presets`, then verified as sliced output before planning.

Page-only search results remain discovery-only until a trusted file URL is available.

## Safety Model

Print Concierge treats agent clients as untrusted planners. Backend code owns the policy boundary.

The queueing path requires:

- a trusted Bambuddy archive or imported library file;
- a file hash;
- printer, material, and profile details;
- a deterministic plan hash;
- a user/session binding;
- a pending print request;
- a scoped request queue action, `queue_print_request(request_id)`, after explicit user confirmation.

The agent never receives raw Bambuddy queue, start, pause, cancel, or broad printer-control tools through Print Concierge. `queue_print_request` can only submit a stored request whose immutable plan still matches the queued payload. Bambuddy manual-start remains the default, so queueing and physical print start are separate steps. Emergency pause and cancel controls remain in Bambuddy for this version.

## Configuration Reference

Common environment variables:

```sh
BAMBUDDY_BASE_URL=http://YOUR-BAMBUDDY-HOST:8000
BAMBUDDY_API_KEY=replace-with-a-least-privilege-token
PRINT_CONCIERGE_STATE_DB=~/.print-concierge/state.sqlite3
PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true
PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=true
PRINT_CONCIERGE_PUBLIC_IMPORT_MAX_BYTES=157286400
PRINT_CONCIERGE_PUBLIC_IMPORT_SLICE_WAIT_SECONDS=300
```

Optional external search configuration:

```sh
PRINT_CONCIERGE_MAKERWORLD_SEARCH_URL=https://search.example/makerworld?q={query}
PRINT_CONCIERGE_PRINTABLES_SEARCH_URL=https://search.example/printables?q={query}
PRINT_CONCIERGE_EXTERNAL_SEARCH_PROVIDERS=[{"name":"thangs","url":"https://search.example/thangs?q={query}","result_path":"items"}]
```

More detailed setup instructions are in [`docs/setup.md`](docs/setup.md).

## Project Structure

- [`src/print_concierge`](src/print_concierge) - application code
- [`tests`](tests) - unit and workflow tests
- [`skills/print-concierge`](skills/print-concierge) - canonical skill package
- [`packages`](packages) - host-specific shims
- [`docs`](docs) - setup, security, and release notes

## Development

Install development dependencies:

```sh
uv sync --extra dev --extra mcp
```

Run checks:

```sh
uv run pytest
uv run python -m compileall -q src
uv build
uvx bandit -r src
uvx pip-audit .
git diff --check
```

## Security

See [`SECURITY.md`](SECURITY.md) and [`docs/security-review.md`](docs/security-review.md).

If you find a security issue, do not include printer credentials, API keys, serial numbers, access codes, camera URLs, or private network details in public reports.
