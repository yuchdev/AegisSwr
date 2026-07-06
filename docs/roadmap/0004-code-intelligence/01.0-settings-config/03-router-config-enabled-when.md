# 03 - `RouterConfig` `enabled_when` extension

**Parent task:** 01.0 OpenClaude Settings & Config
**State:** ⬜ Not started
**Depends on:** 02 (`agents.yaml` `openclaude_agent` role)
**Blocks:** none (this task)

## Objective

Extend `RouterConfig` in `aegis/router/config.py` (Milestone 0003) to parse and
honour the optional `enabled_when` key added to `agents.yaml` in subtask 02, so
that `RouterConfig.from_yaml()` does not raise when `OPENCLAUDE_GRPC_URL` is
absent from the environment.

## File: `aegis/router/config.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AgentConfig:
    role: str
    model: Optional[str]
    fallback: tuple[str, ...]
    timeout_s: float
    retry: RetryPolicy
    provider: Optional[str] = None
    """Explicit provider name, set directly from the YAML `provider:` key.

    Every existing role's provider is inferred from its `model` string prefix
    against the `providers:` block (Milestone 0003); that inference has
    nothing to key off when `model` is `null`, as it is for `openclaude_agent`.
    This field is `None` for all pre-existing roles (they keep using prefix
    inference) and is populated only for roles that set `provider:` explicitly
    in YAML, which today is `openclaude_agent` alone.
    """
    enabled_when: Optional[str] = None
    """Name of an environment variable that gates this role's inclusion.

    When set and the named variable is absent or empty in the process
    environment, :meth:`RouterConfig.from_yaml` silently omits this role from
    :attr:`RouterConfig.agents` - no :class:`ConfigValidationError` is raised.
    Roles without ``enabled_when`` are always included (unchanged behaviour).
    """
```

## Implementation notes

- `AgentConfig` gains two optional fields: `provider` and `enabled_when`
  (both shown above). Because `AgentConfig` is `frozen=True`, these are
  additive, backwards-compatible fields with defaults - existing `agents.yaml`
  roles that omit both parse identically to before this subtask, and continue
  to rely on model-prefix inference rather than the explicit `provider` field.
- The explicit `provider` field exists solely so `openclaude_agent` (whose
  `model` is YAML `null`) can carry a provider identity without a model string
  to infer one from. `RouterConfig.from_yaml()`'s existing prefix-inference
  validation must skip any role that sets `provider` explicitly, rather than
  attempting to derive it from a `None` model.
- In `RouterConfig.from_yaml()`, after parsing each role's raw YAML mapping but
  before adding it to the `agents` dict: if `enabled_when` is present, look up
  `os.environ.get(enabled_when)`. If that value is `None` or an empty string,
  skip the role entirely (do not add it to `agents`, do not raise). Otherwise
  include it normally.
- Roles without `enabled_when` are included unconditionally - this branch is
  new code that must not alter the existing parse path for any other role.
- The env-var check happens once, at parse time, inside `from_yaml()`.
  `ModelRouter` never reads `enabled_when` itself; it only ever sees the
  already-filtered `RouterConfig.agents` dict.
- `os.environ` reads inside `config.py` are already permitted by the existing
  Milestone 0003 isolation rule (config parsing is exempt from the
  provider-SDK isolation `grep` check that applies to the rest of
  `aegis/router/`) - no CI check needs updating for this subtask.

## Constraints

- Only `AgentConfig` and `RouterConfig.from_yaml()` in `aegis/router/config.py`
  change. `ModelRouter`, `LiteLLMClient`, and all existing Milestone 0003
  router tests are unaffected by this subtask.
- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` (C9).
- `mypy --strict` clean on `aegis/router/config.py`.
- No behaviour change for any role that omits `enabled_when`.

## Success criteria

- [ ] `RouterConfig.from_yaml()` with `OPENCLAUDE_GRPC_URL` unset: the
      returned config's `agents` dict does not contain `openclaude_agent`, and
      no exception is raised.
- [ ] `RouterConfig.from_yaml()` with `OPENCLAUDE_GRPC_URL=localhost:50051`:
      the returned config's `agents` dict contains `openclaude_agent` with
      `provider="openclaude"`.
- [ ] `AgentConfig` without `enabled_when` is parsed identically to before
      this subtask (no regressions on existing Milestone 0003 router unit
      tests - full existing suite re-run green).
- [ ] `mypy --strict` clean on `aegis/router/config.py`.
