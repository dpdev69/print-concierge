# Print Concierge Workflow Reference

Print Concierge is a thin safety workflow around Bambuddy. Use the high-level MCP tools rather than raw Bambuddy endpoints.

## Local MCP Command

```sh
uv run print-concierge-mcp
```

Example MCP client shape:

```json
{
  "mcpServers": {
    "print-concierge": {
      "command": "uv",
      "args": ["run", "print-concierge-mcp"],
      "env": {
        "BAMBUDDY_BASE_URL": "http://localhost:8000",
        "BAMBUDDY_API_KEY": "${BAMBUDDY_API_KEY}"
      }
    }
  }
}
```

## Tool Order

1. Search: `search_archive_or_models(query, limit)`. This searches Bambuddy archives plus enabled public/model-search providers; public results are discovery only until imported/verified into a trusted archive.
2. Inspect printer: `list_printers()` and `get_printer_status(printer_id)`.
3. Prepare: `prepare_print_plan(selected, printer, material, profile, user_id, session_id)`.
4. Confirm: `request_confirmation(plan)` through the host user channel.
5. Queue: `queue_confirmed_print(confirmation_token)`.
6. Monitor: `get_job_status(job_id)`.

Public search results are candidates, not print authority. Queue only from a Bambuddy archive/imported trusted item after confirmation. Do not skip confirmation. Do not use broad Bambuddy MCP tools in the same production agent profile.
