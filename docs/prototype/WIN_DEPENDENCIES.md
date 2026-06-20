# Windows-Specific Dependency Register & Cross-Platform Replacement Strategies

---

## 1. Debugger Executable: `cdb.exe`

| Attribute | Detail |
|-----------|--------|
| **Files** | `backends/debug/cdb.py:26`, `backends/debug/js_provider.py:146`, `core/crash_app.py:89–130` |
| **Nature** | External CLI binary - part of "Debugging Tools for Windows" (WinDbg package). Invoked via `subprocess.run` to open `.dmp` files and execute debugger commands. |
| **Hardcoded values** | Default path `"cdb.exe"` (assumes PATH); watchdog timeout `300 s` (`cdb.py:34`) |

### Cross-Platform Replacement Strategy

Introduce an **abstract `DebugBackend` interface** (already exists at `backends/debug/base.py`) and add platform-detected concrete implementations:

| Platform | Replacement Binary | Notes |
|----------|--------------------|-------|
| Windows | `cdb.exe` / `WinDbg` | Current; keep as-is |
| Linux | `gdb` + `minidump-2-core` + `coredumpctl` | Minidump → core file, then GDB |
| macOS | `lldb` + `minidump` LLDB plugin | Apple LLDB reads minidumps natively since LLDB 14 |
| Cross-platform | `minidump-stackwalk` (Breakpad/Crashpad) | Parses Breakpad `.dmp` format without a live debugger |

Factory function in `backends/debug/__init__.py` selects implementation via `platform.system()`.

---

## 2. Symbol Cache Path: `c:\symbols`

| Attribute | Detail |
|-----------|--------|
| **File** | `backends/debug/cdb.py:36`, `cdb.py:54` |
| **Nature** | Hardcoded Windows-format path string used to build the symbol server chain: `srv*c:\symbols*https://msdl.microsoft.com/download/symbols` |

### Cross-Platform Replacement Strategy

- Replace with `pathlib.Path` resolved to a platform-appropriate cache directory:
  - Windows: `%LOCALAPPDATA%\AegisSWR\symbols`
  - Linux/macOS: `~/.cache/aegis-swr/symbols`
- Symbol server URL (`msdl.microsoft.com`) is already Windows-specific - on other platforms, use LLDB/GDB's own symbol server protocol or Breakpad symbol files.
- Extract `WINCRASH_SYMBOL_CACHE` env var override into a universal `AEGIS_SYMBOL_CACHE` variable.

---

## 3. Windows Minidump Format (`.dmp`)

| Attribute | Detail |
|-----------|--------|
| **File** | `cli.py:22–26`, `cdb.py:48–49`, `js_provider.py:121–122` |
| **Nature** | Input validation asserts `.dmp` extension; all file-open logic assumes Windows minidump binary format. |

### Cross-Platform Replacement Strategy

- Broaden `SourceCollection` (`core/data_sources.py`) to accept multiple dump formats: `.dmp` (Windows minidump), `.core` (Linux ELF core), `.ips`/`.crash` (Apple crashreport), `.rpt` (Breakpad).
- Format detection by magic bytes rather than extension.
- Each `DebugBackend` implementation declares `SUPPORTED_FORMATS: list[str]` - the factory checks compatibility.

---

## 4. Windows COM Object: `ActiveXObject("MSXML2.XMLHTTP")`

| Attribute | Detail |
|-----------|--------|
| **File** | `backends/debug/js_provider.py:66` |
| **Nature** | The JavaScript diagnostic template embedded in `_JS_TEMPLATE` uses a Windows COM automation object to POST data back to the local HTTP bridge. This is executable only inside WinDbg's JavaScript engine on Windows. |

### Cross-Platform Replacement Strategy

- The entire `js_provider.py` backend is **WinDbg-specific** and should be **scoped to Windows only** with a capability flag: `capability = "windbg_js_engine"`.
- On non-Windows platforms, the factory must not register this backend.
- For equivalent scriptable debugger extensions:
  - Linux: GDB Python API (`gdb.execute()`, `gdb.parse_and_eval()`)
  - LLDB: LLDB Python scripting (`lldb.SBDebugger`, `lldb.SBProcess`)
  - Both use native Python IPC rather than COM HTTP callbacks.

---

## 5. WinDbg Debugger Data Model

| Attribute | Detail |
|-----------|--------|
| **File** | `backends/debug/js_provider.py:38–40` |
| **Nature** | The JS template queries `host.currentSession`, `process.LastEvent.Attributes.Exception`, and `host.namespace.Debugger.Sessions` - these are WinDbg Debugger Data Model (DDM) objects. |

### Cross-Platform Replacement Strategy

- No direct equivalent on Linux/macOS.
- GDB replacement: `gdb.selected_inferior()`, `gdb.Frame`, signal/exception via `/proc/<pid>/status`.
- LLDB replacement: `process.GetExitStatus()`, `thread.GetStopReason()`, `frame.GetPC()`.
- Abstract the data model query behind a `DebugSession` value object that each backend implementation populates.

---

## 6. Windows SEH / NTSTATUS Exception Codes

| Attribute | Detail |
|-----------|--------|
| **File** | `backends/debug/cdb.py:133`, `backends/ai/gemini.py:11`, test assets |
| **Nature** | Regex `r"EXCEPTION_CODE:\s+\((?:NTSTATUS|HRESULT)\)\s+(0x[0-9a-fA-F]+)"` parses Windows-format exception records. System prompt example hardcodes `0xc0000005`. |

### Cross-Platform Replacement Strategy

Build a **platform-agnostic fault dictionary** (`core/fault_codes.py`):

```
Windows NTSTATUS  0xC0000005  → FaultClass.MEMORY_ACCESS_VIOLATION
Linux signal      SIGSEGV(11) → FaultClass.MEMORY_ACCESS_VIOLATION
macOS exception   EXC_BAD_ACCESS(1) → FaultClass.MEMORY_ACCESS_VIOLATION
```

Each `DebugBackend` maps its native fault indicator to a `FaultClass` enum. The AI backend and prompts use `FaultClass` values - never raw hex or OS signal numbers.

---

## 7. Local HTTP Bridge for WinDbg: `windbg_server.py`

| Attribute | Detail |
|-----------|--------|
| **File** | `core/windbg_server.py:84–109` |
| **Nature** | A local TCP socket server on ports `9999/9998/9997` that receives JSON callbacks from the WinDbg JS script over HTTP. Windows-only because the JS script (point 4 above) is Windows-only. |

### Cross-Platform Replacement Strategy

- On GDB/LLDB-based platforms, use their native Python API directly - no HTTP bridge needed. Data is returned synchronously via Python calls.
- If a bridge pattern is still useful (e.g., for isolation), use Unix domain sockets (Linux/macOS) or named pipes (Windows) instead of TCP, to avoid firewall / port collision issues.

---

## 8. CDB Subprocess Command Sequence

| Attribute | Detail |
|-----------|--------|
| **File** | `backends/debug/cdb.py:58–63` |
| **Nature** | Hardcoded CDB command string: `.sympath+...; .reload /f /i; !analyze -v; q`. These are CDB/WinDbg-specific debugger commands. |

### Cross-Platform Replacement Strategy

Each `DebugBackend` implementation defines its own `_build_command_sequence()` method:

| Backend | Command Sequence |
|---------|-----------------|
| `CdbBackend` | `.sympath+…; .reload /f /i; !analyze -v; q` |
| `GdbBackend` | `core-file …; bt full; info registers; quit` |
| `LldbBackend` | `target create --core …; bt all; register read; quit` |
| `MinidumpStackwalkBackend` | CLI flags only; no interactive command sequence |

---

## 9. Summary: Windows-Only Surface Area

| Component | Scope | Abstraction Effort |
|-----------|-------|--------------------|
| `cdb.exe` invocation | `backends/debug/cdb.py` | Medium - implement `GdbBackend`, `LldbBackend`; update factory |
| `c:\symbols` path | `cdb.py`, `config/` | Low - `pathlib` + env var |
| `.dmp` extension check | `cli.py`, `data_sources.py` | Low - magic-byte format detection |
| `ActiveXObject` COM | `js_provider.py` | Low - scope backend to Windows; provide GDB/LLDB Python equivalents |
| WinDbg DDM queries | `js_provider.py` | High - requires per-platform native API integration |
| NTSTATUS hex codes | `cdb.py`, prompts, test assets | Low - centralized `FaultClass` enum |
| TCP HTTP bridge | `windbg_server.py` | Medium - only needed on Windows; replace with direct Python API elsewhere |
| CDB command sequences | `cdb.py` | Medium - per-backend `_build_command_sequence()` |
