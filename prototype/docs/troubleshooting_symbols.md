# Troubleshooting Symbol Files

This guide covers the most common symbol-resolution problems encountered when
analyzing Windows crash dumps with WinCrash Analyzer and how to resolve them.

---

## 1. Background: Why Symbols Matter

When a crash dump is loaded, the debugger maps raw instruction-pointer (RIP)
values to human-readable function names and line numbers using **Program
Database (PDB)** files.  Without matching symbols:

- Stack frames display as `0x00007ff6abcd1234` instead of
  `myapp!CDocumentView::Render+0x42`.
- `!analyze -v` cannot determine the faulting module.
- AI root-cause analysis receives opaque hex addresses with no semantic value,
  drastically reducing its accuracy.

---

## 2. The `srv*` Symbol Path Syntax

The symbol path tells the debugger *where* to look for PDB files.  The canonical
format understood by both `cdb.exe` and WinDbg is:

```
srv*<local-cache>*<symbol-store-URL>
```

| Component | Example | Purpose |
|-----------|---------|---------|
| `srv*` | `srv*` | Activates the symbol-server protocol |
| `<local-cache>` | `C:\symbols` | Directory where downloaded PDBs are cached |
| `<symbol-store-URL>` | `https://msdl.microsoft.com/download/symbols` | Remote symbol store |

### Full Example

```powershell
wincrash-analyzer --dump crash.dmp `
  --sym "srv*C:\symbols*https://msdl.microsoft.com/download/symbols"
```

You can chain multiple stores, which is useful when you have a private store
for your own binaries **and** need OS symbols from Microsoft:

```
srv*C:\symbols*\\symsrv\symbols*https://msdl.microsoft.com/download/symbols
```

The debugger searches the chain from left to right and caches every downloaded
PDB in `C:\symbols` so the download only happens once.

---

## 3. Handling Mismatched PDBs

### 3.1 Identifying the Error

A mismatched PDB occurs when the GUID embedded in the `.dmp` does not match the
GUID in the `.pdb` you provided.  CDB reports this as:

```
DBGHELP: myapp - mismatched pdb (in c:\symbols\myapp.pdb)
```

or `!analyze -v` shows:

```
MODULE_NAME: myapp
IMAGE_NAME:  myapp.exe
FAILURE_BUCKET_ID:  WRONG_SYMBOLS
```

### 3.2 Force-Loading with the `/i` Flag

The `.reload` command accepts `/i` to **ignore the GUID mismatch** and load
the PDB anyway.  Use this only when you have no alternative and you understand
the symbol offsets may be slightly wrong:

```
.reload /f /i myapp.exe
```

`/f` forces an immediate load (do not defer).  `/i` ignores the timestamp and
GUID mismatch.

> **Warning:** Force-loading a mismatched PDB may produce incorrect stack
> frames.  Treat any analysis with force-loaded symbols as approximate and
> reconfirm with matching symbols when possible.

### 3.3 Diagnosing the Mismatch

Run `!sym noisy` before `.reload` to see detailed symbol-search logs:

```
!sym noisy
.reload /f myapp.exe
```

Look for the `DBGHELP: myapp - mismatched pdb` line.  The log will show which
PDB was tried and why it was rejected (usually a GUID mismatch or a build-ID
difference).

---

## 4. Prepopulating the Local Cache for Air-Gapped Environments

In offline or air-gapped networks the debugger cannot reach
`https://msdl.microsoft.com`.  Prepopulate `C:\symbols` before disconnecting:

### 4.1 Using `symchk.exe`

`symchk.exe` ships with the Windows SDK (same location as `cdb.exe`):

```powershell
symchk.exe /r "C:\Builds\Release\*.exe" `
  /s "srv*C:\symbols*https://msdl.microsoft.com/download/symbols"
```

This recursively downloads every PDB that matches the binaries in
`C:\Builds\Release`.

### 4.2 Copying the Cache to the Air-Gapped Machine

Once the cache is populated, copy the entire `C:\symbols` tree to the offline
machine.  Set the symbol path to the local directory only:

```powershell
wincrash-analyzer --dump crash.dmp --sym "C:\symbols"
```

### 4.3 Symbol Path Priority

WinCrash Analyzer passes the `--sym` argument verbatim to cdb.exe as
`_NT_SYMBOL_PATH`.  You can also set this environment variable globally:

```powershell
$env:_NT_SYMBOL_PATH = "srv*C:\symbols*https://msdl.microsoft.com/download/symbols"
wincrash-analyzer --dump crash.dmp --sym $env:_NT_SYMBOL_PATH
```

---

## 5. Common Errors and Fixes

| Error Message | Root Cause | Fix |
|---------------|-----------|-----|
| `DBGHELP: myapp - mismatched pdb` | PDB GUID does not match `.dmp` | Use `.reload /f /i` or obtain the correct PDB |
| `DBGHELP: myapp - no symbols loaded` | PDB not found anywhere on symbol path | Extend `--sym` path; verify `C:\symbols` cache |
| `FAILURE_BUCKET_ID: WRONG_SYMBOLS` | `!analyze -v` detected wrong symbols | Reload with correct PDB |
| `0x00000000 (no symbol)` in stack | PDB completely absent | Provide matching PDB or symbol server URL |
| Symbol download stalls | Firewall blocks `msdl.microsoft.com` | Prepopulate cache; use internal proxy server |

---

## 6. Updating the Symbol Cache

Over time, PDBs in `C:\symbols` may become stale if you ship new builds.
To refresh:

```powershell
# Delete the cached PDB for a specific module
Remove-Item "C:\symbols\myapp.pdb\*" -Recurse -Force

# Re-run the analyzer – it will re-download the fresh PDB
wincrash-analyzer --dump new_crash.dmp --sym "srv*C:\symbols*https://msdl.microsoft.com/download/symbols"
```

---

## 7. Further Reading

- [Microsoft Symbol Server documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/symbol-stores-and-symbol-servers)
- [`.reload` command reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/debuggercmds/-reload--reload-module-)
- [symchk.exe reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/symchk)
