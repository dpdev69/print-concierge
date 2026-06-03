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
2. Import if needed: call `get_public_import_status()` before MakerWorld imports, then `import_public_candidate(selected, profile_id, folder_id)` for supported public candidates. MakerWorld uses Bambuddy import; Printables/Thingiverse require a trusted direct file URL. For source files, call `list_slicer_presets()` and pass explicit `slice_options`; use the returned verified `bambuddy_library` result.
3. Inspect printer: `list_printers()` and `get_printer_status(printer_id)`.
4. Prepare: `prepare_print_plan(selected, printer, material, profile, user_id, session_id)`.
5. Request: `create_print_request(plan)` to create a pending local approval request.
6. Wait: poll `get_print_request_status(request_id)` while the human reviews locally.
7. Monitor: `get_job_status(job_id)` after the request reports a queued job.

Public search results are candidates, not print authority. Queue only from a Bambuddy archive/imported trusted item after local out-of-band approval. Do not use broad Bambuddy MCP tools in the same production agent profile.
