# Sample doc-registry report (annotated)

Illustrates the output of `python scripts/doc_registry.py` and how to act on each
confidence tier. This is a representative shape, not live output.

```
Missing .md References
======================

[HIGH] Likely rename
  docs/README.md:42
    link:      ](runbooks/acess-violation.md)        # typo'd path
    candidate: docs/runbooks/access-violation.md      (score 0.94)

[MEDIUM] Possible rename
  docs/adr/0001-new-ui-rich-based-design.md:88
    link:      ](../specs/design.md)
    candidates:
      docs/specs/PRODUCTION_DESIGN_SPEC.md            (score 0.61)
      docs/specs/ui-design.md                         (score 0.55)

[REVIEW] No candidates found
  .claude/skills/pr-review/SKILL.md:12
    link:      ](../../docs/reviews/2025-pr-template.md)
    candidates: (none)

Summary
=======
Registry: 128 .md files
Links scanned: 341
Missing: 3   (HIGH 1 | MEDIUM 1 | REVIEW 1)
```

## How to act on each tier

- **[HIGH] Likely rename** — the correct file exists at the candidate path; the
  link was written wrong. Fix the *link* to point at the candidate (shortest
  correct relative path). **Do not rename the file.** Here: change
  `runbooks/acess-violation.md` → `runbooks/access-violation.md`.
- **[MEDIUM] Possible rename** — inspect the candidates. If one is obviously right,
  repoint the link; if genuinely ambiguous, flag for human review rather than guess.
- **[REVIEW] No candidates found** — decide among: create the missing file (and add
  it to `docs/README.md` if it belongs there), delete the broken link, or repoint
  to an existing related file.

## After fixing

1. Re-run `python scripts/doc_registry.py` until it reports
   `All .md cross-references resolve correctly.`
2. Run `/link-check` — doc-registry only checks file *existence*; link-check
   validates *anchors* and non-`.md` links (orthogonal coverage).
