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

## 1 Background

Python is the main dynamic language used at Google. This style guide is
a list of *dos and don'ts* for Python programs.

To help you format code correctly, we've created a [settings file for
Vim](https://google.github.io/styleguide/google_python_style.vim). For
Emacs, the default settings should be fine.

Many teams use the [Black](https://github.com/psf/black) or
[Pyink](https://github.com/google/pyink) auto-formatter to avoid arguing
over formatting.

## 2 Python Language Rules

### 2.1 Lint

Run `pylint` over your code
using this [pylintrc](https://google.github.io/styleguide/pylintrc).

#### 2.1.1 Definition

`pylint` is a tool for finding
bugs and style problems in Python source code. It finds problems that
are typically caught by a compiler for less dynamic languages like C and
C++. Because of the dynamic nature of Python, some warnings may be
incorrect; however, spurious warnings should be fairly infrequent.

#### 2.1.2 Pros

Catches easy-to-miss errors like typos, using-vars-before-assignment,
etc.

#### 2.1.3 Cons

`pylint` isn't perfect. To take
advantage of it, sometimes we'll need to write around it, suppress its
warnings or fix it.

#### 2.1.4 Decision

Make sure you run `pylint` on
your code.

Suppress warnings if they are inappropriate so that other issues are not
hidden. To suppress warnings, you can set a line-level comment:

``` highlight
def do_PUT(self):  # WSGI name, so pylint: disable=invalid-name
  ...
```


`pylint` warnings are each
identified by symbolic name (`empty-docstring`) Google-specific warnings start with
`g-`.

If the reason for the suppression is not clear from the symbolic name,
add an explanation.

Suppressing in this way has the advantage that we can easily search for
suppressions and revisit them.

You can get a list of `pylint`
warnings by doing:

``` highlight
pylint --list-msgs
```


To get more information on a particular message, use:

``` highlight
pylint --help-msg=invalid-name
```


Prefer `pylint: disable` to the
deprecated older form `pylint: disable-msg`.

Unused argument warnings can be suppressed by deleting the variables at
the beginning of the function. Always include a comment explaining why
you are deleting it. "Unused." is sufficient. For example:

``` highlight
def viking_cafe_order(spam: str, beans: str, eggs: str | None = None) -> str:
    del beans, eggs  # Unused by vikings.
    return spam + spam + spam
```


Other common forms of suppressing this warning include using
'`_`' as the identifier for the
unused argument or prefixing the argument name with
'`unused_`', or assigning them
to '`_`'. These forms are
allowed but no longer encouraged. These break callers that pass
arguments by name and do not enforce that the arguments are actually
unused.

### 2.2 Imports

Use `import` statements for
packages and modules only, not for individual types, classes, or
functions.

#### 2.2.1 Definition

Reusability mechanism for sharing code from one module to another.

#### 2.2.2 Pros

The namespace management convention is simple. The source of each
identifier is indicated in a consistent way; `x.Obj` says that object `Obj` is defined in module `x`.

#### 2.2.3 Cons

Module names can still collide. Some module names are inconveniently
long.

#### 2.2.4 Decision

- Use `import x` for importing
  packages and modules.
- Use `from x import y` where
  `x` is the package prefix and
  `y` is the module name with no
  prefix.
- Use `from x import y as z` in
  any of the following circumstances:
  - Two modules named `y` are to
    be imported.
  - `y` conflicts with a
    top-level name defined in the current module.
  - `y` conflicts with a common
    parameter name that is part of the public API (e.g.,
    `features`).
  - `y` is an inconveniently
    long name.
  - `y` is too generic in the
    context of your code (e.g.,
    `from storage.file_system import options as fs_options`).
- Use `import y as z` only when
  `z` is a standard abbreviation
  (e.g., `import numpy as np`).

For example the module `sound.effects.echo` may be imported as follows:

``` highlight
from sound.effects import echo
...
echo.EchoFilter(input, output, delay=0.7, atten=4)
```


Do not use relative names in imports. Even if the module is in the same
package, use the full package name. This helps prevent unintentionally
importing a package twice.

##### 2.2.4.1 Exemptions

Exemptions from this rule:

- Symbols from the following modules are used to support static analysis
  and type checking:
  - [`typing`
    module](#typing-imports)
  - [`collections.abc`
    module](#typing-imports)
  - [`typing_extensions`
    module](https://github.com/python/typing_extensions/blob/main/README.md)
- Redirects from the [six.moves
  module](https://six.readthedocs.io/#module-six.moves).

### 2.3 Packages

Import each module using the full pathname location of the module.

#### 2.3.1 Pros

Avoids conflicts in module names or incorrect imports due to the module
search path not being what the author expected. Makes it easier to find
modules.

#### 2.3.2 Cons

Makes it harder to deploy code because you have to replicate the package
hierarchy. Not really a problem with modern deployment mechanisms.

#### 2.3.3 Decision

All new code should import each module by its full package name.

Imports should be as follows:

``` highlight
Yes:
  # Reference absl.flags in code with the complete name (verbose).
  import absl.flags
  from doctor.who import jodie

  _FOO = absl.flags.DEFINE_string(...)
```


``` highlight
Yes:
  # Reference flags in code with just the module name (common).
  from absl import flags
  from doctor.who import jodie

  _FOO = flags.DEFINE_string(...)
```


*(assume this file lives in `doctor/who/` where `jodie.py` also exists)*

``` highlight
No:
  # Unclear what module the author wanted and what will be imported.  The actual
  # import behavior depends on external factors controlling sys.path.
  # Which possible jodie module did the author intend to import?
  import jodie
```


The directory the main binary is located in should not be assumed to be
in `sys.path` despite that
happening in some environments. This being the case, code should assume
that `import jodie` refers to a
third-party or top-level package named `jodie`, not a local `jodie.py`.

### 2.4 Exceptions

Exceptions are allowed but must be used carefully.

#### 2.4.1 Definition

Exceptions are a means of breaking out of normal control flow to handle
errors or other exceptional conditions.

#### 2.4.2 Pros

The control flow of normal operation code is not cluttered by
error-handling code. It also allows the control flow to skip multiple
frames when a certain condition occurs, e.g., returning from N nested
functions in one step instead of having to plumb error codes through.

#### 2.4.3 Cons

May cause the control flow to be confusing. Easy to miss error cases
when making library calls.

#### 2.4.4 Decision

Exceptions must follow certain conditions:

- Make use of built-in exception classes when it makes sense. For
  example, raise a `ValueError`
  to indicate a programming mistake like a violated precondition, such
  as may happen when validating function arguments.

- Do not use `assert` statements
  in place of conditionals or validating preconditions. They must not be
  critical to the application logic. A litmus test would be that the
  `assert` could be removed
  without breaking the code. `assert` conditionals are [not
  guaranteed](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)
  to be evaluated. For [pytest](https://pytest.org/) based tests,
  `assert` is okay and expected
  to verify expectations. For example:

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
  

- Libraries or packages may define their own exceptions. When doing so
  they must inherit from an existing exception class. Exception names
  should end in `Error` and
  should not introduce repetition (`foo.FooError`).

- Never use catch-all `except:`
  statements, or catch `Exception` or `StandardError`, unless you are

  - re-raising the exception, or
  - creating an isolation point in the program where exceptions are not
    propagated but are recorded and suppressed instead, such as
    protecting a thread from crashing by guarding its outermost block.

  Python is very tolerant in this regard and
  `except:` will really catch
  everything including misspelled names, sys.exit() calls, Ctrl+C
  interrupts, unittest failures and all kinds of other exceptions that
  you simply don't want to catch.

- Minimize the amount of code in a `try`/`except`
  block. The larger the body of the `try`, the more likely that an exception will be raised
  by a line of code that you didn't expect to raise an exception. In
  those cases, the `try`/`except`
  block hides a real error.

- Use the `finally` clause to
  execute code whether or not an exception is raised in the
  `try` block. This is often
  useful for cleanup, i.e., closing a file.

### 2.5 Mutable Global State

Avoid mutable global state.

#### 2.5.1 Definition

Module-level values or class attributes that can get mutated during
program execution.

#### 2.5.2 Pros

Occasionally useful.

#### 2.5.3 Cons

- Breaks encapsulation: Such design can make it hard to achieve valid
  objectives. For example, if global state is used to manage a database
  connection, then connecting to two different databases at the same
  time (such as for computing differences during a migration) becomes
  difficult. Similar problems easily arise with global registries.

- Has the potential to change module behavior during the import, because
  assignments to global variables are done when the module is first
  imported.

#### 2.5.4 Decision

Avoid mutable global state.

In those rare cases where using global state is warranted, mutable
global entities should be declared at the module level or as a class
attribute and made internal by prepending an `_` to the name. If necessary, external access to
mutable global state must be done through public functions or class
methods. See [Naming](#s3.16-naming) below. Please explain the design
reasons why mutable global state is being used in a comment or a doc
linked to from a comment.

Module-level constants are permitted and encouraged. For example:
`_MAX_HOLY_HANDGRENADE_COUNT = 3` for an internal use constant or
`SIR_LANCELOTS_FAVORITE_COLOR = "blue"` for a public API constant. Constants must be named
using all caps with underscores. See [Naming](#s3.16-naming) below.

### 2.6 Nested/Local/Inner Classes and Functions

Nested local functions or classes are fine when used to close over a
local variable. Inner classes are fine.

#### 2.6.1 Definition

A class can be defined inside of a method, function, or class. A
function can be defined inside a method or function. Nested functions
have read-only access to variables defined in enclosing scopes.

#### 2.6.2 Pros

Allows definition of utility classes and functions that are only used
inside of a very limited scope. Very
[ADT](https://en.wikipedia.org/wiki/Abstract_data_type)-y. Commonly used
for implementing decorators.

#### 2.6.3 Cons

Nested functions and classes cannot be directly tested. Nesting can make
the outer function longer and less readable.

#### 2.6.4 Decision

They are fine with some caveats. Avoid nested functions or classes
except when closing over a local value other than
`self` or
`cls`. Do not nest a function
just to hide it from users of a module. Instead, prefix its name with an
\_ at the module level so that it can still be accessed by tests.

### 2.7 Comprehensions & Generator Expressions

Okay to use for simple cases.

#### 2.7.1 Definition

List, Dict, and Set comprehensions as well as generator expressions
provide a concise and efficient way to create container types and
iterators without resorting to the use of traditional loops,
`map()`,
`filter()`, or
`lambda`.

#### 2.7.2 Pros

Simple comprehensions can be clearer and simpler than other dict, list,
or set creation techniques. Generator expressions can be very efficient,
since they avoid the creation of a list entirely.

#### 2.7.3 Cons

Complicated comprehensions or generator expressions can be hard to read.

#### 2.7.4 Decision

Comprehensions are allowed, however multiple `for` clauses or filter expressions are not permitted.
Optimize for readability, not conciseness.

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

  result = 

  return (x**2 for x in range(10))

  unique_names = {user.name for user in users if user is not None}
```


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

### 2.8 Default Iterators and Operators

Use default iterators and operators for types that support them, like
lists, dictionaries, and files.

#### 2.8.1 Definition

Container types, like dictionaries and lists, define default iterators
and membership test operators ("in" and "not in").

#### 2.8.2 Pros

The default iterators and operators are simple and efficient. They
express the operation directly, without extra method calls. A function
that uses default operators is generic. It can be used with any type
that supports the operation.

#### 2.8.3 Cons

You can't tell the type of objects by reading the method names (unless
the variable has type annotations). This is also an advantage.

#### 2.8.4 Decision

Use default iterators and operators for types that support them, like
lists, dictionaries, and files. The built-in types define iterator
methods, too. Prefer these methods to methods that return lists, except
that you should not mutate a container while iterating over it.

``` highlight
Yes:  for key in adict: ...
      if obj in alist: ...
      for line in afile: ...
      for k, v in adict.items(): ...
```


``` highlight
No:   for key in adict.keys(): ...
      for line in afile.readlines(): ...
```

### 2.9 Generators

Use generators as needed.

#### 2.9.1 Definition

A generator function returns an iterator that yields a value each time
it executes a yield statement. After it yields a value, the runtime
state of the generator function is suspended until the next value is
needed.

#### 2.9.2 Pros

Simpler code, because the state of local variables and control flow are
preserved for each call. A generator uses less memory than a function
that creates an entire list of values at once.

#### 2.9.3 Cons

Local variables in the generator will not be garbage collected until the
generator is either consumed to exhaustion or itself garbage collected.

#### 2.9.4 Decision

Fine. Use "Yields:" rather than "Returns:" in the docstring for
generator functions.

If the generator manages an expensive resource, make sure to force the
clean up.

A good way to do the clean up is by wrapping the generator with a
context manager [PEP-0533](https://peps.python.org/pep-0533/).

### 2.10 Lambda Functions

Okay for one-liners. Prefer generator expressions over
`map()` or
`filter()` with a
`lambda`.

#### 2.10.1 Definition

Lambdas define anonymous functions in an expression, as opposed to a
statement.

#### 2.10.2 Pros

Convenient.

#### 2.10.3 Cons

Harder to read and debug than local functions. The lack of names means
stack traces are more difficult to understand. Expressiveness is limited
because the function may only contain an expression.

#### 2.10.4 Decision

Lambdas are allowed. If the code inside the lambda function spans
multiple lines or is longer than 60-80 chars, it might be better to
define it as a regular [nested function](#lexical-scoping).

For common operations like multiplication, use the functions from the
`operator` module instead of
lambda functions. For example, prefer `operator.mul` to `lambda x, y: x * y`.

### 2.11 Conditional Expressions

Okay for simple cases.

#### 2.11.1 Definition

Conditional expressions (sometimes called a "ternary operator") are
mechanisms that provide a shorter syntax for if statements. For example:
`x = 1 if cond else 2`.

#### 2.11.2 Pros

Shorter and more convenient than an if statement.

#### 2.11.3 Cons

May be harder to read than an if statement. The condition may be
difficult to locate if the expression is long.

#### 2.11.4 Decision

Okay to use for simple cases. Each portion must fit on one line:
true-expression, if-expression, else-expression. Use a complete if
statement when things get more complicated.

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


``` highlight
No:
    bad_line_breaking = ('yes' if predicate(value) else
                         'no')
    portion_too_long = ('yes'
                        if some_long_module.some_long_predicate_function(
                            really_long_variable_name)
                        else 'no, false, negative, nay')
```

### 2.12 Default Argument Values

Okay in most cases.

#### 2.12.1 Definition

You can specify values for variables at the end of a function's
parameter list, e.g., `def foo(a, b=0):`. If `foo` is
called with only one argument, `b` is set to 0. If it is called with two arguments,
`b` has the value of the second
argument.

#### 2.12.2 Pros

Often you have a function that uses lots of default values, but on rare
occasions you want to override the defaults. Default argument values
provide an easy way to do this, without having to define lots of
functions for the rare exceptions. As Python does not support overloaded
methods/functions, default arguments are an easy way of "faking" the
overloading behavior.

#### 2.12.3 Cons

Default arguments are evaluated once at module load time. This may cause
problems if the argument is a mutable object such as a list or a
dictionary. If the function modifies the object (e.g., by appending an
item to a list), the default value is modified.

#### 2.12.4 Decision

Okay to use with the following caveat:

Do not use mutable objects as default values in the function or method
definition.

``` highlight
Yes: def foo(a, b=None):
         if b is None:
             b = ):  # Could still get passed to unchecked code.
         ...
```

### 2.13 Properties

Properties may be used to control getting or setting attributes that
require trivial computations or logic. Property implementations must
match the general expectations of regular attribute access: that they
are cheap, straightforward, and unsurprising.

#### 2.13.1 Definition

A way to wrap method calls for getting and setting an attribute as a
standard attribute access.

#### 2.13.2 Pros

- Allows for an attribute access and assignment API rather than [getter
  and setter](#getters-and-setters) method calls.
- Can be used to make an attribute read-only.
- Allows calculations to be lazy.
- Provides a way to maintain the public interface of a class when the
  internals evolve independently of class users.

#### 2.13.3 Cons

- Can hide side-effects much like operator overloading.
- Can be confusing for subclasses.

#### 2.13.4 Decision

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

Properties should be created with the `@property` [decorator](#s2.17-function-and-method-decorators).
Manually implementing a property descriptor is considered a [power
feature](#power-features).

Inheritance with properties can be non-obvious. Do not use properties to
implement computations a subclass may ever want to override and extend.

### 2.14 True/False Evaluations

Use the "implicit" false if at all possible (with a few caveats).

#### 2.14.1 Definition

Python evaluates certain values as `False` when in a boolean context. A quick "rule of thumb"
is that all "empty" values are considered false, so
`0, None, , ''` all
evaluate as false in a boolean context.

#### 2.14.2 Pros

Conditions using Python booleans are easier to read and less
error-prone. In most cases, they're also faster.

#### 2.14.3 Cons

May look strange to C/C++ developers.

#### 2.14.4 Decision

Use the "implicit" false if possible, e.g.,
`if foo:` rather than
`if foo !=  

### 2.16 Lexical Scoping

Okay to use.

#### 2.16.1 Definition

A nested Python function can refer to variables defined in enclosing
functions, but cannot assign to them. Variable bindings are resolved
using lexical scoping, that is, based on the static program text. Any
assignment to a name in a block will cause Python to treat all
references to that name as a local variable, even if the use precedes
the assignment. If a global declaration occurs, the name is treated as a
global variable.

An example of the use of this feature is:

``` highlight
def get_adder(summand1: float) -> Callable[[float], float]:
    """Returns a function that adds numbers to a given number."""
    def adder(summand2: float) -> float:
        return summand1 + summand2

    return adder
```

#### 2.16.2 Pros

Often results in clearer, more elegant code. Especially comforting to
experienced Lisp and Scheme (and Haskell and ML and ...) programmers.

#### 2.16.3 Cons

Can lead to confusing bugs, such as this example based on
[PEP-0227](https://peps.python.org/pep-0227/):

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


So `foo([1, 2, 3])` will print
`1 2 3 3`, not
`1 2 3 4`.

#### 2.16.4 Decision

Okay to use.

### 2.17 Function and Method Decorators

Use decorators judiciously when there is a clear advantage. Avoid
`staticmethod` and limit use of
`classmethod`.

#### 2.17.1 Definition

[Decorators for Functions and
Methods](https://docs.python.org/3/glossary.html#term-decorator) (a.k.a
"the `@` notation"). One common
decorator is `@property`, used
for converting ordinary methods into dynamically computed attributes.
However, the decorator syntax allows for user-defined decorators as
well. Specifically, for some function `my_decorator`, this:

``` highlight
class C:
    @my_decorator
    def method(self):
        # method body ...
```


is equivalent to:

``` highlight
class C:
    def method(self):
        # method body ...
    method = my_decorator(method)
```

#### 2.17.2 Pros

Elegantly specifies some transformation on a method; the transformation
might eliminate some repetitive code, enforce invariants, etc.

#### 2.17.3 Cons

Decorators can perform arbitrary operations on a function's arguments or
return values, resulting in surprising implicit behavior. Additionally,
decorators execute at object definition time. For module-level objects
(classes, module functions, ...) this happens at import time. Failures
in decorator code are pretty much impossible to recover from.

#### 2.17.4 Decision

Use decorators judiciously when there is a clear advantage. Decorators
should follow the same import and naming guidelines as functions. A
decorator docstring should clearly state that the function is a
decorator. Write unit tests for decorators.

Avoid external dependencies in the decorator itself (e.g. don't rely on
files, sockets, database connections, etc.), since they might not be
available when the decorator runs (at import time, perhaps from
`pydoc` or other tools). A
decorator that is called with valid parameters should (as much as
possible) be guaranteed to succeed in all cases.

Decorators are a special case of "top-level code" - see
[main](#s3.17-main) for more discussion.

Never use `staticmethod` unless
forced to in order to integrate with an API defined in an existing
library. Write a module-level function instead.

Use `classmethod` only when
writing a named constructor, or a class-specific routine that modifies
necessary global state such as a process-wide cache.

### 2.18 Threading

Do not rely on the atomicity of built-in types.

While Python's built-in data types such as dictionaries appear to have
atomic operations, there are corner cases where they aren't atomic (e.g.
if `__hash__` or
`__eq__` are implemented as
Python methods) and their atomicity should not be relied upon. Neither
should you rely on atomic variable assignment (since this in turn
depends on dictionaries).

Use the `queue` module's
`Queue` data type as the
preferred way to communicate data between threads. Otherwise, use the
`threading` module and its
locking primitives. Prefer condition variables and
`threading.Condition` instead of
using lower-level locks.

### 2.19 Power Features

Avoid these features.

#### 2.19.1 Definition

Python is an extremely flexible language and gives you many fancy
features such as custom metaclasses, access to bytecode, on-the-fly
compilation, dynamic inheritance, object reparenting, import hacks,
reflection (e.g. some uses of `getattr()`), modification of system internals,
`__del__` methods implementing
customized cleanup, etc.

#### 2.19.2 Pros

These are powerful language features. They can make your code more
compact.

#### 2.19.3 Cons

It's very tempting to use these "cool" features when they're not
absolutely necessary. It's harder to read, understand, and debug code
that's using unusual features underneath. It doesn't seem that way at
first (to the original author), but when revisiting the code, it tends
to be more difficult than code that is longer but is straightforward.

#### 2.19.4 Decision

Avoid these features in your code.

Standard library modules and classes that internally use these features
are okay to use (for example, `abc.ABCMeta`, `dataclasses`, and `enum`).

### 2.20 Modern Python: from \_\_future\_\_ imports

New language version semantic changes may be gated behind a special
future import to enable them on a per-file basis within earlier
runtimes.

#### 2.20.1 Definition

Being able to turn on some of the more modern features via
`from __future__ import`
statements allows early use of features from expected future Python
versions.

#### 2.20.2 Pros

This has proven to make runtime version upgrades smoother as changes can
be made on a per-file basis while declaring compatibility and preventing
regressions within those files. Modern code is more maintainable as it
is less likely to accumulate technical debt that will be problematic
during future runtime upgrades.

#### 2.20.3 Cons

Such code may not work on very old interpreter versions prior to the
introduction of the needed future statement. The need for this is more
common in projects supporting an extremely wide variety of environments.

#### 2.20.4 Decision

##### from \_\_future\_\_ imports 

### 2.21 Type Annotated Code

You can annotate Python code with [type
hints](https://docs.python.org/3/library/typing.html). Type-check the
code at build time with a type checking tool like
[pytype](https://github.com/google/pytype). In most cases, when
feasible, type annotations are in source files. For third-party or
extension modules, annotations can be in [stub
`.pyi`
files](https://peps.python.org/pep-0484/#stub-files).

#### 2.21.1 Definition

Type annotations (or "type hints") are for function or method arguments
and return values:

``` highlight
def func(a: int) -> list[int]:
```


You can also declare the type of a variable using similar syntax:

``` highlight
a: SomeType = some_func()
```

#### 2.21.2 Pros

Type annotations improve the readability and maintainability of your
code. The type checker will convert many runtime errors to build-time
errors, and reduce your ability to use [Power
Features](#power-features).

#### 2.21.3 Cons

You will have to keep the type declarations up to date. You might see
type errors that you think are valid code. Use of a [type
checker](https://github.com/google/pytype) may reduce your ability to
use [Power Features](#power-features).

#### 2.21.4 Decision

You are strongly encouraged to enable Python type analysis when updating
code. When adding or modifying public APIs, include type annotations and
enable checking via pytype in the build system. As static analysis is
relatively new to Python, we acknowledge that undesired side-effects
(such as wrongly inferred types) may prevent adoption by some projects.
In those situations, authors are encouraged to add a comment with a TODO
or link to a bug describing the issue(s) currently preventing type
annotation adoption in the BUILD file or in the code itself as
appropriate.

