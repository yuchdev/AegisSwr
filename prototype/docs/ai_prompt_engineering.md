# AI Prompt Engineering

This document provides full transparency into the system prompts used by each
AI backend.  Understanding *how* the AI interprets a crash stack helps you
judge the quality of the Root Cause Analysis (RCA) output and tune the prompts
for your specific environment.

---

## 1. Why Prompt Transparency Matters

LLMs are sensitive to instruction framing.  Small wording changes can shift the
model's focus from "list all possible causes" to "identify the single most
likely cause".  Publishing the exact prompts used in production allows you to:

- **Reproduce results** independently.
- **Audit** the analysis for accuracy.
- **Customise** the prompts for your organisation's naming conventions or
  severity taxonomy.

---

## 2. Gemini Backend (`gemini.py`)

### 2.1 System Instruction

```text
You are an expert Windows Kernel debugger.
Analyze the provided stack trace.
Identify the specific function and offset where the fault occurred.
Explain the Exception Code (e.g., 0xc0000005 as Null Pointer or Use-After-Free).
```

### 2.2 User Prompt Template

```text
Analyze this crash dump and provide a Root Cause Analysis:

{stack_trace}
```

`{stack_trace}` is replaced at runtime with the sanitized CDB or JS output
(after `0xCCCCCCCC`-style fill patterns are removed by the Orchestrator).

### 2.3 Model Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Model | `gemini-1.5-pro` | Largest context window; handles full-memory dumps |
| Safety – HATE | `BLOCK_NONE` | Stack traces may contain offensive symbol names |
| Safety – HARASSMENT | `BLOCK_NONE` | Same rationale |
| Safety – SEXUAL | `BLOCK_NONE` | Same rationale |
| Safety – DANGEROUS | `BLOCK_NONE` | Same rationale |

> **Note:** Safety filters are set to `BLOCK_NONE` because crash dumps
> frequently contain binary data, offensive-looking function names from
> obfuscated malware, or raw user-generated content embedded in heap memory.
> Blocking this content would prevent useful diagnostic output.

### 2.4 Tuning Tips

- **Add module context:** Prepend a one-paragraph description of your
  application's architecture before `{stack_trace}` to help the model
  distinguish your modules from OS modules.
- **Request structured output:** Append `Return your analysis as Markdown with
  sections: ## Root Cause, ## Faulting Module, ## Recommendation.` to
  standardise parsing downstream.

---

## 3. OpenAI Backend (`openai.py`)

### 3.1 System Message

```text
You are a senior Windows systems engineer.
Provide a structured analysis with the following sections:
Root Cause Analysis (RCA), Faulting Module, and Recommendation.
```

### 3.2 User Prompt Template

```text
Analyze this stack trace:

{sanitized_stack_trace}
```

`{sanitized_stack_trace}` is the output of `_smart_truncate()`: if the raw
trace exceeds **10,000 characters**, the middle section is replaced with
`[... middle section truncated ...]`, keeping the first 5,000 characters
(exception context, registers) and the last 5,000 characters (innermost stack
frames).

### 3.3 Model Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Model | `gpt-5.4` | Best reasoning for structured RCA |
| Timeout | `60 s` | Prevents hanging on slow API responses |
| Truncation threshold | 10,000 chars | Balances cost and context quality |
| Head kept | 5,000 chars | Exception code and register context |
| Tail kept | 5,000 chars | Innermost (most relevant) stack frames |

### 3.4 Tuning Tips

- **Reduce truncation threshold** to lower API cost at the expense of
  completeness.  Edit `_TRUNCATE_THRESHOLD` in `backends/ai/openai.py`.
- **Increase timeout** for slow enterprise proxies.
- **Add JSON mode:** Append `response_format={"type": "json_object"}` to the
  API call and update the system prompt to request JSON output for automated
  downstream parsing.

---

## 4. Sanitization Before AI Inference

Before any prompt reaches the AI API, the `CrashOrchestrator` applies a
lightweight sanitization step:

```python
_FILL_PATTERN = re.compile(r"\b0x[cC]{8}\b")

def _sanitize(self, raw_data: str) -> str:
    return _FILL_PATTERN.sub(" ", raw_data)
```

This strips uninformative `0xCCCCCCCC`-style fill patterns (used by MSVC
debug builds to mark uninitialised stack memory) that inflate token counts
without adding diagnostic value.

---

## 5. Designing Custom Prompts

If neither built-in backend meets your needs, you can subclass `AIBackendBase`
and supply your own prompt:

```python
from wincrash_analyzer.backends.ai.base import AIBackendBase
from wincrash_analyzer.core.exceptions import AIBackendError


class CustomBackend(AIBackendBase):
    _SYSTEM = (
        "You are an embedded-systems debugger specialising in ARM Cortex-M faults. "
        "Identify the HardFault cause from the register dump."
    )

    def analyze(self, stack_trace: str) -> str:
        # Call your preferred LLM API here.
        ...
```

Register your backend by adding a branch to
`wincrash_analyzer/backends/ai/factory.py`.

---

## 6. Security Considerations

- **Never log raw prompts** at `DEBUG` level in production; they may contain
  sensitive heap data extracted from memory.
- The `SensitiveFilter` in `cli.py` automatically redacts `GEMINI_API_KEY=…`
  and `OPENAI_API_KEY=…` patterns from all log records.
- Use `.env` files (loaded by `python-dotenv`) instead of exporting keys in
  shell scripts to reduce the risk of keys appearing in process lists.
