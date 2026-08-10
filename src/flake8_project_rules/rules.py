"""
Project-specific AST lint rules X001–X012.

This module is the authoritative production implementation of the custom rule
engine.  It must never import from ``tests/lint/`` or any other test-only
module.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleViolation:
    """Represents a custom lint rule violation with location and details."""

    filename: str
    lineno: int
    col_offset: int
    code: str
    message: str


def check_tree(
    tree: ast.AST,
    filename: str,
    source: Optional[str] = None,
    *,
    apply_noqa: bool = True,
) -> Iterable[RuleViolation]:
    """Run all custom checks on a parsed AST and yield violations.

    When *source* is available and *apply_noqa* is True, violations located on
    a line that carries a trailing ``# noqa`` comment are suppressed following
    standard flake8 semantics: a bare ``# noqa`` drops every violation on that
    line, while ``# noqa: X002`` (or ``# noqa: X001, X002`` - comma-separated
    and whitespace-tolerant) drops only the listed codes.

    :param tree: the parsed AST for the module under lint.
    :param filename: path used for diagnostic reporting.
    :param source: raw module source; required for ``# noqa`` suppression.
    :param apply_noqa: when False, every violation is reported regardless of
        any ``# noqa`` comment (see ``[tool.flake8_lint_tests] allow_noqa``).
    :return: an iterable of :class:`RuleViolation` after noqa filtering.
    """
    lines: Optional[Sequence[str]] = source.splitlines() if source is not None else None
    for violation in _iter_violations(tree, filename, source):
        if apply_noqa and lines is not None and _is_noqa_suppressed(violation, lines):
            continue
        yield violation


def _iter_violations(
    tree: ast.AST,
    filename: str,
    source: Optional[str],
) -> Iterable[RuleViolation]:
    """Run every custom check and yield the raw (unfiltered) violations."""
    yield from _check_broad_exception(tree, filename)
    yield from _reserved_method(tree, filename)
    yield from _check_muted_exception(tree, filename)
    yield from _check_local_imports(tree, filename)
    yield from _check_docstrings(tree, filename, source)
    yield from _check_return_type_annotations(tree, filename)
    yield from _check_no_none_return_annotations(tree, filename)
    yield from _check_percent_formatting(tree, filename)
    yield from _check_import_error_suppression(tree, filename)
    yield from _check_union_none_annotations(tree, filename)
    yield from _check_union_type_annotations(tree, filename)


# Matches a trailing ``# noqa`` marker anywhere in a line's comment, optionally
# followed by ``: CODE[, CODE...]``. The code list stops at the first character
# outside ``[A-Z0-9, ]`` (e.g. a trailing '` - explanation`'), so a rationale
# after the codes is tolerated.
_NOQA_RE = re.compile(r"#\s*noqa(?::\s*(?P<codes>[A-Z0-9, ]+))?", re.IGNORECASE)


def _noqa_codes_for_line(line: str) -> Optional[frozenset[str]]:
    """Return the ``# noqa`` suppression declared on *line*, if any.

    :param line: a single physical source line.
    :return: ``None`` when there is no ``# noqa`` marker; an empty frozenset when
        a bare ``# noqa`` suppresses every code; otherwise the frozenset of the
        explicitly listed codes (upper-cased).
    """
    match = _NOQA_RE.search(line)
    if match is None:
        return None
    codes = match.group("codes")
    if codes is None:
        return frozenset()
    return frozenset(code.strip().upper() for code in codes.split(",") if code.strip())


def _is_noqa_suppressed(violation: RuleViolation, lines: Sequence[str]) -> bool:
    """Return True when *violation* is suppressed by a ``# noqa`` on its line."""
    index = violation.lineno - 1
    if not (0 <= index < len(lines)):
        return False
    codes = _noqa_codes_for_line(lines[index])
    if codes is None:
        return False
    if not codes:
        return True
    return violation.code in codes


def check_file(path: Path) -> list[RuleViolation]:
    """Run all custom lint rules on a Python file and return violations."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    return list(check_tree(tree, str(path), src))


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _contains_exception(exc_node: ast.expr) -> bool:
    """Return True if the except type contains ``Exception``."""
    if isinstance(exc_node, ast.Name) and exc_node.id == "Exception":
        return True
    if isinstance(exc_node, ast.Tuple):
        return any(isinstance(elt, ast.Name) and elt.id == "Exception" for elt in exc_node.elts)
    return False


def _is_muting_stmt(stmt: ast.stmt) -> bool:
    """Return True if *stmt* is considered a "muting" statement."""
    if isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)):
        return True
    if isinstance(stmt, ast.Return):
        return True
    if isinstance(stmt, ast.Expr):
        value = stmt.value
        if isinstance(value, ast.Constant) and value.value is Ellipsis:
            return True
    return False


def _has_proper_docstring(
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef],
    lines: Optional[Sequence[str]],
) -> bool:
    """Check that *node* has a triple-double-quote docstring as its first statement."""
    body = getattr(node, "body", None)
    if not body:
        return False

    first_stmt = body[0]
    if not isinstance(first_stmt, ast.Expr):
        return False

    value = first_stmt.value
    if isinstance(value, ast.Constant):
        if not isinstance(value.value, str):
            return False
    else:
        return False

    if lines is None:
        return True

    doc_lineno = first_stmt.lineno
    if not (1 <= doc_lineno <= len(lines)):
        return True

    doc_line = lines[doc_lineno - 1]
    stripped = doc_line.lstrip()
    return stripped.startswith('"""')


def _is_test_module(tree: ast.AST, filename: str) -> bool:
    """Return True when *filename* is heuristically determined to be a test module."""
    path = Path(filename)
    name = path.name

    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if any(parent.name == "tests" for parent in path.parents):
        return True
    if _has_test_imports(tree):
        return True
    return False


def _has_test_imports(tree: ast.AST) -> bool:
    """Return True if the module imports ``pytest`` or ``unittest``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in ("pytest", "unittest"):
                    return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in ("pytest", "unittest"):
                return True
    return False


def _iter_test_functions(tree: ast.AST) -> Iterable[ast.AST]:
    """Yield test-case functions/methods (pytest-style and unittest.TestCase)."""

    class _TestVisitor(ast.NodeVisitor):
        """AST visitor that identifies test case functions/methods."""

        def __init__(self):
            """Initialise with empty class stack and function-depth counter."""
            self._class_stack: list[ast.ClassDef] = []
            self._function_depth = 0
            self.test_functions: list[ast.AST] = []

        def visit_ClassDef(self, node: ast.ClassDef):
            """Push class onto stack, recurse, pop."""
            self._class_stack.append(node)
            self.generic_visit(node)
            self._class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            """Delegate to _visit_function."""
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            """Delegate to _visit_function."""
            self._visit_function(node)

        def _visit_function(self, node: ast.AST):
            """Collect outermost test functions at module or test-class scope."""
            name = getattr(node, "name", "")
            is_outermost = self._function_depth == 0

            if is_outermost and name.startswith("test"):
                if not self._class_stack:
                    self.test_functions.append(node)
                else:
                    current_class = self._class_stack[-1]
                    if _is_test_class(current_class):
                        self.test_functions.append(node)

            self._function_depth += 1
            self.generic_visit(node)
            self._function_depth -= 1

    visitor = _TestVisitor()
    visitor.visit(tree)
    return visitor.test_functions


def _is_test_class(node: ast.ClassDef) -> bool:
    """Return True if *node* looks like a pytest test class or unittest.TestCase subclass."""
    if node.name.startswith("Test"):
        return True
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "TestCase":
            return True
        if (
            isinstance(base, ast.Attribute)
            and isinstance(base.value, ast.Name)
            and base.value.id == "unittest"
            and base.attr == "TestCase"
        ):
            return True
    return False


def _docstring_has_structured_header(doc: str) -> bool:
    """Return True when the first non-empty docstring line matches ``[Type] summary``."""
    header_re = re.compile(r"^\s*\[(Unit|Integration|Local|E2E)]\s+\S.*$")
    for line in doc.splitlines():
        if not line.strip():
            continue
        return bool(header_re.match(line))
    return False


def _docstring_has_section(doc: str, section_name: str) -> bool:
    """Return True if any docstring line starts with *section_name*."""
    for line in doc.splitlines():
        if line.strip().startswith(section_name):
            return True
    return False


def _function_returns_value(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
    """Return True if *node* has at least one ``return <expr>`` in its own body."""

    class _ReturnVisitor(ast.NodeVisitor):
        """AST visitor that detects value-bearing return statements."""

        def __init__(self):
            """Initialise with returns_value flag set to False."""
            self.returns_value = False

        def visit_Return(self, ret: ast.Return):
            """Flag if return carries a value."""
            if ret.value is not None:
                self.returns_value = True

        def visit_FunctionDef(self, _: ast.FunctionDef):
            """Skip nested functions."""

        def visit_AsyncFunctionDef(self, _: ast.AsyncFunctionDef):
            """Skip nested async functions."""

        def visit_Lambda(self, _: ast.Lambda):
            """Skip lambdas."""

        def visit_ClassDef(self, _: ast.ClassDef):
            """Skip nested classes."""

    visitor = _ReturnVisitor()
    body = getattr(node, "body", None) or []
    for stmt in body:
        visitor.visit(stmt)
    return visitor.returns_value


def _except_catches_import_error(handler: ast.ExceptHandler) -> bool:
    """Return True if *handler* catches ImportError or ModuleNotFoundError."""
    exc = handler.type
    if exc is None:
        return False
    names = {"ImportError", "ModuleNotFoundError"}
    if isinstance(exc, ast.Name) and exc.id in names:
        return True
    if isinstance(exc, ast.Tuple):
        for elt in exc.elts:
            if isinstance(elt, ast.Name) and elt.id in names:
                return True
    return False


def _except_handler_has_raise(handler: ast.ExceptHandler) -> bool:
    """Return True if *handler* body contains any ``raise`` statement."""
    for stmt in handler.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Raise):
                return True
    return False


def _expr_is_none(expr: Optional[ast.expr]) -> bool:
    """Return True if *expr* syntactically represents ``None``."""
    if expr is None:
        return False
    if isinstance(expr, ast.Name) and expr.id == "None":
        return True
    if isinstance(expr, ast.Constant) and expr.value is None:
        return True
    # Compatibility with very old Python AST nodes (pragma: no cover).
    name_constant = vars(ast).get("NameConstant")
    if name_constant is not None and isinstance(expr, name_constant):
        return getattr(expr, "value", None) is None
    return False


def _is_none_annotation(ann: Optional[ast.expr]) -> bool:
    """Return True when the annotation represents ``None``."""
    return _expr_is_none(ann)


def _is_union_with_none(ann: Optional[ast.expr]) -> bool:
    """Return True when the annotation is a PEP 604 union that includes ``None``."""
    if ann is None:
        return False
    found_none = False
    found_bitor = False
    for sub in ast.walk(ann):
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
            found_bitor = True
        if _expr_is_none(sub):
            found_none = True
    return found_none and found_bitor


def _is_union_without_none(ann: Optional[ast.expr]) -> bool:
    """Return True when the annotation is a PEP 604 union that excludes ``None``."""
    if ann is None:
        return False
    found_none = False
    found_bitor = False
    for sub in ast.walk(ann):
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
            found_bitor = True
        if _expr_is_none(sub):
            found_none = True
    return found_bitor and not found_none


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _check_broad_exception(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X001/X002: Forbid bare ``except:`` and ``except Exception:``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        if node.type is None:
            yield RuleViolation(
                filename,
                node.lineno,
                node.col_offset,
                "X001",
                "Do not use bare `except:`; catch specific exceptions.",
            )
            continue

        if _contains_exception(node.type):
            yield RuleViolation(
                filename,
                node.lineno,
                node.col_offset,
                "X002",
                "Do not use `except Exception:`; catch a more specific exception.",
            )


def _reserved_method(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X003: Intentionally disabled while the code remains reserved."""
    del tree, filename
    return ()


def _check_muted_exception(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X004: Forbid muted exception handlers (pass/continue/break/return/ellipsis)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        if not node.body:
            yield RuleViolation(
                filename,
                node.lineno,
                node.col_offset,
                "X004",
                "Do not silently swallow exceptions; handle them or re-raise.",
            )
            continue

        if all(_is_muting_stmt(stmt) for stmt in node.body):
            yield RuleViolation(
                filename,
                node.lineno,
                node.col_offset,
                "X004",
                "Do not silently swallow exceptions; handle them or re-raise.",
            )


def _check_docstrings(
    tree: ast.AST,
    filename: str,
    source: Optional[str],
) -> Iterable[RuleViolation]:
    """X005: Enforce generic docstrings and structured test docstrings."""
    lines: Optional[Sequence[str]] = source.splitlines() if source is not None else None
    is_test_module = _is_test_module(tree, filename)

    generic_message = (
        "Missing or improperly formatted docstring: add a coherent docstring block as the first statement in the body."
    )

    if is_test_module:
        test_nodes = set(_iter_test_functions(tree))

        for node in ast.walk(tree):
            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                continue

            is_test_case = node in test_nodes

            if is_test_case:
                if not _has_proper_docstring(node, lines):
                    message = (
                        "Missing or improperly formatted test docstring: "
                        "add a structured docstring as the first statement, "
                        "starting with a header line like "
                        "'[Unit] component: behavior summary' (where type is "
                        "one of [Unit, Integration, Local, E2E]), followed by "
                        "'Scenario:', 'Boundaries:', and "
                        "'On failure, first check:' sections."
                    )
                    yield RuleViolation(filename, node.lineno, node.col_offset, "X005", message)
                    continue

                raw_doc = ast.get_docstring(node, clean=False) or ""
                missing_parts: list[str] = []

                if not _docstring_has_structured_header(raw_doc):
                    missing_parts.append("header line like '[Unit] component: behavior summary'")

                for section in ("Scenario:", "Boundaries:", "On failure, first check:"):
                    if not _docstring_has_section(raw_doc, section):
                        missing_parts.append(f'"{section}" section')

                if missing_parts:
                    message = (
                        "Missing or incomplete structured test docstring: "
                        "test docstrings must start with a header line like "
                        "'[Unit] component: behavior summary' (where type is "
                        "one of [Unit, Integration, Local, E2E]) and include "
                        "'Scenario:', 'Boundaries:', and "
                        "'On failure, first check:' sections. "
                        "Missing parts: " + ", ".join(missing_parts) + "."
                    )
                    yield RuleViolation(filename, node.lineno, node.col_offset, "X005", message)
            else:
                if not _has_proper_docstring(node, lines):
                    yield RuleViolation(filename, node.lineno, node.col_offset, "X005", generic_message)
    else:
        for node in ast.walk(tree):
            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                continue
            if not _has_proper_docstring(node, lines):
                yield RuleViolation(filename, node.lineno, node.col_offset, "X005", generic_message)


def _check_local_imports(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X006: Forbid imports inside function bodies."""

    class _LocalImportVisitor(ast.NodeVisitor):
        """AST visitor that detects imports inside function/method bodies."""

        def __init__(self):
            """Initialize with zero function depth and an empty violations list."""
            self._function_depth = 0
            self.violations: list[RuleViolation] = []

        def visit_FunctionDef(self, node: ast.FunctionDef):
            """Increment depth before traversal, decrement after."""
            self._function_depth += 1
            self.generic_visit(node)
            self._function_depth -= 1

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            """Increment depth before traversal, decrement after."""
            self._function_depth += 1
            self.generic_visit(node)
            self._function_depth -= 1

        def visit_Import(self, node: ast.Import):
            """Flag imports inside function bodies."""
            if self._function_depth > 0:
                self.violations.append(
                    RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X006",
                        "Do not use local imports inside function bodies; move imports to module scope.",
                    )
                )

        def visit_ImportFrom(self, node: ast.ImportFrom):
            """Flag from-imports inside function bodies."""
            if self._function_depth > 0:
                self.violations.append(
                    RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X006",
                        "Do not use local imports inside function bodies; move imports to module scope.",
                    )
                )

        def visit_Call(self, node: ast.Call):
            """Flag ``__import__()`` calls inside function bodies."""
            if self._function_depth > 0 and isinstance(node.func, ast.Name) and node.func.id == "__import__":
                self.violations.append(
                    RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X006",
                        "Do not use local imports inside function bodies; "
                        "move imports to module scope (including __import__() calls).",
                    )
                )
            self.generic_visit(node)

    visitor = _LocalImportVisitor()
    visitor.visit(tree)
    return visitor.violations


def _check_return_type_annotations(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X007: Require return annotation when a function returns a value."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _function_returns_value(node):
            continue
        if getattr(node, "returns", None) is None:
            yield RuleViolation(
                filename=filename,
                lineno=node.lineno,
                col_offset=node.col_offset,
                code="X007",
                message=(
                    "Function or method returns a value but has no return type "
                    "annotation; add an explicit '-> return_type' annotation."
                ),
            )


def _check_no_none_return_annotations(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X008: Forbid explicit ``-> None`` return annotation."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_none_annotation(getattr(node, "returns", None)):
            yield RuleViolation(
                filename=filename,
                lineno=node.lineno,
                col_offset=node.col_offset,
                code="X008",
                message=(
                    "Do not use an explicit '-> None' return annotation; "
                    "omit the return type instead for functions that return nothing."
                ),
            )


def _check_percent_formatting(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X009: Forbid ``%`` string formatting and logging printf-style calls."""
    percent_pattern = r"%(?:\(\w+\))?[-#0 +]*\d*(?:\.\d+)?[hlL]?[diouxXeEfFgGcrs]"
    logging_methods = {"debug", "info", "warning", "error", "exception", "critical", "log"}

    def _has_percent_placeholders(s: str) -> bool:
        """Return True if *s* contains percent-style format placeholders."""
        return bool(re.search(percent_pattern, s))

    for node in ast.walk(tree):
        # Case 1: "%s" % value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            fmt_value: Optional[str] = None
            if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                fmt_value = node.left.value
            if fmt_value is None:
                continue
            if not _has_percent_placeholders(fmt_value):
                continue
            yield RuleViolation(
                filename=filename,
                lineno=node.lineno,
                col_offset=node.col_offset,
                code="X009",
                message="Do not use old-style '%' string formatting (e.g. '%s', '%d'); use f-strings instead.",
            )
            continue

        # Case 2: logger.info("foo %s", value)
        if isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in logging_methods:
                continue
            if not node.args:
                continue
            first_arg = node.args[0]
            fmt_value_log: Optional[str] = None
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                fmt_value_log = first_arg.value
            if fmt_value_log is None:
                continue
            if not _has_percent_placeholders(fmt_value_log):
                continue
            yield RuleViolation(
                filename=filename,
                lineno=node.lineno,
                col_offset=node.col_offset,
                code="X009",
                message=(
                    "Do not use old-style '%' formatting in logging calls "
                    "(e.g. '... %s', '... %d'); use f-strings instead, "
                    'e.g. logger.info(f"... {value}").'
                ),
            )


def _check_import_error_suppression(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X010: Forbid suppressed ImportError/ModuleNotFoundError."""

    def _has_import_in_body(try_body: Sequence[ast.stmt]) -> bool:
        """Return True if *try_body* contains import statements or ``__import__()`` calls."""
        for stmt in try_body:
            for node in ast.walk(stmt):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    return True
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
                    return True
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if not _except_catches_import_error(handler):
                continue
            if _except_handler_has_raise(handler):
                continue
            if _has_import_in_body(node.body):
                yield RuleViolation(
                    filename=filename,
                    lineno=handler.lineno,
                    col_offset=handler.col_offset,
                    code="X010",
                    message=(
                        "Do not suppress ImportError/ModuleNotFoundError in try/except; "
                        "let import failures propagate instead of converting them "
                        "into optional dependencies."
                    ),
                )


def _check_union_none_annotations(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X011: Forbid ``Type | None``; require ``Optional[Type]``."""

    def _report(union_node: ast.AST) -> RuleViolation:
        """Build a violation for a ``Type | None`` annotation."""
        return RuleViolation(
            filename=filename,
            lineno=getattr(union_node, "lineno", 1),
            col_offset=getattr(union_node, "col_offset", 0),
            code="X011",
            message="Do not use `Type | None` in type hints; use `Optional[Type]` from typing instead.",
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + ([] if node.args.vararg is None else [node.args.vararg])
                + list(node.args.kwonlyargs)
                + ([] if node.args.kwarg is None else [node.args.kwarg])
            )
            for arg in args:
                ann = getattr(arg, "annotation", None)
                if _is_union_with_none(ann):
                    yield _report(arg)
            if _is_union_with_none(getattr(node, "returns", None)):
                yield _report(node)
        elif isinstance(node, ast.AnnAssign):
            if _is_union_with_none(node.annotation):
                yield _report(node.annotation)


def _check_union_type_annotations(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """X012: Forbid ``Type1 | Type2``; require ``Union[Type1, Type2]``."""

    def _report(annotation_node: ast.AST) -> RuleViolation:
        """Build a violation for a ``Type1 | Type2`` annotation."""
        return RuleViolation(
            filename=filename,
            lineno=getattr(annotation_node, "lineno", 1),
            col_offset=getattr(annotation_node, "col_offset", 0),
            code="X012",
            message="Do not use `Type1 | Type2` in type hints; use `Union[Type1, Type2]` from typing instead.",
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + ([] if node.args.vararg is None else [node.args.vararg])
                + list(node.args.kwonlyargs)
                + ([] if node.args.kwarg is None else [node.args.kwarg])
            )
            for arg in args:
                ann = getattr(arg, "annotation", None)
                if _is_union_without_none(ann):
                    yield _report(arg)
            if _is_union_without_none(getattr(node, "returns", None)):
                yield _report(node)
        elif isinstance(node, ast.AnnAssign):
            if _is_union_without_none(node.annotation):
                yield _report(node.annotation)
