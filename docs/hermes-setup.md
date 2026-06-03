# Hermes Setup

Hermes can act as the chat-facing orchestrator while Print Concierge owns the print safety workflow.

Configuration:

1. Point Hermes at the Print Concierge MCP server or CLI wrapper.
2. Provide `BAMBUDDY_BASE_URL` and `BAMBUDDY_API_KEY` through the runtime environment.
3. Keep the token least-privilege and rotate it like any other printer-control secret.
4. Do not load broad Bambuddy MCP execution tools in the same Hermes agent profile that exposes Print Concierge.

Expected flow:

1. Search Bambuddy archive items plus public discovery candidates.
2. User selects one candidate.
3. Supported MakerWorld candidates and trusted direct-file Printables/Thingiverse candidates are imported/verified with `import_public_candidate`; source files use explicit preset refs from `list_slicer_presets`, while page-only public candidates pause before preparation.
4. Prepare an immutable print plan for the trusted item.
5. Create a pending print request through `create_print_request`.
6. After explicit user confirmation, queue that exact request through `queue_print_request(request_id)`.

V0/V1 excludes direct starts, raw queue/start tools, and unrestricted Bambuddy control.
