# 6.1 Code Backend – PDB Adapter (Windows Source Server)

**Parent task:** Task 6.1 – Code Backend ([plan.md](/docs/roadmap/0001-generic-implementation/plan.md#task-61-code-backend))
**Status:** 🔶 Partial - `GitCodeAdapter` and `FilesystemCodeAdapter` done; `PdbCodeAdapter` not started

## Scope

This sub-plan delivers `PdbCodeAdapter` - the third and highest-fidelity
`CodeBackend`. Where the Git and filesystem adapters guess which commits
are relevant using a time-window heuristic, the PDB adapter reads the
**SrcSrv (Source Server) stream** embedded in the Windows Program Database
(`.pdb`) file produced during the crash build. The SrcSrv stream records the
*exact* VCS revision compiled into each binary: no guessing, no time window.

The adapter wraps two existing Windows tools already required by the debug
pipeline (`pdbstr.exe` ships with Debugging Tools for Windows alongside
`cdb.exe`) and re-uses the git subprocess pattern from `GitCodeAdapter`.

## Subtask overview

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Configuration model extension](01-configuration-model.md) | ⬜ Not started | 05, 06 |
| 02 | [`pdbstr.exe` subprocess wrapper](02-pdbstr-wrapper.md) | ⬜ Not started | 05 |
| 03 | [SrcSrv stream parser + fixtures](03-srcsrv-parser.md) | ⬜ Not started | 05 |
| 04 | [PDB path resolution](04-pdb-path-resolution.md) | ⬜ Not started | 05 |
| 05 | [`PdbCodeAdapter` full implementation](05-pdb-adapter-impl.md) | ⬜ Not started | 06, 07 |
| 06 | [Factory routing and CLI wiring](06-factory-cli.md) | ⬜ Not started | 07 |
| 07 | [Test suite](07-tests.md) | ⬜ Not started | - |

All subtasks are implementable in order with no design ambiguities.
Subtasks 02–04 are independent of each other and may proceed in parallel.

## Key constraints (inherited from the project)

- `PdbCodeAdapter` is **Windows-only**. Constructor raises `CodeBackendError`
  on any other platform. The factory never routes to it on Linux/macOS.
- `pdbstr.exe` is a list-form subprocess call (never `shell=True`), with a
  configurable timeout, mapping failures to `CodeBackendError`.
- All git operations within the adapter (for `get_file_diff` / `blame`) follow
  the same subprocess pattern as `GitCodeAdapter`.
- `ruff check src/ tests/` - clean.
- Data Adapter Stage 8 wraps `CodeBackend` calls in `try/except CodeBackendError`
  and fails open to empty `code_history` - the adapter must never swallow errors
  silently; it must raise them so Stage 8 can degrade gracefully.

## Architecture note: PDB dual-use

The same `.pdb` file is read twice in the pipeline:

| Stage | What reads the PDB | Purpose |
|-------|-------------------|---------|
| Stage 2 (Debug Backend) | `cdb.exe -y {symbol_path}` | Address → function name (symbol resolution) |
| Stage 8 (Code Backend) | `pdbstr.exe -r -p:{pdb} -s:srcsrv` | Source file → exact VCS revision (build provenance) |

These are orthogonal questions at different pipeline stages. Both backends can
reference the same `.pdb`; this is intentional and architecturally correct.
`PdbCodeAdapter` is **not** a Debug Backend concern.
