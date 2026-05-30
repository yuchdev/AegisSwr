# Aegis SWR — Implementation Status

Tracks progress against [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Updated as each phase lands.

| Phase | Name | Status | Tests |
|-------|------|--------|-------|
| 1 | Foundation & Package Setup | ✅ Complete | `test_schemas.py`, `test_settings.py`, `test_interfaces.py` |
| 2 | Data Adapter Layer | ✅ Complete | `test_data_adapter.py` |
| 3 | AI Backends | ✅ Complete | `test_ai_backends.py`, `integration/test_ai_pipeline.py` |
| 4 | Debug Backends | ✅ Complete | `test_debug_backends.py`, `integration/test_debug_pipeline.py` |
| 5 | Multi-Agent System | ✅ Complete | `test_consensus.py`, `test_agents.py`, `test_orchestrator.py` |
| 6 | Storage Backends | ✅ Complete (Postgres stub) | `test_storage_backends.py` |
| 7 | CLI & Local Mode | ✅ Complete | `test_cli.py`, `integration/test_e2e_cli.py` |
| 8 | REST API Layer | ⬜ Not started | — |
| 9 | Secure Code Sandbox | ⬜ Not started | — |
| 10 | Testing & Hardening | ⬜ Not started | — |

**Current gate status:** `ruff` clean · `mypy --strict` clean (47 files) · 228 tests passing (unit + integration).

**Test layout:** `tests/unit/` (isolated component tests, mocked SDKs), `tests/integration/` (cross-component contracts), `tests/unit/fixtures/` (shared `MockAIBackend`, `MockDebugBackend`, and data fixtures, importable as `tests.unit.fixtures.*` via `pythonpath=["."]`).

---

## Phase 1 — Foundation & Package Setup ✅

Delivered:
- `pyproject.toml` (Poetry, `aegis-swr`, `src/aegis_swr/` root, `aegis` CLI entry point, ruff/mypy/pytest config)
- Full package directory skeleton with `__init__.py` files and `py.typed`
- `core/schemas.py` — all Pydantic v2 models + `InvestigationState` TypedDict
- `core/fault_codes.py` — `FaultClass` enum + Windows/Linux/macOS mapping functions
- `core/exceptions.py` — `AegisSWRError` hierarchy
- `backends/base.py` — 7 backend ABCs
- `agents/base.py` — `BaseAgent` ABC
- `config/settings.py` + `config.yaml` — Pydantic Settings v2 with YAML source + `AEGIS__*` env overrides
- `.env.example`, `.github/workflows/ci.yml`, `tests/conftest.py`

## Phase 2 — Data Adapter Layer ✅

Delivered:
- `core/tokens.py` — `count_tokens` / `truncate_to_tokens` with tiktoken + offline fallback
- `core/data_adapter.py` — 9-stage `DataAdapter`:
  1. Hash (SHA-256) + magic-byte format detection
  2. Dump extraction (via injected `DebugBackend`)
  3. `apply_noise_filter` (DBGHELP strip, DLL-list drop, fill-pattern collapse, 8k head+tail truncation)
  4. Log processing (temporal windowing, Drain3 clustering, severity isolation, 2k-token budget)
  5. Screenshot OCR (optional pytesseract)
  6. PII scrubbing (always-on regex baseline + optional Presidio NER)
  7. User-assumption token cap (500)
  8. Code-history query (optional `CodeBackend`)
  9. `IncidentBrief` assembly
- `core/schemas.py` — added `IncidentBrief` model
- Refinements recorded in [PRODUCTION_DESIGN_SPEC.md](PRODUCTION_DESIGN_SPEC.md) §5.4

Test coverage (29 tests): hashing, format detection, every noise-filter rule, ≥60 % token reduction on the canonical CDB fixture, temporal windowing (inner/outer/out-of-window), Drain3 heartbeat dedup, PII scrubbing (emails/AWS keys/IPs/DB strings + stable tokens + map recovery), assumption cap, history-injection rule, and full-pipeline integration (crash-dump, low-symbol-coverage, log-only modes).

Fixtures: `sample_cdb_output.txt`, `sample_logs_with_pii.txt`, `sample_logs_timestamped.txt`.

## Phase 3 — AI Backends ✅

Delivered:
- `backends/ai/_base.py` — `_BaseAIBackend`: structured-output validation, one-shot correction retry, `last_usage` token accounting
- `backends/ai/anthropic_provider.py` — `AnthropicBackend`: tool-use structured output, mandatory `cache_control` ephemeral on the system block, `messages.stream()` token streaming
- `backends/ai/openai_provider.py` — `OpenAIBackend`: `json_schema` strict structured output (`_to_openai_strict_schema`), `stream_options.include_usage` streaming
- `backends/ai/__init__.py` — `create_ai_backend(settings)` factory
- ABC change: `AIAPIBackend.stream` is now a plain `def` returning `AsyncGenerator` (see spec §6.1.1)
- As-built decisions recorded in [PRODUCTION_DESIGN_SPEC.md](PRODUCTION_DESIGN_SPEC.md) §6.1.1

Mock/unit coverage (`test_ai_backends.py`, 20 tests): structured-output happy path, retry-then-valid, raise-after-retry, unstructured text, streaming, cache-control + tool assertion, no-tool-block error, OpenAI strict-schema adapter, malformed-JSON handling, and the provider factory (anthropic/openai/unknown). All SDK clients patched — no network.

## Phase 5 — Multi-Agent System Engine ✅

Delivered:
- `core/consensus.py` — `ConsensusEvaluator`: `calculate(agent_scores, fault_class)` (per-FaultClass weight matrix), `is_converged(score, threshold, same_hypothesis)`, `is_deadlocked(score, round_num, max_rounds, hitl_threshold)`
- `agents/os_kernel.py` — `OSKernelAgent`: kernel/environment specialist; injects Skeptic corrections on round > 1; prepends low-symbol-coverage warning; requests `OSKernelOutput` structured output
- `agents/code_analyst.py` — `CodeAnalystAgent`: code logic analyst; encodes probabilistic fixes in hypothesis evidence for the synthesizer
- `agents/log_historian.py` — `LogHistorianAgent`: historical pattern correlator; conditionally queries `VectorStore` when available
- `agents/skeptic.py` — `SkepticAgent`: programmatic pre-check (module absent from top frames → `confirmed=False` with zero LLM call); LLM-based checks 2+3; stores corrections in `AgentTurn.corrections` for next-round OS Kernel injection
- `core/orchestrator.py` — `Orchestrator`: LangGraph `StateGraph` with 7 nodes; consensus evaluator in Skeptic node; `_route_after_skeptic` conditional edge; `run()` with deduplication cache gate; `run_streaming()` yielding SSE events; `continue_investigation()` stub (Phase 6)
- `core/schemas.py` — added `corrections: list[str]` to `AgentTurn`; added `previous_hypothesis_key`, `current_round_scores`, `result` to `InvestigationState`
- `agents/base.py` — added `_accumulate_tokens(state)` helper

Key implementation decision: LangGraph does not persist in-place state mutations across nodes — `token_tracker` must be included in each node's return dict after the agent call, not only mutated inside `_accumulate_tokens`.

Unit coverage (35 tests across `test_consensus.py`, `test_agents.py`, `test_orchestrator.py`): CS formula at boundary values, `is_converged`/`is_deadlocked` parametrised, all 4 agents' output-schema requests, Skeptic pre-check without LLM call, Skeptic corrections injection, token tracking, full pipeline convergence (1 round), Skeptic rejection → 2nd round, deadlock → HITL, cache-hit dedup, SSE streaming events.

Integration coverage (`integration/test_ai_pipeline.py`, 5 tests): `IncidentSource → DataAdapter → IncidentBrief → AI backend → validated structured output`, driven both by the in-process `MockAIBackend` and the real `AnthropicBackend` over a mocked SDK; asserts adapter-extracted fields reach the prompt, PII stays scrubbed, token usage is tracked, and the low-symbol-coverage warning propagates. These integration tests retroactively cover the Phase 1 + Phase 2 contracts as well.

## Phase 4 — Debug Backends ✅

Delivered:
- `backends/debug/_base.py` — `_BaseDebugBackend`: `extract()` template (validate → build argv → RAII subprocess w/ timeout → parse), `_symbol_score`, `normalize_address`
- `backends/debug/cdb_worker.py` — `CdbBackend` (Windows): ported `!analyze -v` regexes, `parse_cdb_frames`, NTSTATUS→FaultClass, symbol-server chain
- `backends/debug/gdb_worker.py` — `GdbBackend` (Linux): `bt` parsing, `parse_gdb_frames`, signal→FaultClass
- `backends/debug/lldb_worker.py` — `LldbBackend` (macOS): `bt all` parsing, `parse_lldb_frames`, Mach exception→FaultClass
- `backends/debug/_symbol_path.py` — `resolve_symbol_path` (config → `AEGIS_SYMBOL_CACHE` → platform default)
- `backends/debug/__init__.py` — `create_debug_backend(settings, platform=None)` factory
- `core/exceptions.py` — added `DebugExtractionError`
- As-built decisions recorded in [PRODUCTION_DESIGN_SPEC.md](PRODUCTION_DESIGN_SPEC.md) §6.2.1

Unit coverage (`test_debug_backends.py`, 22 tests): per-backend fault-class mapping, structured field + stack-frame parsing, `symbol_resolution_score`, noise-filter application, CDB timestamp + source-line parsing, command-sequence construction, validation errors (no dump / missing file), subprocess errors (missing binary → `PlatformNotSupportedError`, timeout → `DebugExtractionError`), the platform factory (win32/linux/darwin/unsupported), and symbol-path resolution. All `subprocess.run` calls mocked — no debugger binary required.

Integration coverage (`integration/test_debug_pipeline.py`, 3 tests): the *real* `CdbBackend`/`GdbBackend` driven by fixture subprocess output, run through `DataAdapter` to produce an `IncidentBrief` (asserting fault class, faulting module, symbol score, frame count, content hash, noise filtering), then into `MockAIBackend` for a validated `OSKernelOutput`. Covers Steps 1, 2, 4 (and 4→3) together.

Fixtures added: `sample_gdb_bt.txt`, `sample_lldb_bt.txt` (CDB reuses `sample_cdb_output.txt`).

Additional Phase 4 deliverables (WinDbg JS backend):
- `backends/debug/windbg_js_worker.py` — `WinDbgJSBackend`, `_CallbackBridge` (RAII, ephemeral port, per-instance queue), `_make_handler` closure
- `backends/debug/assets/windbg_diagnostic.js` — versioned JS diagnostic script with `__CALLBACK_URL__`/`__MAX_FAULTING_FRAMES__`/`__MAX_OTHER_FRAMES__` substitution tokens; all DDM accesses wrapped in `try/catch`
- `backends/debug/__init__.py` — updated factory with `_windbg_js_available()` probe (`lru_cache`), `engine: auto/cdb/windbg_js` selection on Windows
- `config/settings.py` + `config.yaml` — `DebugSettings` extended with `engine`, `callback_timeout_seconds`, `max_faulting_frames`, `max_other_thread_frames`
- `tests/unit/fixtures/sample_windbg_js_payload.json` — realistic DDM JSON fixture (5 faulting frames, 2 other threads)

## Phase 7 — CLI & Local Mode ✅

Delivered:
- `cli/_config.py` — `load_analyze_config`, `save_analyze_config`, `merge_options`. Typer 0.26 compatibility: compares `source.name == "COMMANDLINE"` by string rather than by identity (Typer 0.26 bundles `typer._click.core.ParameterSource` with different enum values from `click.core`).
- `cli/_logging.py` — `configure_logging(severity)` with sensitive-data loguru filter (redacts API key patterns; ported from prototype `SensitiveFilter`).
- `cli/_formatters.py` — `json_formatter` and `rich_formatter` (root-cause panel, agent dialogue table, mitigation, code diff, HITL warning panel).
- `cli/commands.py` — `aegis analyze` (full flag set, `--config`/`--save-config` JSON round-trip), `aegis export` (migrate via `load_recent`), `aegis server` (stub), `aegis config show` / `aegis config set`.
- `backends/base.py` + all storage backends — added `load_recent(limit)` to `RelationalStore` ABC.
- Typer upgraded 0.13.1 → 0.26.3 to fix Click 8.4 `make_metavar(ctx)` incompatibility.
- `pyproject.toml` — `typer = "^0.26"`.
- Spec updated: `PRODUCTION_DESIGN_SPEC.md §12`, `IMPLEMENTATION_PLAN.md Phase 7`, `AGENTIC_IMPLEMENTATION_PLAN.md Step 7`.

Unit coverage (`test_cli.py`, 12 tests): help flags, --save-config writes JSON, --config sets defaults, CLI flag overrides config, json/rich output, HITL exit code 1, config show redacts, config set writes YAML, config helpers.  
Integration coverage (`test_e2e_cli.py`, 4 tests): JSON output E2E, rich output, log-only mode, config round-trip.
