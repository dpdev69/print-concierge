# GitHub Launch Copy

## GitHub repo description

Safe AI print concierge for Bambuddy: find 3D models, import supported MakerWorld candidates, prepare print plans, require human confirmation, and queue prints through a guarded MCP workflow.

## README hero copy

Find it. Pick it. Print it.

Print Concierge is a safe AI print concierge for Bambuddy and Bambu Lab workflows. Ask for the object you need, get model options from your archive plus public model search, import/verify public candidates when needed with `import_public_candidate`, review an exact print plan for a trusted item, approve a short-lived confirmation token, and let Bambuddy queue the job.

It is not raw AI control of a printer. It is an inspectable, open-source safety layer between chat agents and a physical machine.

## Short pitch

Print Concierge lets Claude, Codex, Hermes, OpenClaw, and other MCP clients help with 3D printing without giving them unchecked printer control. It searches Bambuddy archives and public model indexes like MakerWorld and Printables through 3DSEARCH, imports supported MakerWorld candidates with `import_public_candidate`, prepares immutable print plans only for archive/imported trusted items, and requires backend-enforced human confirmation before queueing.

## Taglines

- Find it. Pick it. Print it.
- A safe AI print concierge for Bambuddy.
- Ask for the object. Approve the job. Keep the printer under control.
- MCP-native 3D print search and confirmation for Bambuddy.

## Topics

`3d-printing`, `bambuddy`, `bambu-lab`, `mcp`, `claude`, `codex`, `hermes`, `openclaw`, `makerworld`, `printables`, `self-hosted`, `ai-agents`, `safety`

## Launch post

I built Print Concierge, an open-source safety layer for AI-assisted 3D printing.

The basic flow:

1. Ask an agent for something printable.
2. It searches your Bambuddy archive plus public model indexes like MakerWorld and Printables; public candidates must be imported/verified before printing.
3. You get a shortlist of options.
4. Supported MakerWorld candidates are imported/verified with `import_public_candidate`, then the backend prepares an exact print plan for a trusted item.
5. You explicitly confirm that plan.
6. Only then can the job be queued through Bambuddy.

The key design choice: the agent never gets a raw "start printer" tool. All clients go through the same MCP workflow: search, prepare, request confirmation, queue confirmed print, check status.

This is built for the Bambuddy crowd, self-hosters, makerspaces, and anyone who wants the convenience of AI print help without handing a physical machine to a chatbot.

Repo: <github-url>

## Hacker News / Reddit variant

I made a small open-source project for safer AI-assisted 3D printing.

It is called Print Concierge. It sits between Claude/Codex/Hermes/OpenClaw-style agents and Bambuddy. The agent can search model options, import/verify supported MakerWorld candidates, and prepare print plans, but it cannot directly start a print. The backend requires a human confirmation token bound to the exact file hash, printer, material/profile, user/session, and plan hash before queueing.

Current V1.1:

- Bambuddy archive search
- public model search via 3DSEARCH across MakerWorld, Printables, Thingiverse, etc.
- MakerWorld import/verify through `import_public_candidate`
- CLI and MCP server
- installable skill packages for Claude, Codex, Hermes, and OpenClaw
- local SQLite confirmation state
- manual-start queue behavior by default

I built it because I wanted the magic of "find me the right thing and set up the print" without giving an agent unchecked control of a physical machine.

## Maintainer notes

- Lead with safety, not "AI controls your printer."
- Show the confirmation step in demos.
- Mention Bambuddy early; it is the adoption wedge.
- Avoid promising non-MakerWorld automatic imports until file provenance and slicer verification adapters are implemented.
- Use screenshots or terminal clips showing search, prepare, confirm, queue, status.
