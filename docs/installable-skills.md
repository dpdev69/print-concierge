# Installable Skills

Print Concierge publishes a canonical skill plus host-specific shims. The skill teaches agents to use the curated MCP/CLI workflow and never raw Bambuddy control.

## Canonical Package

- Skill root: `skills/print-concierge/`
- Main skill: `skills/print-concierge/SKILL.md`
- Progressive references: `skills/print-concierge/references/workflow.md` and `skills/print-concierge/references/safety.md`
- Registry metadata: `skills/print-concierge/agents/openai.yaml`

## Local Install Paths

- Claude: copy or symlink `packages/claude/SKILL.md`; add the MCP example from `packages/claude/claude_desktop_config.example.json`.
- Codex: copy or symlink `packages/codex/print-concierge/` into the Codex skills directory.
- Hermes: load `packages/hermes/skill.yaml`; `handler.js` exports the MCP command and safety metadata.
- OpenClaw: copy or symlink `packages/openclaw/print-concierge/` into the OpenClaw skills directory.

## MCP Server

Run the local MCP server from the repository:

```sh
uv run print-concierge-mcp
```

Example client configuration:

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

Keep Bambuddy credentials in the runtime environment, with least privilege. Do not put secret values in skill files, agent memory, logs, or chat.

## Registry-Ready Paths

- Canonical OpenAI/Codex package: `skills/print-concierge/`
- Claude shim: `packages/claude/`
- Codex shim: `packages/codex/print-concierge/`
- Hermes shim: `packages/hermes/`
- OpenClaw shim: `packages/openclaw/print-concierge/`

## Safety Contract

Every host package must preserve these rules: explicit human confirmation, backend-enforced confirmation token validation, approval bound to the exact print job, untrusted model metadata, no secret exposure, least privilege Bambuddy credentials, and no direct start.
