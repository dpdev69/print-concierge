# Print Concierge for Bambuddy

A secure, open-source, human-in-the-loop 3D printing assistant for Bambu Lab printers and Bambuddy.

**Core idea:** ask for the object you need, review printable model options in chat, approve the exact print job, and let Bambuddy handle the printer.

**Non-negotiable rule:** no AI-selected or AI-prepared print starts without explicit user confirmation enforced by backend code.

---

## Product positioning

Print Concierge is not "AI controls your 3D printer." It is a safety-first print workflow:

1. User asks for an object in Telegram/Discord/Hermes/Claude/etc.
2. The agent searches Bambuddy archives and enabled public indexes such as MakerWorld/Printables via 3DSEARCH.
3. The agent returns a small shortlist with provenance and printability notes.
4. The user selects one.
5. If the selected model is a supported public result, the agent calls `import_public_candidate` to import/verify it into Bambuddy. MakerWorld uses Bambuddy's importer; Printables/Thingiverse imports require a trusted direct file URL, and source geometry requires explicit slicer presets.
6. The backend prepares a print plan for the Bambuddy archive/imported trusted item.
7. The backend displays the exact job details and generates a short-lived confirmation token.
8. The user confirms.
9. Only then does the backend queue the trusted archive item through Bambuddy, manual-start by default.
10. The assistant monitors status. Emergency pause/cancel stays in Bambuddy for V1.

## Priority order

1. Security
2. Trust
3. Reliability
4. Convenience
5. AI magic

## Target users

- Bambu Lab owners who want less browsing/slicing friction.
- Bambuddy users who want a chat-native workflow.
- Self-hosted/homelab users who prefer local-first automation.
- Makerspaces/schools that need approval-based shared printer workflows.
- Small print farms that want chat-based job intake and status.

## Primary tagline candidates

- Find it. Pick it. Print it. From chat.
- A safe AI print concierge for Bambu and Bambuddy.
- Secure, human-approved 3D printing from chat.
- Ask for the object. Approve the job. Let Bambuddy print.

## Why open source

This project controls a physical device, so inspectability is part of the product.

Open source helps with:

- trust in safety logic;
- community review of risky flows;
- self-hosted credibility;
- easier adoption by Bambuddy/Hermes/MCP users;
- plugin contributions for new model repositories;
- avoiding fear around credentials, serials, cameras, and physical control.

## Existing relevant ecosystem

- **Bambuddy:** self-hosted Bambu Lab print archive/control system.
- **bambuddy-mcp:** existing MCP server exposing Bambuddy's REST API dynamically from `/openapi.json`.
- **Hermes Agent:** good front-end/orchestrator because it already supports Telegram, tools, skills, MCP, memory, cron/background jobs, browser/web search, and confirmations.
- **Claude Desktop / Claude Code / Cursor / Codex-like agents:** possible clients if the project exposes an MCP server and/or HTTP API.

## Important distinction

The existing `bambuddy-mcp` server is a control/API layer. Print Concierge is the intent and safety workflow layer:

- search and rank models;
- present choices;
- prepare print plans;
- enforce human confirmation;
- call Bambuddy only through safe high-level actions;
- monitor and notify.

## Repository docs

- `ROADMAP.md` — phased implementation plan.
- `SECURITY.md` — threat model, safety principles, and required controls.
- `ARCHITECTURE.md` — proposed system layers and components.
- `MARKETING.md` — launch audiences, messaging, and demo strategy.
- `IMPLEMENTATION_PLAN.md` — bite-sized build plan for the initial MVP.
- `docs/setup.md` — local CLI/MCP setup instructions.
- `docs/installable-skills.md` — Claude, Codex, Hermes, and OpenClaw skill packaging.
- `docs/security-review.md` — current security review and residual risks.
- `docs/github-launch.md` — promotional copy for publishing the open-source project.

## Local smoke test

Create a local `.env` from `.env.example`, then load it before running the CLI:

```sh
set -a
source .env
set +a
uv run print-concierge printers
uv run print-concierge archives
uv run print-concierge search "cable holder"
uv run print-concierge status 1
uv run print-concierge import-public --candidate-json '<selected supported public result JSON>'
uv run print-concierge prepare --archive-id 8 --printer-id 1 --material PLA --profile 0.2mm
uv run print-concierge-mcp
```

These commands are read-only except `prepare`, which only builds a confirmation-required plan for a Bambuddy archive/imported trusted item. Queueing a print requires `request_confirmation` followed by `queue_confirmed_print` through the confirmation-aware gateway.

By default, `search` combines Bambuddy archives with public model-site search through 3DSEARCH, which indexes MakerWorld, Printables, Thingiverse, and other 3D model platforms. Public search results are discovery candidates until imported/verified. `import_public_candidate` supports MakerWorld through Bambuddy, plus Printables/Thingiverse candidates that include a trusted direct file URL. Already-sliced files (`.gcode`, `.gcode.3mf`, or a Bambuddy-verified sliced `.3mf`) can be verified directly; STL/source-only files require explicit Bambuddy slicer presets from `list_slicer_presets` via `slice_options`, then the sliced output is verified before it becomes queueable. Disable public web search only when you want archive-only mode:

```sh
export PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED=false
```

External JSON search backends can also be added when you want your own indexed/ranked search service:

```sh
export PRINT_CONCIERGE_MAKERWORLD_SEARCH_URL='https://search.example/makerworld?q={query}'
export PRINT_CONCIERGE_PRINTABLES_SEARCH_URL='https://search.example/printables?q={query}'
export PRINT_CONCIERGE_EXTERNAL_SEARCH_PROVIDERS='[{"name":"thangs","url":"https://search.example/thangs?q={query}","result_path":"items"}]'
```

See `docs/installable-skills.md` for Claude, Codex, Hermes, and OpenClaw skill packaging.
