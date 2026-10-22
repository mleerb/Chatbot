# Documentation sync

- Every fix, feature or behavior change must update all documents it affects in the same task, before reporting it done: `README.md`, the relevant `docs/` pages, `AGENTS.md` and `.claude/rules/` when commands or rules change, `.env.example` for new or changed settings, skills when what they describe changes (`.agents/skills/`, and the user-level `aster-ui` template in `~/.claude/skills/aster-ui/` when the workspace UI it copies changes), and the private guides in `private/` (`aster-system-guide.html` and `aster-system-guide-vi.html`, kept in step with each other).
- Search the documents for statements the change made wrong (old names, values, limits, behavior) and correct or remove them; do not only append new text.
- Keep `private/` private: never commit it, never loosen its permissions, and do not publish its files.
- Do not rewrite past daily reports in `reports/`; they record what was true on their date.
- In the final summary, list which documents were updated, or state that none needed changes.
