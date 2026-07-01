# 01 — docs/config-reference.md

**Parent task:** 07.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 01.0 (schema complete)
**Blocks:** —

## Objective

Author `docs/config-reference.md` — the complete reference for `agents.yaml`
and its `providers` + `agents` sections. This document is the primary
self-service resource for adding a new provider or model without needing to
read Python source.

## Required sections

### 1. `providers` block

- All supported keys: `api_key`, `base_url` (which are required vs optional)
- `${ENV_VAR}` resolution rules: when it happens, what happens when the var is
  missing, what happens when it's empty
- Example entry for each supported provider type (`anthropic`, `deepseek`,
  `self_hosted`)
- Note on which fields are optional per provider

### 2. `agents` block

- `model` field: LiteLLM notation explained (`<provider>/<model-id>`), why the
  provider prefix must match a `providers` key
- `role` field: purpose (used by agents to look themselves up in the config)
- `fallback` field: semantics (ordered list, one attempt each, empty = no fallback)
- `timeout_s` field: units (seconds, float), default value
- `retry` sub-object: `attempts` (int, default 2), `backoff_s` (float, default 1.0),
  backoff formula (`backoff_s * attempt_number`)
- Table of defaults for each optional field

### 3. Model string examples

- `anthropic/claude-sonnet-4-6`
- `anthropic/claude-haiku-4-5-20251001`
- `deepseek/deepseek-chat`
- `self_hosted/my-local-model` (and explanation of the `openai/` alias)

### 4. Adding a new provider (step-by-step)

1. Add entry under `providers:` with `api_key` and optionally `base_url`
2. Set the corresponding env var
3. Reference from an agent's `model` or `fallback` using `<key>/<model-id>`
4. No Python changes required

### 5. Adding a new agent role (step-by-step)

1. Add entry under `agents:` with `model`, `role`, and optionally `fallback`/`timeout_s`/`retry`
2. Implement a `BaseAgent` subclass with the matching `role` property
3. Register in `app.py`

## Constraints

- Document must be self-contained: a reader with no Python context can follow
  the "Adding a new provider" guide.
- All env var names must match `.env.example`.
- RST-style `:param:` / `:type:` notation is NOT used in docs (only in
  docstrings); use plain Markdown tables and code fences.

## Success criteria

- [ ] `docs/config-reference.md` created with all 5 sections above.
- [ ] "Adding a new provider" guide walks through the `self_hosted` case as a
      worked example.
- [ ] `docs/README.md` index links to this new file.
