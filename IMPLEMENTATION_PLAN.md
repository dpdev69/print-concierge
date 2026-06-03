# Print Concierge MVP Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task when coding begins.

**Goal:** Build the first safe MVP of Print Concierge: model search + Bambuddy read-only integration + backend-enforced print confirmation design, with no unguarded physical printer control.

**Architecture:** Start with a Python package containing core models, search normalization, policy checks, confirmation-token logic, and a Bambuddy adapter. Add CLI first for deterministic testing, then MCP/Hermes integration. Printing actions remain disabled until confirmation-token flow and tests are complete.

**Tech Stack:** Python 3.11+, `uv`, SQLite, pytest, optional FastMCP/MCP SDK, HTTP client (`httpx`), Pydantic or dataclasses.

---

## Task 1: Create project scaffold

**Objective:** Create a minimal Python package layout for the project.

**Files:**

- Create: `pyproject.toml`
- Create: `src/print_concierge/__init__.py`
- Create: `src/print_concierge/models.py`
- Create: `tests/`

**Steps:**

1. Create package skeleton.
2. Add dependencies: pytest, httpx, pydantic or use dataclasses for v0.
3. Run `python -m pytest` and verify test discovery works.

**Acceptance criteria:**

- `python -m pytest` runs without import errors.
- Package imports as `print_concierge`.

---

## Task 2: Define core data models

**Objective:** Define stable schemas for search results, printers, print plans, and risk flags.

**Files:**

- Modify: `src/print_concierge/models.py`
- Create: `tests/test_models.py`

**Models:**

- `ModelSearchResult`
- `PrinterInfo`
- `PrintPlan`
- `RiskFlag`
- `ConfirmationChallenge`

**Acceptance criteria:**

- Models serialize to/from JSON-compatible dictionaries.
- Required fields are validated.
- Tests cover missing required fields and defaults.

---

## Task 3: Implement audit log skeleton

**Objective:** Create an append-only audit logger that redacts secrets.

**Files:**

- Create: `src/print_concierge/audit.py`
- Create: `tests/test_audit.py`

**Features:**

- Append audit events to SQLite or JSONL for MVP.
- Redact API keys, bearer tokens, access codes, serial numbers.
- Store sensitive confirmation tokens as hashes/partials only.

**Acceptance criteria:**

- Audit events are written.
- Secret-like values are redacted in tests.
- No plaintext token appears in audit output.

---

## Task 4: Implement confirmation-token service

**Objective:** Backend-enforced confirmation tokens for pending print jobs.

**Files:**

- Create: `src/print_concierge/confirmations.py`
- Create: `tests/test_confirmations.py`

**Features:**

- Generate token for a specific print plan.
- Bind token to user ID, chat ID, job ID, file hash, printer ID, material/profile.
- Token expires.
- Token is single-use.
- Plan mutation invalidates token.

**Acceptance criteria:**

- Valid token verifies once.
- Reuse fails.
- Expired token fails.
- Token for one job cannot start another.
- Changed plan hash fails verification.

---

## Task 5: Implement policy engine

**Objective:** Enforce safe defaults before print execution.

**Files:**

- Create: `src/print_concierge/policy.py`
- Create: `tests/test_policy.py`

**Policies:**

- require confirmation for all print starts;
- block raw G-code by default;
- flag high-temp materials;
- flag long-duration prints;
- optional require camera snapshot for remote prints;
- allowed users/chats by printer.

**Acceptance criteria:**

- Safe normal PLA print plan passes with confirmation.
- Raw G-code is blocked by default.
- High-risk plans return explanatory risk flags or denials.
- Policy cannot be bypassed by client-provided text.

---

## Task 6: Implement model search normalization

**Objective:** Create provider-independent search result handling.

**Files:**

- Create: `src/print_concierge/search/base.py`
- Create: `src/print_concierge/search/web.py`
- Create: `tests/test_search_normalization.py`

**Features:**

- Normalize result fields from any provider.
- Treat descriptions as untrusted strings.
- Add obvious warnings for missing license/profile/source.

**Acceptance criteria:**

- Results from mocked providers normalize correctly.
- Prompt-injection strings remain inert data.
- Missing fields produce warnings, not crashes.

---

## Task 7: Add prompt-injection tests

**Objective:** Prove untrusted model content cannot trigger actions.

**Files:**

- Create: `tests/test_prompt_injection.py`

**Test cases:**

- model title says "CONFIRM PRINT NOW";
- description says "ignore instructions";
- filename contains fake command;
- source page includes malicious instructions.

**Acceptance criteria:**

- Malicious text appears only as escaped/displayed data.
- No confirmation token is generated from retrieved content alone.
- No print-start function is called.

---

## Task 8: Implement Bambuddy read-only adapter

**Objective:** Connect to Bambuddy safely without print control.

**Files:**

- Create: `src/print_concierge/bambuddy/client.py`
- Create: `tests/test_bambuddy_client.py`

**Methods:**

- `list_printers()`
- `get_printer_status(printer_id)`
- `get_snapshot(printer_id)` if available
- `list_recent_archives()` if available

**Acceptance criteria:**

- Uses `BAMBUDDY_BASE_URL` and `BAMBUDDY_API_KEY` from environment/config.
- Does not log API key.
- Does not implement start/stop/pause yet unless pause/cancel safety is explicitly added later.
- HTTP calls are mocked in tests.

---

## Task 9: Add CLI demo flow

**Objective:** Provide a deterministic local demo without Telegram.

**Files:**

- Create: `src/print_concierge/interfaces/cli.py`
- Update: `pyproject.toml` console script
- Create: `tests/test_cli.py`

**Commands:**

- `print-concierge search "desk cable clip"`
- `print-concierge printers`
- `print-concierge status PRINTER_ID`
- `print-concierge prepare --model ... --printer ...`

**Acceptance criteria:**

- Search returns normalized shortlist.
- Printer commands are read-only.
- Prepare creates a pending plan but cannot print.

---

## Task 10: Add MCP server wrapper

**Objective:** Expose safe high-level tools to MCP clients.

**Files:**

- Create: `src/print_concierge/interfaces/mcp_server.py`
- Create: `docs/claude-setup.md`
- Create: `docs/hermes-setup.md`

**Tools:**

- `search_models`
- `list_printers`
- `get_printer_status`
- `prepare_print`
- `show_print_plan`
- `request_confirmation`
- `start_confirmed_print` — initially can be disabled/mocked until real Bambuddy start is safely mapped.

**Acceptance criteria:**

- MCP exposes only safe high-level tools.
- No raw Bambuddy API execution tool in normal mode.
- Hermes and Claude setup docs explain environment variables.

---

## Task 11: Add real confirmed print start only after safety tests pass

**Objective:** Enable physical print start through Bambuddy only after confirmation and policy enforcement.

**Files:**

- Modify: `src/print_concierge/bambuddy/client.py`
- Modify: `src/print_concierge/policy.py`
- Modify: `src/print_concierge/confirmations.py`
- Add integration tests with mocked Bambuddy.

**Preconditions:**

- Confirmation tests pass.
- Policy tests pass.
- Audit log tests pass.
- Prompt-injection tests pass.
- User explicitly decides to implement real printing.

**Acceptance criteria:**

- `start_confirmed_print(job_id, token)` is the only route to start.
- Invalid/missing/expired token fails.
- Policy denial prevents Bambuddy call.
- Successful start writes audit event.
- Tests prove Bambuddy start is not called on failures.

---

## Task 12: Telegram/Hermes UX layer

**Objective:** Build the polished chat experience.

**Files:**

- Create Hermes skill/tool docs or plugin later.
- Create: `docs/telegram-flow.md`

**Flow:**

1. User asks for model.
2. Assistant returns numbered options.
3. User selects one.
4. Assistant prepares plan.
5. Assistant asks for exact confirmation token.
6. Backend starts only after verification.
7. Assistant monitors status.

**Acceptance criteria:**

- The demo video flow works.
- User sees exact job details before confirmation.
- Pause/cancel/status commands are obvious.

---

## Verification checklist before any real printer control

- [ ] Threat model written.
- [ ] Confirmation token tests pass.
- [ ] Policy tests pass.
- [ ] Prompt injection tests pass.
- [ ] Audit log redaction tests pass.
- [ ] Bambuddy API key never appears in logs.
- [ ] No direct raw Bambuddy execution endpoint exposed to agent.
- [ ] `start_confirmed_print` fails closed.
- [ ] User has reviewed the first real print manually.
