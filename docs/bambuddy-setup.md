# Bambuddy Setup

Print Concierge expects a local or private Bambuddy instance.

1. Set `BAMBUDDY_BASE_URL` to the Bambuddy HTTP URL, for example `http://127.0.0.1:8080`.
2. Set `BAMBUDDY_API_KEY` to a least-privilege token for printer/archive access.
3. Do not place a broad Bambuddy MCP server in the same agent profile as Print Concierge. Keep unrestricted Bambuddy API access in a separate administrative profile.

V0/V1 scope:

- V0a: local archive search and manual archive/model selection.
- V0b: confirmed queue only after explicit human approval.
- V0c: one curated MCP surface.
- V1: public discovery through one external search provider, such as 3DSEARCH for MakerWorld/Printables; physical queueing still requires Bambuddy archive/imported trusted items.

Direct print start remains disabled. Queueing must use a confirmation service and a confirmed token.
