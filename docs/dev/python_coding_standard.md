# Aegis SWR Python Style Guide

This document is split into two focused files. Read both when onboarding;
link to the specific file when citing a rule in a PR or review.

## Contents

| File                                                 | Covers                                                                                                                                                     |
|------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [python_language_rules.md](python_language_rules.md) | §1 Background · §2 Language Rules - lint, imports, packages, exceptions, mutable globals, comprehensions, generators, lambdas, type annotations, and more. |
| [python_style_rules.md](python_style_rules.md)       | §3 Style Rules - line length, indentation, blank lines, comments, docstrings, naming, main, function length, type annotation style. §4 Parting Words.      |

## Project-specific overrides

The guide above is the baseline. Aegis SWR adds the following mandatory rules
on top (enforced by the `post_edit_format` hook and CI gates):

- **`Optional[T]` always** - never `T | None`, including inside subscripts and
  `Annotated[...]`. Enforced by `scripts/replace_optional.py --check`.
- **Public APIs must be fully annotated.** Unannotated public symbols are a CI failure.
- **ruff** (`select = E,F,I,UP,B,SIM`, line length 100) is the linter and
  formatter (`ruff format`). No Black, no Prettier.
- **`SensitiveFilter`** must be applied to every logger. Never log secrets,
  raw incident payloads, or stack traces that embed them.
- **RAII via context managers** for all subprocess/socket/file resources. No
  bare `except:`.
- **No `print`** for diagnostics in product code - use `loguru`.
