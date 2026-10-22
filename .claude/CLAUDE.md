# Claude Code project memory

`AGENTS.md` holds the project overview and commands and is imported below. Detailed rules live in `.claude/rules/`, which Claude Code loads automatically; edit those files, not this one, when a rule changes.

@../AGENTS.md

## Claude Code notes

- Project skills live in `.agents/skills/` and are linked into `.claude/skills/`, so `frontend-design` and `langfuse` can be invoked as skills. Add new shared skills under `.agents/skills/` and link them here.
- Shared permissions are in `.claude/settings.json`. Personal, machine-specific permissions go in `.claude/settings.local.json`, which is not committed.
- Read `docs/` pages on demand as `AGENTS.md` describes; do not import them here.
