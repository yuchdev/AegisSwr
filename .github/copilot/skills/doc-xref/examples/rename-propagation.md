# Worked example: propagating a doc rename

Illustrates a full `/doc-xref` inbound-reference sweep when renaming a spec and
one of its headings. Scenario: rename
`docs/specs/design.md` → `docs/specs/PRODUCTION_DESIGN_SPEC.md`
and rename its section `## Escalation` → `## Escalation & HITL`.

## 1. Linkify bare mentions first

```bash
python scripts/linkify_doc_mentions.py
```
Turns prose mentions of `design.md` into real links so the grep below finds them.

## 2. Enumerate inbound references (both trees)

```bash
git grep -nF "design.md"          # old path — docs + code
git grep -nF "#escalation"        # old anchor
git grep -nF "Escalation"         # prose mentions of the section title
```

Representative hits:

```
docs/README.md:31:  - [Design spec](specs/design.md)
docs/runbooks/access-violation.md:70:  see [design](../specs/design.md#escalation)
src/aegis_swr/core/orchestrator.py:498:  # routing per docs/specs/design.md#escalation
tests/unit/test_orchestrator.py:12:  # spec: design.md "Escalation"
```

## 3. Update every hit (path + anchor + prose)

| File:line | Old | New |
|-----------|-----|-----|
| docs/README.md:31 | `specs/design.md` | `specs/PRODUCTION_DESIGN_SPEC.md` |
| docs/runbooks/access-violation.md:70 | `../specs/design.md#escalation` | `../specs/PRODUCTION_DESIGN_SPEC.md#escalation--hitl` |
| src/aegis_swr/core/orchestrator.py:498 | `design.md#escalation` | `PRODUCTION_DESIGN_SPEC.md#escalation--hitl` |
| tests/unit/test_orchestrator.py:12 | `design.md "Escalation"` | `PRODUCTION_DESIGN_SPEC.md "Escalation & HITL"` |

- Note the new anchor `#escalation--hitl` — the `&` is removed and its surrounding
  spaces each become a hyphen (double hyphen). See link-check's anchor-slug rules.
- `git mv docs/specs/design.md docs/specs/PRODUCTION_DESIGN_SPEC.md` so history follows.

## 4. Update the registry line

Edit the `docs/README.md` index entry for the renamed file.

## 5. Verify

```bash
python scripts/check_doc_links.py     # or /link-check
```

Confirm exit 0. Flag any reference you could not safely auto-update (e.g. an
ambiguous prose mention) for human review rather than guessing.

## Complement

`/doc-xref` fixes **inbound** references (this sweep); `/link-check` validates the
**outbound** links of any file you edited. Run both after a rename.
