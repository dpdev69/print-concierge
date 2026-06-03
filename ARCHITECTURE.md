# Architecture

## Design goal

Build a modular, secure print concierge that can be used from Hermes/Telegram first, while remaining portable to Claude Desktop, Claude Code, Cursor, Codex-like agents, CLI scripts, and future web UIs.

## High-level system

```text
Client surfaces
  - Hermes Telegram
  - Hermes CLI
  - Discord/Slack/etc.
  - Claude Desktop / Claude Code via MCP
  - CLI
  - optional Web UI
        |
        v
Print Concierge Core
  - intent handling
  - model search
  - ranking
  - print-plan creation
  - confirmation workflow
        |
        v
Safety Gateway / Policy Engine
  - authz
  - confirmation tokens
  - risk checks
  - audit log
  - redaction
  - rate limits
        |
        v
Bambuddy Adapter
  - direct REST API and/or bambuddy-mcp bridge
  - printer status
  - archive/import/queue/status
  - camera/snapshot
        |
        v
Bambuddy
        |
        v
Bambu Lab printer
```

## Key architecture principle

The agent client never gets direct unconstrained printer control.

All clients must go through the same safety gateway. This prevents a safer Hermes flow from being bypassed by Claude/Codex/CLI using a lower-level endpoint.

## Components

### 1. Client surfaces

Potential clients:

- Hermes Telegram bot: flagship demo and initial UX.
- Hermes CLI: local dev/debugging.
- MCP clients: Claude Desktop, Claude Code, Cursor, other agent tools.
- CLI: deterministic testing and automation.
- HTTP API: optional; useful for web UI or Home Assistant later.

### 2. Print Concierge Core

Responsibilities:

- parse user intent;
- call model search providers;
- normalize search results;
- rank by printability;
- format shortlists;
- create print plans;
- request confirmation;
- coordinate monitor notifications.

Should not:

- store secrets in chat/memory;
- start prints directly;
- bypass policy;
- trust model-source text as instructions.

### 3. Model Search Providers

Potential providers:

- Printables;
- MakerWorld if API/access is reliable and ToS-safe;
- Thingiverse;
- Thangs;
- generic web search fallback;
- local Bambuddy archive;
- local filesystem archive.

Normalized result schema:

```json
{
  "id": "provider:model-id",
  "provider": "printables",
  "title": "Cable Clip v3",
  "url": "https://...",
  "thumbnail_url": "https://...",
  "license": "CC-BY",
  "description_snippet": "...",
  "has_bambu_profile": true,
  "file_types": ["3mf", "stl"],
  "rating": 4.8,
  "download_count": 1200,
  "warnings": []
}
```

### 4. Ranking / printability scoring

Early scoring signals:

- trusted source;
- Bambu-ready 3MF/profile available;
- recent successful makes/comments;
- high rating/download count;
- compatible printer/build volume;
- known material/profile;
- license clarity;
- low-risk geometry;
- avoids raw G-code.

### 5. Safety Gateway / Policy Engine

Responsibilities:

- validate user permissions;
- generate and verify confirmation tokens;
- enforce risk policies;
- redact secrets;
- write audit logs;
- rate-limit sensitive actions;
- block direct print starts without confirmation.

Example policy checks:

- `require_confirmation_for_all_prints`
- `block_raw_gcode_by_default`
- `require_camera_snapshot_for_remote_prints`
- `block_unknown_high_temp_materials`
- `extra_confirm_if_duration_over_hours`
- `allowed_users_by_printer`
- `allowed_chat_ids`

### 6. Bambuddy Adapter

Two possible modes:

#### Direct REST mode

Use Bambuddy REST API directly.

Pros:

- explicit safe wrapper;
- easier to restrict endpoints;
- less context/tool noise.

Cons:

- requires maintaining API call mappings.

#### MCP bridge mode

Use existing `bambuddy-mcp` server.

Pros:

- broad API coverage;
- dynamically generated from OpenAPI;
- already exists.

Cons:

- 430+ endpoints are too broad for normal operation;
- must wrap/restrict to avoid unsafe direct tool access.

Recommended approach:

- For v1, build a restricted Bambuddy adapter with explicit safe methods.
- Optionally call `bambuddy-mcp` under the hood for implementation convenience.
- Never expose broad direct-mode API to the user-facing agent by default.

## Proposed package layout

Simple MVP layout:

```text
bambu-print-concierge/
  pyproject.toml
  README.md
  SECURITY.md
  src/print_concierge/
    __init__.py
    config.py
    models.py
    audit.py
    policy.py
    confirmations.py
    search/
      __init__.py
      base.py
      printables.py
      makerworld.py
      web.py
    bambuddy/
      __init__.py
      client.py
      mcp_bridge.py
    interfaces/
      cli.py
      mcp_server.py
      hermes_tool.py
  tests/
    test_confirmations.py
    test_policy.py
    test_prompt_injection.py
    test_file_validation.py
    test_search_normalization.py
  docs/
    hermes-setup.md
    claude-setup.md
    bambuddy-setup.md
```

## Hermes integration

Two options:

### Hermes MCP integration

Expose Print Concierge as an MCP server, then add to Hermes config:

```yaml
mcp_servers:
  print_concierge:
    command: "uvx"
    args: ["print-concierge-mcp"]
    env:
      BAMBUDDY_BASE_URL: "http://localhost:8000"
      BAMBUDDY_API_KEY: "..."
```

Hermes will register MCP tools as `mcp_print_concierge_*`.

### Hermes native tool/plugin

Implement a Hermes toolset/plugin for tighter Telegram UX and richer result formatting.

Recommended path:

1. Start with CLI and core library.
2. Add MCP server for portability.
3. Add Hermes-specific skill/tooling for the best chat UX.

## Claude Code / Codex integration

Claude Code and Claude Desktop can use the MCP version if MCP support is available.

Codex-like agents can use:

- MCP if supported;
- CLI wrapper;
- HTTP API;
- direct Python package calls in development.

## Data storage

MVP can use SQLite for:

- pending print plans;
- confirmation tokens;
- audit log;
- cached search results;
- user/printer policy config.

Important:

- store token hashes, not plaintext tokens;
- do not store secrets in SQLite;
- keep API keys in environment/config.

## Open questions

- What additional Bambuddy endpoints are needed for non-MakerWorld import adapters?
- Is a trusted operator direct-start mode ever worth adding, or should V1 stay queue/manual-start only?
- Which model sources have stable, acceptable APIs?
- Can Bambuddy provide build plate empty detection/camera snapshots reliably?
- How much slicing should be delegated to Bambuddy/Bambu Studio vs local tools?
- Should raw G-code ever be allowed in v1? Default answer: no.
