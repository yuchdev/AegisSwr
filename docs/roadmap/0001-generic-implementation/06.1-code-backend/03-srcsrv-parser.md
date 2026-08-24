# 03 – SrcSrv stream parser and fixtures

**Parent milestone:** 6.1 Code Backend – PDB Adapter
**State:** ⬜ Not started
**Depends on:** none (pure parsing logic, no I/O)
**Blocks:** 05

## Objective

Implement a parser for the Windows **Source Server (SrcSrv)** stream text
that `pdbstr.exe` extracts from a `.pdb` file. The parser converts the raw
text into typed Python dataclasses, exposing the VCS type, repository URL,
and the mapping from source file paths to VCS revision identifiers.

This is entirely pure Python with no I/O - fully testable on any platform
without a real PDB or `pdbstr.exe`.

## SrcSrv stream format

The SrcSrv stream is a structured text block divided into named sections by
header lines of the form `SRCSRV: {section} ---...`. The sections relevant
to Aegis are:

```
SRCSRV: ini ------------------------------------------------
INDEXVERSION=2
VERCTRL=git

SRCSRV: variables ------------------------------------------
GITREPO=https://github.com/acme/svc
SRCSRVTRG=%TARG%\%fnbksl%(%var2%)\%var3%\%fnfile%(%var1%)
SRCSRVCMD=git.exe clone %GITREPO% %TARG% & ...

SRCSRV: source files ----------------------------------------
C:\src\svc\db_writer.cpp*abc123def456*
C:\src\svc\main.cpp*abc123def456*
C:\src\svc\pool.cpp*def789abc012*

SRCSRV: end ------------------------------------------------
```

**Section semantics:**

| Section | Key fields used |
|---------|----------------|
| `ini` | `VERCTRL` - VCS type: `git`, `tfvc`, `svn`, `perforce` |
| `variables` | VCS-specific: `GITREPO` (git remote URL), `VSTFSSERVER` (TFVC), etc. |
| `source files` | One line per file: `{windows_path}*{revision}*[{extra}*]` |

The `source files` section uses `*` as field delimiter. Field positions:
- `[0]` - Windows source file path (may contain spaces)
- `[1]` - VCS revision identifier (git SHA-1, TFVC changeset number, etc.)
- `[2+]` - extra fields depending on VCS/build tool (ignored by Aegis)

## Files

- **Create** `src/aegis_swr/backends/code/srcsrv_parser.py`
- **Create** `tests/unit/fixtures/sample_srcsrv_git.txt`
- **Create** `tests/unit/fixtures/sample_srcsrv_tfvc.txt`
- **Create** `tests/unit/fixtures/sample_srcsrv_empty.txt`

## Dataclasses

```python
@dataclass(frozen=True)
class SrcSrvEntry:
    """A single source-file entry from the SrcSrv ``source files`` section.

    :ivar source_file: Original Windows path as recorded in the PDB
        (e.g. ``C:\\src\\svc\\db_writer.cpp``).
    :ivar revision: VCS revision identifier (git SHA, TFVC changeset, etc.).
    """
    source_file: str
    revision: str


@dataclass(frozen=True)
class SrcSrvStream:
    """Parsed representation of a PDB SrcSrv stream.

    :ivar verctrl: VCS type string as recorded in ``VERCTRL`` (e.g. ``"git"``).
        Empty string when the ``ini`` section is absent or ``VERCTRL`` is missing.
    :ivar repo_url: VCS repository URL, or ``None`` when not present.
        For ``git``: the ``GITREPO`` variable.
        For ``tfvc``: the ``VSTFSSERVER`` variable.
        Other VCS types: ``None``.
    :ivar entries: All source-file entries parsed from the ``source files``
        section. May be empty.
    """
    verctrl: str
    repo_url: Optional[str]
    entries: list[SrcSrvEntry]

    def unique_revisions(self) -> list[str]:
        """Return deduplicated revision identifiers in first-seen order."""
        seen: dict[str, None] = {}
        for e in self.entries:
            seen[e.revision] = None
        return list(seen)

    def files_for_revision(self, revision: str) -> list[str]:
        """Return source file paths recorded at *revision*."""
        return [e.source_file for e in self.entries if e.revision == revision]

    @property
    def is_empty(self) -> bool:
        """True when no source-file entries were found."""
        return not self.entries
```

## Class: `SrcSrvParser`

```python
class SrcSrvParser:
    """Stateless parser for PDB SrcSrv stream text.

    All methods are classmethods.  No I/O.

    Usage::

        stream = SrcSrvParser.parse(raw_text)
        for rev in stream.unique_revisions():
            files = stream.files_for_revision(rev)
    """

    # Section header prefix (case-insensitive match)
    _SECTION_RE = re.compile(r"^SRCSRV:\s*(\S+)", re.IGNORECASE)
    # Key=Value line in ini/variables sections
    _KV_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$", re.IGNORECASE)

    @classmethod
    def parse(cls, text: str) -> SrcSrvStream:
        """Parse a complete SrcSrv stream text into a :class:`SrcSrvStream`.

        Tolerates malformed lines (logs at DEBUG level and skips them).
        Returns an empty :class:`SrcSrvStream` when *text* is blank.

        :param text: Raw stream text as returned by ``pdbstr.exe``.
        :return: Parsed :class:`SrcSrvStream`.
        """

    @classmethod
    def _split_sections(cls, text: str) -> dict[str, list[str]]:
        """Split the stream into a dict mapping section name → content lines."""

    @classmethod
    def _parse_kv_section(cls, lines: list[str]) -> dict[str, str]:
        """Parse ``KEY=VALUE`` lines from an ``ini`` or ``variables`` section."""

    @classmethod
    def _parse_files_section(cls, lines: list[str]) -> list[SrcSrvEntry]:
        """Parse ``path*revision*[extra*]`` lines from the ``source files`` section.

        Skips blank lines and lines with fewer than two ``*``-delimited fields.
        """

    @classmethod
    def _extract_repo_url(cls, verctrl: str, variables: dict[str, str]) -> Optional[str]:
        """Extract the repository URL from the variables section.

        Known mappings:

        =========== ==============
        VERCTRL     Variable key
        =========== ==============
        ``git``     ``GITREPO``
        ``tfvc``    ``VSTFSSERVER``
        ``svn``     ``SVNREPO``
        ``perforce`` ``P4PORT``
        =========== ==============

        Returns ``None`` for unknown VCS types or missing variables.
        """
```

## Fixture files

### `tests/unit/fixtures/sample_srcsrv_git.txt`

```
SRCSRV: ini ------------------------------------------------
INDEXVERSION=2
VERCTRL=git

SRCSRV: variables ------------------------------------------
GITREPO=https://github.com/acme/svc
SRCSRVTRG=%TARG%\%fnbksl%(%var2%)\%var3%\%fnfile%(%var1%)

SRCSRV: source files ----------------------------------------
C:\src\svc\db_writer.cpp*abc123def456789012345678901234567890ab*
C:\src\svc\main.cpp*abc123def456789012345678901234567890ab*
C:\src\svc\pool.cpp*def789abc012345678901234567890abcdef12*

SRCSRV: end ------------------------------------------------
```

Two distinct revisions: `abc123...` (2 files) and `def789...` (1 file).

### `tests/unit/fixtures/sample_srcsrv_tfvc.txt`

```
SRCSRV: ini ------------------------------------------------
INDEXVERSION=2
VERCTRL=TFVC

SRCSRV: variables ------------------------------------------
VSTFSSERVER=https://dev.azure.com/acme/svc
DEPOT=$/svc/main

SRCSRV: source files ----------------------------------------
C:\src\svc\service.cpp*42*$/svc/main/service.cpp*
C:\src\svc\util.cpp*42*$/svc/main/util.cpp*

SRCSRV: end ------------------------------------------------
```

Note: TFVC uses changeset numbers (`42`), not SHAs. Three fields per line.

### `tests/unit/fixtures/sample_srcsrv_empty.txt`

```
SRCSRV: ini ------------------------------------------------
INDEXVERSION=2
VERCTRL=git

SRCSRV: variables ------------------------------------------
GITREPO=https://github.com/acme/svc

SRCSRV: source files ----------------------------------------

SRCSRV: end ------------------------------------------------
```

Empty `source files` section (no entries).

## Constraints

- Parser must not raise on malformed lines - skip with `logger.debug`.
- Section header matching is case-insensitive (`SRCSRV: ini` = `srcsrv: INI`).
- Windows paths in `source files` are preserved as-is (not normalised to POSIX
  here; the adapter normalises when constructing git commands in subtask 05).
- `SrcSrvStream` is a frozen dataclass (no mutation after construction).
- `SrcSrvEntry` is also frozen.
- Module has no imports from `backends/` or `core/` other than `loguru.logger`.
- `Optional[str]` throughout; no `str | None`.

## Tests

**Unit** (`tests/unit/test_srcsrv_parser.py` - new file):

- `test_parse_git_stream_verctrl` - parse `sample_srcsrv_git.txt`; assert
  `stream.verctrl == "git"`.
- `test_parse_git_stream_repo_url` - assert
  `stream.repo_url == "https://github.com/acme/svc"`.
- `test_parse_git_stream_entry_count` - assert `len(stream.entries) == 3`.
- `test_parse_git_stream_unique_revisions` - assert
  `len(stream.unique_revisions()) == 2`.
- `test_parse_git_stream_files_for_revision` - `files_for_revision("abc123...")` ==
  `["C:\\src\\svc\\db_writer.cpp", "C:\\src\\svc\\main.cpp"]`.
- `test_parse_tfvc_verctrl_uppercase` - parse `sample_srcsrv_tfvc.txt`; `verctrl`
  is preserved as `"TFVC"` (not lowercased - the caller normalises).
- `test_parse_tfvc_repo_url` - assert `repo_url == "https://dev.azure.com/acme/svc"`.
- `test_parse_tfvc_three_field_entries` - `entries[0].revision == "42"` (TFVC
  changeset number extracted from field index 1).
- `test_parse_empty_source_files` - parse `sample_srcsrv_empty.txt`; `is_empty
  == True`, `unique_revisions() == []`.
- `test_parse_blank_text_returns_empty_stream` - `parse("")` returns a stream
  with `verctrl == ""`, `repo_url == None`, `entries == []`.
- `test_parse_missing_ini_section_no_raise` - stream with no `ini` section
  parses without raising; `verctrl == ""`.
- `test_parse_malformed_line_skipped` - a line with no `*` in the `source files`
  section is skipped; well-formed entries around it are still parsed.
- `test_split_sections_returns_correct_keys` - `_split_sections` on the git
  fixture returns keys `{"ini", "variables", "source files", "end"}`.
- `test_extract_repo_url_unknown_verctrl_returns_none` - `_extract_repo_url`
  with `verctrl="perforce"` and no `P4PORT` variable returns `None`.

## Success criteria

- [ ] `SrcSrvEntry` and `SrcSrvStream` frozen dataclasses defined with documented
      fields.
- [ ] `SrcSrvParser.parse` handles all three fixtures correctly.
- [ ] Malformed lines skipped without raising.
- [ ] All three fixture files created with the content above.
- [ ] All 14 unit tests above pass with zero I/O.
- [ ] `ruff check src/ tests/` - clean.
