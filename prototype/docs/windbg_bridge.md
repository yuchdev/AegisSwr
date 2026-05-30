# WinDbg JS-to-Python Bridge

This document describes how the `windbg_server` module acts as a "data sink"
for WinDbg's JavaScript engine and how to troubleshoot common issues.

---

## 1. Architecture Overview

```
┌─────────────────────┐          HTTP POST           ┌──────────────────────────┐
│  WinDbg JS engine   │  ──────────────────────────► │  JSCallbackHandler       │
│  (ActiveXObject /   │   http://127.0.0.1:9999      │  (background thread)     │
│   MSXML2.XMLHTTP)   │                               └────────────┬─────────────┘
└─────────────────────┘                                            │ queue.put()
                                                                   ▼
                                                       ┌──────────────────────┐
                                                       │  JSCallbackHandler   │
                                                       │  .data_queue         │
                                                       └────────────┬─────────┘
                                                                    │ queue.get()
                                                                    ▼
                                                       ┌──────────────────────┐
                                                       │  CrashOrchestrator   │
                                                       │  (main thread)       │
                                                       └──────────────────────┘
```

1. The **Orchestrator** calls `start_listening(port)` which binds
   `127.0.0.1:<port>` and spawns a **daemon thread** running
   `HTTPServer.serve_forever()`.
2. A **WinDbg JavaScript script** (loaded via `.scriptload`) instantiates an
   `MSXML2.XMLHTTP` ActiveX object and POSTs the serialised debugger state to
   the listening port.
3. `JSCallbackHandler.do_POST()` reads the body, validates it as JSON, and
   pushes it onto `JSCallbackHandler.data_queue`.
4. The Orchestrator calls `data_queue.get(timeout=<seconds>)` to retrieve the
   payload, then calls `httpd.shutdown()` + `httpd.server_close()` to free the
   port.

---

## 2. JS-to-Python Handshake

### 2.1 Required HTTP Headers

The WinDbg JS script must send the following headers with every POST request:

| Header           | Required Value              | Notes                          |
|------------------|-----------------------------|--------------------------------|
| `Content-Length` | byte length of the body     | Absent → server returns 400    |
| `Content-Type`   | `application/json`          | Recommended; not strictly enforced |

### 2.2 Minimal WinDbg JavaScript Snippet

```javascript
// windbg_callback.js  –  load with: .scriptload windbg_callback.js
function sendCrashData(port) {
    var payload = JSON.stringify({
        ProcessID:   host.currentProcess.Id,
        ProcessName: host.currentProcess.Name,
        Threads:     []   // populate from host.currentProcess.Threads
    });

    var xhr = new ActiveXObject("MSXML2.XMLHTTP");
    xhr.open("POST", "http://127.0.0.1:" + port, false /*synchronous*/);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("Content-Length", payload.length);
    xhr.send(payload);
}
```

> **Note:** `MSXML2.XMLHTTP` performs a *synchronous* request by passing
> `false` as the third argument to `open()`.  This blocks the WinDbg script
> thread until the server acknowledges the data; this is intentional so the
> script does not exit before the data is delivered.

---

## 3. Server Lifecycle

| State        | Description                                              |
|--------------|----------------------------------------------------------|
| `STARTING`   | `start_listening()` is called; daemon thread is spawned. |
| `LISTENING`  | Server is bound and waiting for the first POST.          |
| `CAPTURING`  | A POST arrives; body is read and enqueued.               |
| `TERMINATING`| `httpd.shutdown()` + `httpd.server_close()` are called.  |

The server implements a **one-shot** pattern: it is designed to receive a
single payload and then be shut down by the Orchestrator.

---

## 4. Port Fallback

If the preferred port (default **9999**) is already in use, `start_listening`
automatically attempts **9998** and then **9997** before raising `OSError`.
When a fallback port is used, pass the actual bound port to the JS script:

```python
httpd, data_queue = start_listening(9999)
actual_port = httpd.server_address[1]   # may differ from 9999
```

---

## 5. Troubleshooting Port 9999

### 5.1 Identify the blocking process (Windows)

```cmd
netstat -ano | findstr :9999
```

The last column is the **PID**.  Kill it with:

```cmd
taskkill /PID <PID> /F
```

### 5.2 Identify the blocking process (Linux / WSL)

```bash
ss -tlnp | grep 9999
# or
lsof -i :9999
```

### 5.3 Enterprise firewall / loopback exemptions

`cdb.exe` and `windbg.exe` communicate over the loopback adapter
(`127.0.0.1`).  If an enterprise firewall blocks loopback traffic, add an
exemption for:

* **Direction:** outbound from the WinDbg process
* **Destination:** `127.0.0.1`
* **Port range:** `9997–9999` (TCP)

---

## 6. Large-Payload Handling

For payloads larger than **10 MB** the handler automatically reads the body
in 10 MB chunks to avoid allocating the entire buffer at once.  The server
accepts payloads up to the value declared in `Content-Length` (no hard upper
limit is enforced in code; the practical limit is available system memory).

---

## 7. Security Considerations

* The server binds to `127.0.0.1` only and is never exposed on public
  interfaces.
* Only `POST` requests are accepted; all other verbs are handled by the
  default `BaseHTTPRequestHandler` implementation (405 Method Not Allowed).
* The server must be shut down (`httpd.shutdown()` + `httpd.server_close()`)
  as soon as the data has been consumed to minimise the window during which
  the port is open.
