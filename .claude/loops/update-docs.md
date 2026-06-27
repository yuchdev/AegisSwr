---
name: update-docs
description: >-
  After a documentation file is edited, finds every stale inbound reference
  to its renamed/removed/moved sections - across docs/ AND src/ docstrings
  and comments - delegates fixes to the docs and coder agents, and loops
  until /link-check exits 0. Invoke as: /loop update-docs <doc-path>
invoke: /loop update-docs <doc-path>
terminates-when: >-
  python scripts/check_doc_links.py exits 0 AND no stale heading references
  remain from the detected renames/deletions in the target file.
---

# update-docs - propagate doc-section changes across docs and code

A documentation file was edited: headings renamed, sections moved, content
restructured. Every other file that referenced those headings - as Markdown
links, prose mentions, `See §X.Y` notes in docstrings, `# docs/…` comments -
is now stale. This loop finds and fixes all of them, iterating until clean.

**Supplements, does not replace** `/doc-xref` and `/link-check`. Those skills
are atomic discovery/validation steps. This loop calls them at the right
checkpoints and routes their findings to the right agent.

---

## Iteration algorithm

### Step 1 - resolve the target file

Read the argument supplied to the loop invocation (`$ARGUMENTS`).

- If a path was provided: resolve it relative to the repo root. Confirm the
  file exists. Record it as `TARGET`.
- If no path was provided: run `git diff --name-only HEAD` and filter to
  `*.md` files. If exactly one changed file: use it. If multiple: print the
  list and ask the user which one to process, then stop the loop - it cannot
  proceed without a single unambiguous target.

### Step 2 - detect what changed in TARGET

Run `git diff HEAD -- <TARGET>` to obtain the unified diff.

From the diff, extract two lists:

**Removed headings** - lines starting with `-#` (any level). For each:
- Record the raw heading text (e.g. `Data Adapter Layer`).
- Compute the old GitHub-style anchor: lowercase, spaces→`-`, strip
  punctuation except `-`. Example: `Data Adapter Layer` → `#data-adapter-layer`.

**Added headings** - lines starting with `+#`. If a removed heading has a
corresponding added heading that is clearly a rename (same level, similar
words, adjacent in diff), record the pair as `old_anchor → new_anchor`.
Otherwise treat the removal as a deletion with no replacement.

If the diff shows no heading changes (only content edits within existing
sections), skip to Step 3b - there are no anchor renames to propagate, but
outbound links from TARGET may still be broken.

### Step 3a - find stale inbound references to changed headings

For each old anchor or heading text identified in Step 2, search across the
full repo:

```bash
# Markdown links with anchor
git grep -rn "#<old-anchor>" -- "docs/" "*.md" ".claude/"

# Prose mentions of the old heading text (case-insensitive)
git grep -rin "<old heading text>" -- "docs/" "*.md" ".claude/"

# Code: docstrings and comments pointing at the section
git grep -rn "<old-anchor>\|<old heading text>" -- "src/" "tests/"
```

Collect results as a list of `(file, line_number, match_text, ref_type)` tuples
where `ref_type` is one of: `md-link`, `prose`, `code-docstring`, `code-comment`.

Discard matches in the TARGET file itself (its own edits are already applied).

### Step 3b - find broken outbound links in TARGET

Run the link checker on the target file:

```bash
python scripts/check_doc_links.py <TARGET>
```

Collect each `missing anchor` or `missing file` finding as a separate fix item.
These are broken links inside TARGET, not broken links pointing at TARGET -
they arise when TARGET references another doc that was simultaneously changed.

### Step 4 - check for convergence

If Step 3a produced zero stale references AND Step 3b produced zero broken
links: print "update-docs: clean - no stale references remain." and **stop**
(do NOT call ScheduleWakeup).

If the same stale references appeared in the previous iteration unchanged
(no progress): stop and surface each remaining reference to the user as
"Needs human review - could not auto-resolve."

Otherwise continue to Step 5.

### Step 5 - delegate fixes to the right agent

Split the findings from Step 3a and 3b into two buckets:

#### Bucket A - documentation files (.md)

Files under `docs/`, repo-root `*.md`, `.claude/**/*.md`.

Delegate to the **`docs-updater` agent** in a single call, passing:
- The full list of `(file, line, old_text, new_text)` replacements to make.
  For a rename, `new_text` is the new anchor / heading text; for a deletion
  with no replacement, `new_text` is `""` and the agent must decide whether
  to drop the link, replace it with plain prose, or repoint it to the nearest
  surviving section.
- The instruction: "Do not change anything beyond the stale references listed.
  Prefer updating the anchor slug over rewriting surrounding prose."
- For Step 3b findings (outbound broken links from TARGET itself): also pass
  those to the `docs-updater` agent to fix in place.

#### Bucket B - code files (src/, tests/)

Files under `src/` and `tests/`, any extension.

Classify each hit:
- **Docstring reference** (`"""…See docs/…"""`, `:seealso:`, `References:` block):
  delegate to the **`python-expert` agent**.
- **Inline comment** (`# See §X.Y`, `# docs/…#anchor`): delegate to the
  **`python-expert` agent**.

Brief the `python-expert` agent with:
- The list of files and line numbers to fix.
- The old anchor/text and its replacement.
- The instruction: "Update the reference text only. Do not change logic,
  signatures, or surrounding comments. Run `mypy` on touched files after edits."

Both buckets may be delegated **in parallel** when the file sets do not overlap.

### Step 6 - verify

Run the full link checker over the whole doc set (not just TARGET):

```bash
python scripts/check_doc_links.py
```

If it exits 0: the iteration is clean. Proceed to Step 7 (reschedule check).

If it exits non-zero: the checker found new or remaining broken links. Treat
its output as the input to the next iteration - go back to Step 3b and Step 5
for those specific files. Do NOT re-diff TARGET (Step 2 is skipped on
subsequent passes; the heading-rename map is computed once and reused).

### Step 7 - reschedule or terminate

If Step 6 was clean AND Step 3a found no stale refs this pass:
- Print a summary: number of references fixed, files touched, agents called.
- **Stop** (do NOT call ScheduleWakeup).

Otherwise call ScheduleWakeup with:
- `prompt`: the literal text `/loop update-docs <TARGET>` (preserve the path)
- `delaySeconds`: `270`  ← keeps the cache window warm (< 300 s TTL)
- `reason`: "continuing update-docs pass for <TARGET> - N stale refs remain"

---

## Agent delegation quick-reference

| Finding type | File location | Agent |
|--------------|---------------|-------|
| Broken anchor in a Markdown link | `docs/`, repo `*.md`, `.claude/` | `docs-updater` |
| Stale prose mention of old heading text | `docs/`, repo `*.md` | `docs-updater` |
| `docs/README.md` registry line (file renamed/moved) | `docs/README.md` | `docs-updater` |
| Docstring `See X §Y` or `:seealso:` reference | `src/`, `tests/` | `python-expert` |
| Inline comment pointing to old anchor | `src/`, `tests/` | `python-expert` |
| Broken outbound link inside TARGET itself | TARGET | `docs-updater` |

Never delegate `.claude/CLAUDE.md` edits to an agent - surface those to the
user; they require deliberate human review.

---

## Skill integration

| Point in loop | Skill / command | Purpose |
|---------------|-----------------|---------|
| Step 3a | `git grep` (direct) | Fast, exact inbound-ref discovery |
| Step 3b | `/link-check <TARGET>` | Validates TARGET's outbound links |
| Step 6 | `/link-check` (whole repo) | Final gate; loop continues until exit 0 |
| Optional, before loop | `/doc-xref <TARGET>` | Broader reference audit including prose mentions and registry entries; useful for large structural changes before Step 3a |

> `/link-check` catches broken *outbound* links from a file. `/doc-xref`
> finds *inbound* references from elsewhere. This loop uses both, directed at
> different things and at different iteration stages.

---

## Termination conditions

| Condition | Action |
|-----------|--------|
| Step 6 exits 0 AND Step 3a found 0 stale refs | Print summary, stop |
| Identical stale refs after two consecutive passes | Surface to user, stop |
| No heading changes detected AND Step 3b finds 0 broken links | Print "Nothing to update", stop immediately |
| `docs-updater` or `python-expert` agent returns an edit conflict or ambiguity | Surface the specific file:line to user, continue with the rest |
