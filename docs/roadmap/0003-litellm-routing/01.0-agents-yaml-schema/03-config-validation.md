# 03 — RouterConfig validation contract

**Parent task:** 01.0 agents.yaml Schema Extension
**State:** ⬜ Not started
**Depends on:** 01, 02
**Blocks:** 02.0 (config dataclasses)

## Objective

Define the validation contract that `RouterConfig.from_yaml()` (implemented in
Task 02.0) must enforce. This subtask documents the required error conditions
and acceptance criteria so the Task 02.0 implementation and the `test_config.py`
tests have an agreed spec to target.

## Validation rules

### R1 — Missing environment variables

When `${ENV_VAR}` is referenced in `api_key` or `base_url` but the variable is
not set in the environment:

- **Behavior:** raise `ConfigValidationError` listing **all** missing variable
  names in one message, not just the first.
- **Message format:** `"Missing environment variables: ANTHROPIC_API_KEY, VLLM_BASE_URL"`
- **Rationale:** fail-all-at-once avoids the "fix one, discover another" loop
  at startup.

### R2 — Undefined provider reference

When an agent's `model` string references a provider prefix (e.g.
`anthropic/...`) but no matching key exists in `providers:`:

- **Behavior:** raise `ConfigValidationError` with a message naming the
  missing provider key and the agent that references it.
- **Message format:** `"Agent 'hypothesis' references unknown provider 'anthropic'. Defined providers: deepseek, self_hosted"`

### R3 — Idempotency

`RouterConfig.from_yaml(path)` called twice on the same file with the same
environment returns two objects that compare equal (`==`). This is the frozen
dataclass contract.

### R4 — Unknown role lookup

`RouterConfig.agent_for_role(role)` raises `KeyError` with a message that
names both the requested role and the available roles:

```
KeyError: "Unknown role 'fast_triage'. Available roles: primary_reasoning, contradiction_finder, verdict_compilation"
```

## Constraints

- Validation runs eagerly at `from_yaml()` time, not lazily on first use.
- An empty `VLLM_API_KEY` (`api_key: ${VLLM_API_KEY}` where the var is set to
  `""`) is **valid** — empty string is a legitimate unauthenticated credential.
  Only *missing* (unset) vars raise R1.

## Success criteria

- [ ] R1 through R4 are documented here with exact error message formats.
- [ ] These rules are covered by `tests/router/test_config.py` (see Task 05.0,
      subtask 01).
- [ ] `RouterConfig.from_yaml()` in Task 02.0 is implemented to these rules.
