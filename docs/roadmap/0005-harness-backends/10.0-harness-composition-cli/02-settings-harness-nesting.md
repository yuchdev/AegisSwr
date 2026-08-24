# 02 - `Settings.harness` nesting (C12 breaking rename)

**Parent task:** 10.0 Harness Composition Root & CLI
**State:** ⬜ Not started
**Depends on:** Task 01.0 (`HarnessSettings` exists in `harness/config.py`, with
the nested `openclaude` / `claude_code` / `openhands` sub-settings and the C2
`active_backend` resolution)
**Blocks:** 01 (`build_code_agent` consumes `settings.harness`), 04 (the CLI reads
`settings.harness`); Task 11.0 (tests reading `settings.openclaude` migrate)

## Objective

Perform the deliberate C12 breaking rename: the top-level `Settings` field
`openclaude: OpenClaudeSettings` is **removed** and replaced by a single
`harness: HarnessSettings = Field(default_factory=HarnessSettings)`. After this
subtask, `Settings.openclaude` no longer resolves; the OpenClaude sub-settings
live at `Settings.harness.openclaude`, alongside `Settings.harness.claude_code`
and `Settings.harness.openhands`. Every consumer of `settings.openclaude` is
migrated to `settings.harness.openclaude`.

This mirrors the tolerance the codebase already applied to ADR 0003's
`CodeBackend` → `CodeIntelBackend` rename: the field is internal, has no stable
external API surface, and the CLI is the only composition-root consumer (C12,
[ADR 0004](/docs/adr/0004-harness-composition-generalization.md) §Decision 5).

## Current state (to be replaced)

`src/aegis_swr/config/settings.py` currently declares, on the top-level
`Settings` class (the standalone field, presently the last of the nested-settings
block):

```python
    openclaude: OpenClaudeSettings = Field(default_factory=OpenClaudeSettings)
```

`HarnessSettings` (Task 01.0, `harness/config.py`) already composes the three
per-family sub-settings via `default_factory` and exposes `active_backend` (C1).
This subtask only re-homes the OpenClaude field under it at the top level.

## File: `src/aegis_swr/config/settings.py` (nested-settings block — updated)

```python
from aegis_swr.harness.config import HarnessSettings

# ... within class Settings, the nested-settings block ...

    core: CoreSettings = Field(default_factory=CoreSettings)
    backends: BackendsSettings = Field(default_factory=BackendsSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    api: APISettings = Field(default_factory=APISettings)
    panel: PanelRuntimeSettings = Field(default_factory=PanelRuntimeSettings)
    # C12: the standalone `openclaude` field is REMOVED; OpenClaude settings now
    # live at `settings.harness.openclaude`, alongside `.claude_code` / `.openhands`.
    harness: HarnessSettings = Field(default_factory=HarnessSettings)
```

The removed line was:

```python
    openclaude: OpenClaudeSettings = Field(default_factory=OpenClaudeSettings)
```

If `OpenClaudeSettings` is no longer referenced anywhere else in `settings.py`
after the removal, drop its now-unused import (ruff `F401` will flag it). Do
**not** leave a compatibility alias/property (`Settings.openclaude` forwarding to
`harness.openclaude`) — C12 is a clean break; a silent alias would defeat the
grep that proves the migration is complete.

## Migration path (every `settings.openclaude` consumer)

Enumerated per C12 (task 10.0 updates `settings.py`, the CLI subcommand, and any tests that read `settings.openclaude`):

1. **`src/aegis_swr/config/settings.py`** — the field rename above (this file).
2. **`src/aegis_swr/cli/commands.py`** — `aegis code-intel check` currently calls
   `build_code_agent(settings.openclaude, …)`. It migrates to pass
   `settings.harness` and read `settings.harness.active_backend`. The full CLI
   rework is subtask 04; this subtask only guarantees the field it reads exists.
3. **Tests** — any unit/integration test constructing `Settings()` and reading
   `.openclaude` switches to `.harness.openclaude` (Task 11.0 executes these).
4. **`redacted_dump` / `_redact_secrets`** — no code change: `_redact_secrets`
   walks the serialised dict recursively (`settings.py`), so secrets nested one
   level deeper under `harness.openclaude`/`harness.claude_code` are still
   redacted by substring key match. **Confirm** in review that the deeper nesting
   is still traversed (it is, because the walker recurses into nested dicts).

A repository-wide grep is the migration's completeness gate:

```
grep -R "settings\.openclaude\|\.openclaude\b" src/ tests/
```

must return **zero** hits outside `settings.harness.openclaude` /
`harness.config` references after the subtask.

## Environment-variable compatibility (C2 closing-guarantee check)

The rename is a **Python-attribute** change only. It must **not** change any
environment-variable name. `OpenClaudeSettings` keeps its own `env_prefix` and
`OPENCLAUDE_GRPC_URL` presence signal (C5), sourced by the nested settings object
exactly as before. Therefore, an existing `OPENCLAUDE_GRPC_URL`-only deployment
still auto-selects OpenClaude with zero further changes (C2 / 0004 closing
guarantee) — the env surface is untouched; only the in-Python access path moved.

Verify the top-level `Settings` env nesting (`env_nested_delimiter="__"`, present
in `settings.py`) does not accidentally require `AEGIS__HARNESS__OPENCLAUDE__…`
for variables that OpenClaude sources through its own `env_prefix`. The
per-family settings source their own variables directly (C1/C5), so the harness
nesting must not shadow them.

## Implementation notes

- **No compatibility shim.** Per C12 the break is deliberate and accepted; a
  forwarding property would hide incomplete migrations and defeat the grep gate.
- **Import direction.** `settings.py` imports `HarnessSettings` from
  `aegis_swr.harness.config`. Confirm this does not create an import cycle:
  `harness/config.py` composes the per-family settings classes but must not
  import the top-level `Settings` (it depends only on the backend `*Settings`
  classes and `harness/exceptions.py`). If Task 01.0 placed `HarnessSettings`
  such that a cycle would form, that is a Task 01.0 defect to raise, not to paper
  over here.
- **`OpenClaudeSettings` import.** Whether `settings.py` still needs to import
  `OpenClaudeSettings` directly depends on Task 01.0's layout; if `HarnessSettings`
  now owns that composition, remove the stale import from `settings.py`.
- **Redaction is unchanged but must be confirmed.** `_redact_secrets` recurses
  into nested dicts, so credentials under the new `harness.*` level are still
  redacted; add/keep a `redacted_dump` assertion in Task 11.0 covering a secret
  nested under `harness.claude_code` (e.g., any token-bearing field) to lock this.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- `Settings.openclaude` **no longer resolves**; `Settings.harness.openclaude`does (C12).
- No environment-variable name changes; `OPENCLAUDE_GRPC_URL` (and the other presence signals) behave exactly as before (C2 closing guarantee).
- No compatibility alias/property for the old field name (clean break, C12).
- No import cycle between `config/settings.py` and `harness/config.py`.
- `redacted_dump()` still redacts secrets nested under `harness.*` (C13).
- No secret value logged or emitted while validating settings (C13).

## Success criteria

- [ ] `Settings` has a `harness: HarnessSettings` field and **no** standalone `openclaude` field.
- [ ] `Settings().harness.openclaude` resolves to an `OpenClaudeSettings`; `Settings().openclaude` raises `AttributeError`.
- [ ] `grep -R "settings\\.openclaude" src/ tests/` returns zero hits after the full task lands (with subtask 04 and Task 11.0).
- [ ] With only `OPENCLAUDE_GRPC_URL` set, `Settings().harness.active_backend == "openclaude"` (0004 closing guarantee preserved, C2).
- [ ] No environment-variable name changed; the per-family presence signals are sourced exactly as before.
- [ ] `redacted_dump()` redacts a secret nested under `harness.*` (C13).
- [ ] No import cycle; `import aegis_swr.config.settings` succeeds.
