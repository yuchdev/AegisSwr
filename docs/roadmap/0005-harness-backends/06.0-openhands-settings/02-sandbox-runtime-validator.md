# 02 - Sandbox-runtime enforcement validator

**Parent task:** 06.0 OpenHands Settings & Config
**State:** ⬜ Not started
**Depends on:** 01 (`OpenHandsSettings` Pydantic class — this validator
cross-checks its `runtime_mode` field and adds one new field)
**Blocks:** 07.0 (the sidecar/process lifecycle relies on the runtime having
been validated as sandboxed-by-default before it is launched)

## Objective

Add the security enforcement that makes the Docker sandbox a **requirement, not
an option** (milestone contract C8 item 2). Extend `OpenHandsSettings` with an
explicit `allow_unsandboxed_runtime` override field and a cross-field
model-validator that **rejects construction** when `runtime_mode` selects a
non-sandboxed runtime *unless* that override is explicitly set. This mirrors the
discipline `OpenClaudeSettings` applies to write-capable tools (which are
opt-in and warn loudly) and, more strictly, the OpenClaude allowlist-relaxation
posture referenced throughout the milestone: the safe default is enforced, and
opting out demands deliberate, auditable friction.

Selecting a non-sandboxed runtime is exactly the kind of security-posture
relaxation the milestone requires an **ADR** for (see Constraints) — the
override flag alone lets construction proceed at runtime, but the *decision* to
run OpenHands outside its container must be recorded per project policy before
it is used in any real deployment.

## File: `aegis_swr/openhands/config.py`

**New field** (env var → field name → type → default):

| Env var                        | Field                       | Type   | Default |
|--------------------------------|-----------------------------|--------|---------|
| `OPENHANDS_ALLOW_UNSANDBOXED`  | `allow_unsandboxed_runtime` | `bool` | `False` |

```python
from pydantic import model_validator


class OpenHandsSettings(BaseSettings):
    # ... fields from subtask 01 ...

    allow_unsandboxed_runtime: bool = False
    """Explicit opt-out of the Docker sandbox.

    Defaults to ``False``. When ``False`` (the default), selecting a
    non-sandboxed :attr:`runtime_mode` (any value in ``_UNSANDBOXED_RUNTIMES``,
    e.g. ``"local"``) raises :class:`OpenHandsConfigError` at construction time.
    Setting it ``True`` permits a non-sandboxed runtime but emits a loud
    ``logger.warning``; per milestone policy this must be accompanied by an ADR
    recording why the hostile-payload sandbox was disabled (C8).
    """

    @model_validator(mode="after")
    def _enforce_sandbox_default(self) -> "OpenHandsSettings":
        """Reject a non-sandboxed runtime unless explicitly overridden.

        Docker sandboxing is a design requirement of the OpenHands backend
        (C8): Aegis SWR treats every incident payload as hostile, so the
        runtime that executes navigation tools must be sandboxed by default.
        A non-sandboxed :attr:`runtime_mode` therefore raises
        :class:`OpenHandsConfigError` unless :attr:`allow_unsandboxed_runtime`
        is explicitly ``True``, in which case a warning is emitted instead.

        :raises OpenHandsConfigError: when :attr:`runtime_mode` is a
            non-sandboxed runtime and :attr:`allow_unsandboxed_runtime` is
            ``False``.
        :return: the validated settings instance.
        """
        ...
```

## Implementation notes

- The check is a `model_validator(mode="after")`, not a `field_validator`,
  because it depends on **two** fields (`runtime_mode` and
  `allow_unsandboxed_runtime`); a `field_validator` on `runtime_mode` cannot see
  the override reliably regardless of field declaration order, and `mode="after"`
  runs once all fields are populated and individually validated.
- Enforcement logic:
  - If `runtime_mode in _SANDBOXED_RUNTIMES` (`"docker"`, `"remote"`) →
    no-op; return `self` unchanged. This is the default path and must add zero
    friction.
  - If `runtime_mode in _UNSANDBOXED_RUNTIMES` (`"local"`) and
    `allow_unsandboxed_runtime is False` → raise
    `OpenHandsConfigError(field="runtime_mode", reason=...)`. The `reason` states
    that the runtime is non-sandboxed and that
    `OPENHANDS_ALLOW_UNSANDBOXED=true` plus an ADR are required — it names the
    override var but **no** payload/secret text (C13).
  - If `runtime_mode in _UNSANDBOXED_RUNTIMES` and
    `allow_unsandboxed_runtime is True` → permit, but emit a single
    `logger.warning` that the Docker sandbox is disabled and that an ADR is
    required per milestone policy. This is the same "permit-but-warn-loudly"
    shape as `OpenClaudeSettings._validate_allowed_tools` on write-capable
    tools.
- Because subtask 01's `__init__` already unwraps `OpenHandsConfigError` from
  Pydantic's `ValidationError`, an error raised inside this model-validator
  surfaces to callers as a bare `OpenHandsConfigError` with no extra work — the
  unwrap logic covers validators of both kinds.
- `allow_unsandboxed_runtime` is parsed from `OPENHANDS_ALLOW_UNSANDBOXED` via
  the family `env_prefix` (bool coercion is Pydantic's default). No CSV handling
  needed.
- This subtask does **not** verify Docker is actually installed or that the
  chosen runtime is reachable — that is a composition/health-check concern in
  Task 07.0. This validator governs only the settings-shape decision: which
  runtime the operator asked for, and whether they cleared the guardrail to ask
  for a non-sandboxed one.

## Constraints

- **Relaxing the sandbox default requires an ADR** (`docs/adr/`, MADR). Per
  [plan.md](/docs/roadmap/0005-harness-backends/plan.md) C8, a non-sandboxed runtime "requires an explicit override plus an
  ADR (same discipline as the OpenClaude allowlist)." The `model_validator`
  enforces the explicit-override half; the ADR is a process obligation the
  warning message must point at. This subtask must not silently permit an
  unsandboxed runtime, and must not treat the override flag as sufficient on its
  own to skip the warning.
- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` (C13).
- The error `reason` and warning message name only the field and the override
  env var — never any `server_url` value, credential, or payload text (C13).
- `replace_optional.py --check` clean; `ruff` clean; no new `# type: ignore`.
- No import of the OpenHands client library or any sibling backend package (C3).

## Success criteria

- [ ] `OpenHandsSettings()` (default `runtime_mode="docker"`) constructs without
      raising and emits no sandbox warning.
- [ ] `OpenHandsSettings(runtime_mode="remote")` constructs without raising
      (a sandboxed runtime) and emits no sandbox warning.
- [ ] `OpenHandsSettings(runtime_mode="local")` raises `OpenHandsConfigError`
      whose message names `OPENHANDS_ALLOW_UNSANDBOXED` and references the ADR
      requirement, and contains no `server_url`/payload text.
- [ ] `OpenHandsSettings(runtime_mode="local", allow_unsandboxed_runtime=True)`
      constructs without raising **and** logs a single warning that the Docker
      sandbox is disabled and an ADR is required.
- [ ] `OPENHANDS_RUNTIME=local` alone in the environment raises
      `OpenHandsConfigError`; adding `OPENHANDS_ALLOW_UNSANDBOXED=true` permits
      it with a warning.
- [ ] `allow_unsandboxed_runtime=True` with a sandboxed `runtime_mode`
      (`"docker"`/`"remote"`) constructs without raising and emits no warning
      (the override is inert when the runtime is already sandboxed).
- [ ] `replace_optional.py --check` clean; `ruff` clean.
