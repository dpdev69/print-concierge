# Security Review

Review date: 2026-06-03

## Summary

No high-severity findings remain open in the current V1.1 code. The project is intentionally conservative: public search and agent-facing tools can discover models, but plan preparation for physical queueing and the only print-queue path are limited to Bambuddy archive/imported trusted items and backend-enforced confirmation.

## Threat model

Primary assets:

- Bambuddy API key
- Printer identity, access codes, serial numbers, camera URLs
- Print plans and confirmation tokens
- Physical printer behavior and nearby people/property

Primary adversaries:

- Prompt-injection content embedded in model titles/descriptions/files
- A compromised or over-capable agent profile
- Accidental leakage of local printer credentials
- Ambiguous queue state after a network failure

Primary trust boundary:

- Agent clients are untrusted planners.
- Print Concierge backend code is the policy and confirmation gate.
- Bambuddy is the device-control backend.

## Findings

### 1. Secrets

Status: mitigated.

- `.env` and common local secret files are ignored.
- Unit tests use fake credentials only.
- Bambuddy API key is redacted from `repr`, errors, and public output.
- Printer access code and serial number fields are redacted in Bambuddy responses.
- Secret scan was run for API key, access code, serial number, and private key patterns.

### 2. Prompt injection

Status: mitigated for V1.

- Search result text is treated as inert data.
- Public search results are discovery candidates only; they cannot approve work or queue prints directly.
- CLI/MCP public search output strips raw provider metadata.
- Existing prompt-injection tests cover malicious model text and MCP prepare behavior.

### 3. Physical-device safety

Status: mitigated for V1.

- `prepare_print_plan` creates `confirmation_required` plans and does not emit confirmation tokens.
- `request_confirmation` binds approval to job id, plan hash, user/session, file hash, printer, and material/profile.
- `queue_confirmed_print` consumes a single-use token through backend state before calling Bambuddy.
- Runtime state initializes its directory as `0700` and SQLite database as `0600`.
- `BambuddyClient.queue_print` refuses payloads without the internal `_print_concierge_confirmed` marker.
- Bambuddy queue payload uses `manual_start` by default through `PRINT_CONCIERGE_BAMBUDDY_MANUAL_START=true`.

### 3a. Public import boundary

Status: mitigated for V1.1.

- `import_public_candidate` supports MakerWorld import through Bambuddy, plus Printables/Thingiverse direct-file imports when the candidate includes a trusted provider-domain HTTPS download URL.
- MakerWorld import verifies the resulting Bambuddy library file by fetching file metadata and requiring a file hash.
- Printables/Thingiverse imports upload only trusted direct file URLs to Bambuddy, then fetch the resulting library metadata and require a file hash plus a sliced `gcode`/`gcode.3mf` file type before preparation.
- STL/source geometry requires explicit Bambuddy slicer preset refs. The source upload is sliced through Bambuddy, the slice job is polled, and only the verified sliced output becomes queueable.
- Imported library file identity is carried into the print plan as `library_file_id` and remains subject to the same confirmation-gated queue path.
- Unsupported public providers and page-only public search results remain discovery-only until a trusted adapter provides provenance and file identity.

### 4. Raw Bambuddy access

Status: mitigated by packaging guidance.

- The MCP server exposes curated tools only.
- Setup docs instruct users: do not load broad Bambuddy MCP tools in the same production agent profile.
- Endpoint allowlisting blocks arbitrary Bambuddy paths in the client adapter.

### 5. Queue ambiguity

Status: mitigated with a conservative tradeoff.

- Confirmation tokens are consumed before queueing so retry loops cannot double-submit after an ambiguous physical-control request.
- If a queue call fails after token consumption, the user must request a new confirmation.
- Bambuddy responses without a queue id/job id raise `BambuddyAmbiguousActionError`.

## Verification commands

```sh
uv run pytest
uv run python -m compileall -q src
uv build
uvx pip-audit .
uvx bandit -r src
git diff --check
rg -n --hidden --glob '!.git/**' --glob '!.env' --glob '!dist/**' --glob '!.venv/**' --glob '!**/__pycache__/**' '<project secret patterns>' .
```

## Residual risks

- Public search uses third-party indexed pages and should be treated as discovery only, not proof of printability.
- MakerWorld import depends on Bambuddy's MakerWorld integration and available Bambu Cloud download credentials.
- Printables/Thingiverse adapters require trusted direct file URLs; ordinary page-only search hits remain discovery-only until a search/import gateway resolves files safely.
- STL/source-only public files require explicit slicer/profile refs and successful Bambuddy slice-job verification before they can be queueable.
- Other public providers remain discovery-only until provenance, hash, license, and slicer/profile verification adapters are implemented.
- The default runtime state is local SQLite. Multi-user hosted deployments should move confirmation state to a transactional service with operator observability.
- Least-privilege Bambuddy tokens depend on Bambuddy deployment configuration.
- Pause/cancel controls are not exposed in V1; operators should use Bambuddy directly for emergency control.
