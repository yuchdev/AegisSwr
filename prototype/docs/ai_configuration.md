# AI Backend Configuration Guide

This document explains how to configure and choose between the available AI backends in WinCrash Analyzer.

---

## Available Backends

| Backend | Flag | Model | Best For |
|---------|------|-------|----------|
| Google Gemini | `--ai gemini` | `gemini-1.5-pro` | Complex heap corruption, large full-memory dumps |
| OpenAI gpt-5.4 | `--ai openai` | `gpt-5.4` | Standard access violations, RIP/instruction-pointer deduction |

---

## When to Use Each Backend

### `--ai gemini` (Complex Heap Corruption)

Gemini 1.5 Pro has a very large context window, making it ideal when:

- You are analyzing a **full memory dump** (`!analyze -v` output exceeds tens of thousands of characters).
- The crash involves **heap corruption** where many surrounding allocation records need to be considered together.
- You need to cross-reference multiple thread states simultaneously.

**Example:**

```bash
wincrash-analyzer --dump crash.dmp --symbols C:\Symbols --ai gemini
```

### `--ai openai` (Standard Access Violations)

OpenAI gpt-5.4 is the logical specialist. Use it when:

- The crash is a straightforward **access violation** (`0xc0000005`) with a clean stack.
- You need structured output with **RCA / Faulting Module / Recommendation** sections.
- You want to minimize API cost (the backend automatically trims noisy middle sections of large dumps).

**Example:**

```bash
wincrash-analyzer --dump crash.dmp --symbols C:\Symbols --ai openai
```

---

## Setting API Keys

Both backends read their credentials from environment variables. Never hard-code keys in source files.

### Google Gemini

```bash
# Linux / macOS
export GEMINI_API_KEY="your-gemini-api-key"

# Windows (PowerShell)
$env:GEMINI_API_KEY = "your-gemini-api-key"
```

### OpenAI

```bash
# Linux / macOS
export OPENAI_API_KEY="your-openai-api-key"

# Windows (PowerShell)
$env:OPENAI_API_KEY = "your-openai-api-key"
```

You can also place these variables in a `.env` file at the project root (loaded automatically via `python-dotenv`).

---

## Cost Management

### Google Gemini – Usage Limits

1. Log in to [Google AI Studio](https://aistudio.google.com/).
2. Navigate to **API Keys → Usage & Quotas**.
3. Set a monthly budget alert or hard quota to avoid unexpected charges.
4. Gemini 1.5 Pro pricing is per **input + output token**; full memory dumps can be large, so monitor token usage.

### OpenAI gpt-5.4 – Usage Limits

1. Log in to the [OpenAI Platform](https://platform.openai.com/).
2. Navigate to **Settings → Limits**.
3. Set a **Monthly spend limit** and enable email alerts at a lower threshold.
4. The OpenAI backend automatically truncates dumps larger than 10,000 characters (keeps first 5,000 + last 5,000) to reduce token consumption.

---

## Token Optimization (OpenAI backend)

The `OpenAIBackend` applies smart truncation before sending data to the API:

- If the crash dump exceeds **10,000 characters**, the middle section (typically repetitive symbol-search logs) is discarded.
- The **first 5,000 characters** (exception context, registers) and the **last 5,000 characters** (stack frames) are always preserved.

This keeps the most diagnostically relevant parts of the dump while significantly reducing API costs for verbose traces.

---

## Security and PII

Crash dumps may contain local file paths or usernames. Before sending data to a cloud API:

- Review the dump for sensitive strings (e.g., `C:\Users\<username>\`).
- A PII-masking hook is planned for a future release; it will be available in `BaseAIBackend` and applied automatically before any data leaves the local machine.
