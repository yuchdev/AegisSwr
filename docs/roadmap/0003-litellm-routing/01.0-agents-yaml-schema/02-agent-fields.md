# 02 - Per-agent `fallback`, `timeout_s`, `retry` fields

**Parent task:** 01.0 agents.yaml Schema Extension
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 03

## Objective

Extend each agent entry in `agents.yaml` with three new optional fields:
`fallback` (ordered list of model strings), `timeout_s` (float, seconds),
and `retry` (sub-object with `attempts` and `backoff_s`). Existing entries
that omit these fields must still be valid and use documented defaults.

## Target schema (illustrative entries)

```yaml
agents:
  hypothesis:
    model: anthropic/claude-sonnet-4-6
    role: primary_reasoning
    fallback:
      - deepseek/deepseek-chat
    timeout_s: 30
    retry:
      attempts: 2
      backoff_s: 1.5

  adversarial:
    model: deepseek/deepseek-chat
    role: contradiction_finder
    fallback:
      - anthropic/claude-haiku-4-5-20251001
    timeout_s: 20
    retry:
      attempts: 2
      backoff_s: 1.0

  synthesis:
    model: anthropic/claude-sonnet-4-6
    role: verdict_compilation
    fallback: []
    timeout_s: 45
    retry:
      attempts: 1
      backoff_s: 2.0

  fast_triage:
    model: self_hosted/local-model
    role: evidence_classifier
    fallback:
      - deepseek/deepseek-chat
    timeout_s: 10
    retry:
      attempts: 3
      backoff_s: 0.5
```

## Field defaults (when omitted)

| Field           | Default |
|-----------------|---------|
| `fallback`      | `[]`    |
| `timeout_s`     | `30.0`  |
| `retry.attempts`  | `2`   |
| `retry.backoff_s` | `1.0` |

## Changes

Update the `agents:` entries in `aegis/config/agents.yaml` to include the new
fields. All existing entries without the new fields remain valid - `RouterConfig`
applies defaults (see subtask 03 / Task 02.0).

## Constraints

- Model strings follow LiteLLM notation: `<provider>/<model-id>`.
  `self_hosted/<name>` is resolved to `openai/<name>` + custom `base_url`
  by `LiteLLMClient._configure_providers()`.
- `fallback: []` is explicit "no fallback" (router raises immediately on
  primary exhaustion).
- No Python changes in this subtask.

## Success criteria

- [ ] All four agent entries (hypothesis, adversarial, synthesis, fast_triage)
      include `fallback`, `timeout_s`, and `retry` fields.
- [ ] The `self_hosted/local-model` model string is used for `fast_triage`.
- [ ] Existing entries without the new fields remain parseable (tested in
      `test_config.py::test_optional_fields_have_correct_defaults`).
