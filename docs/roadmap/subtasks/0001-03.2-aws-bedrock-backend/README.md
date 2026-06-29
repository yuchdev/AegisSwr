# Subtask set 0001-03.2 - AWS Bedrock Backend

Atomic decomposition of milestone **3.2 AWS Bedrock Backend** from
[`docs/roadmap/tasks/0001-generic_implementation_plan.md`](../../tasks/0001-generic_implementation_plan.md#milestone-32---aws-bedrock-backend).

Progress is tracked in
[`docs/roadmap/progress/implementation_status.md`](../../progress/implementation_status.md).

## Scope & current reality

A working Bedrock backend already exists in the tree
(`src/aegis_swr/backends/ai/aws_bedrock_provider.py`), reached through the
**Converse API** with forced-tool-use structured output, dual-mode
authentication (SigV4 credential chain *or* `AWS_BEARER_TOKEN_BEDROCK` bearer
token), `converse_stream` streaming, extended-thinking gating, and
botocore-error sanitisation into `AIBackendError`. Settings, the factory route,
and a substantial test suite are in place.

Therefore each subtask below is specified **and** annotated with its real
current state, so this set is simultaneously an implementation spec, a
verification checklist, and a gap-closure plan. "Done" subtasks still carry
their full spec so the milestone can be re-derived or re-reviewed end to end.

## Design agreements honoured (from `.claude/CLAUDE.md` & root `CLAUDE.md`)

- **Factory-Strategy** for the backend family; provider branching only inside
  `create_ai_backend`.
- **Typing**: full annotations, `mypy --strict` clean, always `Optional[T]`
  (never `T | None`).
- **Error handling**: every external call gets a timeout and a defined failure
  path; no bare `except:`; no raw `botocore` exception escapes.
- **Security**: no credentials in config files or logs; credentials read from
  the environment / standard AWS chain; `SensitiveFilter` covers new sinks.
- **Testing**: every feature ships unit tests; every external integration ships
  an integration test with the external mocked (zero network).
- **Provider-neutral parity**: Bedrock implements the same `_BaseAIBackend`
  contract (`generate` / `stream` / `_invoke` / `has_reasoning`) as the
  Anthropic and OpenAI providers.

## Subtasks

| #                                               | Subtask                                                         | Primary files                                 | State                               |
|-------------------------------------------------|-----------------------------------------------------------------|-----------------------------------------------|-------------------------------------|
| [01](01-configuration-model.md)                 | Configuration model (`BedrockSettings` + `AISettings`)          | `config/settings.py`                          | ✅ Done - verify                     |
| [02](02-error-taxonomy-and-mapping.md)          | Error taxonomy & sanitised botocore mapping                     | `core/exceptions.py`, provider                | ✅ Done - broaden coverage           |
| [03](03-client-and-authentication.md)           | Client construction & dual-mode auth                            | provider                                      | ✅ Done - add region-precedence test |
| [04](04-converse-generate-structured-output.md) | Converse `generate()`: request, structured output, parse, usage | provider                                      | ✅ Done                              |
| [05](05-streaming.md)                           | Streaming via `converse_stream`                                 | provider                                      | ✅ Done - add interruption test      |
| [06](06-extended-thinking-and-reasoning.md)     | Extended thinking & `has_reasoning`                             | provider, `config/settings.py`                | ✅ Done - add reasoningContent test  |
| [07](07-factory-routing.md)                     | Factory routing for `provider="bedrock"`                        | `backends/ai/__init__.py`                     | ✅ Done                              |
| [08](08-cli-config-and-env-exposure.md)         | CLI flag, config template & `.env.example`                      | `cli/`, `config.example.json`, `.env.example` | 🔶 Partial                          |
| [09](09-documentation.md)                       | Configuration & CLI documentation                               | `docs/config/`                                | ✅ Done - verify                     |
| [10](10-integration-tests.md)                   | End-to-end integration tests                                    | `tests/integration/`                          | ✅ Done - extend                     |
| [11](11-prompt-caching-optional.md)             | Prompt caching via `cachePoint` (optional)                      | provider                                      | ⬜ Deferred                          |

## Dependency / sequencing

```
01 Configuration ─┬─► 02 Errors ─► 03 Client/Auth ─► 04 generate() ─┬─► 05 Streaming
                  │                                                  ├─► 06 Thinking
                  └────────────────────────────────► 07 Factory ◄───┘
                                                          │
                  08 CLI/config/env ◄─────────────────────┘
                  09 Docs        (follows 08)
                  10 Integration (follows 04, 05, 07)
                  11 Caching     (optional; follows 04)
```

**Definition of done for the milestone:** all of 01-10 satisfied and green under
`poetry run pytest tests/unit/ tests/integration/ -q`; `mypy --strict` clean;
`ruff` clean; status tracker row `3.2 AWS Bedrock` flipped to ✅ Complete.
Subtask 11 is an explicitly deferred enhancement and is **not** required for the
milestone.
