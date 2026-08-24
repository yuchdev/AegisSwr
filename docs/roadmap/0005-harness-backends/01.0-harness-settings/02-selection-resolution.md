# 02 - Selection & ambiguity resolution

**Parent task:** 01.0 Harness Settings & Selection Contract
**State:** ⬜ Not started
**Depends on:** 01 (`HarnessSettings` class shape), 03 (`harness/exceptions.py`)
**Blocks:** 10.0 (Harness Composition Root reads `active_backend`)

## Objective

Extend the `HarnessSettings` class defined in subtask 01 with the **C2**
single-active-backend selection contract: a `presence_signals` helper, an
`active_backend` resolved property, and a construction-time `model_validator`
that raises `HarnessConfigError` on the one ambiguous combination (selector
unset with more than one presence signal). This is the generalization of 0004's
C4 "no sibling backends to fall back to" into "exactly one active backend at a
time; the others are simply not registered." There is **no fallback chain**
(user-confirmed).

The resolution runs **once, at settings-construction time** — the ambiguity
failure is a config-shape error surfaced the moment `HarnessSettings()` is
built, never discovered mid-investigation. The distinct
`HarnessUnavailableError` (an explicitly selected backend whose signal is
absent) is **not** raised here — it belongs to composition/health-check time
(Task 10.0), because the operator asked for that backend explicitly, making it a
runtime capability failure rather than a config-shape error.

## The C2 truth table (authoritative)

| `AEGIS_CODE_INTEL_BACKEND` | Presence signals set | `active_backend` | Raises (where)                                                       |
|----------------------------|----------------------|------------------|----------------------------------------------------------------------|
| unset                      | zero                 | `None`           | — (capability unavailable; unchanged 0004 C4)                        |
| unset                      | exactly one          | that family      | — (auto-select; preserves 0004's guarantee)                          |
| unset                      | more than one        | —                | **`HarnessConfigError`** at construction                             |
| set to *X*                 | *X* present          | `"X"`            | —                                                                    |
| set to *X*                 | *X* absent           | `"X"`            | `HarnessUnavailableError` at **composition** (Task 10.0), *not* here |

A **presence signal** is a family's configured-and-non-empty enabling variable,
read off the nested settings object: `openclaude.grpc_url is not None`,
`claude_code.enabled is True`, `openhands.server_url is not None`.

Note the last row: when the selector is set, `active_backend` returns that
family verbatim regardless of its presence signal — the selector *wins*. It is
Task 10.0's composition root that then checks the selected family's signal and
raises `HarnessUnavailableError` if absent. `HarnessSettings` never raises for
this case, because a deliberately selected-but-unreachable backend is a runtime
capability failure, not a config-shape ambiguity.

## File: `aegis_swr/harness/config.py` (additions to `HarnessSettings`)

```python
from __future__ import annotations

from typing import Optional

from pydantic import model_validator

from aegis_swr.harness.exceptions import HarnessConfigError


class HarnessSettings(BaseSettings):
    # ... fields + __init__ + selector validator from subtask 01 ...

    @property
    def presence_signals(self) -> frozenset[str]:
        """Return the set of backend-family names whose presence signal is set.

        Each signal is read off the already-constructed nested settings object
        (C1) — never re-derived from ``os.environ``. Names are the bare family
        strings (``"openclaude"``, ``"claude_code"``, ``"openhands"``), the
        same values :class:`HarnessBackend` carries and the only thing ever
        placed in a :class:`HarnessConfigError` (never a URL or token, C13).

        :return: The frozenset of families currently signalled as configured.
        """
        ...

    @property
    def active_backend(self) -> Optional[str]:
        """Return the resolved active backend family name, or ``None`` (C2).

        Resolution, per the C2 truth table:

        * selector set → that family's name verbatim (the selector wins; a
          missing presence signal for it is Task 10.0's
          :class:`HarnessUnavailableError`, not decided here);
        * selector unset, exactly one presence signal → that family;
        * selector unset, zero presence signals → ``None`` (capability
          unavailable — identical observable behaviour to 0004's unset path);
        * selector unset, more than one presence signal → cannot occur on a
          successfully-constructed instance (rejected by
          :meth:`_reject_ambiguous_selection` at construction).

        :return: The active family name, or ``None`` when no backend is active.
        """
        ...

    @model_validator(mode="after")
    def _reject_ambiguous_selection(self) -> HarnessSettings:
        """Raise :class:`HarnessConfigError` when the selection is ambiguous (C2).

        The single ambiguous combination is: selector unset **and** more than
        one presence signal set. Fail loud, at construction time — never
        silently pick one backend. The error names only the offending field and
        the *set of signal names* seen, never a URL, token, or payload (C13).
        Every other row of the C2 table is resolved by :attr:`active_backend`
        without raising here.

        :return: ``self`` when the selection is unambiguous.
        :raises HarnessConfigError: selector unset with >1 presence signal.
        """
        ...
```

## Implementation notes

- **Ordering vs `__init__` unwrap.** `_reject_ambiguous_selection` is a
  `model_validator(mode="after")`; the `HarnessConfigError` it raises is wrapped
  by Pydantic into a `ValidationError` and then unwrapped by the `__init__`
  defined in subtask 01 (same mechanism `OpenClaudeSettings` uses). Callers see
  `HarnessConfigError`, not `ValidationError`.
- **`presence_signals` is the single source of truth** for both
  `active_backend` and the ambiguity check — implement it once and call it from
  both, so the definition of "a signal is set" cannot drift between the resolve
  path and the reject path.
- **The selector wins for a set selector.** When `self.backend is not None`,
  `active_backend` returns `self.backend.value` unconditionally and
  `_reject_ambiguous_selection` does nothing — a set selector is never
  ambiguous, and its reachability is Task 10.0's concern. Do not raise
  `HarnessUnavailableError` from this module; it is defined here (subtask 03)
  only so Task 10.0 can raise it from the composition root.
- **Zero-signal, selector-unset is silent** — it returns `None` and never
  raises, preserving 0004 C4's "capability unavailable" observable behavior
  exactly.
- **`HarnessConfigError` message content.** Include the sorted list of signal
  *names* seen (e.g. `["claude_code", "openclaude"]`) and the fixed remediation
  hint ("set `AEGIS_CODE_INTEL_BACKEND` to choose one") — and nothing else. No
  variable *values* (no `grpc_url`/`server_url` content), no credentials.
- **Do not memoise across mutation.** `active_backend` and `presence_signals`
  are computed properties over the current field values; `BaseSettings`
  instances are effectively read-only after construction, so recomputation is
  cheap and always consistent.

## Constraints

- Only `HarnessSettings` in `harness/config.py` changes; no new module. The `HarnessUnavailableError` type is **not** raised anywhere in this task — it is raised by Task 10.0's composition root only.
- `active_backend` returns a plain `str` family name (or `None`), not a `HarnessBackend` member, so Task 10.0's composition branch can compare against the bare family strings without importing the enum.
- No secret or payload text in any exception message or log line produced by the resolution logic (C13).

## Success criteria

- [ ] Selector unset, zero presence signals → `active_backend is None`, no exception (unchanged from 0004 C4).
- [ ] Selector unset, exactly one presence signal (e.g., only `OPENCLAUDE_GRPC_URL` set) → `active_backend == "openclaude"`; an `OPENCLAUDE_GRPC_URL`-only deployment needs zero further changes (C2).
- [ ] Selector unset, more than one presence signal (e.g. `OPENCLAUDE_GRPC_URL` **and** `CLAUDE_CODE_ENABLED=true`) → `HarnessSettings()` raises `HarnessConfigError` at construction time (not `ValidationError`).
- [ ] The raised `HarnessConfigError` names only the signal names seen and the offending field — its `str()` contains **no** URL, token, or payload text.
- [ ] Selector set to `openclaude` with `OPENCLAUDE_GRPC_URL` set → `active_backend == "openclaude"`, no exception.
- [ ] Selector set to `claude_code` with `CLAUDE_CODE_ENABLED` **unset** → `active_backend == "claude_code"` and **no** exception from `HarnessSettings` (the `HarnessUnavailableError` for this case is Task 10.0's composition-time responsibility, verified there).
- [ ] Selector set to one family while a *different* family's signal is the only one present → `active_backend` returns the *selected* family (selector wins), no `HarnessConfigError`.
- [ ] `presence_signals` returns exactly the set of families whose signal is set, computed off the nested settings objects (no `os.environ` read).
- [ ] `active_backend` returns a `str` (or `None`), never a `HarnessBackend` member.
- [ ] `ruff check src/ tests/` - clean; the full C2 truth table is covered by `tests/unit/harness/test_config.py`.
