# Claude Setup

Use Print Concierge as the safety workflow layer, not as a general Bambuddy API proxy.

Recommended profile shape:

- Add the Print Concierge MCP server only.
- Configure `BAMBUDDY_BASE_URL` and `BAMBUDDY_API_KEY` from `.env.example`.
- Use a Bambuddy token with the least privileges needed for archive reads, printer status, and confirmed queueing.
- Avoid loading broad Bambuddy MCP tools in the same Claude profile. That separation prevents a model from bypassing the curated confirmation flow.

Available V0/V1.1 actions are intentionally narrow: list printers, get printer status, search Bambuddy archives plus public discovery indexes, call `import_public_candidate` for supported MakerWorld candidates, prepare a print plan only for archive/imported trusted items, request confirmation, queue a confirmed print, and check job status. There is no direct start tool.
