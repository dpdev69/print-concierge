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
3. Supported MakerWorld candidates are imported/verified with `import_public_candidate`; other public-index candidates wait for a trusted adapter before preparation.
4. Prepare an immutable print plan for the trusted item.
5. Request confirmation through Hermes or the configured confirmation service.
6. Queue only the confirmed trusted archive/imported item.

V0/V1 excludes direct starts and unrestricted Bambuddy control.
