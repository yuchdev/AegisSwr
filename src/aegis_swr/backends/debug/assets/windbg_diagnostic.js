"use strict";

// Substitution tokens replaced by WinDbgJSBackend._prepare_js() at runtime:
//   __CALLBACK_URL__          http://127.0.0.1:{ephemeral_port}/
//   __MAX_FAULTING_FRAMES__   integer (default 20)
//   __MAX_OTHER_FRAMES__      integer (default 3)

function initializeScript() {
    return [new host.apiVersionSupport(1, 9)];
}

(function () {
    var callbackUrl        = "__CALLBACK_URL__";
    var maxFaultingFrames  = __MAX_FAULTING_FRAMES__;
    var maxOtherFrames     = __MAX_OTHER_FRAMES__;

    var process = host.currentProcess;

    var result = {
        ProcessID:         0,
        ProcessName:       "",
        ExceptionCode:     "",
        ExceptionAddress:  "",
        FaultingModule:    "",
        FaultingThread:    null,
        AllThreadsSummary: []
    };

    try { result.ProcessID   = process.Id;   } catch (e) {}
    try { result.ProcessName = process.Name; } catch (e) {}

    // Exception record - guarded individually so a missing field never aborts
    // the script and never prevents the callback POST from firing.
    try {
        var exc = process.LastEvent.Attributes.Exception;
        try { result.ExceptionCode    = "0x" + exc.Code.toString(16);    } catch (e) {}
        try { result.ExceptionAddress = "0x" + exc.Address.toString(16); } catch (e) {}
    } catch (e) {}

    for (var thread of process.Threads) {
        var isFaulting = false;
        try { isFaulting = thread.Attributes.IsFaulting; } catch (e) {}

        var limit  = isFaulting ? maxFaultingFrames : maxOtherFrames;
        var frames = [];
        var idx    = 0;

        try {
            for (var frame of thread.Stack.Frames) {
                if (idx >= limit) { break; }

                var module   = "";
                var baseAddr = "0x0";
                var func     = "";
                var offset   = "0x0";

                try { module   = frame.Module.Name;                             } catch (e) {}
                try { baseAddr = "0x" + frame.Module.BaseAddress.toString(16); } catch (e) {}
                try { func     = frame.FunctionName || "";                      } catch (e) {}
                try { offset   = "0x" + frame.Offset.toString(16);             } catch (e) {}

                frames.push({
                    FrameNumber: idx,
                    Module:      module,
                    ModuleBase:  baseAddr,
                    Function:    func,
                    Offset:      offset
                });
                idx++;
            }
        } catch (e) {}

        var summary = {
            ThreadID:   0,
            IsFaulting: isFaulting,
            Frames:     frames
        };
        try { summary.ThreadID = thread.Id; } catch (e) {}

        if (isFaulting) {
            result.FaultingThread = summary;
            result.FaultingModule = (frames.length > 0) ? frames[0].Module : "";
        }
        result.AllThreadsSummary.push(summary);
    }

    var payload = JSON.stringify(result);

    // ActiveXObject("MSXML2.XMLHTTP") is the only synchronous HTTP client
    // available inside the cdb/WinDbg JavaScript engine (Chakra-based WScript
    // runtime). It is explicitly a Windows COM object; this script is
    // intentionally Windows-only (WinDbgJSBackend.SUPPORTED_PLATFORMS).
    try {
        var xhr = new ActiveXObject("MSXML2.XMLHTTP");
        xhr.open("POST", callbackUrl, false);
        xhr.setRequestHeader("Content-Type",   "application/json");
        xhr.setRequestHeader("Content-Length", payload.length.toString());
        xhr.send(payload);
    } catch (e) {
        // If the POST fails (e.g., bridge already shut down due to timeout),
        // log to the debugger output so the failure is visible in the subprocess
        // stdout captured by Python.
        host.diagnostics.debugLog("aegis-swr: callback POST failed: " + e.message + "\n");
    }
})();
