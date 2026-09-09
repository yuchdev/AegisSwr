# Architecture Decision Records

ADRs for Aegis SWR use the [MADR](https://adr.github.io/madr/) (Markdown Any Decision Records) template.
Each record lives in this directory as `000N-slug.md`. Mermaid diagrams referenced by ADRs
are in `assets/`.

## Inventory

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-new-ui-rich-based-design.md) | New Terminal UI Design (WarRoomView) | Implemented | 2025 |
| [0002](0002-agent-weight-as-property.md) | Consensus weight as a `ClassVar` agent property | Accepted | 2026-07-08 |
| [0003](0003-code-intel-composition-root.md) | Code intelligence composition root and `CodeIntelBackend` rename | Accepted | 2026-07-10 |
| [0004](0004-harness-composition-generalization.md) | Code-intelligence composition root generalised into a neutral `harness/` package (multi-backend selection) | Proposed | 2026-08-19 |
| [0005](0005-flake8-lint-adoption.md) | Adopt the standalone `flake8-lint` package as the single lint engine, run via CLI and/or pytest adapters | Proposed | 2026-09-08 |

## Template

Use `template.md` when creating a new ADR. The recommended invocation is:

```bash
/adr-write <short-title>
```

The `/adr-write` skill scaffolds a MADR-formatted record pre-filled with context
from recent git log and open GitHub issues, then saves it here as the next
`000N-slug.md`.

## Naming conventions

- Filename: `000N-kebab-slug.md` - sequential, zero-padded to four digits.
- Status values: `Proposed` | `Accepted` | `Implemented` | `Superseded` | `Deprecated`.
- Superseded ADRs keep their file; add a `Superseded by: [000N](...)` line to their header.

## What belongs here vs. `docs/specs/`

| Here (`docs/adr/`) | `docs/specs/` |
|---|---|
| A concrete decision with context + rationale + consequences (MADR format) | A long-form design specification or architecture narrative |
| Typically 1–3 pages | May be tens of pages |
| References a point in time ("we decided X because Y on date Z") | Describes the target system state |
