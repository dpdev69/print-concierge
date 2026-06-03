# GitHub Launch Copy

## GitHub repo description

Safe AI print concierge for Bambuddy: find 3D models, import supported public candidates, prepare print plans, and queue only scoped requests.

## README hero copy

Find it. Pick it. Print it.

Print Concierge is a safe AI print concierge for Bambuddy and Bambu Lab workflows. Ask for the object you need, get model options from your archive plus public model search, import/verify public candidates when needed with `import_public_candidate`, review an exact print plan for a trusted item, and approve queueing through a local human channel.

It is not raw AI control of a printer. It is an inspectable, open-source safety layer between chat agents and a physical machine.

## Short pitch

Print Concierge lets Claude, Codex, Hermes, OpenClaw, and other MCP clients help with 3D printing without giving them unchecked printer control. It searches Bambuddy archives and public model indexes like MakerWorld and Printables through 3DSEARCH, imports supported public candidates with `import_public_candidate`, prepares immutable print plans only for archive/imported trusted items, and queues only a specific stored request id. It does not expose raw Bambuddy queue/start tools.

## Taglines

- Find it. Pick it. Print it.
- A safe AI print concierge for Bambuddy.
- Ask for the object. Approve the job. Keep the printer under control.
- MCP-native 3D print search and scoped queueing for Bambuddy.

## Topics

`3d-printing`, `bambuddy`, `bambu-lab`, `mcp`, `claude`, `codex`, `hermes`, `openclaw`, `makerworld`, `printables`, `self-hosted`, `ai-agents`, `safety`

## Launch post

I built Print Concierge, an open-source safety layer for AI-assisted 3D printing.

The basic flow:

1. Ask an agent for something printable.
2. It searches your Bambuddy archive plus public model indexes like MakerWorld and Printables; public candidates must be imported/verified before printing.
3. You get a shortlist of options.
4. Supported public candidates are imported/verified with `import_public_candidate`, then the backend prepares an exact print plan for a trusted item.
5. Print Concierge creates a pending request.
6. You confirm, and the agent queues that exact request id.

The key design choice: the agent never gets raw "start printer" or broad Bambuddy queue tools. All clients go through the same MCP workflow: search, prepare, create request, queue that request id, poll status. Bambuddy manual-start is on by default.

This is built for the Bambuddy crowd, self-hosters, makerspaces, and anyone who wants the convenience of AI print help without handing a physical machine to a chatbot.

Repo: https://github.com/dpdev69/print-concierge

## Hacker News / Reddit variant

I made a small open-source project for safer AI-assisted 3D printing.

It is called Print Concierge. It sits between Claude/Codex/Hermes/OpenClaw-style agents and Bambuddy. The agent can search model options, import/verify supported public candidates, prepare print plans, create pending print requests, and queue a specific request id. It cannot call raw Bambuddy queue/start tools. Request queueing is bound to the exact file hash, printer, material/profile, user/session, and plan hash.

Current V1.2:

- Bambuddy archive search
- public model search via 3DSEARCH across MakerWorld, Printables, Thingiverse, etc.
- MakerWorld import/verify through `import_public_candidate`
- Printables/Thingiverse direct-file import/verify through `import_public_candidate`, including source slicing when explicit presets are provided
- CLI and MCP server
- installable skill packages for Claude, Codex, Hermes, and OpenClaw
- local SQLite approval state
- manual-start queue behavior by default

I built it because I wanted the magic of "find me the right thing and set up the print" without giving an agent unchecked control of a physical machine.

## Maintainer notes

- Lead with safety, not "AI controls your printer."
- Show the exact request review and scoped queue step in demos.
- Mention Bambuddy early; it is the adoption wedge.
- Be precise about public imports: Printables/Thingiverse need trusted direct file URLs; STL/source-only files require explicit preset refs and successful Bambuddy slice verification.
- Use screenshots or terminal clips showing search, prepare, request, approve, queue, status.
