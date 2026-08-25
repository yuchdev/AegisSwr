# 03 - `harness/exceptions.py`

**Parent task:** 01.0 Harness Settings & Selection Contract
**State:** ✅ Complete
**Depends on:** none
**Blocks:** 01, 02 (this task); 10.0 (downstream — the composition root raises `HarnessUnavailableError`)

## Objective

Create `aegis_swr/harness/exceptions.py`, the leaf module defining the two typed
errors the C2 truth table distinguishes:

- **`HarnessConfigError`** — a **construction-time**, config-shape ambiguity
  error (selector unset with more than one presence signal; an unrecognized
  selector value). Raised by `HarnessSettings` (subtasks 01 and 02).
- **`HarnessUnavailableError`** — a **composition-time** runtime capability
  failure: a backend the operator *explicitly selected* is not
  reachable/enabled (its presence signal is absent). Raised by Task 10.0's
  composition root / health check, **not** by `HarnessSettings`.

The two are deliberately **separate hierarchies** — neither subclasses the
other — so callers catch precisely the failure they mean: a config-shape
ambiguity that must be fixed before the process can run, versus a runtime
capability that is simply unavailable this run. This mirrors OpenClaude's
`OpenClaudeConfigError` (a `ValueError`, raised from settings validators) vs
`OpenClaudeUnavailableError` (a plain `Exception`, raised at runtime) split.

Both carry **only** the offending field/backend names and the set of *signal
names* seen — **never** a URL value, token, credential, or any incident payload
text (C13). This is a leaf module: it imports nothing from `aegis_swr.harness`
(or any backend package, `grpc`, `pydantic`, or a client library), so
`config.py` and (later) `composition.py` can both import it without a cycle.

## File: `aegis_swr/harness/exceptions.py`

```python
from __future__ import annotations

from typing import Optional


class HarnessConfigError(ValueError):
    """Raised on an ambiguous or invalid harness selection (C2, construction-time).

    A **config-shape** error surfaced the moment ``HarnessSettings()`` is built:
    the selector is unset while more than one backend presence signal is set (the
    harness must never silently pick one), or the selector holds an unrecognised
    family name. Subclasses ``ValueError`` so it can be raised inside a Pydantic
    field/model validator and unwrapped by ``HarnessSettings.__init__`` (the same
    pattern :class:`OpenClaudeConfigError` uses).

    Distinct from :class:`HarnessUnavailableError` (a runtime capability
    failure); neither subclasses the other. The message and attributes carry only
    field names and *signal names* — never a variable value, secret, or payload
    (C13).

    :param reason: Human-readable, payload-free explanation of the ambiguity.
    :param signals: The set of presence-signal family names seen at
        construction, or ``None`` when not applicable (e.g. a bad selector
        value). Names only — never the variables' values.
    :param field: The offending settings field name; defaults to ``"backend"``
        (the selector).
    :ivar reason: The violation explanation.
    :ivar signals: The signal names seen, or ``None``.
    :ivar field: The offending field name.
    """

    def __init__(
        self,
        reason: str,
        *,
        signals: Optional[frozenset[str]] = None,
        field: str = "backend",
    ):
        """Record the payload-free *reason*, *signals* seen, and offending *field*."""
        self.reason = reason
        self.signals = signals
        self.field = field
        super().__init__(f"HarnessSettings.{field}: {reason}")


class HarnessUnavailableError(Exception):
    """Raised when an explicitly-selected backend is not reachable (C2, composition-time).

    A **runtime capability** failure, distinct from the config-shape
    :class:`HarnessConfigError`: the operator set ``AEGIS_CODE_INTEL_BACKEND`` to
    a family whose presence signal is absent (e.g. ``backend=claude_code`` with
    ``CLAUDE_CODE_ENABLED`` unset). Because the choice was explicit, this is a
    capability failure surfaced at composition / health-check time by Task 10.0's
    composition root — **not** at settings construction, and never by
    :class:`HarnessSettings`. Per C2 there is no fallback: the caller reports the
    capability as unavailable.

    Neither subclasses the other. Carries only the selected backend's family name
    and the signal names seen — never a URL, token, credential, or payload (C13).

    :param backend: The explicitly-selected family name that is unavailable
        (e.g. ``"claude_code"``).
    :param signals: The presence-signal family names actually seen, for
        diagnostics. Names only — never the variables' values. Defaults to the
        empty frozenset.
    :ivar backend: The unavailable selected family name.
    :ivar signals: The signal names seen.
    """

    def __init__(self, backend: str, *, signals: frozenset[str] = frozenset()):
        """Record the unavailable *backend* and the (payload-free) *signals* seen."""
        self.backend = backend
        self.signals = signals
        super().__init__(
            f"Selected code-intelligence backend '{backend}' is not available: "
            f"its presence signal is not set (signals seen: {sorted(signals)})."
        )
```

## Implementation notes

- **`HarnessConfigError` subclasses `ValueError`** specifically so it can be
  raised from a `field_validator` (subtask 01's bad-selector case) and a
  `model_validator` (subtask 02's ambiguity case) and then unwrapped from
  Pydantic's `ValidationError` by `HarnessSettings.__init__` — identical to
  `OpenClaudeConfigError`. `HarnessUnavailableError` subclasses the base
  `Exception` because it is raised imperatively at composition time, never
  through a validator.
- **Payload-free by construction.** The only free-text a caller may pass is
  `reason` (subtask 02 supplies a fixed, payload-free string) and the
  `signals`/`backend` *names*. Do not add a field that could carry a URL value,
  token, or incident text. This keeps the errors safe to log through
  `SensitiveFilter` and safe to surface in an API error body (C13).
- **`signals` are names, not values.** Store `frozenset[str]` of family names
  (`"openclaude"`, `"claude_code"`, `"openhands"`) — the same strings
  `HarnessBackend` carries — so a formatted message can list *which* signals
  collided without ever printing what they were set to.
- **Leaf module discipline.** Import only from `typing`. No import of
  `harness.config`, any backend package, `grpc`, `pydantic`, or a client library
  — so both `config.py` (subtasks 01/02) and `composition.py` (Task 10.0) can
  depend on this module with no import cycle, exactly as
  `openclaude/exceptions.py` is a leaf for its package.
- These names and signatures are the **canonical** definitions for the whole
  milestone (there is no later "moves to exceptions.py" step as there was for
  OpenClaude's forward-declared config error — this module *is* the home from
  the start).

## Constraints

- No import of any `aegis_swr` module, backend package, `grpc`, `pydantic`, or a client library — leaf module only.
- Neither exception subclasses the other (C2). No exception message or attribute ever formats a variable value, credential, or dump/log/stack text (C13).
- Every public class and its `__init__` carries an RST-style docstring.

## Success criteria

- [ ] `aegis_swr/harness/exceptions.py` defines `HarnessConfigError` and `HarnessUnavailableError`.
- [ ] `issubclass(HarnessConfigError, ValueError)` is `True`; `issubclass(HarnessUnavailableError, Exception)` is `True`.
- [ ] `issubclass(HarnessUnavailableError, HarnessConfigError)` is `False` and `issubclass(HarnessConfigError, HarnessUnavailableError)` is `False` (neither subclasses the other, C2).
- [ ] `HarnessConfigError("...", signals=frozenset({"openclaude","claude_code"}))` exposes `.reason`, `.signals`, and `.field == "backend"`, and its `str()` contains no variable value.
- [ ] `HarnessUnavailableError("claude_code")` exposes `.backend == "claude_code"` and `.signals == frozenset()`, and its `str()` contains no variable value, token, or payload.
- [ ] The module imports nothing from `aegis_swr.*`, any backend package, `grpc`, `pydantic`, or a client library (leaf-module check).
- [ ] Both classes and their `__init__` methods have RST-style docstrings.
- [ ] `ruff check src/ tests/` - clean.
