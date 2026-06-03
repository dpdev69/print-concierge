# Claude Setup

Use Print Concierge as the safety workflow layer, not as a general Bambuddy API proxy.

Recommended profile shape:

- Add the Print Concierge MCP server only.
- Configure `BAMBUDDY_BASE_URL` and `BAMBUDDY_API_KEY` from `.env.example`.
- Use a Bambuddy token with the least privileges needed for archive reads, printer status, public imports, slicing, and local approval queueing.
- Avoid loading broad Bambuddy MCP tools in the same Claude profile. That separation prevents a model from bypassing the curated planning flow.
- Mark `queue_print_request(request_id)` as a sensitive tool and require per-call confirmation.

Available V1.3 MCP actions are intentionally narrow: list printers, get printer status, list slicer presets, search Bambuddy archives plus public discovery indexes, call `import_public_candidate` for supported MakerWorld candidates and trusted direct-file Printables/Thingiverse candidates, prepare a print plan only for archive/imported trusted items, create a pending print request, queue that exact request through `queue_print_request`, poll request status, and check job status. There is one sensitive scoped queue tool and no raw Bambuddy queue/start/pause/cancel tools. Queueing is policy-gated, audited, capability-mode controlled, and manual-start by default.
