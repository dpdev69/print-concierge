# Installable Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the remaining V1 pieces for finding prints and installing Print Concierge as a safe skill/MCP workflow across Claude, Codex, Hermes, and OpenClaw.

**Architecture:** Keep printer control in the Python package and MCP server. Agent skills are thin instruction bundles that teach clients to call the curated MCP/CLI workflow and never raw Bambuddy control. External model discovery is provider-based and normalized into the existing `ModelSearchResult` contract.

**Tech Stack:** Python 3.11, httpx, pytest, MCP optional dependency, Markdown/YAML/JSON install artifacts.

---

### Task 1: Search command and provider orchestration

**Files:**
- Create: `src/print_concierge/search/external.py`
- Create: `src/print_concierge/search/composite.py`
- Modify: `src/print_concierge/search/__init__.py`
- Modify: `src/print_concierge/interfaces/cli.py`
- Test: `tests/test_search_providers.py`
- Test: `tests/test_cli.py`

- [ ] Write failing tests for an external HTTP JSON provider, composite search dedupe/limits, and `print-concierge search`.
- [ ] Implement `HttpJsonSearchProvider`, `ConfiguredExternalSearchProvider`, and named `MakerWorldSearchProvider` / `PrintablesSearchProvider` adapters using configurable URL templates.
- [ ] Implement `CompositeSearchProvider` to merge providers, keep inert provider text, dedupe by `(provider, result_id)` and cap results.
- [ ] Wire CLI `search QUERY [--limit N]` to local archives plus configured external providers.
- [ ] Run `uv run pytest tests/test_search_providers.py tests/test_cli.py`.

### Task 2: MCP console script and default runtime clients

**Files:**
- Modify: `src/print_concierge/interfaces/mcp_server.py`
- Modify: `pyproject.toml`
- Test: `tests/test_mcp_server.py`
- Test: `tests/test_scaffold.py`

- [ ] Write failing tests that `print-concierge-mcp` exists, tool wrappers do not expose injected `client` parameters, and default search uses live-configured providers without requiring user-supplied internal objects.
- [ ] Add `print-concierge-mcp = "print_concierge.interfaces.mcp_server:main"`.
- [ ] Add MCP runtime bootstrap helpers for Bambuddy client, local archive provider, configured external providers, and confirmation-aware queue gateway placeholders.
- [ ] Keep direct Python helper functions injectable for tests, but register public MCP wrapper functions without private injection parameters.
- [ ] Run `uv run pytest tests/test_mcp_server.py tests/test_scaffold.py`.

### Task 3: Installable skill packages

**Files:**
- Create: `skills/print-concierge/SKILL.md`
- Create: `skills/print-concierge/references/workflow.md`
- Create: `skills/print-concierge/references/safety.md`
- Create: `skills/print-concierge/agents/openai.yaml`
- Create: `packages/claude/SKILL.md`
- Create: `packages/claude/claude_desktop_config.example.json`
- Create: `packages/codex/print-concierge/SKILL.md`
- Create: `packages/hermes/skill.yaml`
- Create: `packages/hermes/handler.js`
- Create: `packages/openclaw/print-concierge/SKILL.md`
- Create: `docs/installable-skills.md`
- Test: `tests/test_skill_packages.py`

- [ ] Write failing tests that required skill/package files exist and contain core safety instructions, MCP command examples, and no secrets.
- [ ] Create the canonical concise skill under `skills/print-concierge/` with frontmatter and progressive-disclosure references.
- [ ] Add host-specific packaging shims for Claude, Codex, Hermes, and OpenClaw.
- [ ] Document local install and registry-ready paths in `docs/installable-skills.md`.
- [ ] Run `uv run pytest tests/test_skill_packages.py`.

### Task 4: Integration verification and release hygiene

**Files:**
- Modify: `README.md`
- Optional Modify: `docs/claude-setup.md`, `docs/hermes-setup.md`

- [ ] Update README smoke tests to include `search` and MCP server startup.
- [ ] Run full test suite: `uv run pytest`.
- [ ] Run build: `uv build`.
- [ ] Run secret scan excluding ignored `.env`.
- [ ] Commit all changes locally with a clear message.
