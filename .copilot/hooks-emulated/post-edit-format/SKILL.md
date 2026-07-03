---
name: post-edit-format
description: Emulates the Claude post_edit_format.py PostToolUse hook. After editing Python files, run ruff format + ruff check --fix and log the edit. In Claude this ran automatically after every Write/Edit/MultiEdit. In Copilot, invoke /post-edit-format manually after editing Python files, or rely on a pre-commit hook.
allowed-tools: Bash, Read
invocation: /post-edit-format [file ...]
# Ported from Claude (.claude/hooks/post_edit_format.py) on 2026-07-03
# Original hook type: PostToolUse(Write|Edit|MultiEdit) - auto-format + log
# Copilot equivalent: Manual skill — invoke after editing Python files
---

# Post-Edit Format

Auto-format Python files after editing and log the change to the audit trail.

> **Ported from Claude `post_edit_format.py` (PostToolUse Write/Edit hook) on 2026-07-03.**
> In Claude Code this ran automatically after every file write/edit. In Copilot CLI,
> call `/post-edit-format [file ...]` after editing Python files, or configure a
> pre-commit hook with `ruff format` + `ruff check --fix`.

## Steps

1. **Determine target files** from `$ARGUMENTS`. If empty, format all Python
   files changed in the working tree:
   ```bash
   git diff --name-only | Select-String '\.py$'
   ```

2. **Format** each `.py` file:
   ```bash
   ruff format <file>
   ruff check --fix --quiet <file>
   ```
   Formatting failures are **non-blocking** — log a note but do not abort.

3. **Log the edit** to `.claude/logs/edits.log`:
   ```
   <ISO-8601-UTC> edited <relative-path>
   ```
   (Maintains the audit trail that `.claude/hooks/post_edit_format.py` produced.)

## Notes

- The project uses `ruff` for both formatting and import-safe linting (see `ruff.toml`).
- There is no Black or Prettier config — `ruff format` is the formatter.
- For CI enforcement, the `ruff` check runs in `.github/workflows/ci.yml`.
- Consider adding a pre-commit hook that runs `ruff format` + `ruff check --fix`
  automatically (e.g. with `pre-commit` framework) to recover the auto-format
  behavior Claude had natively.
