# Print Concierge Roadmap

## North star

Build an open-source, security-first, human-in-the-loop print concierge for Bambu Lab printers through Bambuddy.

The product should make 3D printing feel like:

> "Tell the assistant what you need, choose from vetted printable options, approve the exact job, and receive progress updates."

## MVP principles

- Start narrow and safe.
- No autonomous printing in early versions.
- Prefer read-only and prepare-only flows before physical actions.
- Make all risky actions auditable.
- Make security claims true in code, not only in prompts.
- Build modularly so Hermes is the flagship surface but not the only client.

---

## Phase 0 — Project foundation and security spec

**Goal:** Make the project trustworthy before it can control hardware.

Deliverables:

- Public repo skeleton.
- `README.md` with clear positioning.
- `SECURITY.md` with threat model.
- Architecture diagram/document.
- Local development instructions.
- Example `.env.example` with no secrets.
- Contribution guidelines.
- Basic CI: lint, type-check, tests.

Acceptance criteria:

- A new contributor can understand the safety model in 5 minutes.
- No printer-control code exists without a documented confirmation policy.
- Security policy explicitly says the LLM is not a trust boundary.

---

## Phase 1 — Model search and shortlist only

**Goal:** Prove the user-facing value without touching printers.

Features:

- Search model sources:
  - Printables;
  - MakerWorld if accessible/allowed;
  - Thingiverse/Thangs if practical;
  - generic web search fallback;
  - local archive later.
- Normalize search results into a common schema.
- Return top 3–5 candidates.
- Include:
  - title;
  - source URL;
  - thumbnail when available;
  - license;
  - rating/download count when available;
  - whether a Bambu-ready 3MF/profile appears available;
  - obvious fit warnings.

Output surfaces:

- CLI first for testing.
- Hermes/Telegram demo second.

Acceptance criteria:

- User can ask: "find me a cable clip for my desk" and get a clean shortlist.
- No model description text can cause tool calls or bypass policy.
- Search result content is treated as untrusted data.

---

## Phase 2 — Bambuddy read-only integration

**Goal:** Safely connect to Bambuddy without controlling prints.

Features:

- Configure Bambuddy URL and API key.
- Support either direct Bambuddy REST API or `bambuddy-mcp` adapter.
- Read-only actions:
  - list printers;
  - get printer status;
  - get recent archives;
  - get camera snapshot if available;
  - get filament/AMS status if available;
  - get capabilities/build volume if available.

Acceptance criteria:

- No action can start, pause, stop, or modify a print.
- Secrets are read from environment/config only.
- API key and printer access codes are never printed to logs or chat.

---

## Phase 3 — Print plan preparation

**Goal:** Turn a selected model into a reviewable print plan.

Features:

- User selects a shortlisted model.
- Backend downloads or imports model metadata/file where legally/technically allowed.
- Compute file hash and validate size/type.
- Prepare a print plan with:
  - model title;
  - source;
  - file hash;
  - target printer;
  - material/profile;
  - estimated time if available;
  - estimated filament if available;
  - risk flags;
  - preview/thumbnail where available.
- Store print plan as pending.

Acceptance criteria:

- Preparing a print plan cannot start a print.
- Every plan has a stable `job_id` and content hash.
- If model/profile/printer/material changes, a new plan is required.

---

## Phase 4 — Confirmation-token queue flow

**Goal:** Enable real printing, guarded by backend-enforced user approval.

Features:

- Generate short-lived confirmation token for a specific pending job.
- Confirmation is bound to:
  - user ID;
  - chat/session ID;
  - job ID;
  - model file hash;
  - source URL;
  - printer ID;
  - material/profile;
  - timestamp and expiry.
- User must reply with exact token or click a trusted UI button.
- Backend verifies token before calling Bambuddy.
- Start with import plus confirmation-gated queueing; keep direct start out of the default agent surface.

Acceptance criteria:

- The LLM cannot call `start_print` directly.
- `start_confirmed_print(job_id, token)` fails without a valid unexpired token.
- Tokens expire after 5–10 minutes by default.
- Any plan mutation invalidates previous tokens.
- All print starts are written to audit log.

---

## Phase 5 — Monitoring and emergency control

**Goal:** Make the workflow useful after print start.

Features:

- Progress updates.
- Done/failure notifications.
- Camera snapshot on demand.
- Safe commands:
  - status;
  - snapshot;
  - pause;
  - cancel.
- Optional scheduled polling through Hermes cron/background job.

Acceptance criteria:

- Pause/cancel are always easier than starting a print.
- User can cancel from chat quickly.
- Failure states are reported without leaking secrets.

---

## Phase 6 — Policy engine and high-risk jobs

**Goal:** Add configurable safety rules.

Policy examples:

- no remote prints without camera snapshot;
- no print if plate-clear check fails/unavailable, depending on user policy;
- no raw G-code from untrusted sources;
- no ABS/ASA/high-temp material without extra confirmation;
- no jobs over N hours without extra confirmation;
- no overnight prints unless explicitly allowed;
- per-printer allowed users;
- per-chat allowlist.

Acceptance criteria:

- Policies are enforced in backend code.
- Policy denial explains what blocked the print.
- Users can configure stricter defaults.

---

## Phase 7 — Multi-client integrations

**Goal:** Make Hermes the flagship, but keep the core portable.

Targets:

- Hermes native tool/plugin.
- MCP server for Claude Desktop, Claude Code, Cursor, and other MCP clients.
- CLI for local testing and scripting.
- Optional HTTP API.
- Optional Home Assistant integration later.

Acceptance criteria:

- Same safety gateway is used by all clients.
- No client can bypass confirmation by using a lower-level endpoint.

---

## Phase 8 — Print-farm and advanced convenience

**Goal:** Serve power users after safety is proven.

Features:

- Multi-printer queue optimization.
- Filament inventory awareness.
- Cost estimation.
- Team/makerspace approval workflow.
- User quotas.
- Local model archive search.
- Creator/source trust scoring.
- Failure analysis from snapshots/history.

Acceptance criteria:

- Advanced features do not weaken default safety guarantees.
