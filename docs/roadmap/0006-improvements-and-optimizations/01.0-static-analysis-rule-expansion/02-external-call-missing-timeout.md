# 02 — `X014`: External call missing an explicit timeout

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none (Group A subtasks are mutually independent)
**Blocks:** none

## Objective

Flag a call to a known external-I/O function that has no `timeout=` keyword
argument. `.claude/CLAUDE.md` §2 states this as a non-negotiable convention:
*"every external call (debugger subprocess, AI backend, DB, S3, Qdrant) gets
a timeout and a defined failure path."* No linter (ruff included) has a
generic "this call needs a timeout kwarg" check — it is inherently
project-specific, since it requires knowing which call sites are "external."

## Detection logic

A **fixed, explicit allowlist** of call shapes, not a generic
heuristic — false positives here are expensive (the rule would otherwise
have to guess what counts as "external"), so scope precisely:

| Call shape                                                        | Required kwarg |
|---------------------------------------------------------------------|----------------|
| `subprocess.run(...)`                                                | `timeout=`     |
| `subprocess.Popen(...).communicate(...)`                              | `timeout=` (on `.communicate`, not `Popen` itself — `Popen` has no timeout param) |
| `httpx.get/post/put/delete/patch/request(...)`                        | `timeout=`     |
| `httpx.Client(...)` / `httpx.AsyncClient(...)` constructor            | `timeout=`     |
| `requests.get/post/put/delete/patch/request(...)`                     | `timeout=`     |
| `asyncio.wait_for(...)` is exempt — it *is* the timeout mechanism      | n/a — never flagged |

Match on `ast.Call` where `node.func` is an `ast.Attribute` whose `.attr` is
one of the method names above and whose value resolves (by simple name
tracking, not full type inference) to `subprocess`, `httpx`, or `requests` —
either the module name directly or a local alias recorded via the module's
own `import httpx as X` statement. Reject the call if none of `node.keywords`
has `arg == "timeout"` **and** no positional argument occupies that
parameter's position (keep it keyword-only in practice — a positional
timeout on these APIls is rare and this rule does not need to chase it).

## Message

```
X014 External call to `{qualified_name}` has no explicit `timeout=`; every
external call must have a bounded timeout and a defined failure path
(.claude/CLAUDE.md §2). Add `timeout=<seconds>` (or a `Timeout(...)` object
for httpx).
```

## Examples

No (flagged):

```python
result = subprocess.run(["cdb.exe", "-z", dump_path], capture_output=True)
```

```python
async with httpx.AsyncClient() as client:
    resp = await client.get(url)
```

Yes:

```python
result = subprocess.run(
    ["cdb.exe", "-z", dump_path], capture_output=True, timeout=settings.cdb_timeout_s
)
```

```python
async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
    resp = await client.get(url)
```

## Exclusions

- `tests/` — mocked calls in tests do not need a real timeout; excluded via
  the same test-module heuristic `X005`/`X013` already use.
- A call already wrapped in `asyncio.wait_for(...)` at the same statement is
  not flagged — the wrapper *is* the timeout.

## Test plan

- `tests/flake8_lint/samples/x014_missing_timeout.py` — one violation per
  allowlisted call shape (subprocess.run, httpx.get, requests.post, an
  `httpx.AsyncClient()` constructor) — 4+ cases in one file, each on its own
  line for an unambiguous `lineno` assertion.
- A companion clean sample with the same four calls, each carrying
  `timeout=...`, proving no false positive.
- `tests/flake8_lint/test_plugin_direct.py::test_x014_...`.
