## 3 Python Style Rules

### 3.1 Semicolons

Do not terminate your lines with semicolons, and do not use semicolons to put two statements on the same line.

### 3.2 Line length

The maximum line length is *120 characters*.

Explicit exceptions to the 120-character limit:

- Long import statements.
- URLs, pathnames, or long flags in comments of docstrings
- Long string module-level constants do not contain whitespace that would be inconvenient to split across lines such as URLs or pathnames.
- Pylint disables comments. (e.g., `# pylint: disable=invalid-name`)

Do not use a backslash for [explicit line continuation](https://docs.python.org/3/reference/lexical_analysis.html#explicit-line-joining).

Instead, make use of Python's [implicit line joining inside parentheses, brackets and braces](http://docs.python.org/reference/lexical_analysis.html#implicit-line-joining).
If necessary, you can add an extra pair of parentheses around an expression.

When a literal string doesn't fit on a single line, use parentheses for
implicit line joining.

``` highlight
x = ('This will build a very long long '
    'long long long long long long string')
```

Prefer to break lines at the highest possible syntactic level. If you
must break a line twice, break it at the same syntactic level both
times.

``` highlight
Yes: bridgekeeper.answer(
        name="Arthur", quest=questlib.find(owner="Arthur", perilous=True)
    )
     answer = (a_long_line().of_chained_methods()
        .that_eventually_provides().an_answer())

     if (
         config is None
         or 'editor.language' not in config
         or config['editor.language'].use_spaces is False
     ):
       use_tabs()
```

``` highlight
No: bridgekeeper.answer(name="Arthur", quest=questlib.find(owner="Arthur", 
    perilous=True))
    if (config is None or 'editor.language' not in config or config[
      'editor.language'].use_spaces is False):
      use_tabs()
```

Within comments, put long URLs on one line if necessary.

``` highlight
Yes:  
  # See details at
  # https://www.example.com/us/developer/documentation/api/content/v2.0/csv_file_name_extension_full_specification.html
```

``` highlight
No:  
  # See details at
  # https://www.example.com/us/developer/documentation/api/content/\
  # v2.0/csv_file_name_extension_full_specification.html
```

Make note regarding the indentation of the elements in the line continuation examples above; see the [indentation](#s3.4-indentation) section for explanation.

### 3.3 Parentheses

Use parentheses sparingly.

It is fine, though not required, to use parentheses around tuples. Do not use them in return statements or conditional statements unless using parentheses for implied line continuation or to indicate a tuple.

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
     dish = (spam, beans,)
     for (x, y) in dict.items(): ...
```

``` highlight
No:  if (x):
         bar()
     if not(x):
         bar()
     return (foo)
```

Parentheses are redundant for returning the tuple:

``` highlight
Yes:
    return foo, bar
    
No:
    return (foo, bar)
```

### 3.4 Indentation

Indent your code blocks with *4 spaces*.

Never use tabs. Implied line continuation should align wrapped elements vertically (see [line length examples](#s3.2-line-length)), or use a hanging 4-space indent. Closing (round, square or curly) brackets can be placed at the end of the expression, or on separate lines, but then should be indented the same as the line with the corresponding opening bracket.

``` highlight
Yes:   # Aligned with opening delimiter.
       foo = long_function_name(var_one, var_two, var_three, var_four)
       meal = (spam, beans)

       # Aligned with opening delimiter in a dictionary.
       foo = {
           'long_dictionary_key': value1 + value2,
           ...
       }

       # 4-space hanging indent; nothing on first line.
       foo = long_function_name(var_one, var_two, var_three, var_four)
       meal = (spam, beans)

       # 4-space hanging indent; nothing on first line,
       # closing parenthesis on a new line.
       foo = long_function_name(var_one, var_two, var_three, var_four)
       meal = (spam, beans,)

       # 4-space hanging indent in a dictionary.
       foo = {
           'long_dictionary_key': long_dictionary_value,
           ...
       }
```

``` highlight
No:    # Stuff below forbidden.
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

#### 3.4.1 Trailing commas in sequences of items?

Trailing commas in sequences of items are recommended only when the closing container token `)`.

``` highlight
Yes:   golomb3 = (0, 1, 3,)
```

``` highlight
No:    golomb4 = [0, 1, 4, 6,]
```

### 3.5 Blank Lines

Two blank lines between top-level definitions, be they function or class definitions. One blank line between method definitions and between the docstring of a `class` and the first method. No blank line following a `def` line. Use single blank lines as you judge appropriate within functions or methods.

Blank lines need not be anchored to the definition. For example, related comments immediately preceding function, class, and method definitions can make sense. Consider if your comment might be more useful as part of the docstring.

### 3.6 Whitespace

Follow standard typographic rules for the use of spaces around
punctuation.

No whitespace inside parentheses, brackets or braces.

``` highlight
Yes: spam(ham[1], {'eggs': 2}, , [ ] )
```

No whitespace before a comma, semicolon, or colon. Do use whitespace
after a comma, semicolon, or colon, except at the end of the line.

``` highlight
Yes: if x == 4:
         print(x, y)
     x, y = y, x
```

``` highlight
No:  if x == 4 :
         print(x , y)
     x , y = y , x
```

No whitespace before the open paren/bracket that starts an argument
list, indexing or slicing.

``` highlight
Yes: spam(1)
```

``` highlight
No:  spam (1)
```

``` highlight
Yes: dict['key'] = list[index]
```

``` highlight
No:  dict ['key'] = list [index]
```

No trailing whitespace.

Surround binary operators with a single space on either side for
assignment (`=`), comparisons
(`==, <, >, !=, <>, <=, >=, in, not in, is, is not`), and Booleans (`and, or, not`). Use your better judgment for the insertion of
spaces around arithmetic operators (`+`, `-`,
`*`, `/`, `//`,
`%`, `**`, `@`).

``` highlight
Yes: x == 1
```

``` highlight
No:  x<1
```

Never use spaces around `=` when passing keyword arguments or defining a default parameter value, with one exception: [when a type annotation is present](#typing-default-values), *do* use spaces around the `=` for the default parameter value.

``` highlight
Yes: def complex(real, imag=0.0): return Magic(r=real, i=imag)
Yes: def complex(real, imag: float = 0.0): return Magic(r=real, i=imag)
```

``` highlight
No:  def complex(real, imag = 0.0): return Magic(r = real, i = imag)
No:  def complex(real, imag: float=0.0): return Magic(r = real, i = imag)
```

Don't use spaces to vertically align tokens on consecutive lines, since it becomes a maintenance burden (applies to `:`, `#`, `=`, etc.):

``` highlight
Yes:
  foo = 1000  # comment
  long_name = 2  # comment that should not be aligned

  dictionary = {
      'foo': 1,
      'long_name': 2,
  }
```

``` highlight
No:
  foo       = 1000  # comment
  long_name = 2     # comment that should not be aligned

  dictionary = {
      'foo'      : 1,
      'long_name': 2,
  }
```

### 3.7 Shebang Line

Most `.py` files do not need to start with a `#!` line. Start the main file of a program with `#!/usr/bin/env python3` (to support virtualenvs) or `#!/usr/bin/python3` per [PEP-394](https://peps.python.org/pep-0394/).

This line is used by the kernel to find the Python interpreter, but is ignored by Python when importing modules. It is only necessary on a file intended to be executed directly.

### 3.8 Comments and Docstrings

Be sure to use the right style for module, function, method docstrings and inline comments.

#### 3.8.1 Docstrings

Python uses *docstrings* to document code. A docstring is a string that
is the first statement in a package, module, class or function. These
strings can be extracted automatically through the
`__doc__` member of the object
and are used by `pydoc`. (Try
running `pydoc` on your module
to see how it looks.) Always use the three-double-quote
`"""` format for docstrings (per
[PEP 257](https://peps.python.org/pep-0257/)). A docstring should be
organized as a summary line (one physical line not exceeding 120
characters) terminated by a period, question mark, or exclamation point.
When writing more (encouraged), this must be followed by a blank line,
followed by the rest of the docstring starting at the same cursor
position as the first quote of the first line.

**Note: Sphinx notation (`@param`, `@type`, `@returns`, `@raises`, `@ivar`, etc.) is required for documenting functions, classes, and methods instead of Google style (`Args:`, `Raises:`).**
There are more formatting guidelines for docstrings below.

#### 3.8.2 Modules

Every file should contain license boilerplate. Choose the appropriate
boilerplate for the license used by the project (for example, Apache
2.0, BSD, LGPL, GPL).

Files should start with a docstring describing the contents and usage of
the module.

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

##### 3.8.2.1 Test modules

Module-level docstrings for test files are not required. They should be
included only when there is additional information that can be provided.

Examples include some specifics on how the test should be run, an
explanation of an unusual setup pattern, dependency on the external
environment, and so on.

``` highlight
"""This blaze test uses golden files.

You can update those files by running
`blaze run //foo/bar:foo_test -- --update_golden_files` from the `google3`
directory.
"""
```

Docstrings that do not provide any new information should not be used.

``` highlight
"""Tests for foo.bar."""
```

#### 3.8.3 Functions and Methods

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
(`"""Fetches rows from a Bigtable."""`) or imperative-style
(`"""Fetch rows from a Bigtable."""`), but the style should be consistent within a file.
The docstring for a `@property`
data descriptor should use the same style as the docstring for an
attribute or a [function argument](#doc-function-args)
(`"""The Bigtable path."""`,
rather than `"""Returns the Bigtable path."""`).

Certain aspects of a function should be documented using Sphinx notation, using the tags `@param`, `@type`, `@returns`, `@yields`, and `@raises` (or alternatively `:param`, `:type`, `:returns`, `:yields`, `:raises`). The tags must be aligned with the text of the docstring.

##### 3.8.3.1 Param and Return Tags

[*@param* and *@type:*](#doc-function-args)
: `@param name: description` lists a parameter by name and describes it.
  `@type name: type` defines the type of the parameter, if not present in the type annotations.
  If the description is too long to fit on a single 120-character line, use a hanging indent of 2 or 4 spaces (be consistent with the rest of the docstrings in the file).
  If a function accepts `*foo` (variable length argument lists) and/or `**bar` (arbitrary keyword arguments), they should be listed as `@param *foo:` and `@param **bar:`.

##### 3.8.3.2 Raises Tag

[*@returns* (or *@yields* for generators):](#doc-function-returns)
: `@returns: description` describes the semantics of the return value, including any type information that the type annotation does not provide. If the function only returns None, this tag is not required.
  If the function uses `yield` (is a generator), the `@yields` tag should document the object returned by `next()`, instead of the generator object itself.

##### 3.8.3.3 Raises Tag

[*@raises:*](#doc-function-raises)
: `@raises ExceptionType: description` lists exceptions that are relevant to the interface followed by a description.

``` highlight
def fetch_smalltable_rows(
    table_handle: smalltable.Table,
    keys: Sequence[bytes | str],
    require_all_keys: bool = False,
) -> Mapping[bytes, tuple[str, ...]]:
    """Fetches rows from a Smalltable.

    Retrieves rows pertaining to the given keys from the Table instance
    represented by table_handle.  String keys will be UTF-8 encoded.

    @param table_handle: An open smalltable.Table instance.
    @param keys: A sequence of strings representing the key of each table row to fetch.  String keys will be UTF-8 encoded.
    @param require_all_keys: If True only rows with values set for all keys will be returned.
    @returns: A dict mapping keys to the corresponding table row data fetched. Each row is represented as a tuple of strings. For
      example:

      {b'Serak': ('Rigel VII', 'Preparer'),
       b'Zim': ('Irk', 'Invader'),
       b'Lrrr': ('Omicron Persei 8', 'Emperor')}

      Returned keys are always bytes.  If a key from the keys argument is
      missing from the dictionary, then that row was not found in the
      table (and require_all_keys must have been False).
    @raises IOError: An error occurred accessing the smalltable.
    """
```

##### 3.8.3.4 Colon-based Sphinx Notation

Similarly, this variation using colon-based Sphinx notation is also allowed:

``` highlight
def fetch_smalltable_rows(
    table_handle: smalltable.Table,
    keys: Sequence[bytes | str],
    require_all_keys: bool = False,
) -> Mapping[bytes, tuple[str, ...]]:
    """Fetches rows from a Smalltable.

    Retrieves rows pertaining to the given keys from the Table instance
    represented by table_handle.  String keys will be UTF-8 encoded.

    :param table_handle: An open smalltable.Table instance.
    :param keys: A sequence of strings representing the key of each table row to fetch.  String keys will be UTF-8 encoded.
    :param require_all_keys: If True only rows with values set for all keys will be returned.
    :returns: A dict mapping keys to the corresponding table row data fetched. Each row is represented as a tuple of strings. For
      example:

      {b'Serak': ('Rigel VII', 'Preparer'),
       b'Zim': ('Irk', 'Invader'),
       b'Lrrr': ('Omicron Persei 8', 'Emperor')}

      Returned keys are always bytes.  If a key from the keys argument is
      missing from the dictionary, then that row was not found in the
      table (and require_all_keys must have been False).
    :raises IOError: An error occurred accessing the smalltable.
    """
```

##### 3.8.3.5 Overridden Methods

A method that overrides a method from a base class does not need a
docstring if it is explicitly decorated with
[`@override`](https://typing-extensions.readthedocs.io/en/latest/#override)
(from `typing_extensions` or
`typing` modules), unless the
overriding method's behavior materially refines the base method's
contract, or details need to be provided (e.g., documenting additional
side effects), in which case a docstring with at least those differences
is required on the overriding method.

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

#### 3.8.4 Classes

Classes should have a docstring below the class definition describing
the class. Public attributes, excluding [properties](#properties),
should be documented here using `@ivar` (instance variable) or `@type` tags and follow the same formatting as a
[function's parameters](#doc-function-args).

``` highlight
class SampleClass:
    """Summary of class here.

    Longer class information...
    Longer class information...

    @ivar likes_spam: A boolean indicating if we like SPAM or not.
    @ivar eggs: An integer count of the eggs we have laid.
    """

    def __init__(self, likes_spam: bool = False):
        """Initializes the instance based on spam preference.

        @param likes_spam: Defines if instance exhibits this preference.
        """
        self.likes_spam = likes_spam
        self.eggs = 0

    @property
    def butter_sticks(self) -> int:
        """The number of butter sticks we have."""
```

All class docstrings should start with a one-line summary that describes
what the class instance represents. This implies that subclasses of
`Exception` should also describe
what the exception represents, and not the context in which it might
occur. The class docstring should not repeat unnecessary information,
such as that the class is a class.

``` highlight
# Yes:
class CheeseShopAddress:
  """The address of a cheese shop.

  ...
  """

class OutOfCheeseError(Exception):
  """No more cheese is available."""
```

``` highlight
# No:
class CheeseShopAddress:
  """Class that describes the address of a cheese shop.

  ...
  """

class OutOfCheeseError(Exception):
  """Raised when no more cheese is available."""
```

#### 3.8.5 Block and Inline Comments

The final place to have comments is in tricky parts of the code. If
you're going to have to explain it at the next [code
review](http://en.wikipedia.org/wiki/Code_review), you should comment it
now. Complicated operations get a few lines of comments before the
operations commence. Non-obvious ones get comments at the end of the
line.

``` highlight
# We use a weighted dictionary search to find out where i is in
# the array.  We extrapolate position based on the largest num
# in the array and the array size and then do binary search to
# get the exact number.

if i & (i-1) == 0:  # True if i is 0 or a power of 2.
```

To improve legibility, these comments should start at least 2 spaces
away from the code with the comment character `#`, followed by at least one space before the text of
the comment itself.

On the other hand, never describe the code. Assume the person reading
the code knows Python (though not what you're trying to do) better than
you do.

``` highlight
# BAD COMMENT: Now go through the b array and make sure whenever i occurs
# the next element is i+1
```

#### 3.8.6 Punctuation, Spelling, and Grammar

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

### 3.10 Strings

Use an
[f-string](https://docs.python.org/3/reference/lexical_analysis.html#f-strings),
the `%` operator, or the
`format` method for formatting
strings, even when the parameters are all strings. Use your best
judgment to decide between string formatting options. A single join with
`+` is okay but do not format
with `+`.

``` highlight
Yes: x = f'name: {name}; score: {n}'
     x = '%s, %s!' % (imperative, expletive)
     x = '{}, {}'.format(first, second)
     x = 'name: %s; score: %d' % (name, n)
     x = 'name: %(name)s; score: %(score)d' % {'name':name, 'score':n}
     x = 'name: {}; score: {}'.format(name, n)
     x = a + b
```

``` highlight
No: x = first + ', ' + second
    x = 'name: ' + name + '; score: ' + str(n)
```

Avoid using the `+` and
`+=` operators to accumulate a
string within a loop. In some conditions, accumulating a string with
addition can lead to quadratic rather than linear running time. Although
common accumulations of this sort may be optimized on CPython, that is
an implementation detail. The conditions under which an optimization
applies are not easy to predict and may change. Instead, add each
substring to a list and `''.join` the list after the loop terminates, or write each
substring to an `io.StringIO`
buffer. These techniques consistently have amortized-linear run-time
complexity.

``` highlight
Yes: items = ['<table>']
     for last_name, first_name in employee_list:
         items.append('<tr><td>%s, %s</td></tr>' % (last_name, first_name))
     items.append('</table>')
     employee_table = ''.join(items)
```

``` highlight
No: employee_table = '<table>'
    for last_name, first_name in employee_list:
        employee_table += '<tr><td>%s, %s</td></tr>' % (last_name, first_name)
    employee_table += '</table>'
```

Be consistent with your choice of string quote character within a file.
Pick `'` or
`"` and stick with it. It is
okay to use the other quote character on a string to avoid the need to
backslash-escape quote characters within the string.

``` highlight
Yes:
  Python('Why are you hiding your eyes?')
  Gollum("I'm scared of lint errors.")
  Narrator('"Good!" thought a happy Python reviewer.')
```

``` highlight
No:
  Python("Why are you hiding your eyes?")
  Gollum('The lint. It burns. It burns us.')
  Gollum("Always the great lint. Watching. Watching.")
```

Prefer `"""` for multi-line
strings rather than `'''`.
Projects may choose to use `'''`
for all non-docstring multi-line strings if and only if they also use
`'` for regular strings.
Docstrings must use `"""`
regardless.

Multi-line strings do not flow with the indentation of the rest of the
program. If you need to avoid embedding extra space in the string, use
either concatenated single-line strings or a multi-line string with
[`textwrap.dedent()`](https://docs.python.org/3/library/textwrap.html#textwrap.dedent)
to remove the initial space on each line:

``` highlight
  No:
  long_string = """This is pretty ugly.
Don't do this.
"""
```

``` highlight
  Yes:
  long_string = """This is fine if your use case can accept
      extraneous leading spaces."""
```

``` highlight
  Yes:
  long_string = ("And this is fine if you cannot accept\n" +
                 "extraneous leading spaces.")
```

``` highlight
  Yes:
  long_string = ("And this too is fine if you cannot accept\n"
                 "extraneous leading spaces.")
```

``` highlight
  Yes:
  import textwrap

  long_string = textwrap.dedent("""\
      This is also fine, because textwrap.dedent()
      will collapse common leading spaces in each line.""")
```

Note that using a backslash here does not violate the prohibition
against [explicit line continuation](#line-length); in this case, the
backslash is [escaping a
newline](https://docs.python.org/3/reference/lexical_analysis.html#string-and-bytes-literals)
in a string literal.

#### 3.10.1 Logging

For logging functions that expect a pattern-string (with %-placeholders)
as their first argument: Always call them with a string literal (not an
f-string!) as their first argument with pattern-parameters as subsequent
arguments. Some logging implementations collect the unexpanded
pattern-string as a queryable field. It also prevents spending time
rendering a message that no logger is configured to output.

``` highlight
  Yes:
  import tensorflow as tf
  logger = tf.get_logger()
  logger.info('TensorFlow Version is: %s', tf.__version__)
```

``` highlight
  Yes:
  import os
  from absl import logging

  logging.info('Current $PAGER is: %s', os.getenv('PAGER', default=''))

  homedir = os.getenv('HOME')
  if homedir is None or not os.access(homedir, os.W_OK):
    logging.error('Cannot write to home directory, $HOME=%r', homedir)
```

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

#### 3.10.2 Error Messages

Error messages (such as: message strings on exceptions like
`ValueError`, or messages shown
to the user) should follow three guidelines:

1.  The message needs to precisely match the actual error condition.

2.  Interpolated pieces need to always be clearly identifiable as such.

3.  They should allow simple automated processing (e.g. grepping).

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

### 3.11 Files, Sockets, and similar Stateful Resources

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
  the `__del__` method.
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
[`with`
statement](http://docs.python.org/reference/compound_stmts.html#the-with-statement):

``` highlight
with open("hello.txt") as hello_file:
    for line in hello_file:
        print(line)
```

For file-like objects that do not support the `with` statement, use
`contextlib.closing()`:

``` highlight
import contextlib

with contextlib.closing(urllib.urlopen("http://www.python.org/")) as front_page:
    for line in front_page:
        print(line)
```

In rare cases where context-based resource management is infeasible,
code documentation must explain clearly how resource lifetime is
managed.

### 3.12 TODO Comments

Use `TODO` comments for code
that is temporary, a short-term solution, or good-enough but not
perfect.

A `TODO` comment begins with the
word `TODO` in all caps, a
following colon, and a link to a resource that contains the context,
ideally a bug reference. A bug reference is preferable because bugs are
tracked and have follow-up comments. Follow this piece of context with
an explanatory string introduced with a hyphen `-`. The purpose is to have a consistent
`TODO` format that can be
searched to find out how to get more details.

``` highlight
# TODO: crbug.com/192795 - Investigate cpufreq optimizations.
```

Old style, formerly recommended, but discouraged for use in new code:

``` highlight
# TODO(crbug.com/192795): Investigate cpufreq optimizations.
# TODO(yourusername): Use a "\*" here for concatenation operator.
```

Avoid adding TODOs that refer to an individual or team as the context:

``` highlight
# TODO: @yourusername - File an issue and use a '*' for repetition.
```

If your `TODO` is of the form
"At a future date do something" make sure that you either include a very
specific date ("Fix by November 2009") or a very specific event ("Remove
this code when all clients can handle XML responses.") that future code
maintainers will comprehend. Issues are ideal for tracking this.

### 3.13 Imports formatting

Imports should be on separate lines; there are [exceptions for
`typing` and
`collections.abc`
imports](#typing-imports).

E.g.:

``` highlight
Yes: from collections.abc import Mapping, Sequence
     import os
     import sys
     from typing import Any, NewType
```

``` highlight
No:  import os, sys
```

Imports are always put at the top of the file, just after any module
comments and docstrings and before module globals and constants. Imports
should be grouped from most generic to least generic:

1.  Python future import statements. For example:

    ``` highlight
    from __future__ import annotations
    ```

    See [above](#from-future-imports) for more information about those.

2.  Python standard library imports. For example:

    ``` highlight
    import sys
    ```

3.  [third-party](https://pypi.org/) module or package imports. For
    example:

    ``` highlight
    import tensorflow as tf
    ```

4.  Code repository sub-package imports. For example:

    ``` highlight
    from otherproject.ai import mind
    ```

5.  **Deprecated:** application-specific imports that are part of the
    same top-level sub-package as this file. For example:

    ``` highlight
    from myproject.backend.hgwells import time_machine
    ```

    You may find older Google Python Style code doing this, but it is no
    longer required. **New code is encouraged not to bother with this.**
    Simply treat application-specific sub-package imports the same as
    other sub-package imports.

Within each grouping, imports should be sorted lexicographically,
ignoring case, according to each module's full package path (the
`path` in
`from path import ...`). Code
may optionally place a blank line between import sections.

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

### 3.14 Statements

Generally only one statement per line.

However, you may put the result of a test on the same line as the test
only if the entire statement fits on one line. In particular, you can
never do so with `try`/`except`
since the `try` and
`except` can't both fit on the
same line, and you can only do so with an `if` if there is no `else`.

``` highlight
Yes:

  if foo: bar(foo)
```

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

### 3.15 Getters and Setters

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
guidelines, such as `get_foo()`
and `set_foo()`.

If the past behavior allowed access through a property, do not bind the
new getter/setter functions to the property. Any code still attempting
to access the variable by the old method should break visibly so they
are made aware of the change in complexity.

### 3.16 Naming

`module_name`,
`package_name`,
`ClassName`,
`method_name`,
`ExceptionName`,
`function_name`,
`GLOBAL_CONSTANT_NAME`,
`global_var_name`,
`instance_var_name`,
`function_parameter_name`,
`local_var_name`,
`query_proper_noun_for_thing`,
`send_acronym_via_https`.

Names should be descriptive. This includes functions, classes,
variables, attributes, files and any other type of named entities.

Avoid abbreviation. In particular, do not use abbreviations that are
ambiguous or unfamiliar to readers outside your project, and do not
abbreviate by deleting letters within a word.

Always use a `.py` filename
extension. Never use dashes.

#### 3.16.1 Names to Avoid

- single character names, except for specifically allowed cases:

  - counters or iterators (e.g. `i`, `j`,
    `k`, `v`, et al.)
  - `e` as an exception
    identifier in `try/except`
    statements.
  - `f` as a file handle in
    `with` statements
  - private [type variables](#typing-type-var) with no constraints (e.g.
    `_T = TypeVar("_T")`,
    `_P = ParamSpec("_P")`)
  - names that match established notation in a reference paper or
    algorithm (see [Mathematical Notation](#math-notation))

  Please be mindful not to abuse single-character naming. Generally
  speaking, descriptiveness should be proportional to the name's scope
  of visibility. For example, `i` might be a fine name for 5-line code block but
  within multiple nested scopes, it is likely too vague.

- dashes (`-`) in any
  package/module name

- `__double_leading_and_trailing_underscore__` names (reserved by Python)

- offensive terms

- names that needlessly include the type of the variable (for example:
  `id_to_name_dict`)

#### 3.16.2 Naming Conventions

- "Internal" means internal to a module, or protected or private within
  a class.

- Prepending a single underscore (`_`) has some support for protecting module variables
  and functions (linters will flag protected member access). Note that
  it is okay for unit tests to access protected constants from the
  modules under test.

- Prepending a double underscore (`__` aka "dunder") to an instance variable or method
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
  `import StringIO` or
  `from StringIO import StringIO`?")

- New *unit test* files follow PEP 8 compliant lower_with_under method
  names, for example,
  `test_<method_under_test>_<state>`. For consistency(\*) with legacy modules that
  follow CapWords function names, underscores may appear in method names
  starting with `test` to
  separate logical components of the name. One possible pattern is
  `test<MethodUnderTest>_<state>`.

#### 3.16.3 File Naming

Python filenames must have a `.py` extension and must not contain dashes
(`-`). This allows them to be
imported and unittested. If you want an executable to be accessible
without the extension, use a symbolic link or a simple bash wrapper
containing `exec "$0.py" "$@"`.

#### 3.16.4 Guidelines derived from [Guido](https://en.wikipedia.org/wiki/Guido_van_Rossum)'s Recommendations

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

#### 3.16.5 Mathematical Notation

For mathematically-heavy code, short variable names that would otherwise
violate the style guide are preferred when they match established
notation in a reference paper or algorithm.

When using names based on established notation:

1.  Cite the source of all naming conventions, preferably with a
    hyperlink to academic resource itself, in a comment or docstring. If
    the source is not accessible, clearly document the naming
    conventions.
2.  Prefer PEP8-compliant `descriptive_names` for public APIs, which are much more likely to
    be encountered out of context.
3.  Use a narrowly-scoped
    `pylint: disable=invalid-name` directive to silence warnings. For just a few
    variables, use the directive as an endline comment for each one; for
    more, apply the directive at the beginning of a block.

### 3.17 Main

In Python, `pydoc` as well as
unit tests require modules to be importable. If a file is meant to be
used as an executable, its main functionality should be in a
`main()` function, and your code
should always check `if __name__ == '__main__'` before executing your main program, so that it is
not executed when the module is imported.

When using [absl](https://github.com/abseil/abseil-py), use
`app.run`:

``` highlight
from absl import app
...

def main(argv: Sequence[str]):
    # process non-flag arguments
    ...

if __name__ == '__main__':
    app.run(main)
```

Otherwise, use:

``` highlight
def main():
    ...

if __name__ == '__main__':
    main()
```

All code at the top level will be executed when the module is imported.
Be careful not to call functions, create objects, or perform other
operations that should not be executed when the file is being
`pydoc`ed.

### 3.18 Function length

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

### 3.19 Type Annotations

#### 3.19.1 General Rules

- Familiarize yourself with [type
  hints](https://docs.python.org/3/library/typing.html).

- Annotating `self` or
  `cls` is generally not
  necessary. [`Self`](https://docs.python.org/3/library/typing.html#typing.Self)
  can be used if it is necessary for proper type information, e.g.

  ``` highlight
  from typing import Self

  class BaseClass:
    @classmethod
    def create(cls) -> Self:
      ...

    def difference(self, other: Self) -> float:
      ...
  ```

- Similarly, don't feel compelled to annotate the return value of
  `__init__` (where
  `None` is the only valid
  option).

- If any other variable or a returned type should not be expressed, use
  `Any`.

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

#### 3.19.2 Line Breaking

Try to follow the existing [indentation](#indentation) rules.

After annotating, many function signatures will become "one parameter
per line". To ensure the return type is also given its own line, a comma
can be placed after the last parameter.

``` highlight
def my_method(
    self,
    first_var: int,
    second_var: Foo,
    third_var: Bar | None,
) -> int:
  ...
```

Always prefer breaking between variables, and not, for example, between
variable names and type annotations. However, if everything fits on the
same line, go for it.

``` highlight
def my_method(self, first_var: int) -> int:
  ...
```

If the combination of the function name, the last parameter, and the
return type is too long, indent by 4 in a new line. When using line
breaks, prefer putting each parameter and the return type on their own
lines and aligning the closing parenthesis with the
`def`:

``` highlight
Yes:
def my_method(
    self,
    other_arg: MyLongType | None,
) -> tuple[MyLongType1, MyLongType1]:
  ...
```

Optionally, the return type may be put on the same line as the last
parameter:

``` highlight
Okay:
def my_method(
    self,
    first_var: int,
    second_var: int) -> dict[OtherLongType, MyLongType]:
  ...
```

`pylint` allows you to move the
closing parenthesis to a new line and align with the opening one, but
this is less readable.

``` highlight
No:
def my_method(self,
              other_arg: MyLongType | None,
             ) -> dict[OtherLongType, MyLongType]:
  ...
```

As in the examples above, prefer not to break types. However, sometimes
they are too long to be on a single line (try to keep sub-types
unbroken).

``` highlight
def my_method(
    self,
    first_var: tuple[list[MyLongType1],
                     list[MyLongType2]],
    second_var: list[dict[
        MyLongType3, MyLongType4]],
):
  ...
```

If a single name and type is too long, consider using an
[alias](#typing-aliases) for the type. The last resort is to break after
the colon and indent by 4.

``` highlight
Yes:
def my_function(
    long_variable_name:
        long_module_name.LongTypeName,
):
  ...
```

``` highlight
No:
def my_function(
    long_variable_name: long_module_name.
        LongTypeName,
):
  ...
```

#### 3.19.3 Forward Declarations

If you need to use a class name (from the same module) that is not yet
defined -- for example, if you need the class name inside the
declaration of that class, or if you use a class that is defined later
in the code -- either use
`from __future__ import annotations` or use a string for the class name.

``` highlight
Yes:
from __future__ import annotations

class MyClass:
  def __init__(self, stack: Sequence[MyClass], item: OtherClass):

class OtherClass:
  ...
```

``` highlight
Yes:
class MyClass:
  def __init__(self, stack: Sequence['MyClass'], item: 'OtherClass'):

class OtherClass:
  ...
```

#### 3.19.4 Default Values

As per
[PEP-008](https://peps.python.org/pep-0008/#other-recommendations), use
spaces around the `=` *only* for
arguments that have both a type annotation and a default value.

``` highlight
Yes:
def func(a: int = 0) -> int:
  ...
```

``` highlight
No:
def func(a:int=0) -> int:
  ...
```

#### 3.19.5 NoneType

In the Python type system, `NoneType` is a "first class" type, and for typing purposes,
`None` is an alias for
`NoneType`. If an argument can
be `None`, it has to be
declared! You can use `|` union
type expressions (recommended in new Python 3.10+ code), or the older
`Optional` and
`Union` syntaxes.

Use explicit `X | None` instead
of implicit. Earlier versions of type checkers allowed
`a: str = None` to be
interpreted as `a: str | None = None`, but that is no longer the preferred behavior.

``` highlight
Yes:
def modern_or_union(a: str | int | None, b: str | None = None) -> str:
  ...
def union_optional(a: Union[str, int, None], b: Optional[str] = None) -> str:
  ...
```

``` highlight
No:
def nullable_union(a: Union[None, str]) -> str:
  ...
def implicit_optional(a: str = None) -> str:
  ...
```

#### 3.19.6 Type Aliases

You can declare aliases of complex types. The name of an alias should be
CapWorded. If the alias is used only in this module, it should be
\_Private.

Note that the `: TypeAlias`
annotation is only supported in versions 3.10+.

``` highlight
from typing import TypeAlias

_LossAndGradient: TypeAlias = tuple[tf.Tensor, tf.Tensor]
ComplexTFMap: TypeAlias = Mapping[str, _LossAndGradient]
```

#### 3.19.7 Ignoring Types

You can disable type checking on a line with the special comment
`# type: ignore`.

`pytype` has a disable option
for specific errors (similar to lint):

``` highlight
# pytype: disable=attribute-error
```

#### 3.19.8 Typing Variables

\
[*Annotated Assignments*](#annotated-assignments)
: If an internal variable has a type that is hard or impossible to
  infer, specify its type with an annotated assignment - use a colon and
  type between the variable name and value (the same as is done with
  function arguments that have a default value):
  ``` highlight
  a: Foo = SomeUndecoratedFunction()
  ```

\
[*Type Comments*](#type-comments)
: Though you may see them remaining in the codebase (they were necessary
  before Python 3.6), do not add any more uses of a
  `# type: <type name>` comment
  on the end of the line:
  ``` highlight
  a = SomeUndecoratedFunction()  # type: Foo
  ```

#### 3.19.9 Tuples vs Lists

Typed lists can only contain objects of a single type. Typed tuples can
either have a single repeated type or a set number of elements with
different types. The latter is commonly used as the return type from a
function.

``` highlight
a: list[int] = [1, 2, 3]
b: tuple[int, ...] = (1, 2, 3)
c: tuple[int, str, float] = (1, "2", 3.5)
```

#### 3.19.10 Type variables

The Python type system has
[generics](https://docs.python.org/3/library/typing.html#generics). A
type variable, such as `TypeVar`
and `ParamSpec`, is a common way
to use them.

Example:

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

A `TypeVar` can be constrained:

``` highlight
AddableType = TypeVar("AddableType", int, float, str)
def add(a: AddableType, b: AddableType) -> AddableType:
  return a + b
```

A common predefined type variable in the `typing` module is `AnyStr`. Use it for multiple annotations that can be
`bytes` or
`str` and must all be the same
type.

``` highlight
from typing import AnyStr
def check_length(x: AnyStr) -> AnyStr:
  if len(x) <= 42:
    return x
  raise ValueError()
```

A type variable must have a descriptive name, unless it meets all of the
following criteria:

- not externally visible
- not constrained

``` highlight
Yes:
  _T = TypeVar("_T")
  _P = ParamSpec("_P")
  AddableType = TypeVar("AddableType", int, float, str)
  AnyFunction = TypeVar("AnyFunction", bound=Callable)
```

``` highlight
No:
  T = TypeVar("T")
  P = ParamSpec("P")
  _T = TypeVar("_T", int, float, str)
  _F = TypeVar("_F", bound=Callable)
```

#### 3.19.11 String types

> Do not use `typing.Text` in
> new code. It's only for Python 2/3 compatibility.

Use `str` for string/text data.
For code that deals with binary data, use `bytes`.

``` highlight
def deals_with_text_data(x: str) -> str:
  ...
def deals_with_binary_data(x: bytes) -> bytes:
  ...
```

If all the string types of a function are always the same, for example
if the return type is the same as the argument type in the code above,
use [AnyStr](#typing-type-var).

#### 3.19.12 Imports For Typing

For symbols (including types, functions, and constants) from the
`typing` or
`collections.abc` modules used
to support static analysis and type checking, always import the symbol
itself. This keeps common annotations more concise and matches typing
practices used around the world. You are explicitly allowed to import
multiple specific symbols on one line from the
`typing` and
`collections.abc` modules. For
example:

``` highlight
from collections.abc import Mapping, Sequence
from typing import Any, Generic, cast, TYPE_CHECKING
```

Given that this way of importing adds items to the local namespace,
names in `typing` or
`collections.abc` should be
treated similarly to keywords, and not be defined in your Python code,
typed or not. If there is a collision between a type and an existing
name in a module, import it using `import x as y`.

``` highlight
from typing import Any as AnyType
```

When annotating function signatures, prefer abstract container types
like `collections.abc.Sequence`
over concrete types like `list`.
If you need to use a concrete type (for example, a
`tuple` of typed elements),
prefer built-in types like `tuple` over the parametric type aliases from the
`typing` module (e.g.,
`typing.Tuple`).

``` highlight
from typing import List, Tuple

def transform_coordinates(original: list[tuple[float, float]]) ->
    list[tuple[float, float]]:
  ...
```

``` highlight
from collections.abc import Sequence

def transform_coordinates(original: Sequence[tuple[float, float]]) ->
    Sequence[tuple[float, float]]:
  ...
```

#### 3.19.13 Conditional Imports

Use conditional imports only in exceptional cases where the additional
imports needed for type checking must be avoided at runtime. This
pattern is discouraged; alternatives such as refactoring the code to
allow top-level imports should be preferred.

Imports that are needed only for type annotations can be placed within
an `if TYPE_CHECKING:` block.

- Conditionally imported types need to be referenced as strings, to be
  forward compatible with Python 3.6 where the annotation expressions
  are actually evaluated.
- Only entities that are used solely for typing should be defined here;
  this includes aliases. Otherwise it will be a runtime error, as the
  module will not be imported at runtime.
- The block should be right after all the normal imports.
- There should be no empty lines in the typing imports list.
- Sort this list as if it were a regular imports list.

  ``` highlight
  import typing
  if typing.TYPE_CHECKING:
    import sketch
  def f(x: "sketch.Sketch"): ...
  ```

#### 3.19.14 Circular Dependencies

Circular dependencies that are caused by typing are code smells. Such
code is a good candidate for refactoring. Although technically it is
possible to keep circular dependencies, various build systems will not
let you do so because each module has to depend on the other.

Replace modules that create circular dependency imports with
`Any`. Set an
[alias](#typing-aliases) with a meaningful name, and use the real type
name from this module (any attribute of `Any` is `Any`).
Alias definitions should be separated from the last import by one line.

``` highlight
from typing import Any

some_mod = Any  # some_mod.py imports this module.
...

def my_method(self, var: "some_mod.SomeType"):
  ...
```

#### 3.19.15 Generics

When annotating, prefer to specify type parameters for
[generic](https://docs.python.org/3/library/typing.html#generics) types
in a parameter list; otherwise, the generics' parameters will be assumed
to be [`Any`](https://docs.python.org/3/library/typing.html#the-any-type).

``` highlight
# Yes:
def get_names(employee_ids: Sequence[int]) -> Mapping[int, str]:
  ...
```

``` highlight
# No:
# This is interpreted as get_names(employee_ids: Sequence[Any]) -> Mapping[Any, Any]
def get_names(employee_ids: Sequence) -> Mapping:
  ...
```

If the best type parameter for a generic is `Any`, make it explicit, but remember that in many cases
[`TypeVar`](#typing-type-var)
might be more appropriate:

``` highlight
# No:
def get_names(employee_ids: Sequence[Any]) -> Mapping[Any, str]:
  """Returns a mapping from employee ID to employee name for given IDs."""
```

``` highlight
# Yes:
_T = TypeVar('_T')
def get_names(employee_ids: Sequence[_T]) -> Mapping[_T, str]:
  """Returns a mapping from employee ID to employee name for given IDs."""
```

## 4 Parting Words

*BE CONSISTENT*.

If you're editing code, take a few minutes to look at the code around
you and determine its style. If they use `_idx` suffixes in index variable names, you should too. If
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

This site is open source. [Improve this
page](https://github.com/google/styleguide/edit/gh-pages/pyguide.md).

