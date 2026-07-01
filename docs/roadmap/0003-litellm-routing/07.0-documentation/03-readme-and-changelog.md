# 03 - README.md update + CHANGELOG.md

**Parent task:** 07.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 01, 02
**Blocks:** -

## Objective

Update the project `README.md` with a **Model Configuration** section and
update `CHANGELOG.md` with an `[Unreleased]` entry for this milestone.

## README.md changes

Add a **Model Configuration** section (after the quick-start / installation
section) with the following content:

1. A one-paragraph summary: "All model calls in Aegis SWR are routed through
   a unified LiteLLM router. Model selection, fallback chains, and retry
   policy are configured in `aegis/config/agents.yaml`. No Python changes are
   required to add or swap a model."

2. Required environment variables (table):

   | Variable           | Required for     | Description                      |
   |--------------------|------------------|----------------------------------|
   | `ANTHROPIC_API_KEY`| Anthropic models | API key from console.anthropic.com |
   | `DEEPSEEK_API_KEY` | DeepSeek models  | API key from platform.deepseek.com |
   | `VLLM_BASE_URL`    | Self-hosted vLLM | Base URL of the vLLM server       |
   | `VLLM_API_KEY`     | Self-hosted vLLM | Optional auth key (can be empty)  |

3. Link: "See [docs/config-reference.md](docs/config-reference.md) for full
   `agents.yaml` reference."

## CHANGELOG.md changes

Add under `[Unreleased]` (or create the section if absent):

```markdown
### Added
- LiteLLM model router (`aegis/router/`) providing a unified async completion
  interface across Anthropic, DeepSeek, and self-hosted vLLM providers
- Declarative fallback chains and retry policy per agent role in `agents.yaml`
- Router telemetry events (`RouterCallStarted`, `RouterCallCompleted`,
  `RouterCallFailed`, `RouterFallbackUsed`) emitted on the existing EventBus
- `NullClient` and `--dry-run` CLI flag for pipeline testing without API keys
- Integration test suite (skipped unless API keys present in environment)
- `docs/config-reference.md` - full `agents.yaml` reference
- `docs/router-architecture.md` - router internals and boundary contract
```

## Success criteria

- [ ] `README.md` has a **Model Configuration** section with the env var table.
- [ ] `README.md` links to `docs/config-reference.md`.
- [ ] `CHANGELOG.md` has the `[Unreleased]` entry with all bullet points above.
