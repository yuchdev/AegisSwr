# Debug Backends

This document describes the available debugger backends in WinCrash Analyzer and how to configure them.

---

## Prerequisites

### CDB Backend

The `CDBBackend` requires **cdb.exe**, which is part of the **Debugging Tools for Windows** distributed with the Windows SDK.

**Installation steps:**

1. Download the [Windows SDK](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/).
2. During installation, select the **Debugging Tools for Windows** component.
3. After installation, `cdb.exe` is typically located at:
   - `C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe` (64-bit)
   - `C:\Program Files (x86)\Windows Kits\10\Debuggers\x86\cdb.exe` (32-bit)
4. Add the appropriate directory to your system `PATH` so that `cdb.exe` is resolvable.

---

## CDB Backend (`cdb`)

The `CDBBackend` orchestrates `cdb.exe` via a Python `subprocess` layer to extract crash information from Windows `.dmp` files.

### How It Works

1. **Path Verification** — Confirms the dump file is readable (`os.access`) before spawning the process.
2. **Command Composition** — Chains `.sympath`, `.reload /f /i`, `!analyze -v`, and `q` into a single `-c` argument.
3. **Process Spawn** — Launches `cdb.exe -z <dump> -c <cmds>` with `subprocess.run(capture_output=True)` to prevent `PIPE` deadlocks.
4. **Noise Reduction** — Strips repetitive `DBGHELP: … file not found` lines via regex before returning the output.
5. **Timeout Watchdog** — Raises `DebuggerEngineError` if `cdb.exe` runs longer than 300 seconds.

### Symbol Path and Caching

The backend automatically appends the Microsoft Public Symbol Server to whatever `symbol_path` the caller supplies:

```
<symbol_path>;srv*c:\symbols*https://msdl.microsoft.com/download/symbols
```

`c:\symbols` acts as a **downstream cache**: on the first run, `cdb.exe` downloads PDB files from
`msdl.microsoft.com` and stores them locally. Subsequent runs resolve symbols from the local cache,
significantly reducing analysis time and network usage.

To use only local symbols (e.g. in an air-gapped environment), pass the path to your local PDB store
as `symbol_path` and ensure the machine cannot reach the public symbol server. A `WARNING` will be
logged if the public server is unreachable.

### Usage

```python
from wincrash_analyzer.backends.debug.factory import create_debug_backend

backend = create_debug_backend("cdb")
result = backend.extract(
    dump_path=r"C:\CrashDumps\app_crash.dmp",
    symbol_path=r"C:\MyApp\symbols",
)
print(result)
```

### Exceptions

| Exception | Raised When |
|---|---|
| `DebuggerEngineError` | Dump file is not readable, `cdb.exe` times out, or the process exits with a non-zero code during a fatal error. |
| `DebuggerNotFoundError` | `cdb.exe` cannot be found in the system `PATH`. |

---

## JS Provider Backend (`js`)

The `JSProviderBackend` uses the WinDbg JavaScript engine for more flexible extraction. See the
WinDbg bridge documentation for details: [windbg_bridge.md](windbg_bridge.md).
