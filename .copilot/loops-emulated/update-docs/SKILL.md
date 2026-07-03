---
name: update-docs
description: >
  Two modes: (A) no-arg scan — full-corpus registry audit that finds broken
  .md cross-references, auto-fixes high-confidence link targets, and writes a
  review report for everything else; (B) <path> — after editing a specific doc,
  finds and fixes every stale reference to its renamed/removed headings across
  docs/ AND src/ docstrings and comments until check_doc_links.py exits 0.
  Re-invoke as /update-docs [<path>] if more passes are needed.
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, Agent
invocation: /update-docs [<doc-path>]
# Ported from Claude (.claude/loops/update-docs.md) on 2026-07-03
# Original entity type: Loop (ScheduleWakeup-based, self-rescheduling, two modes)
# Copilot equivalent: Iterative skill — user re-invokes; ScheduleWakeup replaced by manual re-invocation
---

# update-docs — documentation link repair (one iteration)

> **Ported from Claude loop `update-docs.md` on 2026-07-03.**
> In Claude Code this used `ScheduleWakeup` to re-fire automatically until all
> links resolved. In Copilot CLI, each invocation does one pass and reports what
> remains. Re-invoke `/update-docs [<path>]` if more passes are needed.

Dispatch on `$ARGUMENTS`:
- **No argument** → [Scan mode](#scan-mode)
- **`<path>` argument** → [Path mode](#path-mode)

---

## Scan mode

Runs when `$ARGUMENTS` is empty. Audits every `*.md` file under `docs/` and
`.copilot/`, finds cross-references that point at missing files, auto-fixes
those it can, and produces a review report for the rest.

### A0 — Linkify bare mentions first

```bash
python scripts/linkify_doc_mentions.py
```

Unresolvable mentions → `.claude/state/linkify-report.md`.

### A1 — Run the registry scanner

```bash
python scripts/doc_registry.py --json --cursor .claude/state/update-docs-scan.json
```

Read `.claude/state/update-docs-scan.json`. Schema: `registry`, `missing[]`,
`summary { registry_size, total_md_links, missing_count, high_confidence, needs_review }`.

### A2 — Check for convergence

If `missing_count == 0`: print `"update-docs scan: clean"` and **stop**.

If `missing` list unchanged from previous iteration (no progress): write review
report (A5) and **stop**.

### A3 — Classify

| Bucket | Criterion | Action |
|--------|-----------|--------|
| `auto_fix` | top candidate confidence `"high"` | delegate to `docs-updater` |
| `review` | no candidates or medium confidence | write report, user decides |

### A4 — Auto-fix high-confidence targets

Delegate to **`docs-updater`** in one call, passing:
- List of `(source_file, line, old_target, new_target)` corrections.
- Instruction: "Update only the link target. Do not change link text or prose."

Do NOT rename files. Only update the broken link.

### A5 — Write review report

Write `.claude/state/update-docs-report.md`:
```markdown
# Documentation Link Review — <ISO date>
## Items requiring human decision
| # | Source | Line | Missing target | Top candidate | Confidence |
...
## How to resolve
- Update link → edit source, run `/link-check <source>`.
- Create missing file → create it, re-run `/update-docs`.
- Remove link → delete it, run `/link-check <source>`.
After all items resolved, re-run `/update-docs` to confirm clean.
```

Print the full report to the conversation.

### A6 — Re-verify after fixes

```bash
python scripts/doc_registry.py
```

If `missing_count == 0`: print summary and **stop**.

If new `high_confidence` items appeared (rare): print
`"Re-invoke /update-docs to process new high-confidence items."` and **stop**.

---

## Path mode

Runs when `$ARGUMENTS` is a file path. Propagates heading renames and deletions
from a single edited file across the whole repo.

### Step 1 — Resolve the target file

Read `$ARGUMENTS`. Confirm it exists as `TARGET`. If no argument and multiple
markdown files changed, list them and ask user to pick one.

### Step 2 — Detect what changed in TARGET

Run `git diff HEAD -- <TARGET>`. Extract:
- **Removed headings** (`-#` lines): compute old GitHub-style anchors.
- **Added headings** (`+#` lines): if a rename pair is evident, record `old → new`.

If no heading changes: skip to Step 3b (only outbound links in TARGET may be broken).

### Step 3a — Find stale inbound references

```bash
git grep -rn "#<old-anchor>" -- "docs/" "*.md" ".copilot/"
git grep -rin "<old heading text>" -- "docs/" "*.md" ".copilot/"
git grep -rn "<old-anchor>" -- "src/" "tests/"
```

Collect as `(file, line_number, match_text, ref_type)` list.

### Step 3b — Find broken outbound links in TARGET

```bash
python scripts/check_doc_links.py <TARGET>
```

### Step 4 — Check for convergence

If zero stale refs AND zero broken links: print `"update-docs: clean"` and **stop**.

If same stale refs as previous iteration: surface to user as "Needs human review" and **stop**.

### Step 5 — Delegate fixes

**Bucket A — documentation files**: delegate to **`docs-updater`** with the
full `(file, line, old_text, new_text)` replacement list.

**Bucket B — code files (`src/`, `tests/`)**: delegate to **`python-expert`**
with file:line list, old anchor/text, replacement, instruction to run `mypy`.

Both buckets may be delegated in parallel when file sets do not overlap.

### Step 6 — Verify

```bash
python scripts/check_doc_links.py
```

If exits 0: **stop** and print summary (N refs fixed, files touched, agents called).

If exits non-zero: print
`"Re-invoke /update-docs <TARGET> to process remaining broken links."` and **stop**.

---

## Agent delegation quick-reference

| Finding type | File location | Agent |
|--------------|---------------|-------|
| Broken .md link (high-confidence rename) | `docs/`, `.copilot/` | `docs-updater` |
| Broken anchor in Markdown link | `docs/`, repo `*.md` | `docs-updater` |
| Stale prose mention of old heading | `docs/`, repo `*.md` | `docs-updater` |
| `docs/README.md` registry line | `docs/README.md` | `docs-updater` |
| Docstring `See X §Y` reference | `src/`, `tests/` | `python-expert` |
| Inline comment pointing to old anchor | `src/`, `tests/` | `python-expert` |

Never delegate `.copilot/` CLAUDE.md-equivalent edits to an agent — surface to user.
