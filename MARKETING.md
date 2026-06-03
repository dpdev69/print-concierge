# Marketing and Launch Notes

## Core message

Print Concierge is a secure, open-source, human-in-the-loop 3D printing assistant for Bambu/Bambuddy.

It helps users:

1. ask for the thing they need;
2. review vetted printable models;
3. approve the exact print job;
4. let Bambuddy queue/start/monitor safely.

Lead with security and control, not autonomy.

## Best framing

Use:

- "human-approved";
- "security-first";
- "open-source";
- "self-hosted";
- "Bambuddy-compatible";
- "chat-based print workflow";
- "find, pick, print."

Avoid:

- "fully autonomous AI printing";
- "AI controls your printer";
- "hands-free physical automation";
- "no human needed."

## Tagline options

- Find it. Pick it. Print it. From chat.
- A safe AI print concierge for Bambu and Bambuddy.
- Human-approved 3D printing from chat.
- The secure chat workflow for Bambuddy printing.
- Ask for the object. Approve the job. Let Bambuddy print.

## Launch audiences

### Bambu/Bambuddy users

Highest-intent audience.

Channels:

- Bambuddy Discord/community;
- Bambu Lab Forum;
- `r/BambuLab`;
- `r/3Dprinting`;
- `r/functionalprint`;
- `r/3DPrintFarms`.

Message:

> I built an open-source, human-approved print concierge for Bambuddy. Ask for an object in chat, review printable options, approve the exact job, then Bambuddy handles the printer.

### Self-hosted / homelab

Good fit because the project is local-first and open-source.

Channels:

- `r/selfhosted`;
- `r/homelab`;
- Hacker News Show HN;
- Lobsters;
- Awesome-selfhosted submissions;
- Tailscale community if using Tailscale/WireGuard.

Message:

> Self-hosted chat workflow for Bambu printers. No public cloud required. No print starts without explicit confirmation.

### AI agent / MCP community

Useful for demos, contributors, and stars.

Channels:

- MCP directories;
- Claude Desktop/Claude Code communities;
- Cursor/agent communities;
- AI Twitter/X;
- Product Hunt;
- GitHub.

Message:

> An MCP-compatible safety layer for physical-world 3D printing agents. The LLM can search and prepare, but backend policy enforces confirmation before print start.

### Makerspaces and schools

Useful if policy/approval workflow matures.

Message:

> A safe chat-based request and approval workflow for shared Bambu printers.

## Killer demo

Make a 60–90 second video.

Storyboard:

1. Telegram message: "Find me a small cable holder for my desk."
2. Assistant returns 3 model cards with thumbnails.
3. User replies: "2".
4. Assistant prepares print plan:
   - model;
   - source;
   - printer;
   - material;
   - estimated time;
   - risk flags.
5. Assistant says: "Reply `CONFIRM K81Q` to queue this in Bambuddy."
6. User confirms.
7. Bambuddy starts/queues the print.
8. Assistant sends progress and snapshot.
9. End card: "The AI cannot print without your explicit confirmation."

## First public post draft

Title:

> Show HN: Open-source print concierge for Bambuddy — find, approve, and print from chat

Body:

```text
I’m building Print Concierge, an open-source, human-in-the-loop assistant for Bambu/Bambuddy users.

The idea: ask for an object in chat, get a few printable model options, pick one, review the exact print plan, and only then allow Bambuddy to queue/start the job.

The main design rule is that the LLM is not the safety boundary. It can search and prepare, but the backend enforces confirmation tokens before any physical printer action.

Current focus:
- model search + shortlist;
- Bambuddy read-only status;
- confirmation-token safety layer;
- MCP/Hermes integration.

I’d love feedback from Bambuddy, Bambu, self-hosted, and makerspace users — especially around security, safe defaults, and what model sources matter most.
```

## Early contributor asks

Ask the community for:

- Bambuddy API endpoint mapping;
- safe model-source APIs;
- printer capability metadata;
- threat-model review;
- UX feedback on confirmation flow;
- test cases for prompt injection and malicious model metadata;
- help with Bambu/MakerWorld/Printables compatibility.

## Monetization later, not first

Start open-source-first. If monetization happens later, possible options:

- hosted search/ranking index;
- hosted notification relay;
- print-farm dashboard;
- makerspace/team approval features;
- support/sponsorship;
- paid convenience cloud while core remains self-hosted.

Do not compromise trust by making the safety layer closed-source.
