# JS Provider Setup

This document explains how to configure and use the **JS Provider Backend**
(`js_provider.py`) for WinCrash Analyzer.

---

## Overview

The `JSProviderBackend` uses the **WinDbg JavaScript engine** to gather crash
data from a Windows dump file and push it to a local HTTP server instead of
parsing flat text output.  This "push" model is especially effective for
complex crashes such as stack corruption, where the raw `!analyze -v` output
may be incomplete or misleading.

---

## How It Works

1. **Server startup** — A lightweight `WinDbgServer` thread is started on
   `localhost:9999` (falls back to `9998` / `9997` if the port is busy).
2. **Script generation** — A temporary `.js` file is written to the system
   temp directory.  The file embeds the correct callback URL and symbol path.
3. **CDB spawn** — `cdb.exe` is launched with `.scriptload <file>; q`.
4. **Data push** — The JS script iterates `host.currentProcess.Threads`,
   serialises up to 100 stack frames per thread, and POSTs the JSON payload
   to the waiting server via `MSXML2.XMLHTTP`.
5. **Handshake** — The Python main thread blocks on `data_queue.get()` until
   the payload arrives or the timeout (60 s) expires.

---

## Prerequisites

### 1. Debugging Tools for Windows

`cdb.exe` must be on the system `PATH`.  It ships with the
[Windows SDK](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/).

During the SDK installer, select **Debugging Tools for Windows**.
After installation the executable is usually at:

```
C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe
```

### 2. Enabling the JavaScript Provider (`JsProvider.dll`)

Modern versions of WinDbg (WinDbg Preview and WinDbg 10+) load
`JsProvider.dll` automatically.  Older builds may require a manual load:

```
.load JsProvider.dll
```

To verify the provider is active, run the following inside the debugger:

```
.scriptproviders
```

The output should include a line similar to:

```
JavaScript  .js  (JsProvider.dll)
```

If `JsProvider.dll` is missing, install a recent version of
[WinDbg Preview](https://apps.microsoft.com/detail/9pgjgd53tn86) from the
Microsoft Store.

---

## Configuration

Symbol paths are forwarded to the JS script unchanged.  Pass the path when
calling `extract()`:

```python
from wincrash_analyzer.backends.debug.factory import create_debug_backend

backend = create_debug_backend("js")
result = backend.extract(
    dump_path=r"C:\CrashDumps\app_crash.dmp",
    symbol_path=r"C:\MyApp\symbols",
)
print(result)   # JSON string containing thread/stack data
```

Backslashes in `symbol_path` are automatically escaped for the JS string
literal, so passing a raw Windows path is safe.

---

## Exceptions

| Exception | Raised When |
|---|---|
| `DebuggerEngineError` | Dump is unreadable; `cdb.exe` times out; `JsProvider.dll` is unavailable; JS callback never arrives within 60 s. |
| `DebuggerNotFoundError` | `cdb.exe` is not found in the system `PATH`. |

---

## Object Model Reference

The diagnostic script uses the following WinDbg JS namespaces:

| Object | Description | Reference |
|---|---|---|
| `host.currentProcess` | The process being debugged | [host.currentProcess](https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/javascript-debugger-scripting#host.currentprocess) |
| `host.currentProcess.Threads` | Iterable of all threads | [Debugger.Utility.Control](https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/native-debugger-objects-in-javascript-extensions) |
| `thread.Stack.Frames` | Stack frames for a thread | [Stack object model](https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/native-debugger-objects-in-javascript-extensions-debugger-objects) |
| `host.apiVersionSupport` | Declares the minimum host API | [initializeScript()](https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/javascript-debugger-scripting#initializescript) |

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| **JS engine disabled** | `DebuggerEngineError` is raised with message *"WinDbg JS provider is unavailable"*. Fall back to the `cdb` backend. |
| **ActiveX blocked** | `MSXML2.XMLHTTP` throws inside the JS engine; the callback never arrives, triggering the 60 s timeout. |
| **Very deep stacks** | The `maxFrames = 100` guard in the JS script prevents oversized payloads. |
| **Port collision** | `WinDbgServer` tries `9999`, `9998`, and `9997` before raising `OSError`. |
