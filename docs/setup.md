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
PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true
PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=true
PRINT_CONCIERGE_PUBLIC_IMPORT_MAX_BYTES=157286400
PRINT_CONCIERGE_PUBLIC_IMPORT_SLICE_WAIT_SECONDS=300
```

`PRINT_CONCIERGE_STATE_DB` stores print plans, confirmation challenges, and queue receipts. It stores confirmation token hashes, not plaintext tokens.

The runtime creates the state directory with `0700` permissions and the SQLite database with `0600` permissions.

`PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true` keeps queued prints in a manual-start posture. This preserves the product boundary: the agent can discover public models, but physical queueing is limited to Bambuddy archive/imported trusted items after backend confirmation.

Public web search is on by default, so the agent can discover candidates from indexed public model sites such as MakerWorld, Printables, and Thingiverse through 3DSEARCH. Queueing is intentionally narrower: a print must resolve to a Bambuddy archive/imported trusted item and pass confirmation before it can be sent to Bambuddy. `import_public_candidate` can import/verify supported MakerWorld candidates through Bambuddy, and Printables/Thingiverse candidates when the selected result includes a trusted direct file URL. Source files such as STL require explicit `slice_options` chosen from Bambuddy slicer presets before they can become queueable. Set `PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=false` only when you intentionally want the agent to search Bambuddy/local archives and no public web sources.

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
- `list_slicer_presets`
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
4. For supported public results, call `import_public_candidate(selected, profile_id, folder_id)` and use the returned `bambuddy_library` result. Printables/Thingiverse results must include a trusted direct file URL. For source files, call `list_slicer_presets()` and pass explicit preset refs in `slice_options`.
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
