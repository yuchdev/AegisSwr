"""Windows CDB debug backend.

Wraps ``cdb.exe`` (Debugging Tools for Windows). Regexes are ported from the
WinCrashAnalyzer prototype (see docs/prototype-analysis-specs/PROMPT_HEURISTICS.md
§4 and WIN_DEPENDENCIES.md §8).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import ClassVar, Optional

from loguru import logger

from aegis_swr.backends.debug.base import _BaseDebugBackend, normalize_address
from aegis_swr.backends.debug.symbol_path import resolve_symbol_path
from aegis_swr.core.fault_codes import map_windows_ntstatus
from aegis_swr.core.schemas import DebugExtractionResult, DumpFormat, IncidentSource, StackFrame

_DEFAULT_SYMBOL_SERVER = "https://msdl.microsoft.com/download/symbols"

# !analyze -v reports the fault code under several different keys depending on
# the crash. Try them in priority order; the prototype only matched the first,
# which silently yielded 0x0 (→ FaultClass.UNKNOWN) for NULL_POINTER_WRITE dumps
# that use ERROR_CODE / EXCEPTION_CODE_STR instead.
_EXC_CODE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"EXCEPTION_CODE:\s+\((?:NTSTATUS|HRESULT)\)\s+(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"ERROR_CODE:\s+\((?:NTSTATUS|HRESULT)\)\s+(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"EXCEPTION_CODE_STR:\s+([0-9a-fA-F]{8})\b", re.IGNORECASE),
    re.compile(r"ExceptionCode:\s+([0-9a-fA-F]{8})\b", re.IGNORECASE),
)
_EXC_ADDR_RE = re.compile(r"ExceptionAddress:\s+([0-9a-fA-F`]+)", re.IGNORECASE)


def _extract_exception_code(raw: str) -> str:
    """Return the fault code as ``0x``-prefixed lowercase hex, or ``0x0``"""
    for pattern in _EXC_CODE_RES:
        match = pattern.search(raw)
        if match:
            token = match.group(1).lower()
            return token if token.startswith("0x") else f"0x{token}"
    return "0x0"


_MODULE_RE = re.compile(r"MODULE_NAME:\s+(\S+)")
_TIMESTAMP_RE = re.compile(r"Debug session time:\s+(.*?)\s+\(UTC")
# Optional trailing source annotation: " [c:\src\file.cpp @ 142]".
_SOURCE_RE = re.compile(r"\[(?P<file>.+?)\s+@\s+(?P<line>\d+)\]\s*$")
# A debugger address column: hex digits, optional 0x prefix, optional `64-bit`
# backtick separator (e.g. ``00007ff7`2a7359c9`` or ``0xCCCCCCCC``).
_HEXLIKE_RE = re.compile(r"^(?:0x)?[0-9a-fA-F`]+$")


def _looks_like_address(token: str) -> bool:
    """Return True when *token* looks like a hex debugger address column."""
    return bool(_HEXLIKE_RE.match(token)) and any(c in "0123456789abcdefABCDEF" for c in token)


def _parse_callsite(symbol: str) -> tuple[Optional[str], Optional[str]]:
    """Split a CDB call-site token into (module, function)"""
    if symbol.startswith("0x") or symbol.startswith("<"):
        return None, None
    if "!" in symbol:
        module, func_part = symbol.split("!", 1)
        function = func_part.split("+", 1)[0]
        return module, function
    if "+" in symbol:
        return symbol.split("+", 1)[0], None  # module known, function unresolved
    return symbol, None


def _normalize_symbol(symbol: str) -> str:
    """Collapse internal whitespace in a call-site *symbol* for stable matching.

    STACK_TEXT and ``k`` rows print the same symbol but may differ in the runs of
    whitespace around templated argument lists, so both sides are normalised to
    single spaces before they are used as a merge key.

    :param symbol: a raw call-site token (e.g. ``mod!Type::method+0x509``).
    :return: the symbol with each internal whitespace run collapsed to one space.
    """
    return " ".join(symbol.split())


def _parse_k_frames(raw: str) -> list[tuple[StackFrame, str]]:
    """Parse the ``.ecxr; k`` stack block into ``(frame, callsite-key)`` pairs.

    The ``k`` block is the only CDB output that carries ``[file @ line]`` source
    annotations, so it is parsed separately from ``!analyze -v`` STACK_TEXT. Its
    rows look like::

        Child-SP          RetAddr               Call Site
        000000f6`b28fe850 00007ff6`74634087     CrashUi!Sym+0x509 [C:\\src\\f.cpp @ 121]

    The block is located by its ``Child-SP ... Call Site`` header; crucially the
    STACK_TEXT header contains ``" : "`` argument columns and is excluded on that
    basis. Parsing stops at the first blank line or the first row that lacks the
    two leading address columns (i.e. the trailing command echo/prompt).

    Inline-function rows (``(Inline Function) --------`--------  ...``) carry no
    physical return address and are **skipped by design**: they have no matching
    STACK_TEXT return-address frame, so keeping them would desynchronise the two
    lists and risk pinning a source line onto the wrong frame.

    :param raw: the full combined CDB output.
    :return: a list of ``(StackFrame, normalised-callsite)`` pairs in stack order;
        empty when no ``k`` block is present.
    """
    lines = raw.splitlines()
    header_idx = -1
    for idx, line in enumerate(lines):
        if "Child-SP" in line and "Call Site" in line and " : " not in line:
            header_idx = idx
            break
    if header_idx < 0:
        return []

    results: list[tuple[StackFrame, str]] = []
    number = 0
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if not stripped:
            break
        if stripped.startswith("(Inline Function)"):
            continue  # documented: inline pseudo-frames are skipped

        source_file: Optional[str] = None
        source_line: Optional[int] = None
        src = _SOURCE_RE.search(stripped)
        if src:
            source_file = src.group("file")
            source_line = int(src.group("line"))
            stripped = stripped[: src.start()].strip()

        tokens = stripped.split()
        if len(tokens) < 3 or not _looks_like_address(tokens[0]) or not _looks_like_address(tokens[1]):
            break  # end of the k block (command echo, prompt, or non-frame line)

        callsite = " ".join(tokens[2:])
        module, function = _parse_callsite(callsite)
        frame = StackFrame(
            frame_number=number,
            module=module,
            function=function,
            source_file=source_file,
            source_line=source_line,
            instruction_address=normalize_address(tokens[1]),
        )
        results.append((frame, _normalize_symbol(callsite)))
        number += 1
    return results


def parse_cdb_frames(raw: str) -> list[StackFrame]:
    """Parse CDB output into StackFrames, merging two complementary blocks.

    Two blocks in the debugger output describe the stack, each with a different
    strength, and this function combines them:

    * ``!analyze -v`` **STACK_TEXT** - ``<child-sp> <ret-addr> : <args…> : <CallSite>``
      with backtick-split 64-bit addresses and colon-delimited argument columns.
      This is the reliable, always-present frame list, but it *never* carries a
      ``[file @ line]`` annotation.
    * ``.ecxr; k`` - the faulting-context stack walk, whose rows *do* carry
      ``[file @ line]`` annotations (see :func:`_parse_k_frames`).

    **Merge rule.** STACK_TEXT is treated as the canonical, ordered frame list so
    the returned count is stable and never duplicated. The ``k`` block is parsed
    only to build a lookup keyed by the exact normalised call-site symbol
    (module + function + ``+0x`` offset); each STACK_TEXT frame that has no inline
    annotation of its own is then enriched with the ``source_file``/``source_line``
    of the matching ``k`` row. Because the key is the full symbol-plus-offset
    token, a frame is only ever annotated with its own source location.

    If STACK_TEXT is absent or empty (some dumps emit only the ``k`` block), the
    parsed ``k`` frames are returned directly so frames are still produced. A line
    that already carries an inline annotation inside STACK_TEXT keeps it.

    :param raw: the full combined CDB output (``.lines``/``!analyze -v``/``k``).
    :return: the merged, source-enriched list of stack frames in stack order.
    """
    k_frames = _parse_k_frames(raw)
    annotations: dict[str, tuple[str, int]] = {
        key: (frame.source_file, frame.source_line)
        for frame, key in k_frames
        if frame.source_file is not None and frame.source_line is not None
    }

    frames: list[StackFrame] = []
    in_stack = False
    number = 0
    for line in raw.splitlines():
        if "STACK_TEXT:" in line:
            in_stack = True
            continue
        if not in_stack:
            continue
        stripped = line.strip()
        if not stripped:
            break

        source_file: Optional[str] = None
        source_line: Optional[int] = None
        src = _SOURCE_RE.search(stripped)
        if src:
            source_file = src.group("file")
            source_line = int(src.group("line"))
            stripped = stripped[: src.start()].strip()

        if " : " in stripped:
            segments = stripped.split(" : ")
            callsite = segments[-1].strip()
            addr_tokens = segments[0].split()
        else:
            tokens = stripped.split()
            if len(tokens) < 2:
                continue
            callsite = tokens[-1]
            addr_tokens = tokens[:-1]

        ret_candidates = [t for t in addr_tokens if _looks_like_address(t)]
        if not ret_candidates or not callsite:
            continue  # column header or non-frame line

        if source_file is None:
            annotated = annotations.get(_normalize_symbol(callsite))
            if annotated is not None:
                source_file, source_line = annotated

        module, function = _parse_callsite(callsite)
        frames.append(
            StackFrame(
                frame_number=number,
                module=module,
                function=function,
                source_file=source_file,
                source_line=source_line,
                instruction_address=normalize_address(ret_candidates[-1]),
            )
        )
        number += 1

    if not frames:
        # STACK_TEXT absent/empty: fall back to the annotated k block directly.
        return [frame for frame, _ in k_frames]
    return frames


class CdbBackend(_BaseDebugBackend):
    """Debug backend that extracts crash data from Windows minidumps via ``cdb.exe``."""

    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]] = [DumpFormat.WINDOWS_MINIDUMP]
    SUPPORTED_PLATFORMS: ClassVar[list[str]] = ["Windows"]

    def _symbol_path_string(self, symbol_paths: list[str]) -> str:
        """Build the CDB symbol-path string from the cache, server, and extra paths."""
        cache = resolve_symbol_path(self._settings.symbol_cache)
        server = self._settings.symbol_server_url or _DEFAULT_SYMBOL_SERVER
        parts = [f"srv*{cache}*{server}", *symbol_paths]
        return ";".join(parts)

    def _build_command_sequence(
        self,
        source: IncidentSource,
        symbol_path: list[str],
    ) -> list[str]:
        """Build the ``cdb.exe`` argv that reloads symbols and dumps annotated frames.

        The command chain does three distinct jobs:

        * ``.lines -e`` enables source line-number loading so subsequent stack
          walks can emit ``[file @ line]`` annotations.
        * ``.reload /f /i; !analyze -v`` forces a full symbol reload and produces
          the reliable STACK_TEXT frame list plus bucket/exception metadata
          (still consumed by :meth:`_parse`). STACK_TEXT never carries source
          annotations, no matter the switches.
        * ``.ecxr; k`` sets the register context to the exception record and walks
          the *faulting* stack; unlike STACK_TEXT this ``k`` block carries the
          ``[file @ line]`` annotations that :func:`parse_cdb_frames` merges back
          onto the STACK_TEXT frames.

        :param source: the incident source carrying the dump to analyse.
        :param symbol_path: extra symbol search paths appended to the SRV chain.
        :return: the ``cdb.exe`` argv to execute.
        """
        return [
            "cdb.exe",
            "-z",
            str(source.dump_path),
            "-y",
            self._symbol_path_string(symbol_path),
            "-c",
            ".lines -e; .reload /f /i; !analyze -v; .ecxr; k; q",
        ]

    def _parse(self, raw: str, source: IncidentSource) -> DebugExtractionResult:
        """Map the NTSTATUS code, fault address, and frames into a structured result."""
        exception_code = _extract_exception_code(raw)
        fault_class = map_windows_ntstatus(exception_code)

        frames = parse_cdb_frames(raw)

        addr_match = _EXC_ADDR_RE.search(raw)
        if addr_match:
            exception_address = normalize_address(addr_match.group(1))
        elif frames:
            exception_address = frames[0].instruction_address
        else:
            exception_address = "0x0"

        module_match = _MODULE_RE.search(raw)
        faulting_module = module_match.group(1) if module_match else None
        if faulting_module is None and frames:
            faulting_module = frames[0].module
        faulting_function = frames[0].function if frames else None

        return DebugExtractionResult(
            fault_class=fault_class,
            exception_code_raw=exception_code,
            exception_address=exception_address,
            faulting_module=faulting_module,
            faulting_function=faulting_function,
            stack_frames=frames,
            debug_timestamp=self._parse_timestamp(raw),
            symbol_resolution_score=self._symbol_score(frames),
            raw_text_excerpt=self._excerpt(raw),
        )

    @staticmethod
    def _parse_timestamp(raw: str) -> Optional[datetime]:
        """Parse the CDB ``Debug session time`` into a datetime, or ``None``."""
        match = _TIMESTAMP_RE.search(raw)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1).strip(), "%a %b %d %H:%M:%S.%f %Y")
        except ValueError:
            logger.debug("CdbBackend._parse_timestamp: unrecognised timestamp format; using None")
            return None
