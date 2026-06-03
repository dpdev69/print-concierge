# Setup Guide

This guide gets Print Concierge running as a local CLI and MCP server for Claude, Codex, Hermes, OpenClaw, or another MCP client.

## Requirements

- Python 3.11+
- `uv`
- A running Bambuddy instance reachable from this machine
- A least-privilege Bambuddy API key

## Install

```sh
git clone https://github.com/your-org/print-concierge.git
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

`PRINT_CONCIERGE_STATE_DB` stores print plans, confirmation challenges, and queue receipts. It stores confirmation token hashes, not plaintext tokens.

The runtime creates the state directory with `0700` permissions and the SQLite database with `0600` permissions.

`PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true` keeps queued prints in a manual-start posture. This preserves the product boundary: the agent can discover public models, but physical queueing is limited to Bambuddy archive/imported trusted items after backend confirmation.

Public web search is on by default, so the agent can discover candidates from indexed public model sites such as MakerWorld, Printables, and Thingiverse through 3DSEARCH. Queueing is intentionally narrower: a print must resolve to a Bambuddy archive/imported trusted item and pass confirmation before it can be sent to Bambuddy. For V1.1, `import_public_candidate` can import/verify supported MakerWorld candidates through Bambuddy. Set `PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=false` only when you intentionally want the agent to search Bambuddy/local archives and no public web sources.

MakerWorld import depends on Bambuddy's MakerWorld integration and Bambu Cloud download credentials. If `get_public_import_status` or `print-concierge import-status` reports `can_download=false`, public MakerWorld results will remain discovery-only until Bambuddy is configured for downloads.

## CLI Smoke Test

```sh
set -a
source .env
set +a

uv run print-concierge printers
uv run print-concierge archives
uv run print-concierge search "gridfinity screwdriver rack" --limit 3
uv run print-concierge import-status
uv run print-concierge import-public --candidate-json '<selected MakerWorld result JSON>'
uv run print-concierge status 1
uv run print-concierge prepare --archive-id 8 --printer-id 1 --material PLA --profile 0.2mm
```

`prepare` only creates a confirmation-required plan. It does not queue a print.

## MCP Server

```sh
set -a
source .env
set +a
uv run print-concierge-mcp
```

Available V1.1 tools:

- `search_archive_or_models`
- `get_public_import_status`
- `import_public_candidate`
- `list_printers`
- `get_printer_status`
- `prepare_print_plan`
- `show_print_plan`
- `request_confirmation`
- `queue_confirmed_print`
- `get_job_status`

Safe tool order:

1. `search_archive_or_models(query, limit)`
2. Select a Bambuddy archive/imported trusted item. Public-index results must be imported/verified before preparation.
3. Call `get_public_import_status()` before MakerWorld import.
4. For supported MakerWorld results, call `import_public_candidate(selected, profile_id, folder_id)` and use the returned `bambuddy_library` result.
5. `list_printers()` and `get_printer_status(printer_id)`
6. `prepare_print_plan(...)`
7. `request_confirmation(plan)`
8. Human reviews the exact plan and token
9. `queue_confirmed_print(confirmation_token)`
10. `get_job_status(job_id)`

Security rule: do not load broad Bambuddy MCP tools in the same production agent profile. The point of Print Concierge is that all clients go through the curated confirmation-gated workflow.

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
