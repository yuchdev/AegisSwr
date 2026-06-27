# Aegis SWR Python Style Guide

Table of Contents

- [1 Background](#s1-background)
- [2 Python Language Rules](#s2-python-language-rules)
  - [2.1 Lint](#s2.1-lint)
  - [2.2 Imports](#s2.2-imports)
  - [2.3 Packages](#s2.3-packages)
  - [2.4 Exceptions](#s2.4-exceptions)
  - [2.5 Mutable Global State](#s2.5-global-variables)
  - [2.6 Nested/Local/Inner Classes and Functions](#s2.6-nested)
  - [2.7 Comprehensions & Generator Expressions](#s2.7-comprehensions)
  - [2.8 Default Iterators and
    Operators](#s2.8-default-iterators-and-operators)
  - [2.9 Generators](#s2.9-generators)
  - [2.10 Lambda Functions](#s2.10-lambda-functions)
  - [2.11 Conditional Expressions](#s2.11-conditional-expressions)
  - [2.12 Default Argument Values](#s2.12-default-argument-values)
  - [2.13 Properties](#s2.13-properties)
  - [2.14 True/False Evaluations](#s2.14-truefalse-evaluations)
  - [2.16 Lexical Scoping](#s2.16-lexical-scoping)
  - [2.17 Function and Method
    Decorators](#s2.17-function-and-method-decorators)
  - [2.18 Threading](#s2.18-threading)
  - [2.19 Power Features](#s2.19-power-features)
  - [2.20 Modern Python: from \_\_future\_\_
    imports](#s2.20-modern-python)
  - [2.21 Type Annotated Code](#s2.21-type-annotated-code)
- [3 Python Style Rules](#s3-python-style-rules)
  - [3.1 Semicolons](#s3.1-semicolons)
  - [3.2 Line length](#s3.2-line-length)
  - [3.3 Parentheses](#s3.3-parentheses)
  - [3.4 Indentation](#s3.4-indentation)
    - [3.4.1 Trailing commas in sequences of
      items?](#s3.4.1-trailing-commas)
  - [3.5 Blank Lines](#s3.5-blank-lines)
  - [3.6 Whitespace](#s3.6-whitespace)
  - [3.7 Shebang Line](#s3.7-shebang-line)
  - [3.8 Comments and Docstrings](#s3.8-comments-and-docstrings)
    - [3.8.1 Docstrings](#s3.8.1-comments-in-doc-strings)
    - [3.8.2 Modules](#s3.8.2-comments-in-modules)
    - [3.8.2.1 Test modules](#s3.8.2.1-test-modules)
    - [3.8.3 Functions and Methods](#s3.8.3-functions-and-methods)
    - [3.8.3.1 Overridden Methods](#s3.8.3.1-overridden-methods)
    - [3.8.4 Classes](#s3.8.4-comments-in-classes)
    - [3.8.5 Block and Inline
      Comments](#s3.8.5-block-and-inline-comments)
    - [3.8.6 Punctuation, Spelling, and
      Grammar](#s3.8.6-punctuation-spelling-and-grammar)
  - [3.10 Strings](#s3.10-strings)
    - [3.10.1 Logging](#s3.10.1-logging)
    - [3.10.2 Error Messages](#s3.10.2-error-messages)
  - [3.11 Files, Sockets, and similar Stateful
    Resources](#s3.11-files-sockets-closeables)
  - [3.12 TODO Comments](#s3.12-todo-comments)
  - [3.13 Imports formatting](#s3.13-imports-formatting)
  - [3.14 Statements](#s3.14-statements)
  - [3.15 Accessors](#s3.15-accessors)
  - [3.16 Naming](#s3.16-naming)
    - [3.16.1 Names to Avoid](#s3.16.1-names-to-avoid)
    - [3.16.2 Naming Conventions](#s3.16.2-naming-conventions)
    - [3.16.3 File Naming](#s3.16.3-file-naming)
    - [3.16.4 Guidelines derived from Guido's
      Recommendations](#s3.16.4-guidelines-derived-from-guidos-recommendations)
  - [3.17 Main](#s3.17-main)
  - [3.18 Function length](#s3.18-function-length)
  - [3.19 Type Annotations](#s3.19-type-annotations)
    - [3.19.1 General Rules](#s3.19.1-general-rules)
    - [3.19.2 Line Breaking](#s3.19.2-line-breaking)
    - [3.19.3 Forward Declarations](#s3.19.3-forward-declarations)
    - [3.19.4 Default Values](#s3.19.4-default-values)
    - [3.19.5 NoneType](#s3.19.5-nonetype)
    - [3.19.6 Type Aliases](#s3.19.6-type-aliases)
    - [3.19.7 Ignoring Types](#s3.19.7-ignoring-types)
    - [3.19.8 Typing Variables](#s3.19.8-typing-variables)
    - [3.19.9 Tuples vs Lists](#s3.19.9-tuples-vs-lists)
    - [3.19.10 Type variables](#s3.19.10-typevars)
    - [3.19.11 String types](#s3.19.11-string-types)
    - [3.19.12 Imports For Typing](#s3.19.12-imports-for-typing)
    - [3.19.13 Conditional Imports](#s3.19.13-conditional-imports)
    - [3.19.14 Circular Dependencies](#s3.19.14-circular-dependencies)
    - [3.19.15 Generics](#s3.19.15-generics)
    - [3.19.16 Build Dependencies](#s3.19.16-build-dependencies)
- [4 Parting Words](#4-parting-words)

[]{#s1-background} []{#1-background}

[]{#background}

## 1 Background[](#1-background){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#1-background}

Python is the main dynamic language used at Google. This style guide is
a list of *dos and don'ts* for Python programs.

To help you format code correctly, we've created a [settings file for
Vim](https://google.github.io/styleguide/google_python_style.vim). For
Emacs, the default settings should be fine.

Many teams use the [Black](https://github.com/psf/black) or
[Pyink](https://github.com/google/pyink) auto-formatter to avoid arguing
over formatting.

[]{#s2-python-language-rules} []{#2-python-language-rules}

[]{#python-language-rules}

## 2 Python Language Rules[](#2-python-language-rules){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2-python-language-rules}

[]{#s2.1-lint} []{#21-lint}

[]{#lint}

### 2.1 Lint[](#21-lint){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#21-lint}

Run `pylint`{.language-plaintext .highlighter-rouge} over your code
using this [pylintrc](https://google.github.io/styleguide/pylintrc).

[]{#s2.1.1-definition} []{#211-definition}

[]{#lint-definition}

#### 2.1.1 Definition[](#211-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#211-definition}

`pylint`{.language-plaintext .highlighter-rouge} is a tool for finding
bugs and style problems in Python source code. It finds problems that
are typically caught by a compiler for less dynamic languages like C and
C++. Because of the dynamic nature of Python, some warnings may be
incorrect; however, spurious warnings should be fairly infrequent.

[]{#s2.1.2-pros} []{#212-pros}

[]{#lint-pros}

#### 2.1.2 Pros[](#212-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#212-pros}

Catches easy-to-miss errors like typos, using-vars-before-assignment,
etc.

[]{#s2.1.3-cons} []{#213-cons}

[]{#lint-cons}

#### 2.1.3 Cons[](#213-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#213-cons}

`pylint`{.language-plaintext .highlighter-rouge} isn't perfect. To take
advantage of it, sometimes we'll need to write around it, suppress its
warnings or fix it.

[]{#s2.1.4-decision} []{#214-decision}

[]{#lint-decision}

#### 2.1.4 Decision[](#214-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#214-decision}

Make sure you run `pylint`{.language-plaintext .highlighter-rouge} on
your code.

Suppress warnings if they are inappropriate so that other issues are not
hidden. To suppress warnings, you can set a line-level comment:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def do_PUT(self):  # WSGI name, so pylint: disable=invalid-name
  ...
```
:::
::::

`pylint`{.language-plaintext .highlighter-rouge} warnings are each
identified by symbolic name (`empty-docstring`{.language-plaintext
.highlighter-rouge}) Google-specific warnings start with
`g-`{.language-plaintext .highlighter-rouge}.

If the reason for the suppression is not clear from the symbolic name,
add an explanation.

Suppressing in this way has the advantage that we can easily search for
suppressions and revisit them.

You can get a list of `pylint`{.language-plaintext .highlighter-rouge}
warnings by doing:

:::: {.language-shell .highlighter-rouge}
::: highlight
``` highlight
pylint --list-msgs
```
:::
::::

To get more information on a particular message, use:

:::: {.language-shell .highlighter-rouge}
::: highlight
``` highlight
pylint --help-msg=invalid-name
```
:::
::::

Prefer `pylint: disable`{.language-plaintext .highlighter-rouge} to the
deprecated older form `pylint: disable-msg`{.language-plaintext
.highlighter-rouge}.

Unused argument warnings can be suppressed by deleting the variables at
the beginning of the function. Always include a comment explaining why
you are deleting it. "Unused." is sufficient. For example:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def viking_cafe_order(spam: str, beans: str, eggs: str | None = None) -> str:
    del beans, eggs  # Unused by vikings.
    return spam + spam + spam
```
:::
::::

Other common forms of suppressing this warning include using
'`_`{.language-plaintext .highlighter-rouge}' as the identifier for the
unused argument or prefixing the argument name with
'`unused_`{.language-plaintext .highlighter-rouge}', or assigning them
to '`_`{.language-plaintext .highlighter-rouge}'. These forms are
allowed but no longer encouraged. These break callers that pass
arguments by name and do not enforce that the arguments are actually
unused.

[]{#s2.2-imports} []{#22-imports}

[]{#imports}

### 2.2 Imports[](#22-imports){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#22-imports}

Use `import`{.language-plaintext .highlighter-rouge} statements for
packages and modules only, not for individual types, classes, or
functions.

[]{#s2.2.1-definition} []{#221-definition}

[]{#imports-definition}

#### 2.2.1 Definition[](#221-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#221-definition}

Reusability mechanism for sharing code from one module to another.

[]{#s2.2.2-pros} []{#222-pros}

[]{#imports-pros}

#### 2.2.2 Pros[](#222-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#222-pros}

The namespace management convention is simple. The source of each
identifier is indicated in a consistent way; `x.Obj`{.language-plaintext
.highlighter-rouge} says that object `Obj`{.language-plaintext
.highlighter-rouge} is defined in module `x`{.language-plaintext
.highlighter-rouge}.

[]{#s2.2.3-cons} []{#223-cons}

[]{#imports-cons}

#### 2.2.3 Cons[](#223-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#223-cons}

Module names can still collide. Some module names are inconveniently
long.

[]{#s2.2.4-decision} []{#224-decision}

[]{#imports-decision}

#### 2.2.4 Decision[](#224-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#224-decision}

- Use `import x`{.language-plaintext .highlighter-rouge} for importing
  packages and modules.
- Use `from x import y`{.language-plaintext .highlighter-rouge} where
  `x`{.language-plaintext .highlighter-rouge} is the package prefix and
  `y`{.language-plaintext .highlighter-rouge} is the module name with no
  prefix.
- Use `from x import y as z`{.language-plaintext .highlighter-rouge} in
  any of the following circumstances:
  - Two modules named `y`{.language-plaintext .highlighter-rouge} are to
    be imported.
  - `y`{.language-plaintext .highlighter-rouge} conflicts with a
    top-level name defined in the current module.
  - `y`{.language-plaintext .highlighter-rouge} conflicts with a common
    parameter name that is part of the public API (e.g.,
    `features`{.language-plaintext .highlighter-rouge}).
  - `y`{.language-plaintext .highlighter-rouge} is an inconveniently
    long name.
  - `y`{.language-plaintext .highlighter-rouge} is too generic in the
    context of your code (e.g.,
    `from storage.file_system import options as fs_options`{.language-plaintext
    .highlighter-rouge}).
- Use `import y as z`{.language-plaintext .highlighter-rouge} only when
  `z`{.language-plaintext .highlighter-rouge} is a standard abbreviation
  (e.g., `import numpy as np`{.language-plaintext .highlighter-rouge}).

For example the module `sound.effects.echo`{.language-plaintext
.highlighter-rouge} may be imported as follows:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from sound.effects import echo
...
echo.EchoFilter(input, output, delay=0.7, atten=4)
```
:::
::::

Do not use relative names in imports. Even if the module is in the same
package, use the full package name. This helps prevent unintentionally
importing a package twice.

[]{#imports-exemptions}

##### 2.2.4.1 Exemptions[](#2241-exemptions){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2241-exemptions}

Exemptions from this rule:

- Symbols from the following modules are used to support static analysis
  and type checking:
  - [`typing`{.language-plaintext .highlighter-rouge}
    module](#typing-imports)
  - [`collections.abc`{.language-plaintext .highlighter-rouge}
    module](#typing-imports)
  - [`typing_extensions`{.language-plaintext .highlighter-rouge}
    module](https://github.com/python/typing_extensions/blob/main/README.md)
- Redirects from the [six.moves
  module](https://six.readthedocs.io/#module-six.moves).

[]{#s2.3-packages} []{#23-packages}

[]{#packages}

### 2.3 Packages[](#23-packages){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#23-packages}

Import each module using the full pathname location of the module.

[]{#s2.3.1-pros} []{#231-pros}

[]{#packages-pros}

#### 2.3.1 Pros[](#231-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#231-pros}

Avoids conflicts in module names or incorrect imports due to the module
search path not being what the author expected. Makes it easier to find
modules.

[]{#s2.3.2-cons} []{#232-cons}

[]{#packages-cons}

#### 2.3.2 Cons[](#232-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#232-cons}

Makes it harder to deploy code because you have to replicate the package
hierarchy. Not really a problem with modern deployment mechanisms.

[]{#s2.3.3-decision} []{#233-decision}

[]{#packages-decision}

#### 2.3.3 Decision[](#233-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#233-decision}

All new code should import each module by its full package name.

Imports should be as follows:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
  # Reference absl.flags in code with the complete name (verbose).
  import absl.flags
  from doctor.who import jodie

  _FOO = absl.flags.DEFINE_string(...)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
  # Reference flags in code with just the module name (common).
  from absl import flags
  from doctor.who import jodie

  _FOO = flags.DEFINE_string(...)
```
:::
::::

*(assume this file lives in `doctor/who/`{.language-plaintext
.highlighter-rouge} where `jodie.py`{.language-plaintext
.highlighter-rouge} also exists)*

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
  # Unclear what module the author wanted and what will be imported.  The actual
  # import behavior depends on external factors controlling sys.path.
  # Which possible jodie module did the author intend to import?
  import jodie
```
:::
::::

The directory the main binary is located in should not be assumed to be
in `sys.path`{.language-plaintext .highlighter-rouge} despite that
happening in some environments. This being the case, code should assume
that `import jodie`{.language-plaintext .highlighter-rouge} refers to a
third-party or top-level package named `jodie`{.language-plaintext
.highlighter-rouge}, not a local `jodie.py`{.language-plaintext
.highlighter-rouge}.

[]{#s2.4-exceptions} []{#24-exceptions}

[]{#exceptions}

### 2.4 Exceptions[](#24-exceptions){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#24-exceptions}

Exceptions are allowed but must be used carefully.

[]{#s2.4.1-definition} []{#241-definition}

[]{#exceptions-definition}

#### 2.4.1 Definition[](#241-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#241-definition}

Exceptions are a means of breaking out of normal control flow to handle
errors or other exceptional conditions.

[]{#s2.4.2-pros} []{#242-pros}

[]{#exceptions-pros}

#### 2.4.2 Pros[](#242-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#242-pros}

The control flow of normal operation code is not cluttered by
error-handling code. It also allows the control flow to skip multiple
frames when a certain condition occurs, e.g., returning from N nested
functions in one step instead of having to plumb error codes through.

[]{#s2.4.3-cons} []{#243-cons}

[]{#exceptions-cons}

#### 2.4.3 Cons[](#243-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#243-cons}

May cause the control flow to be confusing. Easy to miss error cases
when making library calls.

[]{#s2.4.4-decision} []{#244-decision}

[]{#exceptions-decision}

#### 2.4.4 Decision[](#244-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#244-decision}

Exceptions must follow certain conditions:

- Make use of built-in exception classes when it makes sense. For
  example, raise a `ValueError`{.language-plaintext .highlighter-rouge}
  to indicate a programming mistake like a violated precondition, such
  as may happen when validating function arguments.

- Do not use `assert`{.language-plaintext .highlighter-rouge} statements
  in place of conditionals or validating preconditions. They must not be
  critical to the application logic. A litmus test would be that the
  `assert`{.language-plaintext .highlighter-rouge} could be removed
  without breaking the code. `assert`{.language-plaintext
  .highlighter-rouge} conditionals are [not
  guaranteed](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)
  to be evaluated. For [pytest](https://pytest.org/) based tests,
  `assert`{.language-plaintext .highlighter-rouge} is okay and expected
  to verify expectations. For example:

  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  Yes:
    def connect_to_next_port(self, minimum: int) -> int:
      """Connects to the next available port.

      Args:
        minimum: A port value greater or equal to 1024.

      Returns:
        The new minimum port.

      Raises:
        ConnectionError: If no available port is found.
      """
      if minimum < 1024:
        # Note that this raising of ValueError is not mentioned in the doc
        # string's "Raises:" section because it is not appropriate to
        # guarantee this specific behavioral reaction to API misuse.
        raise ValueError(f'Min. port must be at least 1024, not {minimum}.')
      port = self._find_next_open_port(minimum)
      if port is None:
        raise ConnectionError(
            f'Could not connect to service on port {minimum} or higher.')
      # The code does not depend on the result of this assert.
      assert port >= minimum, (
          f'Unexpected port {port} when minimum was {minimum}.')
      return port
  ```
  :::
  ::::

  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  No:
    def connect_to_next_port(self, minimum: int) -> int:
      """Connects to the next available port.

      Args:
        minimum: A port value greater or equal to 1024.

      Returns:
        The new minimum port.
      """
      assert minimum >= 1024, 'Minimum port must be at least 1024.'
      # The following code depends on the previous assert.
      port = self._find_next_open_port(minimum)
      assert port is not None
      # The type checking of the return statement relies on the assert.
      return port
  ```
  :::
  ::::

- Libraries or packages may define their own exceptions. When doing so
  they must inherit from an existing exception class. Exception names
  should end in `Error`{.language-plaintext .highlighter-rouge} and
  should not introduce repetition (`foo.FooError`{.language-plaintext
  .highlighter-rouge}).

- Never use catch-all `except:`{.language-plaintext .highlighter-rouge}
  statements, or catch `Exception`{.language-plaintext
  .highlighter-rouge} or `StandardError`{.language-plaintext
  .highlighter-rouge}, unless you are

  - re-raising the exception, or
  - creating an isolation point in the program where exceptions are not
    propagated but are recorded and suppressed instead, such as
    protecting a thread from crashing by guarding its outermost block.

  Python is very tolerant in this regard and
  `except:`{.language-plaintext .highlighter-rouge} will really catch
  everything including misspelled names, sys.exit() calls, Ctrl+C
  interrupts, unittest failures and all kinds of other exceptions that
  you simply don't want to catch.

- Minimize the amount of code in a `try`{.language-plaintext
  .highlighter-rouge}/`except`{.language-plaintext .highlighter-rouge}
  block. The larger the body of the `try`{.language-plaintext
  .highlighter-rouge}, the more likely that an exception will be raised
  by a line of code that you didn't expect to raise an exception. In
  those cases, the `try`{.language-plaintext
  .highlighter-rouge}/`except`{.language-plaintext .highlighter-rouge}
  block hides a real error.

- Use the `finally`{.language-plaintext .highlighter-rouge} clause to
  execute code whether or not an exception is raised in the
  `try`{.language-plaintext .highlighter-rouge} block. This is often
  useful for cleanup, i.e., closing a file.

[]{#s2.5-global-variables} []{#25-global-variables}
[]{#s2.5-global-state} []{#25-global-state}

[]{#global-variables}

### 2.5 Mutable Global State[](#25-mutable-global-state){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#25-mutable-global-state}

Avoid mutable global state.

[]{#s2.5.1-definition} []{#251-definition}

[]{#global-variables-definition}

#### 2.5.1 Definition[](#251-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#251-definition}

Module-level values or class attributes that can get mutated during
program execution.

[]{#s2.5.2-pros} []{#252-pros}

[]{#global-variables-pros}

#### 2.5.2 Pros[](#252-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#252-pros}

Occasionally useful.

[]{#s2.5.3-cons} []{#253-cons}

[]{#global-variables-cons}

#### 2.5.3 Cons[](#253-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#253-cons}

- Breaks encapsulation: Such design can make it hard to achieve valid
  objectives. For example, if global state is used to manage a database
  connection, then connecting to two different databases at the same
  time (such as for computing differences during a migration) becomes
  difficult. Similar problems easily arise with global registries.

- Has the potential to change module behavior during the import, because
  assignments to global variables are done when the module is first
  imported.

[]{#s2.5.4-decision} []{#254-decision}

[]{#global-variables-decision}

#### 2.5.4 Decision[](#254-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#254-decision}

Avoid mutable global state.

In those rare cases where using global state is warranted, mutable
global entities should be declared at the module level or as a class
attribute and made internal by prepending an `_`{.language-plaintext
.highlighter-rouge} to the name. If necessary, external access to
mutable global state must be done through public functions or class
methods. See [Naming](#s3.16-naming) below. Please explain the design
reasons why mutable global state is being used in a comment or a doc
linked to from a comment.

Module-level constants are permitted and encouraged. For example:
`_MAX_HOLY_HANDGRENADE_COUNT = 3`{.language-plaintext
.highlighter-rouge} for an internal use constant or
`SIR_LANCELOTS_FAVORITE_COLOR = "blue"`{.language-plaintext
.highlighter-rouge} for a public API constant. Constants must be named
using all caps with underscores. See [Naming](#s3.16-naming) below.

[]{#s2.6-nested} []{#26-nested}

[]{#nested-classes-functions}

### 2.6 Nested/Local/Inner Classes and Functions[](#26-nestedlocalinner-classes-and-functions){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#26-nestedlocalinner-classes-and-functions}

Nested local functions or classes are fine when used to close over a
local variable. Inner classes are fine.

[]{#s2.6.1-definition} []{#261-definition}

[]{#nested-classes-functions-definition}

#### 2.6.1 Definition[](#261-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#261-definition}

A class can be defined inside of a method, function, or class. A
function can be defined inside a method or function. Nested functions
have read-only access to variables defined in enclosing scopes.

[]{#s2.6.2-pros} []{#262-pros}

[]{#nested-classes-functions-pros}

#### 2.6.2 Pros[](#262-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#262-pros}

Allows definition of utility classes and functions that are only used
inside of a very limited scope. Very
[ADT](https://en.wikipedia.org/wiki/Abstract_data_type)-y. Commonly used
for implementing decorators.

[]{#s2.6.3-cons} []{#263-cons}

[]{#nested-classes-functions-cons}

#### 2.6.3 Cons[](#263-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#263-cons}

Nested functions and classes cannot be directly tested. Nesting can make
the outer function longer and less readable.

[]{#s2.6.4-decision} []{#264-decision}

[]{#nested-classes-functions-decision}

#### 2.6.4 Decision[](#264-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#264-decision}

They are fine with some caveats. Avoid nested functions or classes
except when closing over a local value other than
`self`{.language-plaintext .highlighter-rouge} or
`cls`{.language-plaintext .highlighter-rouge}. Do not nest a function
just to hide it from users of a module. Instead, prefix its name with an
\_ at the module level so that it can still be accessed by tests.

[]{#s2.7-comprehensions} []{#s2.7-list_comprehensions}
[]{#27-list_comprehensions} []{#list_comprehensions}
[]{#list-comprehensions}

[]{#comprehensions}

### 2.7 Comprehensions & Generator Expressions[](#27-comprehensions--generator-expressions){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#27-comprehensions--generator-expressions}

Okay to use for simple cases.

[]{#s2.7.1-definition} []{#271-definition}

[]{#comprehensions-definition}

#### 2.7.1 Definition[](#271-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#271-definition}

List, Dict, and Set comprehensions as well as generator expressions
provide a concise and efficient way to create container types and
iterators without resorting to the use of traditional loops,
`map()`{.language-plaintext .highlighter-rouge},
`filter()`{.language-plaintext .highlighter-rouge}, or
`lambda`{.language-plaintext .highlighter-rouge}.

[]{#s2.7.2-pros} []{#272-pros}

[]{#comprehensions-pros}

#### 2.7.2 Pros[](#272-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#272-pros}

Simple comprehensions can be clearer and simpler than other dict, list,
or set creation techniques. Generator expressions can be very efficient,
since they avoid the creation of a list entirely.

[]{#s2.7.3-cons} []{#273-cons}

[]{#comprehensions-cons}

#### 2.7.3 Cons[](#273-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#273-cons}

Complicated comprehensions or generator expressions can be hard to read.

[]{#s2.7.4-decision} []{#274-decision}

[]{#comprehensions-decision}

#### 2.7.4 Decision[](#274-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#274-decision}

Comprehensions are allowed, however multiple `for`{.language-plaintext
.highlighter-rouge} clauses or filter expressions are not permitted.
Optimize for readability, not conciseness.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
  result = [mapping_expr for value in iterable if filter_expr]

  result = [
      is_valid(metric={'key': value})
      for value in interesting_iterable
      if a_longer_filter_expression(value)
  ]

  descriptive_name = [
      transform({'key': key, 'value': value}, color='black')
      for key, value in generate_iterable(some_input)
      if complicated_condition_is_met(key, value)
  ]

  result = []
  for x in range(10):
    for y in range(5):
      if x * y > 10:
        result.append((x, y))

  return {
      x: complicated_transform(x)
      for x in long_generator_function(parameter)
      if x is not None
  }

  return (x**2 for x in range(10))

  unique_names = {user.name for user in users if user is not None}
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
  result = [(x, y) for x in range(10) for y in range(5) if x * y > 10]

  return (
      (x, y, z)
      for x in range(5)
      for y in range(5)
      if x != y
      for z in range(5)
      if y != z
  )
```
:::
::::

[]{#s2.8-default-iterators-and-operators}

[]{#default-iterators-operators}

### 2.8 Default Iterators and Operators[](#28-default-iterators-and-operators){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#28-default-iterators-and-operators}

Use default iterators and operators for types that support them, like
lists, dictionaries, and files.

[]{#s2.8.1-definition} []{#281-definition}

[]{#default-iterators-operators-definition}

#### 2.8.1 Definition[](#281-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#281-definition}

Container types, like dictionaries and lists, define default iterators
and membership test operators ("in" and "not in").

[]{#s2.8.2-pros} []{#282-pros}

[]{#default-iterators-operators-pros}

#### 2.8.2 Pros[](#282-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#282-pros}

The default iterators and operators are simple and efficient. They
express the operation directly, without extra method calls. A function
that uses default operators is generic. It can be used with any type
that supports the operation.

[]{#s2.8.3-cons} []{#283-cons}

[]{#default-iterators-operators-cons}

#### 2.8.3 Cons[](#283-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#283-cons}

You can't tell the type of objects by reading the method names (unless
the variable has type annotations). This is also an advantage.

[]{#s2.8.4-decision} []{#284-decision}

[]{#default-iterators-operators-decision}

#### 2.8.4 Decision[](#284-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#284-decision}

Use default iterators and operators for types that support them, like
lists, dictionaries, and files. The built-in types define iterator
methods, too. Prefer these methods to methods that return lists, except
that you should not mutate a container while iterating over it.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:  for key in adict: ...
      if obj in alist: ...
      for line in afile: ...
      for k, v in adict.items(): ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:   for key in adict.keys(): ...
      for line in afile.readlines(): ...
```
:::
::::

[]{#s2.9-generators} []{#29-generators}

[]{#generators}

### 2.9 Generators[](#29-generators){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#29-generators}

Use generators as needed.

[]{#s2.9.1-definition} []{#291-definition}

[]{#generators-definition}

#### 2.9.1 Definition[](#291-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#291-definition}

A generator function returns an iterator that yields a value each time
it executes a yield statement. After it yields a value, the runtime
state of the generator function is suspended until the next value is
needed.

[]{#s2.9.2-pros} []{#292-pros}

[]{#generators-pros}

#### 2.9.2 Pros[](#292-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#292-pros}

Simpler code, because the state of local variables and control flow are
preserved for each call. A generator uses less memory than a function
that creates an entire list of values at once.

[]{#s2.9.3-cons} []{#293-cons}

[]{#generators-cons}

#### 2.9.3 Cons[](#293-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#293-cons}

Local variables in the generator will not be garbage collected until the
generator is either consumed to exhaustion or itself garbage collected.

[]{#s2.9.4-decision} []{#294-decision}

[]{#generators-decision}

#### 2.9.4 Decision[](#294-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#294-decision}

Fine. Use "Yields:" rather than "Returns:" in the docstring for
generator functions.

If the generator manages an expensive resource, make sure to force the
clean up.

A good way to do the clean up is by wrapping the generator with a
context manager [PEP-0533](https://peps.python.org/pep-0533/).

[]{#s2.10-lambda-functions} []{#210-lambda-functions}

[]{#lambdas}

### 2.10 Lambda Functions[](#210-lambda-functions){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#210-lambda-functions}

Okay for one-liners. Prefer generator expressions over
`map()`{.language-plaintext .highlighter-rouge} or
`filter()`{.language-plaintext .highlighter-rouge} with a
`lambda`{.language-plaintext .highlighter-rouge}.

[]{#s2.10.1-definition} []{#2101-definition}

[]{#lambdas-definition}

#### 2.10.1 Definition[](#2101-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2101-definition}

Lambdas define anonymous functions in an expression, as opposed to a
statement.

[]{#s2.10.2-pros} []{#2102-pros}

[]{#lambdas-pros}

#### 2.10.2 Pros[](#2102-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2102-pros}

Convenient.

[]{#s2.10.3-cons} []{#2103-cons}

[]{#lambdas-cons}

#### 2.10.3 Cons[](#2103-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2103-cons}

Harder to read and debug than local functions. The lack of names means
stack traces are more difficult to understand. Expressiveness is limited
because the function may only contain an expression.

[]{#s2.10.4-decision} []{#2104-decision}

[]{#lambdas-decision}

#### 2.10.4 Decision[](#2104-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2104-decision}

Lambdas are allowed. If the code inside the lambda function spans
multiple lines or is longer than 60-80 chars, it might be better to
define it as a regular [nested function](#lexical-scoping).

For common operations like multiplication, use the functions from the
`operator`{.language-plaintext .highlighter-rouge} module instead of
lambda functions. For example, prefer `operator.mul`{.language-plaintext
.highlighter-rouge} to `lambda x, y: x * y`{.language-plaintext
.highlighter-rouge}.

[]{#s2.11-conditional-expressions} []{#211-conditional-expressions}

[]{#conditional-expressions}

### 2.11 Conditional Expressions[](#211-conditional-expressions){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#211-conditional-expressions}

Okay for simple cases.

[]{#s2.11.1-definition} []{#2111-definition}

[]{#conditional-expressions-definition}

#### 2.11.1 Definition[](#2111-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2111-definition}

Conditional expressions (sometimes called a "ternary operator") are
mechanisms that provide a shorter syntax for if statements. For example:
`x = 1 if cond else 2`{.language-plaintext .highlighter-rouge}.

[]{#s2.11.2-pros} []{#2112-pros}

[]{#conditional-expressions-pros}

#### 2.11.2 Pros[](#2112-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2112-pros}

Shorter and more convenient than an if statement.

[]{#s2.11.3-cons} []{#2113-cons}

[]{#conditional-expressions-cons}

#### 2.11.3 Cons[](#2113-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2113-cons}

May be harder to read than an if statement. The condition may be
difficult to locate if the expression is long.

[]{#s2.11.4-decision} []{#2114-decision}

[]{#conditional-expressions-decision}

#### 2.11.4 Decision[](#2114-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2114-decision}

Okay to use for simple cases. Each portion must fit on one line:
true-expression, if-expression, else-expression. Use a complete if
statement when things get more complicated.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
    one_line = 'yes' if predicate(value) else 'no'
    slightly_split = ('yes' if predicate(value)
                      else 'no, nein, nyet')
    the_longest_ternary_style_that_can_be_done = (
        'yes, true, affirmative, confirmed, correct'
        if predicate(value)
        else 'no, false, negative, nay')
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
    bad_line_breaking = ('yes' if predicate(value) else
                         'no')
    portion_too_long = ('yes'
                        if some_long_module.some_long_predicate_function(
                            really_long_variable_name)
                        else 'no, false, negative, nay')
```
:::
::::

[]{#s2.12-default-argument-values} []{#212-default-argument-values}

[]{#default-arguments}

### 2.12 Default Argument Values[](#212-default-argument-values){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#212-default-argument-values}

Okay in most cases.

[]{#s2.12.1-definition} []{#2121-definition}

[]{#default-arguments-definition}

#### 2.12.1 Definition[](#2121-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2121-definition}

You can specify values for variables at the end of a function's
parameter list, e.g., `def foo(a, b=0):`{.language-plaintext
.highlighter-rouge}. If `foo`{.language-plaintext .highlighter-rouge} is
called with only one argument, `b`{.language-plaintext
.highlighter-rouge} is set to 0. If it is called with two arguments,
`b`{.language-plaintext .highlighter-rouge} has the value of the second
argument.

[]{#s2.12.2-pros} []{#2122-pros}

[]{#default-arguments-pros}

#### 2.12.2 Pros[](#2122-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2122-pros}

Often you have a function that uses lots of default values, but on rare
occasions you want to override the defaults. Default argument values
provide an easy way to do this, without having to define lots of
functions for the rare exceptions. As Python does not support overloaded
methods/functions, default arguments are an easy way of "faking" the
overloading behavior.

[]{#s2.12.3-cons} []{#2123-cons}

[]{#default-arguments-cons}

#### 2.12.3 Cons[](#2123-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2123-cons}

Default arguments are evaluated once at module load time. This may cause
problems if the argument is a mutable object such as a list or a
dictionary. If the function modifies the object (e.g., by appending an
item to a list), the default value is modified.

[]{#s2.12.4-decision} []{#2124-decision}

[]{#default-arguments-decision}

#### 2.12.4 Decision[](#2124-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2124-decision}

Okay to use with the following caveat:

Do not use mutable objects as default values in the function or method
definition.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: def foo(a, b=None):
         if b is None:
             b = []
Yes: def foo(a, b: Sequence | None = None):
         if b is None:
             b = []
Yes: def foo(a, b: Sequence = ()):  # Empty tuple OK since tuples are immutable.
         ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from absl import flags
_FOO = flags.DEFINE_string(...)

No:  def foo(a, b=[]):
         ...
No:  def foo(a, b=time.time()):  # Is `b` supposed to represent when this module was loaded?
         ...
No:  def foo(a, b=_FOO.value):  # sys.argv has not yet been parsed...
         ...
No:  def foo(a, b: Mapping = {}):  # Could still get passed to unchecked code.
         ...
```
:::
::::

[]{#s2.13-properties} []{#213-properties}

[]{#properties}

### 2.13 Properties[](#213-properties){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#213-properties}

Properties may be used to control getting or setting attributes that
require trivial computations or logic. Property implementations must
match the general expectations of regular attribute access: that they
are cheap, straightforward, and unsurprising.

[]{#s2.13.1-definition} []{#2131-definition}

[]{#properties-definition}

#### 2.13.1 Definition[](#2131-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2131-definition}

A way to wrap method calls for getting and setting an attribute as a
standard attribute access.

[]{#s2.13.2-pros} []{#2132-pros}

[]{#properties-pros}

#### 2.13.2 Pros[](#2132-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2132-pros}

- Allows for an attribute access and assignment API rather than [getter
  and setter](#getters-and-setters) method calls.
- Can be used to make an attribute read-only.
- Allows calculations to be lazy.
- Provides a way to maintain the public interface of a class when the
  internals evolve independently of class users.

[]{#s2.13.3-cons} []{#2133-cons}

[]{#properties-cons}

#### 2.13.3 Cons[](#2133-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2133-cons}

- Can hide side-effects much like operator overloading.
- Can be confusing for subclasses.

[]{#s2.13.4-decision} []{#2134-decision}

[]{#properties-decision}

#### 2.13.4 Decision[](#2134-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2134-decision}

Properties are allowed, but, like operator overloading, should only be
used when necessary and match the expectations of typical attribute
access; follow the [getters and setters](#getters-and-setters) rules
otherwise.

For example, using a property to simply both get and set an internal
attribute isn't allowed: there is no computation occurring, so the
property is unnecessary ([make the attribute public
instead](#getters-and-setters)). In comparison, using a property to
control attribute access or to calculate a *trivially* derived value is
allowed: the logic is simple and unsurprising.

Properties should be created with the `@property`{.language-plaintext
.highlighter-rouge} [decorator](#s2.17-function-and-method-decorators).
Manually implementing a property descriptor is considered a [power
feature](#power-features).

Inheritance with properties can be non-obvious. Do not use properties to
implement computations a subclass may ever want to override and extend.

[]{#s2.14-truefalse-evaluations} []{#214-truefalse-evaluations}

[]{#truefalse-evaluations}

### 2.14 True/False Evaluations[](#214-truefalse-evaluations){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#214-truefalse-evaluations}

Use the "implicit" false if at all possible (with a few caveats).

[]{#s2.14.1-definition} []{#2141-definition}

[]{#truefalse-evaluations-definition}

#### 2.14.1 Definition[](#2141-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2141-definition}

Python evaluates certain values as `False`{.language-plaintext
.highlighter-rouge} when in a boolean context. A quick "rule of thumb"
is that all "empty" values are considered false, so
`0, None, [], {}, ''`{.language-plaintext .highlighter-rouge} all
evaluate as false in a boolean context.

[]{#s2.14.2-pros} []{#2142-pros}

[]{#truefalse-evaluations-pros}

#### 2.14.2 Pros[](#2142-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2142-pros}

Conditions using Python booleans are easier to read and less
error-prone. In most cases, they're also faster.

[]{#s2.14.3-cons} []{#2143-cons}

[]{#truefalse-evaluations-cons}

#### 2.14.3 Cons[](#2143-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2143-cons}

May look strange to C/C++ developers.

[]{#s2.14.4-decision} []{#2144-decision}

[]{#truefalse-evaluations-decision}

#### 2.14.4 Decision[](#2144-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2144-decision}

Use the "implicit" false if possible, e.g.,
`if foo:`{.language-plaintext .highlighter-rouge} rather than
`if foo != []:`{.language-plaintext .highlighter-rouge}. There are a few
caveats that you should keep in mind though:

- Always use `if foo is None:`{.language-plaintext .highlighter-rouge}
  (or `is not None`{.language-plaintext .highlighter-rouge}) to check
  for a `None`{.language-plaintext .highlighter-rouge} value. E.g., when
  testing whether a variable or argument that defaults to
  `None`{.language-plaintext .highlighter-rouge} was set to some other
  value. The other value might be a value that's false in a boolean
  context!

- Never compare a boolean variable to `False`{.language-plaintext
  .highlighter-rouge} using `==`{.language-plaintext
  .highlighter-rouge}. Use `if not x:`{.language-plaintext
  .highlighter-rouge} instead. If you need to distinguish
  `False`{.language-plaintext .highlighter-rouge} from
  `None`{.language-plaintext .highlighter-rouge} then chain the
  expressions, such as `if not x and x is not None:`{.language-plaintext
  .highlighter-rouge}.

- For sequences (strings, lists, tuples), use the fact that empty
  sequences are false, so `if seq:`{.language-plaintext
  .highlighter-rouge} and `if not seq:`{.language-plaintext
  .highlighter-rouge} are preferable to
  `if len(seq):`{.language-plaintext .highlighter-rouge} and
  `if not len(seq):`{.language-plaintext .highlighter-rouge}
  respectively.

- When handling integers, implicit false may involve more risk than
  benefit (i.e., accidentally handling `None`{.language-plaintext
  .highlighter-rouge} as 0). You may compare a value which is known to
  be an integer (and is not the result of `len()`{.language-plaintext
  .highlighter-rouge}) against the integer 0.

  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  Yes: if not users:
           print('no users')

       if i % 10 == 0:
           self.handle_multiple_of_ten()

       def f(x=None):
           if x is None:
               x = []
  ```
  :::
  ::::

  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  No:  if len(users) == 0:
           print('no users')

       if not i % 10:
           self.handle_multiple_of_ten()

       def f(x=None):
           x = x or []
  ```
  :::
  ::::

- Note that `'0'`{.language-plaintext .highlighter-rouge} (i.e.,
  `0`{.language-plaintext .highlighter-rouge} as string) evaluates to
  true.

- Note that Numpy arrays may raise an exception in an implicit boolean
  context. Prefer the `.size`{.language-plaintext .highlighter-rouge}
  attribute when testing emptiness of a `np.array`{.language-plaintext
  .highlighter-rouge} (e.g. `if not users.size`{.language-plaintext
  .highlighter-rouge}).

[]{#s2.16-lexical-scoping} []{#216-lexical-scoping}

[]{#lexical-scoping}

### 2.16 Lexical Scoping[](#216-lexical-scoping){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#216-lexical-scoping}

Okay to use.

[]{#s2.16.1-definition} []{#2161-definition}

[]{#lexical-scoping-definition}

#### 2.16.1 Definition[](#2161-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2161-definition}

A nested Python function can refer to variables defined in enclosing
functions, but cannot assign to them. Variable bindings are resolved
using lexical scoping, that is, based on the static program text. Any
assignment to a name in a block will cause Python to treat all
references to that name as a local variable, even if the use precedes
the assignment. If a global declaration occurs, the name is treated as a
global variable.

An example of the use of this feature is:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def get_adder(summand1: float) -> Callable[[float], float]:
    """Returns a function that adds numbers to a given number."""
    def adder(summand2: float) -> float:
        return summand1 + summand2

    return adder
```
:::
::::

[]{#s2.16.2-pros} []{#2162-pros}

[]{#lexical-scoping-pros}

#### 2.16.2 Pros[](#2162-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2162-pros}

Often results in clearer, more elegant code. Especially comforting to
experienced Lisp and Scheme (and Haskell and ML and ...) programmers.

[]{#s2.16.3-cons} []{#2163-cons}

[]{#lexical-scoping-cons}

#### 2.16.3 Cons[](#2163-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2163-cons}

Can lead to confusing bugs, such as this example based on
[PEP-0227](https://peps.python.org/pep-0227/):

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
i = 4
def foo(x: Iterable[int]):
    def bar():
        print(i, end='')
    # ...
    # A bunch of code here
    # ...
    for i in x:  # Ah, i *is* local to foo, so this is what bar sees
        print(i, end='')
    bar()
```
:::
::::

So `foo([1, 2, 3])`{.language-plaintext .highlighter-rouge} will print
`1 2 3 3`{.language-plaintext .highlighter-rouge}, not
`1 2 3 4`{.language-plaintext .highlighter-rouge}.

[]{#s2.16.4-decision} []{#2164-decision}

[]{#lexical-scoping-decision}

#### 2.16.4 Decision[](#2164-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2164-decision}

Okay to use.

[]{#s2.17-function-and-method-decorators}
[]{#217-function-and-method-decorators}
[]{#function-and-method-decorators}

[]{#decorators}

### 2.17 Function and Method Decorators[](#217-function-and-method-decorators){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#217-function-and-method-decorators}

Use decorators judiciously when there is a clear advantage. Avoid
`staticmethod`{.language-plaintext .highlighter-rouge} and limit use of
`classmethod`{.language-plaintext .highlighter-rouge}.

[]{#s2.17.1-definition} []{#2171-definition}

[]{#decorators-definition}

#### 2.17.1 Definition[](#2171-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2171-definition}

[Decorators for Functions and
Methods](https://docs.python.org/3/glossary.html#term-decorator) (a.k.a
"the `@`{.language-plaintext .highlighter-rouge} notation"). One common
decorator is `@property`{.language-plaintext .highlighter-rouge}, used
for converting ordinary methods into dynamically computed attributes.
However, the decorator syntax allows for user-defined decorators as
well. Specifically, for some function `my_decorator`{.language-plaintext
.highlighter-rouge}, this:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
class C:
    @my_decorator
    def method(self):
        # method body ...
```
:::
::::

is equivalent to:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
class C:
    def method(self):
        # method body ...
    method = my_decorator(method)
```
:::
::::

[]{#s2.17.2-pros} []{#2172-pros}

[]{#decorators-pros}

#### 2.17.2 Pros[](#2172-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2172-pros}

Elegantly specifies some transformation on a method; the transformation
might eliminate some repetitive code, enforce invariants, etc.

[]{#s2.17.3-cons} []{#2173-cons}

[]{#decorators-cons}

#### 2.17.3 Cons[](#2173-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2173-cons}

Decorators can perform arbitrary operations on a function's arguments or
return values, resulting in surprising implicit behavior. Additionally,
decorators execute at object definition time. For module-level objects
(classes, module functions, ...) this happens at import time. Failures
in decorator code are pretty much impossible to recover from.

[]{#s2.17.4-decision} []{#2174-decision}

[]{#decorators-decision}

#### 2.17.4 Decision[](#2174-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2174-decision}

Use decorators judiciously when there is a clear advantage. Decorators
should follow the same import and naming guidelines as functions. A
decorator docstring should clearly state that the function is a
decorator. Write unit tests for decorators.

Avoid external dependencies in the decorator itself (e.g. don't rely on
files, sockets, database connections, etc.), since they might not be
available when the decorator runs (at import time, perhaps from
`pydoc`{.language-plaintext .highlighter-rouge} or other tools). A
decorator that is called with valid parameters should (as much as
possible) be guaranteed to succeed in all cases.

Decorators are a special case of "top-level code" - see
[main](#s3.17-main) for more discussion.

Never use `staticmethod`{.language-plaintext .highlighter-rouge} unless
forced to in order to integrate with an API defined in an existing
library. Write a module-level function instead.

Use `classmethod`{.language-plaintext .highlighter-rouge} only when
writing a named constructor, or a class-specific routine that modifies
necessary global state such as a process-wide cache.

[]{#s2.18-threading} []{#218-threading}

[]{#threading}

### 2.18 Threading[](#218-threading){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#218-threading}

Do not rely on the atomicity of built-in types.

While Python's built-in data types such as dictionaries appear to have
atomic operations, there are corner cases where they aren't atomic (e.g.
if `__hash__`{.language-plaintext .highlighter-rouge} or
`__eq__`{.language-plaintext .highlighter-rouge} are implemented as
Python methods) and their atomicity should not be relied upon. Neither
should you rely on atomic variable assignment (since this in turn
depends on dictionaries).

Use the `queue`{.language-plaintext .highlighter-rouge} module's
`Queue`{.language-plaintext .highlighter-rouge} data type as the
preferred way to communicate data between threads. Otherwise, use the
`threading`{.language-plaintext .highlighter-rouge} module and its
locking primitives. Prefer condition variables and
`threading.Condition`{.language-plaintext .highlighter-rouge} instead of
using lower-level locks.

[]{#s2.19-power-features} []{#219-power-features}

[]{#power-features}

### 2.19 Power Features[](#219-power-features){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#219-power-features}

Avoid these features.

[]{#s2.19.1-definition} []{#2191-definition}

[]{#power-features-definition}

#### 2.19.1 Definition[](#2191-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2191-definition}

Python is an extremely flexible language and gives you many fancy
features such as custom metaclasses, access to bytecode, on-the-fly
compilation, dynamic inheritance, object reparenting, import hacks,
reflection (e.g. some uses of `getattr()`{.language-plaintext
.highlighter-rouge}), modification of system internals,
`__del__`{.language-plaintext .highlighter-rouge} methods implementing
customized cleanup, etc.

[]{#s2.19.2-pros} []{#2192-pros}

[]{#power-features-pros}

#### 2.19.2 Pros[](#2192-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2192-pros}

These are powerful language features. They can make your code more
compact.

[]{#s2.19.3-cons} []{#2193-cons}

[]{#power-features-cons}

#### 2.19.3 Cons[](#2193-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2193-cons}

It's very tempting to use these "cool" features when they're not
absolutely necessary. It's harder to read, understand, and debug code
that's using unusual features underneath. It doesn't seem that way at
first (to the original author), but when revisiting the code, it tends
to be more difficult than code that is longer but is straightforward.

[]{#s2.19.4-decision} []{#2194-decision}

[]{#power-features-decision}

#### 2.19.4 Decision[](#2194-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2194-decision}

Avoid these features in your code.

Standard library modules and classes that internally use these features
are okay to use (for example, `abc.ABCMeta`{.language-plaintext
.highlighter-rouge}, `dataclasses`{.language-plaintext
.highlighter-rouge}, and `enum`{.language-plaintext
.highlighter-rouge}).

[]{#s2.20-modern-python} []{#220-modern-python}

[]{#modern-python}

### 2.20 Modern Python: from \_\_future\_\_ imports[](#220-modern-python-from-__future__-imports){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#220-modern-python-from-__future__-imports}

New language version semantic changes may be gated behind a special
future import to enable them on a per-file basis within earlier
runtimes.

[]{#s2.20.1-definition} []{#2201-definition}

[]{#modern-python-definition}

#### 2.20.1 Definition[](#2201-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2201-definition}

Being able to turn on some of the more modern features via
`from __future__ import`{.language-plaintext .highlighter-rouge}
statements allows early use of features from expected future Python
versions.

[]{#s2.20.2-pros} []{#2202-pros}

[]{#modern-python-pros}

#### 2.20.2 Pros[](#2202-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2202-pros}

This has proven to make runtime version upgrades smoother as changes can
be made on a per-file basis while declaring compatibility and preventing
regressions within those files. Modern code is more maintainable as it
is less likely to accumulate technical debt that will be problematic
during future runtime upgrades.

[]{#s2.20.3-cons} []{#2203-cons}

[]{#modern-python-cons}

#### 2.20.3 Cons[](#2203-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2203-cons}

Such code may not work on very old interpreter versions prior to the
introduction of the needed future statement. The need for this is more
common in projects supporting an extremely wide variety of environments.

[]{#s2.20.4-decision} []{#2204-decision}

[]{#modern-python-decision}

#### 2.20.4 Decision[](#2204-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2204-decision}

##### from \_\_future\_\_ imports[](#from-__future__-imports){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"}

Use of `from __future__ import`{.language-plaintext .highlighter-rouge}
statements is encouraged. It allows a given source file to start using
more modern Python syntax features today. Once you no longer need to run
on a version where the features are hidden behind a
`__future__`{.language-plaintext .highlighter-rouge} import, feel free
to remove those lines.

In code that may execute on versions as old as 3.5 rather than \>= 3.7,
import:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from __future__ import generator_stop
```
:::
::::

For more information read the [Python future statement
definitions](https://docs.python.org/3/library/__future__.html)
documentation.

Please don't remove these imports until you are confident the code is
only ever used in a sufficiently modern environment. Even if you do not
currently use the feature a specific future import enables in your code
today, keeping it in place in the file prevents later modifications of
the code from inadvertently depending on the older behavior.

Use other `from __future__`{.language-plaintext .highlighter-rouge}
import statements as you see fit.

[]{#s2.21-type-annotated-code} []{#s2.21-typed-code}
[]{#221-type-annotated-code} []{#typed-code}

[]{#typed-code}

### 2.21 Type Annotated Code[](#221-type-annotated-code){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#221-type-annotated-code}

You can annotate Python code with [type
hints](https://docs.python.org/3/library/typing.html). Type-check the
code at build time with a type checking tool like
[pytype](https://github.com/google/pytype). In most cases, when
feasible, type annotations are in source files. For third-party or
extension modules, annotations can be in [stub
`.pyi`{.language-plaintext .highlighter-rouge}
files](https://peps.python.org/pep-0484/#stub-files).

[]{#s2.21.1-definition} []{#2211-definition}

[]{#typed-code-definition}

#### 2.21.1 Definition[](#2211-definition){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2211-definition}

Type annotations (or "type hints") are for function or method arguments
and return values:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def func(a: int) -> list[int]:
```
:::
::::

You can also declare the type of a variable using similar syntax:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
a: SomeType = some_func()
```
:::
::::

[]{#s2.21.2-pros} []{#2212-pros}

[]{#typed-code-pros}

#### 2.21.2 Pros[](#2212-pros){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2212-pros}

Type annotations improve the readability and maintainability of your
code. The type checker will convert many runtime errors to build-time
errors, and reduce your ability to use [Power
Features](#power-features).

[]{#s2.21.3-cons} []{#2213-cons}

[]{#typed-code-cons}

#### 2.21.3 Cons[](#2213-cons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2213-cons}

You will have to keep the type declarations up to date. You might see
type errors that you think are valid code. Use of a [type
checker](https://github.com/google/pytype) may reduce your ability to
use [Power Features](#power-features).

[]{#s2.21.4-decision} []{#2214-decision}

[]{#typed-code-decision}

#### 2.21.4 Decision[](#2214-decision){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#2214-decision}

You are strongly encouraged to enable Python type analysis when updating
code. When adding or modifying public APIs, include type annotations and
enable checking via pytype in the build system. As static analysis is
relatively new to Python, we acknowledge that undesired side-effects
(such as wrongly inferred types) may prevent adoption by some projects.
In those situations, authors are encouraged to add a comment with a TODO
or link to a bug describing the issue(s) currently preventing type
annotation adoption in the BUILD file or in the code itself as
appropriate.

[]{#s3-python-style-rules} []{#3-python-style-rules}

[]{#python-style-rules}

## 3 Python Style Rules[](#3-python-style-rules){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3-python-style-rules}

[]{#s3.1-semicolons} []{#31-semicolons}

[]{#semicolons}

### 3.1 Semicolons[](#31-semicolons){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#31-semicolons}

Do not terminate your lines with semicolons, and do not use semicolons
to put two statements on the same line.

[]{#s3.2-line-length} []{#32-line-length}

[]{#line-length}

### 3.2 Line length[](#32-line-length){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#32-line-length}

Maximum line length is *80 characters*.

Explicit exceptions to the 80 character limit:

- Long import statements.
- URLs, pathnames, or long flags in comments.
- Long string module-level constants not containing whitespace that
  would be inconvenient to split across lines such as URLs or pathnames.
  - Pylint disable comments. (e.g.:
    `# pylint: disable=invalid-name`{.language-plaintext
    .highlighter-rouge})

Do not use a backslash for [explicit line
continuation](https://docs.python.org/3/reference/lexical_analysis.html#explicit-line-joining).

Instead, make use of Python's [implicit line joining inside parentheses,
brackets and
braces](http://docs.python.org/reference/lexical_analysis.html#implicit-line-joining).
If necessary, you can add an extra pair of parentheses around an
expression.

Note that this rule doesn't prohibit backslash-escaped newlines within
strings (see [below](#strings)).

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: foo_bar(self, width, height, color='black', design=None, x='foo',
             emphasis=None, highlight=0)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight

Yes: if (width == 0 and height == 0 and
         color == 'red' and emphasis == 'strong'):

     (bridge_questions.clarification_on
      .average_airspeed_of.unladen_swallow) = 'African or European?'

     with (
         very_long_first_expression_function() as spam,
         very_long_second_expression_function() as beans,
         third_thing() as eggs,
     ):
       place_order(eggs, beans, spam, beans)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight

No:  if width == 0 and height == 0 and \
         color == 'red' and emphasis == 'strong':

     bridge_questions.clarification_on \
         .average_airspeed_of.unladen_swallow = 'African or European?'

     with very_long_first_expression_function() as spam, \
           very_long_second_expression_function() as beans, \
           third_thing() as eggs:
       place_order(eggs, beans, spam, beans)
```
:::
::::

When a literal string won't fit on a single line, use parentheses for
implicit line joining.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
x = ('This will build a very long long '
     'long long long long long long string')
```
:::
::::

Prefer to break lines at the highest possible syntactic level. If you
must break a line twice, break it at the same syntactic level both
times.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: bridgekeeper.answer(
         name="Arthur", quest=questlib.find(owner="Arthur", perilous=True))

     answer = (a_long_line().of_chained_methods()
               .that_eventually_provides().an_answer())

     if (
         config is None
         or 'editor.language' not in config
         or config['editor.language'].use_spaces is False
     ):
       use_tabs()
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No: bridgekeeper.answer(name="Arthur", quest=questlib.find(
        owner="Arthur", perilous=True))

    answer = a_long_line().of_chained_methods().that_eventually_provides(
        ).an_answer()

    if (config is None or 'editor.language' not in config or config[
        'editor.language'].use_spaces is False):
      use_tabs()
```
:::
::::

Within comments, put long URLs on their own line if necessary.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:  # See details at
      # http://www.example.com/us/developer/documentation/api/content/v2.0/csv_file_name_extension_full_specification.html
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  # See details at
     # http://www.example.com/us/developer/documentation/api/content/\
     # v2.0/csv_file_name_extension_full_specification.html
```
:::
::::

Make note of the indentation of the elements in the line continuation
examples above; see the [indentation](#s3.4-indentation) section for
explanation.

[Docstring](#docstrings) summary lines must remain within the 80
character limit.

In all other cases where a line exceeds 80 characters, and the
[Black](https://github.com/psf/black) or
[Pyink](https://github.com/google/pyink) auto-formatter does not help
bring the line below the limit, the line is allowed to exceed this
maximum. Authors are encouraged to manually break the line up per the
notes above when it is sensible.

[]{#s3.3-parentheses} []{#33-parentheses}

[]{#parentheses}

### 3.3 Parentheses[](#33-parentheses){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#33-parentheses}

Use parentheses sparingly.

It is fine, though not required, to use parentheses around tuples. Do
not use them in return statements or conditional statements unless using
parentheses for implied line continuation or to indicate a tuple.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: if foo:
         bar()
     while x:
         x = bar()
     if x and y:
         bar()
     if not x:
         bar()
     # For a 1 item tuple the ()s are more visually obvious than the comma.
     onesie = (foo,)
     return foo
     return spam, beans
     return (spam, beans)
     for (x, y) in dict.items(): ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  if (x):
         bar()
     if not(x):
         bar()
     return (foo)
```
:::
::::

[]{#s3.4-indentation} []{#34-indentation}

[]{#indentation}

### 3.4 Indentation[](#34-indentation){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#34-indentation}

Indent your code blocks with *4 spaces*.

Never use tabs. Implied line continuation should align wrapped elements
vertically (see [line length examples](#s3.2-line-length)), or use a
hanging 4-space indent. Closing (round, square or curly) brackets can be
placed at the end of the expression, or on separate lines, but then
should be indented the same as the line with the corresponding opening
bracket.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:   # Aligned with opening delimiter.
       foo = long_function_name(var_one, var_two,
                                var_three, var_four)
       meal = (spam,
               beans)

       # Aligned with opening delimiter in a dictionary.
       foo = {
           'long_dictionary_key': value1 +
                                  value2,
           ...
       }

       # 4-space hanging indent; nothing on first line.
       foo = long_function_name(
           var_one, var_two, var_three,
           var_four)
       meal = (
           spam,
           beans)

       # 4-space hanging indent; nothing on first line,
       # closing parenthesis on a new line.
       foo = long_function_name(
           var_one, var_two, var_three,
           var_four
       )
       meal = (
           spam,
           beans,
       )

       # 4-space hanging indent in a dictionary.
       foo = {
           'long_dictionary_key':
               long_dictionary_value,
           ...
       }
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:    # Stuff on first line forbidden.
       foo = long_function_name(var_one, var_two,
           var_three, var_four)
       meal = (spam,
           beans)

       # 2-space hanging indent forbidden.
       foo = long_function_name(
         var_one, var_two, var_three,
         var_four)

       # No hanging indent in a dictionary.
       foo = {
           'long_dictionary_key':
           long_dictionary_value,
           ...
       }
```
:::
::::

[]{#s3.4.1-trailing-comma} []{#s3.4.1-trailing-commas}
[]{#s3.4.1-trailing_comma} []{#s3.4.1-trailing_commas}
[]{#341-trailing_comma} []{#341-trailing_commas} []{#trailing_comma}
[]{#trailing_commas}

[]{#trailing-comma}

#### 3.4.1 Trailing commas in sequences of items?[](#341-trailing-commas-in-sequences-of-items){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#341-trailing-commas-in-sequences-of-items}

Trailing commas in sequences of items are recommended only when the
closing container token `]`{.language-plaintext .highlighter-rouge},
`)`{.language-plaintext .highlighter-rouge}, or `}`{.language-plaintext
.highlighter-rouge} does not appear on the same line as the final
element, as well as for tuples with a single element. The presence of a
trailing comma is also used as a hint to our Python code auto-formatter
[Black](https://github.com/psf/black) or
[Pyink](https://github.com/google/pyink) to direct it to auto-format the
container of items to one item per line when the `,`{.language-plaintext
.highlighter-rouge} after the final element is present.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:   golomb3 = [0, 1, 3]
       golomb4 = [
           0,
           1,
           4,
           6,
       ]
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:    golomb4 = [
           0,
           1,
           4,
           6,]
```
:::
::::

[]{#s3.5-blank-lines} []{#35-blank-lines}

[]{#blank-lines}

### 3.5 Blank Lines[](#35-blank-lines){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#35-blank-lines}

Two blank lines between top-level definitions, be they function or class
definitions. One blank line between method definitions and between the
docstring of a `class`{.language-plaintext .highlighter-rouge} and the
first method. No blank line following a `def`{.language-plaintext
.highlighter-rouge} line. Use single blank lines as you judge
appropriate within functions or methods.

Blank lines need not be anchored to the definition. For example, related
comments immediately preceding function, class, and method definitions
can make sense. Consider if your comment might be more useful as part of
the docstring.

[]{#s3.6-whitespace} []{#36-whitespace}

[]{#whitespace}

### 3.6 Whitespace[](#36-whitespace){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#36-whitespace}

Follow standard typographic rules for the use of spaces around
punctuation.

No whitespace inside parentheses, brackets or braces.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: spam(ham[1], {'eggs': 2}, [])
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  spam( ham[ 1 ], { 'eggs': 2 }, [ ] )
```
:::
::::

No whitespace before a comma, semicolon, or colon. Do use whitespace
after a comma, semicolon, or colon, except at the end of the line.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: if x == 4:
         print(x, y)
     x, y = y, x
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  if x == 4 :
         print(x , y)
     x , y = y , x
```
:::
::::

No whitespace before the open paren/bracket that starts an argument
list, indexing or slicing.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: spam(1)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  spam (1)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: dict['key'] = list[index]
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  dict ['key'] = list [index]
```
:::
::::

No trailing whitespace.

Surround binary operators with a single space on either side for
assignment (`=`{.language-plaintext .highlighter-rouge}), comparisons
(`==, <, >, !=, <>, <=, >=, in, not in, is, is not`{.language-plaintext
.highlighter-rouge}), and Booleans (`and, or, not`{.language-plaintext
.highlighter-rouge}). Use your better judgment for the insertion of
spaces around arithmetic operators (`+`{.language-plaintext
.highlighter-rouge}, `-`{.language-plaintext .highlighter-rouge},
`*`{.language-plaintext .highlighter-rouge}, `/`{.language-plaintext
.highlighter-rouge}, `//`{.language-plaintext .highlighter-rouge},
`%`{.language-plaintext .highlighter-rouge}, `**`{.language-plaintext
.highlighter-rouge}, `@`{.language-plaintext .highlighter-rouge}).

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: x == 1
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  x<1
```
:::
::::

Never use spaces around `=`{.language-plaintext .highlighter-rouge} when
passing keyword arguments or defining a default parameter value, with
one exception: [when a type annotation is
present](#typing-default-values), *do* use spaces around the
`=`{.language-plaintext .highlighter-rouge} for the default parameter
value.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: def complex(real, imag=0.0): return Magic(r=real, i=imag)
Yes: def complex(real, imag: float = 0.0): return Magic(r=real, i=imag)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  def complex(real, imag = 0.0): return Magic(r = real, i = imag)
No:  def complex(real, imag: float=0.0): return Magic(r = real, i = imag)
```
:::
::::

Don't use spaces to vertically align tokens on consecutive lines, since
it becomes a maintenance burden (applies to `:`{.language-plaintext
.highlighter-rouge}, `#`{.language-plaintext .highlighter-rouge},
`=`{.language-plaintext .highlighter-rouge}, etc.):

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
  foo = 1000  # comment
  long_name = 2  # comment that should not be aligned

  dictionary = {
      'foo': 1,
      'long_name': 2,
  }
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
  foo       = 1000  # comment
  long_name = 2     # comment that should not be aligned

  dictionary = {
      'foo'      : 1,
      'long_name': 2,
  }
```
:::
::::

[]{#Python_Interpreter} []{#s3.7-shebang-line} []{#37-shebang-line}

[]{#shebang-line}

### 3.7 Shebang Line[](#37-shebang-line){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#37-shebang-line}

Most `.py`{.language-plaintext .highlighter-rouge} files do not need to
start with a `#!`{.language-plaintext .highlighter-rouge} line. Start
the main file of a program with
`#!/usr/bin/env python3`{.language-plaintext .highlighter-rouge} (to
support virtualenvs) or `#!/usr/bin/python3`{.language-plaintext
.highlighter-rouge} per [PEP-394](https://peps.python.org/pep-0394/).

This line is used by the kernel to find the Python interpreter, but is
ignored by Python when importing modules. It is only necessary on a file
intended to be executed directly.

[]{#s3.8-comments-and-docstrings} []{#s3.8-comments}
[]{#38-comments-and-docstrings}

[]{#documentation}

### 3.8 Comments and Docstrings[](#38-comments-and-docstrings){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#38-comments-and-docstrings}

Be sure to use the right style for module, function, method docstrings
and inline comments.

[]{#s3.8.1-comments-in-doc-strings} []{#381-docstrings}
[]{#comments-in-doc-strings}

[]{#docstrings}

#### 3.8.1 Docstrings[](#381-docstrings){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#381-docstrings}

Python uses *docstrings* to document code. A docstring is a string that
is the first statement in a package, module, class or function. These
strings can be extracted automatically through the
`__doc__`{.language-plaintext .highlighter-rouge} member of the object
and are used by `pydoc`{.language-plaintext .highlighter-rouge}. (Try
running `pydoc`{.language-plaintext .highlighter-rouge} on your module
to see how it looks.) Always use the three-double-quote
`"""`{.language-plaintext .highlighter-rouge} format for docstrings (per
[PEP 257](https://peps.python.org/pep-0257/)). A docstring should be
organized as a summary line (one physical line not exceeding 80
characters) terminated by a period, question mark, or exclamation point.
When writing more (encouraged), this must be followed by a blank line,
followed by the rest of the docstring starting at the same cursor
position as the first quote of the first line. There are more formatting
guidelines for docstrings below.

[]{#s3.8.2-comments-in-modules} []{#382-modules}
[]{#comments-in-modules}

[]{#module-docs}

#### 3.8.2 Modules[](#382-modules){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#382-modules}

Every file should contain license boilerplate. Choose the appropriate
boilerplate for the license used by the project (for example, Apache
2.0, BSD, LGPL, GPL).

Files should start with a docstring describing the contents and usage of
the module.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
"""A one-line summary of the module or program, terminated by a period.

Leave one blank line.  The rest of this docstring should contain an
overall description of the module or program.  Optionally, it may also
contain a brief description of exported classes and functions and/or usage
examples.

Typical usage example:

  foo = ClassFoo()
  bar = foo.function_bar()
"""
```
:::
::::

[]{#s3.8.2.1-test-modules}

[]{#test-docs}

##### 3.8.2.1 Test modules[](#3821-test-modules){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3821-test-modules}

Module-level docstrings for test files are not required. They should be
included only when there is additional information that can be provided.

Examples include some specifics on how the test should be run, an
explanation of an unusual setup pattern, dependency on the external
environment, and so on.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
"""This blaze test uses golden files.

You can update those files by running
`blaze run //foo/bar:foo_test -- --update_golden_files` from the `google3`
directory.
"""
```
:::
::::

Docstrings that do not provide any new information should not be used.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
"""Tests for foo.bar."""
```
:::
::::

[]{#s3.8.3-functions-and-methods} []{#383-functions-and-methods}
[]{#functions-and-methods}

[]{#function-docs}

#### 3.8.3 Functions and Methods[](#383-functions-and-methods){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#383-functions-and-methods}

In this section, "function" means a method, function, generator, or
property.

A docstring is mandatory for every function that has one or more of the
following properties:

- being part of the public API
- nontrivial size
- non-obvious logic

A docstring should give enough information to write a call to the
function without reading the function's code. The docstring should
describe the function's calling syntax and its semantics, but generally
not its implementation details, unless those details are relevant to how
the function is to be used. For example, a function that mutates one of
its arguments as a side effect should note that in its docstring.
Otherwise, subtle but important details of a function's implementation
that are not relevant to the caller are better expressed as comments
alongside the code than within the function's docstring.

The docstring may be descriptive-style
(`"""Fetches rows from a Bigtable."""`{.language-plaintext
.highlighter-rouge}) or imperative-style
(`"""Fetch rows from a Bigtable."""`{.language-plaintext
.highlighter-rouge}), but the style should be consistent within a file.
The docstring for a `@property`{.language-plaintext .highlighter-rouge}
data descriptor should use the same style as the docstring for an
attribute or a [function argument](#doc-function-args)
(`"""The Bigtable path."""`{.language-plaintext .highlighter-rouge},
rather than `"""Returns the Bigtable path."""`{.language-plaintext
.highlighter-rouge}).

Certain aspects of a function should be documented in special sections,
listed below. Each section begins with a heading line, which ends with a
colon. All sections other than the heading should maintain a hanging
indent of two or four spaces (be consistent within a file). These
sections can be omitted in cases where the function's name and signature
are informative enough that it can be aptly described using a one-line
docstring.

[]{#doc-function-args}\
[*Args:*](#doc-function-args)
: List each parameter by name. A description should follow the name, and
  be separated by a colon followed by either a space or newline. If the
  description is too long to fit on a single 80-character line, use a
  hanging indent of 2 or 4 spaces more than the parameter name (be
  consistent with the rest of the docstrings in the file). The
  description should include required type(s) if the code does not
  contain a corresponding type annotation. If a function accepts
  `*foo`{.language-plaintext .highlighter-rouge} (variable length
  argument lists) and/or `**bar`{.language-plaintext .highlighter-rouge}
  (arbitrary keyword arguments), they should be listed as
  `*foo`{.language-plaintext .highlighter-rouge} and
  `**bar`{.language-plaintext .highlighter-rouge}.

[]{#doc-function-returns}\
[*Returns:* (or *Yields:* for generators)](#doc-function-returns)
: Describe the semantics of the return value, including any type
  information that the type annotation does not provide. If the function
  only returns None, this section is not required. It may also be
  omitted if the docstring starts with "Return", "Returns", "Yield", or
  "Yields" (e.g.
  `"""Returns row from Bigtable as a tuple of strings."""`{.language-plaintext
  .highlighter-rouge}) *and* the opening sentence is sufficient to
  describe the return value. Do not imitate older 'NumPy style'
  ([example](https://numpy.org/doc/1.24/reference/generated/numpy.linalg.qr.html)),
  which frequently documented a tuple return value as if it were
  multiple return values with individual names (never mentioning the
  tuple). Instead, describe such a return value as: "Returns: A tuple
  (mat_a, mat_b), where mat_a is ..., and ...". The auxiliary names in
  the docstring need not necessarily correspond to any internal names
  used in the function body (as those are not part of the API). If the
  function uses `yield`{.language-plaintext .highlighter-rouge} (is a
  generator), the `Yields:`{.language-plaintext .highlighter-rouge}
  section should document the object returned by
  `next()`{.language-plaintext .highlighter-rouge}, instead of the
  generator object itself that the call evaluates to.

[]{#doc-function-raises}\
[*Raises:*](#doc-function-raises)
: List all exceptions that are relevant to the interface followed by a
  description. Use a similar exception name + colon + space or newline
  and hanging indent style as described in *Args:*. You should not
  document exceptions that get raised if the API specified in the
  docstring is violated (because this would paradoxically make behavior
  under violation of the API part of the API).

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def fetch_smalltable_rows(
    table_handle: smalltable.Table,
    keys: Sequence[bytes | str],
    require_all_keys: bool = False,
) -> Mapping[bytes, tuple[str, ...]]:
    """Fetches rows from a Smalltable.

    Retrieves rows pertaining to the given keys from the Table instance
    represented by table_handle.  String keys will be UTF-8 encoded.

    Args:
        table_handle: An open smalltable.Table instance.
        keys: A sequence of strings representing the key of each table
          row to fetch.  String keys will be UTF-8 encoded.
        require_all_keys: If True only rows with values set for all keys will be
          returned.

    Returns:
        A dict mapping keys to the corresponding table row data
        fetched. Each row is represented as a tuple of strings. For
        example:

        {b'Serak': ('Rigel VII', 'Preparer'),
         b'Zim': ('Irk', 'Invader'),
         b'Lrrr': ('Omicron Persei 8', 'Emperor')}

        Returned keys are always bytes.  If a key from the keys argument is
        missing from the dictionary, then that row was not found in the
        table (and require_all_keys must have been False).

    Raises:
        IOError: An error occurred accessing the smalltable.
    """
```
:::
::::

Similarly, this variation on `Args:`{.language-plaintext
.highlighter-rouge} with a line break is also allowed:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def fetch_smalltable_rows(
    table_handle: smalltable.Table,
    keys: Sequence[bytes | str],
    require_all_keys: bool = False,
) -> Mapping[bytes, tuple[str, ...]]:
    """Fetches rows from a Smalltable.

    Retrieves rows pertaining to the given keys from the Table instance
    represented by table_handle.  String keys will be UTF-8 encoded.

    Args:
      table_handle:
        An open smalltable.Table instance.
      keys:
        A sequence of strings representing the key of each table row to
        fetch.  String keys will be UTF-8 encoded.
      require_all_keys:
        If True only rows with values set for all keys will be returned.

    Returns:
      A dict mapping keys to the corresponding table row data
      fetched. Each row is represented as a tuple of strings. For
      example:

      {b'Serak': ('Rigel VII', 'Preparer'),
       b'Zim': ('Irk', 'Invader'),
       b'Lrrr': ('Omicron Persei 8', 'Emperor')}

      Returned keys are always bytes.  If a key from the keys argument is
      missing from the dictionary, then that row was not found in the
      table (and require_all_keys must have been False).

    Raises:
      IOError: An error occurred accessing the smalltable.
    """
```
:::
::::

[]{#s3.8.3.1-overridden-methods}

[]{#overridden-method-docs}

##### 3.8.3.1 Overridden Methods[](#3831-overridden-methods){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3831-overridden-methods}

A method that overrides a method from a base class does not need a
docstring if it is explicitly decorated with
[`@override`{.language-plaintext
.highlighter-rouge}](https://typing-extensions.readthedocs.io/en/latest/#override)
(from `typing_extensions`{.language-plaintext .highlighter-rouge} or
`typing`{.language-plaintext .highlighter-rouge} modules), unless the
overriding method's behavior materially refines the base method's
contract, or details need to be provided (e.g., documenting additional
side effects), in which case a docstring with at least those differences
is required on the overriding method.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from typing_extensions import override

class Parent:
  def do_something(self):
    """Parent method, includes docstring."""

# Child class, method annotated with override.
class Child(Parent):
  @override
  def do_something(self):
    pass
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# Child class, but without @override decorator, a docstring is required.
class Child(Parent):
  def do_something(self):
    pass

# Docstring is trivial, @override is sufficient to indicate that docs can be
# found in the base class.
class Child(Parent):
  @override
  def do_something(self):
    """See base class."""
```
:::
::::

[]{#s3.8.4-comments-in-classes} []{#384-classes}
[]{#comments-in-classes}

[]{#class-docs}

#### 3.8.4 Classes[](#384-classes){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#384-classes}

Classes should have a docstring below the class definition describing
the class. Public attributes, excluding [properties](#properties),
should be documented here in an `Attributes`{.language-plaintext
.highlighter-rouge} section and follow the same formatting as a
[function's `Args`{.language-plaintext
.highlighter-rouge}](#doc-function-args) section.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
class SampleClass:
    """Summary of class here.

    Longer class information...
    Longer class information...

    Attributes:
        likes_spam: A boolean indicating if we like SPAM or not.
        eggs: An integer count of the eggs we have laid.
    """

    def __init__(self, likes_spam: bool = False):
        """Initializes the instance based on spam preference.

        Args:
          likes_spam: Defines if instance exhibits this preference.
        """
        self.likes_spam = likes_spam
        self.eggs = 0

    @property
    def butter_sticks(self) -> int:
        """The number of butter sticks we have."""
```
:::
::::

All class docstrings should start with a one-line summary that describes
what the class instance represents. This implies that subclasses of
`Exception`{.language-plaintext .highlighter-rouge} should also describe
what the exception represents, and not the context in which it might
occur. The class docstring should not repeat unnecessary information,
such as that the class is a class.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# Yes:
class CheeseShopAddress:
  """The address of a cheese shop.

  ...
  """

class OutOfCheeseError(Exception):
  """No more cheese is available."""
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# No:
class CheeseShopAddress:
  """Class that describes the address of a cheese shop.

  ...
  """

class OutOfCheeseError(Exception):
  """Raised when no more cheese is available."""
```
:::
::::

[]{#s3.8.5-block-and-inline-comments} []{#comments-in-block-and-inline}
[]{#s3.8.5-comments-in-block-and-inline}
[]{#385-block-and-inline-comments}

[]{#comments}

#### 3.8.5 Block and Inline Comments[](#385-block-and-inline-comments){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#385-block-and-inline-comments}

The final place to have comments is in tricky parts of the code. If
you're going to have to explain it at the next [code
review](http://en.wikipedia.org/wiki/Code_review), you should comment it
now. Complicated operations get a few lines of comments before the
operations commence. Non-obvious ones get comments at the end of the
line.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# We use a weighted dictionary search to find out where i is in
# the array.  We extrapolate position based on the largest num
# in the array and the array size and then do binary search to
# get the exact number.

if i & (i-1) == 0:  # True if i is 0 or a power of 2.
```
:::
::::

To improve legibility, these comments should start at least 2 spaces
away from the code with the comment character `#`{.language-plaintext
.highlighter-rouge}, followed by at least one space before the text of
the comment itself.

On the other hand, never describe the code. Assume the person reading
the code knows Python (though not what you're trying to do) better than
you do.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# BAD COMMENT: Now go through the b array and make sure whenever i occurs
# the next element is i+1
```
:::
::::

[]{#s3.8.6-punctuation-spelling-and-grammar}
[]{#386-punctuation-spelling-and-grammar} []{#spelling} []{#punctuation}
[]{#grammar}

[]{#punctuation-spelling-grammar}

#### 3.8.6 Punctuation, Spelling, and Grammar[](#386-punctuation-spelling-and-grammar){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#386-punctuation-spelling-and-grammar}

Pay attention to punctuation, spelling, and grammar; it is easier to
read well-written comments than badly written ones.

Comments should be as readable as narrative text, with proper
capitalization and punctuation. In many cases, complete sentences are
more readable than sentence fragments. Shorter comments, such as
comments at the end of a line of code, can sometimes be less formal, but
you should be consistent with your style.

Although it can be frustrating to have a code reviewer point out that
you are using a comma when you should be using a semicolon, it is very
important that source code maintain a high level of clarity and
readability. Proper punctuation, spelling, and grammar help with that
goal.

[]{#s3.10-strings} []{#310-strings}

[]{#strings}

### 3.10 Strings[](#310-strings){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#310-strings}

Use an
[f-string](https://docs.python.org/3/reference/lexical_analysis.html#f-strings),
the `%`{.language-plaintext .highlighter-rouge} operator, or the
`format`{.language-plaintext .highlighter-rouge} method for formatting
strings, even when the parameters are all strings. Use your best
judgment to decide between string formatting options. A single join with
`+`{.language-plaintext .highlighter-rouge} is okay but do not format
with `+`{.language-plaintext .highlighter-rouge}.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: x = f'name: {name}; score: {n}'
     x = '%s, %s!' % (imperative, expletive)
     x = '{}, {}'.format(first, second)
     x = 'name: %s; score: %d' % (name, n)
     x = 'name: %(name)s; score: %(score)d' % {'name':name, 'score':n}
     x = 'name: {}; score: {}'.format(name, n)
     x = a + b
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No: x = first + ', ' + second
    x = 'name: ' + name + '; score: ' + str(n)
```
:::
::::

Avoid using the `+`{.language-plaintext .highlighter-rouge} and
`+=`{.language-plaintext .highlighter-rouge} operators to accumulate a
string within a loop. In some conditions, accumulating a string with
addition can lead to quadratic rather than linear running time. Although
common accumulations of this sort may be optimized on CPython, that is
an implementation detail. The conditions under which an optimization
applies are not easy to predict and may change. Instead, add each
substring to a list and `''.join`{.language-plaintext
.highlighter-rouge} the list after the loop terminates, or write each
substring to an `io.StringIO`{.language-plaintext .highlighter-rouge}
buffer. These techniques consistently have amortized-linear run-time
complexity.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: items = ['<table>']
     for last_name, first_name in employee_list:
         items.append('<tr><td>%s, %s</td></tr>' % (last_name, first_name))
     items.append('</table>')
     employee_table = ''.join(items)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No: employee_table = '<table>'
    for last_name, first_name in employee_list:
        employee_table += '<tr><td>%s, %s</td></tr>' % (last_name, first_name)
    employee_table += '</table>'
```
:::
::::

Be consistent with your choice of string quote character within a file.
Pick `'`{.language-plaintext .highlighter-rouge} or
`"`{.language-plaintext .highlighter-rouge} and stick with it. It is
okay to use the other quote character on a string to avoid the need to
backslash-escape quote characters within the string.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
  Python('Why are you hiding your eyes?')
  Gollum("I'm scared of lint errors.")
  Narrator('"Good!" thought a happy Python reviewer.')
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
  Python("Why are you hiding your eyes?")
  Gollum('The lint. It burns. It burns us.')
  Gollum("Always the great lint. Watching. Watching.")
```
:::
::::

Prefer `"""`{.language-plaintext .highlighter-rouge} for multi-line
strings rather than `'''`{.language-plaintext .highlighter-rouge}.
Projects may choose to use `'''`{.language-plaintext .highlighter-rouge}
for all non-docstring multi-line strings if and only if they also use
`'`{.language-plaintext .highlighter-rouge} for regular strings.
Docstrings must use `"""`{.language-plaintext .highlighter-rouge}
regardless.

Multi-line strings do not flow with the indentation of the rest of the
program. If you need to avoid embedding extra space in the string, use
either concatenated single-line strings or a multi-line string with
[`textwrap.dedent()`{.language-plaintext
.highlighter-rouge}](https://docs.python.org/3/library/textwrap.html#textwrap.dedent)
to remove the initial space on each line:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  No:
  long_string = """This is pretty ugly.
Don't do this.
"""
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  Yes:
  long_string = """This is fine if your use case can accept
      extraneous leading spaces."""
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  Yes:
  long_string = ("And this is fine if you cannot accept\n" +
                 "extraneous leading spaces.")
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  Yes:
  long_string = ("And this too is fine if you cannot accept\n"
                 "extraneous leading spaces.")
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  Yes:
  import textwrap

  long_string = textwrap.dedent("""\
      This is also fine, because textwrap.dedent()
      will collapse common leading spaces in each line.""")
```
:::
::::

Note that using a backslash here does not violate the prohibition
against [explicit line continuation](#line-length); in this case, the
backslash is [escaping a
newline](https://docs.python.org/3/reference/lexical_analysis.html#string-and-bytes-literals)
in a string literal.

[]{#s3.10.1-logging} []{#3101-logging} []{#logging}

[]{#logging}

#### 3.10.1 Logging[](#3101-logging){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3101-logging}

For logging functions that expect a pattern-string (with %-placeholders)
as their first argument: Always call them with a string literal (not an
f-string!) as their first argument with pattern-parameters as subsequent
arguments. Some logging implementations collect the unexpanded
pattern-string as a queryable field. It also prevents spending time
rendering a message that no logger is configured to output.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  Yes:
  import tensorflow as tf
  logger = tf.get_logger()
  logger.info('TensorFlow Version is: %s', tf.__version__)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  Yes:
  import os
  from absl import logging

  logging.info('Current $PAGER is: %s', os.getenv('PAGER', default=''))

  homedir = os.getenv('HOME')
  if homedir is None or not os.access(homedir, os.W_OK):
    logging.error('Cannot write to home directory, $HOME=%r', homedir)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  No:
  import os
  from absl import logging

  logging.info('Current $PAGER is:')
  logging.info(os.getenv('PAGER', default=''))

  homedir = os.getenv('HOME')
  if homedir is None or not os.access(homedir, os.W_OK):
    logging.error(f'Cannot write to home directory, $HOME={homedir!r}')
```
:::
::::

[]{#s3.10.2-error-messages} []{#3102-error-messages} []{#error-messages}

[]{#error-messages}

#### 3.10.2 Error Messages[](#3102-error-messages){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3102-error-messages}

Error messages (such as: message strings on exceptions like
`ValueError`{.language-plaintext .highlighter-rouge}, or messages shown
to the user) should follow three guidelines:

1.  The message needs to precisely match the actual error condition.

2.  Interpolated pieces need to always be clearly identifiable as such.

3.  They should allow simple automated processing (e.g. grepping).

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  Yes:
  if not 0 <= p <= 1:
    raise ValueError(f'Not a probability: {p=}')

  try:
    os.rmdir(workdir)
  except OSError as error:
    logging.warning('Could not remove directory (reason: %r): %r',
                    error, workdir)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
  No:
  if p < 0 or p > 1:  # PROBLEM: also false for float('nan')!
    raise ValueError(f'Not a probability: {p=}')

  try:
    os.rmdir(workdir)
  except OSError:
    # PROBLEM: Message makes an assumption that might not be true:
    # Deletion might have failed for some other reason, misleading
    # whoever has to debug this.
    logging.warning('Directory already was deleted: %s', workdir)

  try:
    os.rmdir(workdir)
  except OSError:
    # PROBLEM: The message is harder to grep for than necessary, and
    # not universally non-confusing for all possible values of `workdir`.
    # Imagine someone calling a library function with such code
    # using a name such as workdir = 'deleted'. The warning would read:
    # "The deleted directory could not be deleted."
    logging.warning('The %s directory could not be deleted.', workdir)
```
:::
::::

[]{#s3.11-files-sockets-closeables} []{#s3.11-files-and-sockets}
[]{#311-files-and-sockets} []{#files-and-sockets}

[]{#files}

### 3.11 Files, Sockets, and similar Stateful Resources[](#311-files-sockets-and-similar-stateful-resources){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#311-files-sockets-and-similar-stateful-resources}

Explicitly close files and sockets when done with them. This rule
naturally extends to closeable resources that internally use sockets,
such as database connections, and also other resources that need to be
closed down in a similar fashion. To name only a few examples, this also
includes [mmap](https://docs.python.org/3/library/mmap.html) mappings,
[h5py File objects](https://docs.h5py.org/en/stable/high/file.html), and
[matplotlib.pyplot figure
windows](https://matplotlib.org/2.1.0/api/_as_gen/matplotlib.pyplot.close.html).

Leaving files, sockets or other such stateful objects open unnecessarily
has many downsides:

- They may consume limited system resources, such as file descriptors.
  Code that deals with many such objects may exhaust those resources
  unnecessarily if they're not returned to the system promptly after
  use.
- Holding files open may prevent other actions such as moving or
  deleting them, or unmounting a filesystem.
- Files and sockets that are shared throughout a program may
  inadvertently be read from or written to after logically being closed.
  If they are actually closed, attempts to read or write from them will
  raise exceptions, making the problem known sooner.

Furthermore, while files and sockets (and some similarly behaving
resources) are automatically closed when the object is destructed,
coupling the lifetime of the object to the state of the resource is poor
practice:

- There are no guarantees as to when the runtime will actually invoke
  the `__del__`{.language-plaintext .highlighter-rouge} method.
  Different Python implementations use different memory management
  techniques, such as delayed garbage collection, which may increase the
  object's lifetime arbitrarily and indefinitely.
- Unexpected references to the file, e.g. in globals or exception
  tracebacks, may keep it around longer than intended.

Relying on finalizers to do automatic cleanup that has observable side
effects has been rediscovered over and over again to lead to major
problems, across many decades and multiple languages (see e.g. [this
article](https://wiki.sei.cmu.edu/confluence/display/java/MET12-J.+Do+not+use+finalizers)
for Java).

The preferred way to manage files and similar resources is using the
[`with`{.language-plaintext .highlighter-rouge}
statement](http://docs.python.org/reference/compound_stmts.html#the-with-statement):

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
with open("hello.txt") as hello_file:
    for line in hello_file:
        print(line)
```
:::
::::

For file-like objects that do not support the `with`{.language-plaintext
.highlighter-rouge} statement, use
`contextlib.closing()`{.language-plaintext .highlighter-rouge}:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
import contextlib

with contextlib.closing(urllib.urlopen("http://www.python.org/")) as front_page:
    for line in front_page:
        print(line)
```
:::
::::

In rare cases where context-based resource management is infeasible,
code documentation must explain clearly how resource lifetime is
managed.

[]{#s3.12-todo-comments} []{#312-todo-comments}

[]{#todo}

### 3.12 TODO Comments[](#312-todo-comments){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#312-todo-comments}

Use `TODO`{.language-plaintext .highlighter-rouge} comments for code
that is temporary, a short-term solution, or good-enough but not
perfect.

A `TODO`{.language-plaintext .highlighter-rouge} comment begins with the
word `TODO`{.language-plaintext .highlighter-rouge} in all caps, a
following colon, and a link to a resource that contains the context,
ideally a bug reference. A bug reference is preferable because bugs are
tracked and have follow-up comments. Follow this piece of context with
an explanatory string introduced with a hyphen `-`{.language-plaintext
.highlighter-rouge}. The purpose is to have a consistent
`TODO`{.language-plaintext .highlighter-rouge} format that can be
searched to find out how to get more details.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# TODO: crbug.com/192795 - Investigate cpufreq optimizations.
```
:::
::::

Old style, formerly recommended, but discouraged for use in new code:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# TODO(crbug.com/192795): Investigate cpufreq optimizations.
# TODO(yourusername): Use a "\*" here for concatenation operator.
```
:::
::::

Avoid adding TODOs that refer to an individual or team as the context:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# TODO: @yourusername - File an issue and use a '*' for repetition.
```
:::
::::

If your `TODO`{.language-plaintext .highlighter-rouge} is of the form
"At a future date do something" make sure that you either include a very
specific date ("Fix by November 2009") or a very specific event ("Remove
this code when all clients can handle XML responses.") that future code
maintainers will comprehend. Issues are ideal for tracking this.

[]{#s3.13-imports-formatting} []{#313-imports-formatting}

[]{#imports-formatting}

### 3.13 Imports formatting[](#313-imports-formatting){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#313-imports-formatting}

Imports should be on separate lines; there are [exceptions for
`typing`{.language-plaintext .highlighter-rouge} and
`collections.abc`{.language-plaintext .highlighter-rouge}
imports](#typing-imports).

E.g.:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes: from collections.abc import Mapping, Sequence
     import os
     import sys
     from typing import Any, NewType
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:  import os, sys
```
:::
::::

Imports are always put at the top of the file, just after any module
comments and docstrings and before module globals and constants. Imports
should be grouped from most generic to least generic:

1.  Python future import statements. For example:

    :::: {.language-python .highlighter-rouge}
    ::: highlight
    ``` highlight
    from __future__ import annotations
    ```
    :::
    ::::

    See [above](#from-future-imports) for more information about those.

2.  Python standard library imports. For example:

    :::: {.language-python .highlighter-rouge}
    ::: highlight
    ``` highlight
    import sys
    ```
    :::
    ::::

3.  [third-party](https://pypi.org/) module or package imports. For
    example:

    :::: {.language-python .highlighter-rouge}
    ::: highlight
    ``` highlight
    import tensorflow as tf
    ```
    :::
    ::::

4.  Code repository sub-package imports. For example:

    :::: {.language-python .highlighter-rouge}
    ::: highlight
    ``` highlight
    from otherproject.ai import mind
    ```
    :::
    ::::

5.  **Deprecated:** application-specific imports that are part of the
    same top-level sub-package as this file. For example:

    :::: {.language-python .highlighter-rouge}
    ::: highlight
    ``` highlight
    from myproject.backend.hgwells import time_machine
    ```
    :::
    ::::

    You may find older Google Python Style code doing this, but it is no
    longer required. **New code is encouraged not to bother with this.**
    Simply treat application-specific sub-package imports the same as
    other sub-package imports.

Within each grouping, imports should be sorted lexicographically,
ignoring case, according to each module's full package path (the
`path`{.language-plaintext .highlighter-rouge} in
`from path import ...`{.language-plaintext .highlighter-rouge}). Code
may optionally place a blank line between import sections.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
import collections
import queue
import sys

from absl import app
from absl import flags
import bs4
import cryptography
import tensorflow as tf

from book.genres import scifi
from myproject.backend import huxley
from myproject.backend.hgwells import time_machine
from myproject.backend.state_machine import main_loop
from otherproject.ai import body
from otherproject.ai import mind
from otherproject.ai import soul

# Older style code may have these imports down here instead:
#from myproject.backend.hgwells import time_machine
#from myproject.backend.state_machine import main_loop
```
:::
::::

[]{#s3.14-statements} []{#314-statements}

[]{#statements}

### 3.14 Statements[](#314-statements){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#314-statements}

Generally only one statement per line.

However, you may put the result of a test on the same line as the test
only if the entire statement fits on one line. In particular, you can
never do so with `try`{.language-plaintext
.highlighter-rouge}/`except`{.language-plaintext .highlighter-rouge}
since the `try`{.language-plaintext .highlighter-rouge} and
`except`{.language-plaintext .highlighter-rouge} can't both fit on the
same line, and you can only do so with an `if`{.language-plaintext
.highlighter-rouge} if there is no `else`{.language-plaintext
.highlighter-rouge}.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:

  if foo: bar(foo)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:

  if foo: bar(foo)
  else:   baz(foo)

  try:               bar(foo)
  except ValueError: baz(foo)

  try:
      bar(foo)
  except ValueError: baz(foo)
```
:::
::::

[]{#s3.15-accessors} []{#s3.15-access-control} []{#315-access-control}
[]{#access-control} []{#accessors}

[]{#getters-and-setters}

### 3.15 Getters and Setters[](#315-getters-and-setters){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#315-getters-and-setters}

Getter and setter functions (also called accessors and mutators) should
be used when they provide a meaningful role or behavior for getting or
setting a variable's value.

In particular, they should be used when getting or setting the variable
is complex or the cost is significant, either currently or in a
reasonable future.

If, for example, a pair of getters/setters simply read and write an
internal attribute, the internal attribute should be made public
instead. By comparison, if setting a variable means some state is
invalidated or rebuilt, it should be a setter function. The function
invocation hints that a potentially non-trivial operation is occurring.
Alternatively, [properties](#properties) may be an option when simple
logic is needed, or refactoring to no longer need getters and setters.

Getters and setters should follow the [Naming](#s3.16-naming)
guidelines, such as `get_foo()`{.language-plaintext .highlighter-rouge}
and `set_foo()`{.language-plaintext .highlighter-rouge}.

If the past behavior allowed access through a property, do not bind the
new getter/setter functions to the property. Any code still attempting
to access the variable by the old method should break visibly so they
are made aware of the change in complexity.

[]{#s3.16-naming} []{#316-naming}

[]{#naming}

### 3.16 Naming[](#316-naming){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#316-naming}

`module_name`{.language-plaintext .highlighter-rouge},
`package_name`{.language-plaintext .highlighter-rouge},
`ClassName`{.language-plaintext .highlighter-rouge},
`method_name`{.language-plaintext .highlighter-rouge},
`ExceptionName`{.language-plaintext .highlighter-rouge},
`function_name`{.language-plaintext .highlighter-rouge},
`GLOBAL_CONSTANT_NAME`{.language-plaintext .highlighter-rouge},
`global_var_name`{.language-plaintext .highlighter-rouge},
`instance_var_name`{.language-plaintext .highlighter-rouge},
`function_parameter_name`{.language-plaintext .highlighter-rouge},
`local_var_name`{.language-plaintext .highlighter-rouge},
`query_proper_noun_for_thing`{.language-plaintext .highlighter-rouge},
`send_acronym_via_https`{.language-plaintext .highlighter-rouge}.

Names should be descriptive. This includes functions, classes,
variables, attributes, files and any other type of named entities.

Avoid abbreviation. In particular, do not use abbreviations that are
ambiguous or unfamiliar to readers outside your project, and do not
abbreviate by deleting letters within a word.

Always use a `.py`{.language-plaintext .highlighter-rouge} filename
extension. Never use dashes.

[]{#s3.16.1-names-to-avoid} []{#3161-names-to-avoid}

[]{#names-to-avoid}

#### 3.16.1 Names to Avoid[](#3161-names-to-avoid){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3161-names-to-avoid}

- single character names, except for specifically allowed cases:

  - counters or iterators (e.g. `i`{.language-plaintext
    .highlighter-rouge}, `j`{.language-plaintext .highlighter-rouge},
    `k`{.language-plaintext .highlighter-rouge}, `v`{.language-plaintext
    .highlighter-rouge}, et al.)
  - `e`{.language-plaintext .highlighter-rouge} as an exception
    identifier in `try/except`{.language-plaintext .highlighter-rouge}
    statements.
  - `f`{.language-plaintext .highlighter-rouge} as a file handle in
    `with`{.language-plaintext .highlighter-rouge} statements
  - private [type variables](#typing-type-var) with no constraints (e.g.
    `_T = TypeVar("_T")`{.language-plaintext .highlighter-rouge},
    `_P = ParamSpec("_P")`{.language-plaintext .highlighter-rouge})
  - names that match established notation in a reference paper or
    algorithm (see [Mathematical Notation](#math-notation))

  Please be mindful not to abuse single-character naming. Generally
  speaking, descriptiveness should be proportional to the name's scope
  of visibility. For example, `i`{.language-plaintext
  .highlighter-rouge} might be a fine name for 5-line code block but
  within multiple nested scopes, it is likely too vague.

- dashes (`-`{.language-plaintext .highlighter-rouge}) in any
  package/module name

- `__double_leading_and_trailing_underscore__`{.language-plaintext
  .highlighter-rouge} names (reserved by Python)

- offensive terms

- names that needlessly include the type of the variable (for example:
  `id_to_name_dict`{.language-plaintext .highlighter-rouge})

[]{#s3.16.2-naming-conventions} []{#3162-naming-convention}

[]{#naming-conventions}

#### 3.16.2 Naming Conventions[](#3162-naming-conventions){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3162-naming-conventions}

- "Internal" means internal to a module, or protected or private within
  a class.

- Prepending a single underscore (`_`{.language-plaintext
  .highlighter-rouge}) has some support for protecting module variables
  and functions (linters will flag protected member access). Note that
  it is okay for unit tests to access protected constants from the
  modules under test.

- Prepending a double underscore (`__`{.language-plaintext
  .highlighter-rouge} aka "dunder") to an instance variable or method
  effectively makes the variable or method private to its class (using
  name mangling); we discourage its use as it impacts readability and
  testability, and isn't *really* private. Prefer a single underscore.

- Place related classes and top-level functions together in a module.
  Unlike Java, there is no need to limit yourself to one class per
  module.

- Use CapWords for class names, but lower_with_under.py for module
  names. Although there are some old modules named CapWords.py, this is
  now discouraged because it's confusing when the module happens to be
  named after a class. ("wait -- did I write
  `import StringIO`{.language-plaintext .highlighter-rouge} or
  `from StringIO import StringIO`{.language-plaintext
  .highlighter-rouge}?")

- New *unit test* files follow PEP 8 compliant lower_with_under method
  names, for example,
  `test_<method_under_test>_<state>`{.language-plaintext
  .highlighter-rouge}. For consistency(\*) with legacy modules that
  follow CapWords function names, underscores may appear in method names
  starting with `test`{.language-plaintext .highlighter-rouge} to
  separate logical components of the name. One possible pattern is
  `test<MethodUnderTest>_<state>`{.language-plaintext
  .highlighter-rouge}.

[]{#s3.16.3-file-naming} []{#3163-file-naming}

[]{#file-naming}

#### 3.16.3 File Naming[](#3163-file-naming){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3163-file-naming}

Python filenames must have a `.py`{.language-plaintext
.highlighter-rouge} extension and must not contain dashes
(`-`{.language-plaintext .highlighter-rouge}). This allows them to be
imported and unittested. If you want an executable to be accessible
without the extension, use a symbolic link or a simple bash wrapper
containing `exec "$0.py" "$@"`{.language-plaintext .highlighter-rouge}.

[]{#s3.16.4-guidelines-derived-from-guidos-recommendations}
[]{#3164-guidelines-derived-from-guidos-recommendations}

[]{#guidelines-derived-from-guidos-recommendations}

#### 3.16.4 Guidelines derived from [Guido](https://en.wikipedia.org/wiki/Guido_van_Rossum)'s Recommendations[](#3164-guidelines-derived-from-guidos-recommendations){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3164-guidelines-derived-from-guidos-recommendations}

  ---------------------------- ---------------------- -----------------------------------
  Type                         Public                 Internal
  Packages                     `lower_with_under`     
  Modules                      `lower_with_under`     `_lower_with_under`
  Classes                      `CapWords`             `_CapWords`
  Exceptions                   `CapWords`             
  Functions                    `lower_with_under()`   `_lower_with_under()`
  Global/Class Constants       `CAPS_WITH_UNDER`      `_CAPS_WITH_UNDER`
  Global/Class Variables       `lower_with_under`     `_lower_with_under`
  Instance Variables           `lower_with_under`     `_lower_with_under` (protected)
  Method Names                 `lower_with_under()`   `_lower_with_under()` (protected)
  Function/Method Parameters   `lower_with_under`     
  Local Variables              `lower_with_under`     
  ---------------------------- ---------------------- -----------------------------------

[]{#s3.17-main} []{#317-main}

[]{#math-notation}

#### 3.16.5 Mathematical Notation[](#3165-mathematical-notation){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3165-mathematical-notation}

For mathematically-heavy code, short variable names that would otherwise
violate the style guide are preferred when they match established
notation in a reference paper or algorithm.

When using names based on established notation:

1.  Cite the source of all naming conventions, preferably with a
    hyperlink to academic resource itself, in a comment or docstring. If
    the source is not accessible, clearly document the naming
    conventions.
2.  Prefer PEP8-compliant `descriptive_names`{.language-plaintext
    .highlighter-rouge} for public APIs, which are much more likely to
    be encountered out of context.
3.  Use a narrowly-scoped
    `pylint: disable=invalid-name`{.language-plaintext
    .highlighter-rouge} directive to silence warnings. For just a few
    variables, use the directive as an endline comment for each one; for
    more, apply the directive at the beginning of a block.

[]{#main}

### 3.17 Main[](#317-main){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#317-main}

In Python, `pydoc`{.language-plaintext .highlighter-rouge} as well as
unit tests require modules to be importable. If a file is meant to be
used as an executable, its main functionality should be in a
`main()`{.language-plaintext .highlighter-rouge} function, and your code
should always check `if __name__ == '__main__'`{.language-plaintext
.highlighter-rouge} before executing your main program, so that it is
not executed when the module is imported.

When using [absl](https://github.com/abseil/abseil-py), use
`app.run`{.language-plaintext .highlighter-rouge}:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from absl import app
...

def main(argv: Sequence[str]):
    # process non-flag arguments
    ...

if __name__ == '__main__':
    app.run(main)
```
:::
::::

Otherwise, use:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def main():
    ...

if __name__ == '__main__':
    main()
```
:::
::::

All code at the top level will be executed when the module is imported.
Be careful not to call functions, create objects, or perform other
operations that should not be executed when the file is being
`pydoc`{.language-plaintext .highlighter-rouge}ed.

[]{#s3.18-function-length} []{#318-function-length}

[]{#function-length}

### 3.18 Function length[](#318-function-length){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#318-function-length}

Prefer small and focused functions.

We recognize that long functions are sometimes appropriate, so no hard
limit is placed on function length. If a function exceeds about 40
lines, think about whether it can be broken up without harming the
structure of the program.

Even if your long function works perfectly now, someone modifying it in
a few months may add new behavior. This could result in bugs that are
hard to find. Keeping your functions short and simple makes it easier
for other people to read and modify your code.

You could find long and complicated functions when working with some
code. Do not be intimidated by modifying existing code: if working with
such a function proves to be difficult, you find that errors are hard to
debug, or you want to use a piece of it in several different contexts,
consider breaking up the function into smaller and more manageable
pieces.

[]{#s3.19-type-annotations} []{#319-type-annotations}

[]{#type-annotations}

### 3.19 Type Annotations[](#319-type-annotations){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#319-type-annotations}

[]{#s3.19.1-general-rules} []{#s3.19.1-general} []{#3191-general-rules}

[]{#typing-general}

#### 3.19.1 General Rules[](#3191-general-rules){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3191-general-rules}

- Familiarize yourself with [type
  hints](https://docs.python.org/3/library/typing.html).

- Annotating `self`{.language-plaintext .highlighter-rouge} or
  `cls`{.language-plaintext .highlighter-rouge} is generally not
  necessary. [`Self`{.language-plaintext
  .highlighter-rouge}](https://docs.python.org/3/library/typing.html#typing.Self)
  can be used if it is necessary for proper type information, e.g.

  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  from typing import Self

  class BaseClass:
    @classmethod
    def create(cls) -> Self:
      ...

    def difference(self, other: Self) -> float:
      ...
  ```
  :::
  ::::

- Similarly, don't feel compelled to annotate the return value of
  `__init__`{.language-plaintext .highlighter-rouge} (where
  `None`{.language-plaintext .highlighter-rouge} is the only valid
  option).

- If any other variable or a returned type should not be expressed, use
  `Any`{.language-plaintext .highlighter-rouge}.

- You are not required to annotate all the functions in a module.

  - At least annotate your public APIs.
  - Use judgment to get to a good balance between safety and clarity on
    the one hand, and flexibility on the other.
  - Annotate code that is prone to type-related errors (previous bugs or
    complexity).
  - Annotate code that is hard to understand.
  - Annotate code as it becomes stable from a types perspective. In many
    cases, you can annotate all the functions in mature code without
    losing too much flexibility.

[]{#s3.19.2-line-breaking} []{#3192-line-breaking}

[]{#typing-line-breaking}

#### 3.19.2 Line Breaking[](#3192-line-breaking){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3192-line-breaking}

Try to follow the existing [indentation](#indentation) rules.

After annotating, many function signatures will become "one parameter
per line". To ensure the return type is also given its own line, a comma
can be placed after the last parameter.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def my_method(
    self,
    first_var: int,
    second_var: Foo,
    third_var: Bar | None,
) -> int:
  ...
```
:::
::::

Always prefer breaking between variables, and not, for example, between
variable names and type annotations. However, if everything fits on the
same line, go for it.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def my_method(self, first_var: int) -> int:
  ...
```
:::
::::

If the combination of the function name, the last parameter, and the
return type is too long, indent by 4 in a new line. When using line
breaks, prefer putting each parameter and the return type on their own
lines and aligning the closing parenthesis with the
`def`{.language-plaintext .highlighter-rouge}:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
def my_method(
    self,
    other_arg: MyLongType | None,
) -> tuple[MyLongType1, MyLongType1]:
  ...
```
:::
::::

Optionally, the return type may be put on the same line as the last
parameter:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Okay:
def my_method(
    self,
    first_var: int,
    second_var: int) -> dict[OtherLongType, MyLongType]:
  ...
```
:::
::::

`pylint`{.language-plaintext .highlighter-rouge} allows you to move the
closing parenthesis to a new line and align with the opening one, but
this is less readable.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
def my_method(self,
              other_arg: MyLongType | None,
             ) -> dict[OtherLongType, MyLongType]:
  ...
```
:::
::::

As in the examples above, prefer not to break types. However, sometimes
they are too long to be on a single line (try to keep sub-types
unbroken).

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def my_method(
    self,
    first_var: tuple[list[MyLongType1],
                     list[MyLongType2]],
    second_var: list[dict[
        MyLongType3, MyLongType4]],
) -> None:
  ...
```
:::
::::

If a single name and type is too long, consider using an
[alias](#typing-aliases) for the type. The last resort is to break after
the colon and indent by 4.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
def my_function(
    long_variable_name:
        long_module_name.LongTypeName,
) -> None:
  ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
def my_function(
    long_variable_name: long_module_name.
        LongTypeName,
) -> None:
  ...
```
:::
::::

[]{#s3.19.3-forward-declarations} []{#3193-forward-declarations}

[]{#forward-declarations}

#### 3.19.3 Forward Declarations[](#3193-forward-declarations){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3193-forward-declarations}

If you need to use a class name (from the same module) that is not yet
defined -- for example, if you need the class name inside the
declaration of that class, or if you use a class that is defined later
in the code -- either use
`from __future__ import annotations`{.language-plaintext
.highlighter-rouge} or use a string for the class name.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
from __future__ import annotations

class MyClass:
  def __init__(self, stack: Sequence[MyClass], item: OtherClass) -> None:

class OtherClass:
  ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
class MyClass:
  def __init__(self, stack: Sequence['MyClass'], item: 'OtherClass') -> None:

class OtherClass:
  ...
```
:::
::::

[]{#s3.19.4-default-values} []{#3194-default-values}

[]{#typing-default-values}

#### 3.19.4 Default Values[](#3194-default-values){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3194-default-values}

As per
[PEP-008](https://peps.python.org/pep-0008/#other-recommendations), use
spaces around the `=`{.language-plaintext .highlighter-rouge} *only* for
arguments that have both a type annotation and a default value.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
def func(a: int = 0) -> int:
  ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
def func(a:int=0) -> int:
  ...
```
:::
::::

[]{#s3.19.5-nonetype} []{#s3.19.5-none-type} []{#3195-nonetype}

[]{#none-type}

#### 3.19.5 NoneType[](#3195-nonetype){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3195-nonetype}

In the Python type system, `NoneType`{.language-plaintext
.highlighter-rouge} is a "first class" type, and for typing purposes,
`None`{.language-plaintext .highlighter-rouge} is an alias for
`NoneType`{.language-plaintext .highlighter-rouge}. If an argument can
be `None`{.language-plaintext .highlighter-rouge}, it has to be
declared! You can use `|`{.language-plaintext .highlighter-rouge} union
type expressions (recommended in new Python 3.10+ code), or the older
`Optional`{.language-plaintext .highlighter-rouge} and
`Union`{.language-plaintext .highlighter-rouge} syntaxes.

Use explicit `X | None`{.language-plaintext .highlighter-rouge} instead
of implicit. Earlier versions of type checkers allowed
`a: str = None`{.language-plaintext .highlighter-rouge} to be
interpreted as `a: str | None = None`{.language-plaintext
.highlighter-rouge}, but that is no longer the preferred behavior.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
def modern_or_union(a: str | int | None, b: str | None = None) -> str:
  ...
def union_optional(a: Union[str, int, None], b: Optional[str] = None) -> str:
  ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
def nullable_union(a: Union[None, str]) -> str:
  ...
def implicit_optional(a: str = None) -> str:
  ...
```
:::
::::

[]{#s3.19.6-type-aliases} []{#s3.19.6-aliases} []{#3196-type-aliases}
[]{#typing-aliases}

[]{#type-aliases}

#### 3.19.6 Type Aliases[](#3196-type-aliases){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3196-type-aliases}

You can declare aliases of complex types. The name of an alias should be
CapWorded. If the alias is used only in this module, it should be
\_Private.

Note that the `: TypeAlias`{.language-plaintext .highlighter-rouge}
annotation is only supported in versions 3.10+.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from typing import TypeAlias

_LossAndGradient: TypeAlias = tuple[tf.Tensor, tf.Tensor]
ComplexTFMap: TypeAlias = Mapping[str, _LossAndGradient]
```
:::
::::

[]{#s3.19.7-ignoring-types} []{#s3.19.7-ignore} []{#3197-ignoring-types}

[]{#typing-ignore}

#### 3.19.7 Ignoring Types[](#3197-ignoring-types){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3197-ignoring-types}

You can disable type checking on a line with the special comment
`# type: ignore`{.language-plaintext .highlighter-rouge}.

`pytype`{.language-plaintext .highlighter-rouge} has a disable option
for specific errors (similar to lint):

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# pytype: disable=attribute-error
```
:::
::::

[]{#s3.19.8-typing-variables} []{#s3.19.8-comments}
[]{#3198-typing-internal-variables}

[]{#typing-variables}

#### 3.19.8 Typing Variables[](#3198-typing-variables){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3198-typing-variables}

[]{#annotated-assignments}\
[*Annotated Assignments*](#annotated-assignments)
: If an internal variable has a type that is hard or impossible to
  infer, specify its type with an annotated assignment - use a colon and
  type between the variable name and value (the same as is done with
  function arguments that have a default value):
  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  a: Foo = SomeUndecoratedFunction()
  ```
  :::
  ::::

[]{#type-comments}\
[*Type Comments*](#type-comments)
: Though you may see them remaining in the codebase (they were necessary
  before Python 3.6), do not add any more uses of a
  `# type: <type name>`{.language-plaintext .highlighter-rouge} comment
  on the end of the line:
  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  a = SomeUndecoratedFunction()  # type: Foo
  ```
  :::
  ::::

[]{#s3.19.9-tuples-vs-lists} []{#s3.19.9-tuples}
[]{#3199-tuples-vs-lists}

[]{#typing-tuples}

#### 3.19.9 Tuples vs Lists[](#3199-tuples-vs-lists){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#3199-tuples-vs-lists}

Typed lists can only contain objects of a single type. Typed tuples can
either have a single repeated type or a set number of elements with
different types. The latter is commonly used as the return type from a
function.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
a: list[int] = [1, 2, 3]
b: tuple[int, ...] = (1, 2, 3)
c: tuple[int, str, float] = (1, "2", 3.5)
```
:::
::::

[]{#s3.19.10-typevars} []{#s3.19.10-type-var} []{#31910-typevar}
[]{#typing-type-var}

[]{#typevars}

#### 3.19.10 Type variables[](#31910-type-variables){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#31910-type-variables}

The Python type system has
[generics](https://docs.python.org/3/library/typing.html#generics). A
type variable, such as `TypeVar`{.language-plaintext .highlighter-rouge}
and `ParamSpec`{.language-plaintext .highlighter-rouge}, is a common way
to use them.

Example:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from collections.abc import Callable
from typing import ParamSpec, TypeVar
_P = ParamSpec("_P")
_T = TypeVar("_T")
...
def next(l: list[_T]) -> _T:
  return l.pop()

def print_when_called(f: Callable[_P, _T]) -> Callable[_P, _T]:
  def inner(*args: _P.args, **kwargs: _P.kwargs) -> _T:
    print("Function was called")
    return f(*args, **kwargs)
  return inner
```
:::
::::

A `TypeVar`{.language-plaintext .highlighter-rouge} can be constrained:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
AddableType = TypeVar("AddableType", int, float, str)
def add(a: AddableType, b: AddableType) -> AddableType:
  return a + b
```
:::
::::

A common predefined type variable in the `typing`{.language-plaintext
.highlighter-rouge} module is `AnyStr`{.language-plaintext
.highlighter-rouge}. Use it for multiple annotations that can be
`bytes`{.language-plaintext .highlighter-rouge} or
`str`{.language-plaintext .highlighter-rouge} and must all be the same
type.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from typing import AnyStr
def check_length(x: AnyStr) -> AnyStr:
  if len(x) <= 42:
    return x
  raise ValueError()
```
:::
::::

A type variable must have a descriptive name, unless it meets all of the
following criteria:

- not externally visible
- not constrained

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
Yes:
  _T = TypeVar("_T")
  _P = ParamSpec("_P")
  AddableType = TypeVar("AddableType", int, float, str)
  AnyFunction = TypeVar("AnyFunction", bound=Callable)
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
No:
  T = TypeVar("T")
  P = ParamSpec("P")
  _T = TypeVar("_T", int, float, str)
  _F = TypeVar("_F", bound=Callable)
```
:::
::::

[]{#s3.19.11-string-types} []{#s3.19.11-strings} []{#31911-string-types}

[]{#typing-strings}

#### 3.19.11 String types[](#31911-string-types){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#31911-string-types}

> Do not use `typing.Text`{.language-plaintext .highlighter-rouge} in
> new code. It's only for Python 2/3 compatibility.

Use `str`{.language-plaintext .highlighter-rouge} for string/text data.
For code that deals with binary data, use `bytes`{.language-plaintext
.highlighter-rouge}.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
def deals_with_text_data(x: str) -> str:
  ...
def deals_with_binary_data(x: bytes) -> bytes:
  ...
```
:::
::::

If all the string types of a function are always the same, for example
if the return type is the same as the argument type in the code above,
use [AnyStr](#typing-type-var).

[]{#s3.19.12-imports-for-typing} []{#s3.19.12-imports}
[]{#31912-imports-for-typing}

[]{#typing-imports}

#### 3.19.12 Imports For Typing[](#31912-imports-for-typing){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#31912-imports-for-typing}

For symbols (including types, functions, and constants) from the
`typing`{.language-plaintext .highlighter-rouge} or
`collections.abc`{.language-plaintext .highlighter-rouge} modules used
to support static analysis and type checking, always import the symbol
itself. This keeps common annotations more concise and matches typing
practices used around the world. You are explicitly allowed to import
multiple specific symbols on one line from the
`typing`{.language-plaintext .highlighter-rouge} and
`collections.abc`{.language-plaintext .highlighter-rouge} modules. For
example:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from collections.abc import Mapping, Sequence
from typing import Any, Generic, cast, TYPE_CHECKING
```
:::
::::

Given that this way of importing adds items to the local namespace,
names in `typing`{.language-plaintext .highlighter-rouge} or
`collections.abc`{.language-plaintext .highlighter-rouge} should be
treated similarly to keywords, and not be defined in your Python code,
typed or not. If there is a collision between a type and an existing
name in a module, import it using `import x as y`{.language-plaintext
.highlighter-rouge}.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from typing import Any as AnyType
```
:::
::::

When annotating function signatures, prefer abstract container types
like `collections.abc.Sequence`{.language-plaintext .highlighter-rouge}
over concrete types like `list`{.language-plaintext .highlighter-rouge}.
If you need to use a concrete type (for example, a
`tuple`{.language-plaintext .highlighter-rouge} of typed elements),
prefer built-in types like `tuple`{.language-plaintext
.highlighter-rouge} over the parametric type aliases from the
`typing`{.language-plaintext .highlighter-rouge} module (e.g.,
`typing.Tuple`{.language-plaintext .highlighter-rouge}).

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from typing import List, Tuple

def transform_coordinates(original: List[Tuple[float, float]]) ->
    List[Tuple[float, float]]:
  ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from collections.abc import Sequence

def transform_coordinates(original: Sequence[tuple[float, float]]) ->
    Sequence[tuple[float, float]]:
  ...
```
:::
::::

[]{#s3.19.13-conditional-imports} []{#31913-conditional-imports}

[]{#typing-conditional-imports}

#### 3.19.13 Conditional Imports[](#31913-conditional-imports){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#31913-conditional-imports}

Use conditional imports only in exceptional cases where the additional
imports needed for type checking must be avoided at runtime. This
pattern is discouraged; alternatives such as refactoring the code to
allow top-level imports should be preferred.

Imports that are needed only for type annotations can be placed within
an `if TYPE_CHECKING:`{.language-plaintext .highlighter-rouge} block.

- Conditionally imported types need to be referenced as strings, to be
  forward compatible with Python 3.6 where the annotation expressions
  are actually evaluated.
- Only entities that are used solely for typing should be defined here;
  this includes aliases. Otherwise it will be a runtime error, as the
  module will not be imported at runtime.
- The block should be right after all the normal imports.
- There should be no empty lines in the typing imports list.
- Sort this list as if it were a regular imports list.

  :::: {.language-python .highlighter-rouge}
  ::: highlight
  ``` highlight
  import typing
  if typing.TYPE_CHECKING:
    import sketch
  def f(x: "sketch.Sketch"): ...
  ```
  :::
  ::::

[]{#s3.19.14-circular-dependencies} []{#s3.19.14-circular-deps}
[]{#31914-circular-dependencies}

[]{#typing-circular-deps}

#### 3.19.14 Circular Dependencies[](#31914-circular-dependencies){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#31914-circular-dependencies}

Circular dependencies that are caused by typing are code smells. Such
code is a good candidate for refactoring. Although technically it is
possible to keep circular dependencies, various build systems will not
let you do so because each module has to depend on the other.

Replace modules that create circular dependency imports with
`Any`{.language-plaintext .highlighter-rouge}. Set an
[alias](#typing-aliases) with a meaningful name, and use the real type
name from this module (any attribute of `Any`{.language-plaintext
.highlighter-rouge} is `Any`{.language-plaintext .highlighter-rouge}).
Alias definitions should be separated from the last import by one line.

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
from typing import Any

some_mod = Any  # some_mod.py imports this module.
...

def my_method(self, var: "some_mod.SomeType") -> None:
  ...
```
:::
::::

[]{#typing-generics} []{#s3.19.15-generics} []{#31915-generics}

[]{#generics}

#### 3.19.15 Generics[](#31915-generics){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#31915-generics}

When annotating, prefer to specify type parameters for
[generic](https://docs.python.org/3/library/typing.html#generics) types
in a parameter list; otherwise, the generics' parameters will be assumed
to be [`Any`{.language-plaintext
.highlighter-rouge}](https://docs.python.org/3/library/typing.html#the-any-type).

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# Yes:
def get_names(employee_ids: Sequence[int]) -> Mapping[int, str]:
  ...
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# No:
# This is interpreted as get_names(employee_ids: Sequence[Any]) -> Mapping[Any, Any]
def get_names(employee_ids: Sequence) -> Mapping:
  ...
```
:::
::::

If the best type parameter for a generic is `Any`{.language-plaintext
.highlighter-rouge}, make it explicit, but remember that in many cases
[`TypeVar`{.language-plaintext .highlighter-rouge}](#typing-type-var)
might be more appropriate:

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# No:
def get_names(employee_ids: Sequence[Any]) -> Mapping[Any, str]:
  """Returns a mapping from employee ID to employee name for given IDs."""
```
:::
::::

:::: {.language-python .highlighter-rouge}
::: highlight
``` highlight
# Yes:
_T = TypeVar('_T')
def get_names(employee_ids: Sequence[_T]) -> Mapping[_T, str]:
  """Returns a mapping from employee ID to employee name for given IDs."""
```
:::
::::

[]{#4-parting-words}

[]{#consistency}

## 4 Parting Words[](#4-parting-words){.anchorjs-link aria-label="Anchor" anchorjs-icon="" style="font: 1em / 1 anchorjs-icons; padding-left: 0.375em;"} {#4-parting-words}

*BE CONSISTENT*.

If you're editing code, take a few minutes to look at the code around
you and determine its style. If they use `_idx`{.language-plaintext
.highlighter-rouge} suffixes in index variable names, you should too. If
their comments have little boxes of hash marks around them, make your
comments have little boxes of hash marks around them too.

The point of having style guidelines is to have a common vocabulary of
coding so people can concentrate on what you're saying rather than on
how you're saying it. We present global style rules here so people know
the vocabulary, but local style is also important. If code you add to a
file looks drastically different from the existing code around it, it
throws readers out of their rhythm when they go to read it.

However, there are limits to consistency. It applies more heavily
locally and on choices unspecified by the global style. Consistency
should not generally be used as a justification to do things in an old
style without considering the benefits of the new style, or the tendency
of the codebase to converge on newer styles over time.

::: {.footer .border-top .border-gray-light .mt-5 .pt-3 .text-right .text-gray}
This site is open source. [Improve this
page](https://github.com/google/styleguide/edit/gh-pages/pyguide.md).

