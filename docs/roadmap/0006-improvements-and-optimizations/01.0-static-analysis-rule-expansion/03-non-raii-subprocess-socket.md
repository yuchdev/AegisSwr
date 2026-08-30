# 03 — `X015`: Non-RAII `subprocess.Popen`/`socket.socket` resource

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none (Group A subtasks are mutually independent)
**Blocks:** none

## Objective

Flag `subprocess.Popen(...)` or `socket.socket(...)` assigned via a plain
`name = Call(...)` statement rather than used as a `with`-statement context
manager. `.claude/CLAUDE.md` §2 states: *"RAII via context managers for all
subprocess/socket/file resources."* `root CLAUDE.md`'s Key Conventions repeats
it verbatim. Ruff's `SIM115` (flake8-simplify) already catches the equivalent
mistake for bare `open()`, but **not** for `Popen`/`socket.socket` — this
rule fills exactly that gap, scoped to avoid overlapping `SIM115`'s territory.

## Detection logic

Walk the AST for an `ast.Assign` (or `ast.AnnAssign`, or a bare `ast.Expr`
call-statement whose value is not assigned at all — an even worse case,
since the handle isn't even reachable to close) whose value is an
`ast.Call` matching `subprocess.Popen(...)` or `socket.socket(...)`
(including a bare `Popen(...)`/`socket(...)` after a `from subprocess import
Popen` / `from socket import socket`), **and** whose parent statement is not
inside an `ast.With`/`ast.AsyncWith`'s `items` list (i.e. the call does not
appear as a `with subprocess.Popen(...) as proc:` context expression).

A conservative implementation: track, per function scope, every `Name`
bound to such a call via plain assignment; if that name is never the subject
of a `with` block using it directly (`with proc:`) — which is rare — and
there is no corresponding `.wait()`/`.close()`/`.__exit__()` call reachable
in a `finally` or immediately following `try` block, flag the assignment
site. To keep the check tractable and low-false-positive, the *shipped*
version only needs the simpler, high-value case: **flag the assignment
itself whenever it is not the target of a `with` statement**, and rely on
`# noqa: X015` for the rare legitimate exception (e.g. a `Popen` object
stored on `self` and closed in a sibling `__aexit__`/`close()` method, which
this static, single-function-scope check cannot see across methods).

## Message

```
X015 `{call_name}(...)` is not used as a context manager; assign it in a
`with` statement (`with subprocess.Popen(...) as proc:`) so the process/socket
is always closed, even on an exception (RAII, .claude/CLAUDE.md §2).
```

## Examples

No (flagged):

```python
proc = subprocess.Popen(["cdb.exe", "-z", dump_path], stdout=subprocess.PIPE)
output = proc.communicate()[0]
```

Yes:

```python
with subprocess.Popen(["cdb.exe", "-z", dump_path], stdout=subprocess.PIPE) as proc:
    output = proc.communicate()[0]
```

## Exclusions

- `tests/` — a test double or a mock `Popen` return value assigned plainly is
  common and harmless; excluded via the test-module heuristic.
- A call already inside a `with`/`async with` statement's `items` is never
  flagged (the common, correct case).

## Test plan

- `tests/flake8_lint/samples/x015_non_raii_resource.py` — a bare
  `subprocess.Popen(...)` assignment and a bare `socket.socket(...)`
  assignment, each on its own line.
- A companion clean sample with both wrapped in `with`.
- `tests/flake8_lint/test_plugin_direct.py::test_x015_...`, including a case
  proving `open(...)` alone (no `Popen`/`socket`) is **not** flagged by this
  rule — that is `SIM115`'s job once Task 01.0's Group B subtasks land, and
  this rule must not double-report it.
