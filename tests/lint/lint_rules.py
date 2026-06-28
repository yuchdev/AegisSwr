from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Optional


# ---------------------------------------------------------------------------
# Core Linter Pytest Wiring
# ---------------------------------------------------------------------------
@dataclass
class RuleViolation:
    """Represents a custom lint rule violation with location and details."""
    filename: str
    lineno: int
    col_offset: int
    code: str
    message: str


def check_tree(tree: ast.AST, filename: str, source: Optional[str] = None) -> Iterable[RuleViolation]:
    """Run all custom checks on a parsed AST."""
    yield from check_broad_exception(tree, filename)
    yield from check_settings_set_method(tree, filename)
    yield from check_muted_exception(tree, filename)
    yield from check_local_imports(tree, filename)
    yield from check_docstrings(tree, filename, source)
    yield from check_return_type_annotations(tree, filename)
    yield from check_no_none_return_annotations(tree, filename)
    yield from check_percent_formatting(tree, filename)
    yield from check_import_error_suppression(tree, filename)
    yield from check_union_none_annotations(tree, filename)

def check_file(path: Path) -> List[RuleViolation]:
    """
    Run all custom lint rules on a Python file and return violations.

    Reads the file, parses its AST, and applies all custom checks including
    broad exception handling, muted exceptions, Settings.set() usage,
    local imports, docstring requirements, and return type annotations.
    """
    src = path.read_text(encoding="utf8")
    tree = ast.parse(src, filename=str(path))
    return list(check_tree(tree, str(path), src))


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _contains_exception(exc_node: ast.expr) -> bool:
    """Return True if the `except` type contains `Exception`."""
    # `except Exception:`
    if isinstance(exc_node, ast.Name) and exc_node.id == "Exception":
        return True

    # `except (Exception, ValueError):`
    if isinstance(exc_node, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id == "Exception"
            for elt in exc_node.elts
        )

    return False


def _is_muting_stmt(stmt: ast.stmt) -> bool:
    """
    Return True if a statement is considered "muting" in an except block.

    Currently treated as muting:
        - pass
        - continue
        - break
        - return <anything>
        - a bare ellipsis expression: `...`
          (common "TODO" / placeholder pattern)
    """
    # pass / continue / break
    if isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)):
        return True

    # return / return <value>
    if isinstance(stmt, ast.Return):
        return True

    # Bare ellipsis literal: `...`
    if isinstance(stmt, ast.Expr):
        value = stmt.value
        if isinstance(value, ast.Constant) and value.value is Ellipsis:
            return True

    return False


def _has_proper_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, lines: Optional[Sequence[str]]) -> bool:
    """
    Check that `node` has a docstring as its first statement and that the
    corresponding source line begins with triple double quotes after
    indentation.
    """
    body = getattr(node, "body", None)
    if not body:
        return False

    first_stmt = body[0]
    if not isinstance(first_stmt, ast.Expr):
        return False

    value = first_stmt.value

    # Docstring is represented as ast.Constant(str).
    if isinstance(value, ast.Constant):
        if not isinstance(value.value, str):
            return False
    else:
        return False

    # If we don't have the original source, we can't enforce the precise
    # formatting; accept any string-literal docstring in that case.
    if lines is None:
        return True

    doc_lineno = first_stmt.lineno
    if not (1 <= doc_lineno <= len(lines)):
        # Be lenient if coordinates look odd.
        return True

    doc_line = lines[doc_lineno - 1]
    stripped = doc_line.lstrip()

    # Require that the first non-whitespace characters are triple double quotes.
    return stripped.startswith('"""')


def _is_test_module(tree: ast.AST, filename: str) -> bool:
    """
    Heuristically determine whether this module is a test module.

    Criteria:
        - File name starts with `test_` or ends with `_test.py`, OR
        - Any parent directory is named `tests`, OR
        - Module imports `pytest` or `unittest`.
    """
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
    """Return True if the module imports pytest or unittest."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in ("pytest", "unittest"):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".", 1)[0]
                if root in ("pytest", "unittest"):
                    return True
    return False


def _iter_test_functions(tree: ast.AST) -> Iterable[ast.AST]:
    """
    Yield test case functions/methods:

    - Top-level `def test_*` (pytest-style)
    - Methods `def test_*` on classes whose name starts with `Test`
      or which inherit from `unittest.TestCase`.
    """

    class _TestVisitor(ast.NodeVisitor):
        """
        AST visitor that identifies test case functions/methods.

        Tracks class context and function nesting to distinguish top-level test
        functions from nested helpers, collecting pytest/unittest test cases.
        """

        def __init__(self):
            """Initialize a visitor with an empty class stack, zero function depth, and empty test list."""
            self._class_stack: List[ast.ClassDef] = []
            self._function_depth = 0
            self.test_functions: List[ast.AST] = []

        def visit_ClassDef(self, node: ast.ClassDef):
            """Visit a class definition, pushing it onto the stack for context tracking."""
            self._class_stack.append(node)
            self.generic_visit(node)
            self._class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            """Visit a function definition, delegating to _visit_function for test detection."""
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            """Visit an async function definition, delegating to _visit_function for test detection."""
            self._visit_function(node)

        def _visit_function(self, node: ast.AST):
            """
            Process a function/method node to detect if it's a test case.

            Collects top-level test_* functions at module scope or within test classes,
            while tracking nesting depth to exclude nested helper functions.
            """
            name = getattr(node, "name", "")
            is_outermost = self._function_depth == 0

            if is_outermost and name.startswith("test"):
                if not self._class_stack:
                    # Module-level pytest test
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
    """Heuristic: pytest test class or unittest.TestCase subclass."""
    if node.name.startswith("Test"):
        return True

    for base in node.bases:
        # class Foo(TestCase):
        if isinstance(base, ast.Name) and base.id == "TestCase":
            return True

        # class Foo(unittest.TestCase):
        if isinstance(base, ast.Attribute):
            if isinstance(base.value, ast.Name) and base.value.id == "unittest":
                if base.attr == "TestCase":
                    return True

    return False


def _docstring_has_structured_header(doc: str) -> bool:
    """Check first non-empty docstring line matches `[Type] summary` pattern with Type in {Unit, Integration, Local, E2E}.

    Only accept [Unit], [Integration], [Local], or [E2E] headers for test docstrings.
    """
    test_docstring_header_re = re.compile(r"^\s*\[(Unit|Integration|Local|E2E)]\s+\S.*$")
    for line in doc.splitlines():
        if not line.strip():
            continue
        return bool(test_docstring_header_re.match(line))
    return False


def _docstring_has_section(doc: str, section_name: str) -> bool:
    """Return True if any line starts with the given section name."""
    for line in doc.splitlines():
        if line.strip().startswith(section_name):
            return True
    return False


def _function_returns_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    Return True if this function/method has at least one `return` that
    returns a value (i.e. `return <expr>` rather than bare `return`).

    NOTE: Does NOT inspect nested inner functions/lambdas/classes.
    """

    class _ReturnVisitor(ast.NodeVisitor):
        """AST visitor that detects whether a function returns a value."""
        def __init__(self):
            """Initialize the visitor with returns_value flag set to False."""
            self.returns_value = False

        def visit_Return(self, ret: ast.Return):
            """Visit Return node and check if it returns a value."""
            # Anything with a value counts as "returns something"
            if ret.value is not None:
                self.returns_value = True

        # Do NOT descend into nested scopes when analyzing the outer function
        def visit_FunctionDef(self, _1: ast.FunctionDef):
            """Skip nested function bodies."""
            return

        def visit_AsyncFunctionDef(self, _1: ast.AsyncFunctionDef):
            """Skip nested async function bodies."""
            return

        def visit_Lambda(self, _1: ast.Lambda):
            """Skip nested lambdas."""
            return

        def visit_ClassDef(self, _1: ast.ClassDef):  # pragma: no cover
            """Skip nested classes."""
            return

    visitor = _ReturnVisitor()

    # IMPORTANT: only walk the body of this function/method, not the node itself,
    # so that our visit_FunctionDef/visit_AsyncFunctionDef only applies to nested defs.
    body = getattr(node, "body", None) or []
    for stmt in body:
        visitor.visit(stmt)

    return visitor.returns_value


def _except_catches_import_error(handler: ast.ExceptHandler) -> bool:
    """Return True if this except handler catches ImportError / ModuleNotFoundError."""
    exc = handler.type
    if exc is None:
        return False

    names = {"ImportError", "ModuleNotFoundError"}

    # except ImportError:
    if isinstance(exc, ast.Name) and exc.id in names:
        return True

    # except (ImportError, ModuleNotFoundError, ...):
    if isinstance(exc, ast.Tuple):
        for elt in exc.elts:
            if isinstance(elt, ast.Name) and elt.id in names:
                return True

    return False


def _except_handler_has_raise(handler: ast.ExceptHandler) -> bool:
    """
    Return True if the except block contains any `raise` statement.

    We treat any raise in the handler body (even nested) as re-raising or
    propagating an error, so it's not considered suppression.
    """
    for stmt in handler.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Raise):
                return True
    return False


def _is_union_with_none(ann: Optional[ast.expr]) -> bool:
    """
    Return True if the annotation contains a PEP 604-style union with None,
    e.g. `Foo | None`, `None | Foo`, or wider unions that include None.
    """
    if ann is None:
        return False

    # We treat any BitOr-based expression containing a None leaf as a union with None.
    found_none = False
    found_other = False

    for sub in ast.walk(ann):
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
            # presence of BitOr marks this as a union-like expression
            found_other = True

        if _expr_is_none(sub):
            found_none = True

    return found_none and found_other


def _is_none_annotation(ann: Optional[ast.expr]) -> bool:
    """Return True if the given annotation node syntactically represents `None`.

    This is a compatibility wrapper kept for callers that expect an
    "annotation-focused" helper. The canonical implementation lives in
    `_expr_is_none`, which inspects AST nodes (including older AST node
    types) and returns True when they represent the literal `None`.
    """
    return _expr_is_none(ann)


def _expr_is_none(expr: Optional[ast.expr]) -> bool:
    """Return True if expr syntactically represents `None`."""
    if expr is None:
        return False

    # Name: None
    if isinstance(expr, ast.Name) and expr.id == "None":
        return True

    # Constant: None
    if isinstance(expr, ast.Constant) and expr.value is None:
        return True

    # Very defensive: older Python NameConstant
    name_constant = vars(ast).get("NameConstant")  # pragma: no cover
    if name_constant is not None and isinstance(expr, name_constant):
        return getattr(expr, "value", None) is None

    return False

# ---------------------------------------------------------------------------
# Linter rules
# ---------------------------------------------------------------------------

def check_broad_exception(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """Rule 1: forbid broad `except Exception:` and bare `except:`."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        # bare `except:`
        if node.type is None:
            yield RuleViolation(
                filename,
                node.lineno,
                node.col_offset,
                "X001",
                "Do not use bare `except:`; catch specific exceptions.",
            )
            continue

        # `except Exception:` or `except (Exception, ...)`
        if _contains_exception(node.type):
            yield RuleViolation(
                filename,
                node.lineno,
                node.col_offset,
                "X002",
                "Do not use `except Exception:`; catch a more specific exception.",
            )


def check_settings_set_method(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """Rule 2: in class Settings, method `set` is forbidden."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        if node.name != "Settings":
            continue

        for member in node.body:
            if isinstance(member, ast.FunctionDef) and member.name == "set":
                yield RuleViolation(
                    filename,
                    member.lineno,
                    member.col_offset,
                    "X003",
                    "Method `Settings.set()` is forbidden (use an explicit "
                    "API, e.g. `update_from_env`, `set_option`, etc).",
                )


def check_muted_exception(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """
    Rule 3: forbid muted exception handlers.

    Any `except` block whose body consists only of "muting" statements:
        - pass
        - continue
        - break
        - return (with or without a value)
        - an ellipsis literal (`...`)
    is considered a violation (X004).
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        # Empty body is also effectively muting.
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


def check_docstrings(tree: ast.AST, filename: str, source: Optional[str]) -> Iterable[RuleViolation]:
    """
    Rule 4 (unified X005):

    - If the module is a *code module*:
        Require a proper docstring as the first statement in every class /
        function / method body.

    - If the module is a *test module* (pytest/unittest or test_* heuristics):
        - For test functions/methods: require a structured test docstring with:
            * Header line: "[Type] component: behavior summary"
              where Type ∈ {Unit, Integration, Local, E2E}
            * Sections: "Scenario:", "Boundaries:",
              "On failure, first check:"
        - For other functions/classes: require a generic docstring as above.
    """
    lines: Optional[Sequence[str]] = source.splitlines() if source is not None else None
    is_test_module = _is_test_module(tree, filename)

    generic_message = (
        "Missing or improperly formatted docstring: add a coherent docstring "
        "block as the first statement in the body."
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
                # For test cases: require structured test docstring.
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
                    yield RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X005",
                        message,
                    )
                    continue

                raw_doc = ast.get_docstring(node, clean=False) or ""
                missing_parts: List[str] = []

                if not _docstring_has_structured_header(raw_doc):
                    missing_parts.append(
                        "header line like '[Unit] component: behavior summary'"
                    )

                for section in (
                    "Scenario:",
                    "Boundaries:",
                    "On failure, first check:",
                ):
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
                    yield RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X005",
                        message,
                    )

            else:
                # Non-test helper or class in a test module: generic rule.
                if not _has_proper_docstring(node, lines):
                    yield RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X005",
                        generic_message,
                    )
    else:
        # Non-test module: generic rule for every class/function/method.
        for node in ast.walk(tree):
            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                continue

            if not _has_proper_docstring(node, lines):
                yield RuleViolation(
                    filename,
                    node.lineno,
                    node.col_offset,
                    "X005",
                    generic_message,
                )


def check_local_imports(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """
    Rule 5: forbid imports inside function bodies (local imports).

    Any `import ...` or `from ... import ...` statement that appears inside
    a function or method body is considered a violation (X006). Additionally,
    `__import__()` function calls are also flagged as local imports.
    """

    class _LocalImportVisitor(ast.NodeVisitor):
        """
        AST visitor that detects imports inside function/method bodies.

        Tracks function nesting depth and collects violations for any
        import statements found within function scopes, including __import__() calls.
        """

        def __init__(self):
            """Initialize the visitor with zero function depth and empty violations list."""
            self._function_depth = 0
            self.violations: List[RuleViolation] = []

        def visit_FunctionDef(self, node: ast.FunctionDef):
            """Visit a function definition, incrementing depth before traversal."""
            self._function_depth += 1
            self.generic_visit(node)
            self._function_depth -= 1

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            """Visit an async function definition, incrementing depth before traversal."""
            self._function_depth += 1
            self.generic_visit(node)
            self._function_depth -= 1

        def visit_Import(self, node: ast.Import):
            """Visit an import statement, recording violation if inside a function."""
            if self._function_depth > 0:
                self.violations.append(
                    RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X006",
                        "Do not use local imports inside function bodies; "
                        "move imports to module scope.",
                    )
                )

        def visit_ImportFrom(self, node: ast.ImportFrom):
            """Visit a from-import statement, recording violation if inside a function."""
            if self._function_depth > 0:
                self.violations.append(
                    RuleViolation(
                        filename,
                        node.lineno,
                        node.col_offset,
                        "X006",
                        "Do not use local imports inside function bodies; "
                        "move imports to module scope.",
                    )
                )

        def visit_Call(self, node: ast.Call):
            """Visit a function call, checking for __import__() inside function bodies."""
            if self._function_depth > 0:
                # Check if this is a __import__() call
                if isinstance(node.func, ast.Name) and node.func.id == "__import__":
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


def check_return_type_annotations(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """
    Rule 6 (X007):

    Every function or method that returns a value (has `return <expr>` in its
    own body) must declare an explicit return type annotation:

        def func(...) -> ReturnType:

    We don't validate *which* type, only that some annotation is present.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Skip functions/methods that never return a value.
        if not _function_returns_value(node):
            continue

        # If `returns` is None, there is no `-> ...` annotation.
        if getattr(node, "returns", None) is None:
            message = (
                "Function or method returns a value but has no return type "
                "annotation; add an explicit '-> return_type' annotation."
            )
            yield RuleViolation(
                filename=filename,
                lineno=node.lineno,
                col_offset=node.col_offset,
                code="X007",
                message=message,
            )


def check_no_none_return_annotations(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """
    Rule 7 (X008):

    Never use an explicit `-> None` return annotation.

    Functions or methods that conceptually return nothing should omit a return
    annotation entirely instead of declaring `-> None`.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        if _is_none_annotation(getattr(node, "returns", None)):
            yield RuleViolation(
                filename=filename,
                lineno=node.lineno,
                col_offset=node.col_offset,
                code="X008",
                message="Do not use an explicit '-> None' return annotation; "
                        "omit the return type instead for functions that return nothing.",
            )


def check_percent_formatting(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """
    Rule 8 (X009):

    Forbid old-style '%' string formatting such as:

        "%s %d" % (name, count)
        "%(name)s" % mapping

    and logging-style printf formatting such as:

        logger.info("Updated JSON %s", path)
        logger.debug("value=%d", value)

    Prefer f-strings instead, e.g.:

        logger.info(f"Updated JSON {path}")
    """
    # Matches %s, %d, %(name)s, etc., with optional flags/width/precision.
    percent_pattern = r"%(?:\(\w+\))?[-#0 +]*\d*(?:\.\d+)?[hlL]?[diouxXeEfFgGcrs]"

    def _has_percent_placeholders(s: str) -> bool:
        """Check if string contains percent-style placeholders."""
        return bool(re.search(percent_pattern, s))

    logging_methods = {
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "log",
    }

    for node in ast.walk(tree):
        # ------------------------------------------------------------------
        # Case 1: "%s" % value
        # ------------------------------------------------------------------
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
                message=(
                    "Do not use old-style '%' string formatting "
                    "(e.g. '%s', '%d'); use f-strings instead."
                ),
            )
            continue

        # ------------------------------------------------------------------
        # Case 2: logger.info("foo %s", value)
        # ------------------------------------------------------------------
        if isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue

            if func.attr not in logging_methods:
                continue

            if not node.args:
                continue

            first_arg = node.args[0]
            fmt_value: Optional[str] = None

            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                fmt_value = first_arg.value
            if fmt_value is None:
                continue

            if not _has_percent_placeholders(fmt_value):
                continue

            yield RuleViolation(
                filename=filename,
                lineno=node.lineno,
                col_offset=node.col_offset,
                code="X009",
                message=(
                    "Do not use old-style '%' formatting in logging calls "
                    "(e.g. '... %s', '... %d'); use f-strings instead, "
                    "e.g. logger.info(f\"... {value}\")."
                ),
            )


def check_import_error_suppression(tree: ast.AST, filename: str) -> Iterable[RuleViolation]:
    """
    Rule 9 (X010):

    Forbid suppressing ImportError / ModuleNotFoundError via try/except, e.g.:

        try:
            import foo
        except ImportError:
            foo = None

    This includes not only `import` statements but also `__import__()` calls.
    Import failures must not be turned into optional dependencies or otherwise
    silently ignored. Let them propagate or handle them in a dedicated layer.
    """
    def _has_import_statement_or_call(try_body: Sequence[ast.stmt]) -> bool:
        """Return True if the try body contains import statements or __import__() calls."""
        for stmt in try_body:
            for current_node in ast.walk(stmt):
                if isinstance(current_node, (ast.Import, ast.ImportFrom)):
                    return True
                # Check for __import__() calls
                if isinstance(current_node, ast.Call):
                    if isinstance(current_node.func, ast.Name) and current_node.func.id == "__import__":
                        return True
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue

        for handler in node.handlers:
            if not _except_catches_import_error(handler):
                continue

            if _except_handler_has_raise(handler):
                # Handler re-raises; not considered suppression.
                continue

            # Check if the try block has import statements or __import__() calls
            if _has_import_statement_or_call(node.body):
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


def check_union_none_annotations(tree: ast.AST, filename: str,) -> Iterable[RuleViolation]:
    """
    Rule 10 (X011):

    Forbid use of `Type | None` (PEP 604 union syntax with `None`) in type
    hints and encourage `Optional[Type]` instead, e.g.:

        # forbidden
        def func(param: Foo | None) -> Bar | None: ...

        # preferred
        def func(param: Optional[Foo]) -> Optional[Bar]: ...
    """

    def _report(union_node: ast.AST) -> RuleViolation:
        """Create a RuleViolation for a union type annotation with None."""
        return RuleViolation(
            filename=filename,
            lineno=getattr(union_node, "lineno", 1),
            col_offset=getattr(union_node, "col_offset", 0),
            code="X011",
            message=(
                "Do not use `Type | None` in type hints; "
                "use `Optional[Type]` from typing instead."
            ),
        )

    for node in ast.walk(tree):
        # Function/method parameters
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

            # Return annotation
            if _is_union_with_none(getattr(node, "returns", None)):
                yield _report(node)

        # Annotated assignments: x: Type | None = ...
        elif isinstance(node, ast.AnnAssign):
            if _is_union_with_none(node.annotation):
                yield _report(node.annotation)
