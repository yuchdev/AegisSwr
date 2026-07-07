# Agent Policy File (`agents.json`)

> `<config-dir>` = `~/.aegis-swr/`

The per-fault-class **domain-authority weights** and the **agent panel policy**
for the Synthetic War Room live in:

```
<config-dir>/agents.json
```

A template lives at [`agents.example.json`](../../agents.example.json) - copy it
to the default path:

```bash
cp agents.example.json <config-dir>/agents.json
```

`Settings` loads this file and mounts its `weights` sub-object under the
`agent_weights` key and its `panel` sub-object under the `agent_panel` key. A
missing or malformed file falls back to the built-in defaults (identical to the
example), so the file is optional.

---

## File shape

The file has a **two-key top-level structure**:

```json
{
  "weights": { "<fault_class>": { "<agent_key>": <weight>, ... }, ... },
  "panel":   { "default_panel": [...], "per_fault_class": {...} }
}
```

### `weights` section

A JSON object keyed by **fault class**. Each value is an object of agent weights:

```json
{
  "weights": {
    "memory_access_violation": {
      "os_kernel": 0.40,
      "code_analyst": 0.35,
      "log_historian": 0.15,
      "skeptic": 0.10
    },
    "unknown": {
      "os_kernel": 0.30,
      "code_analyst": 0.35,
      "log_historian": 0.20,
      "skeptic": 0.15
    }
  }
}
```

Weight keys are arbitrary agent keys - the schema is agent-count-agnostic so
the roster can grow without a format change. Any agent key absent from a
fault-class entry falls back to the priority-normalized default at runtime.

| Default weight key | Description |
|---|---|
| `os_kernel` | Authority of the **OS Kernel** agent. |
| `code_analyst` | Authority of the **Code Analyst** agent. |
| `log_historian` | Authority of the **Log Historian** agent. |
| `skeptic` | Authority of the **Skeptic** agent. |

> **Weights should sum to 1.0** per fault class by convention. The consensus
> math normalises by the total anyway (so any positive sum is valid), but the
> defaults are authored to sum to exactly 1.0.

### `panel` section

The ops-curated candidate pool that seeds automatic panel selection:

```json
{
  "panel": {
    "default_panel": ["os_kernel", "code_analyst", "log_historian", "skeptic"],
    "per_fault_class": {}
  }
}
```

| Field | Type | Description |
|---|---|---|
| `default_panel` | `list[str]` | Ordered agent keys for the default panel when no per-fault-class override applies. |
| `per_fault_class` | `dict[str, list[str]]` | Optional overrides keyed by fault-class value (e.g. `"stack_overflow"`). When a matching entry exists for the detected fault class, those keys are used instead of `default_panel`. |

Leave `per_fault_class` as `{}` when no curated per-fault-class rosters have been
defined yet. The `AgenticManagerStrategy` treats an empty map as "always use
the default panel".

---

## The four built-in agents

| Agent | Key | Role |
|---|---|---|
| **OS Kernel** | `os_kernel` | System-environment specialist. Focuses on memory-allocation state, I/O latency, driver conflicts, thread-blocking primitives, and hardware-signal mapping. Maps raw exception codes to a `FaultClass` and forms the first structural hypothesis. |
| **Code Analyst** | `code_analyst` | Software-architecture / logic-error specialist. Pinpoints the code-level root cause - faulting function, line, and logical path - and may emit a probabilistic fix (unified diff). |
| **Log Historian** | `log_historian` | Historical-pattern correlator. Compares the current signature to historical baselines, decides first-occurrence vs. recurrence, and adjusts confidence (±0.2). |
| **Skeptic** | `skeptic` | Adversarial moderator. Challenges the primary hypothesis - verifies the faulting module appears in the stack, checks exception-code consistency, surfaces overlooked evidence - and confirms (HIGH/MEDIUM) or rejects (LOW). |

---

## How weights are used

The `ConsensusEvaluator` computes a weighted consensus score each debate round:

```
CS = Σ(Wᵢ · Sᵢ) / Σ(Wᵢ)
```

where `Wᵢ` is the weight of agent *i* for the **detected fault class** and `Sᵢ`
is that agent's confidence score (`[0.0, 1.0]`) this round. Agents missing from a
round contribute `0.0`. The round converges when `CS ≥` `core.consensus_threshold`
(default `0.85`) on a stable hypothesis; it deadlocks into a human-in-the-loop
request when rounds are exhausted with `CS <` `core.hitl_confidence_threshold`
(default `0.50`). See [config.md](config.md#core).

### Three-tier weight precedence

When computing the weight map for a panel, the orchestrator applies the following
precedence (highest wins) **per agent**:

1. **Explicit override** — `AgentSpec.weight` when set via CLI (`--agent key::0.7`)
   or `config.json`'s `panel.explicit` list.
2. **Curated per-fault-class weight** — the ops-authored value from this file's
   `weights` section for the detected fault class.
3. **Priority-normalized default** — for agents not covered by tiers 1 or 2,
   their `priority` (1–5) divided by the sum of all tier-3 agents' priorities.

No pre-normalization is needed - `ConsensusEvaluator` divides by `Σ(Wᵢ)`.

The fault class is detected from the crash's exception code (Windows NTSTATUS,
Linux signal, or macOS Mach exception). If the detected class has **no entry** in
`agents.json`, the evaluator falls back to the `unknown` entry.

---

## Fault classes (the keys)

All ten `FaultClass` values are valid keys. Provide every class for full
coverage; any class you omit (except `unknown`) is resolved via the `unknown`
fallback at runtime.

| Fault class key | Meaning | Default weights (`os_kernel` / `code_analyst` / `log_historian` / `skeptic`) |
|---|---|---|
| `memory_access_violation` | Invalid memory access (e.g. SIGSEGV, `0xc0000005`, heap corruption). | 0.40 / 0.35 / 0.15 / 0.10 |
| `null_pointer_dereference` | Null-pointer dereference. | 0.40 / 0.35 / 0.15 / 0.10 |
| `use_after_free` | Access to freed memory. | 0.35 / 0.40 / 0.15 / 0.10 |
| `stack_overflow` | Stack exhaustion (`0xc00000fd`). | 0.45 / 0.30 / 0.10 / 0.15 |
| `integer_divide_by_zero` | Division by zero / integer overflow (SIGFPE, `0xc0000094`). | 0.35 / 0.40 / 0.10 / 0.15 |
| `deadlock` | Thread deadlock / lock contention. | 0.35 / 0.30 / 0.20 / 0.15 |
| `assertion_failure` | Assertion / breakpoint / abort (SIGABRT, `0x80000003`). | 0.25 / 0.45 / 0.15 / 0.15 |
| `resource_exhaustion` | Out of memory / handles / stack fault (`0xc0000017`). | 0.35 / 0.25 / 0.30 / 0.10 |
| `unhandled_exception` | Uncaught exception / illegal or privileged instruction. | 0.30 / 0.35 / 0.20 / 0.15 |
| `unknown` | Fallback when the exception code is unrecognised. | 0.30 / 0.35 / 0.20 / 0.15 |

The weighting reflects domain authority: kernel-level faults (memory, stack)
lean on `os_kernel`; logic faults (`use_after_free`, `integer_divide_by_zero`,
`assertion_failure`) lean on `code_analyst`; `resource_exhaustion` gives more
weight to `log_historian` for trend evidence.

---

## Tuning example

Make the Skeptic more influential for null-pointer faults by editing
`<config-dir>/agents.json`:

```json
{
  "weights": {
    "null_pointer_dereference": {
      "os_kernel": 0.35,
      "code_analyst": 0.30,
      "log_historian": 0.15,
      "skeptic": 0.20
    }
  },
  "panel": {
    "default_panel": ["os_kernel", "code_analyst", "log_historian", "skeptic"],
    "per_fault_class": {}
  }
}
```

Re-run `aegis analyze`; the new weights take effect on the next investigation.

See also: [config.md](config.md) (which references `core.consensus_threshold` and
`core.hitl_confidence_threshold`) and [cli.md](cli.md).
