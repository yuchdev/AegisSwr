"use strict";

function initializeScript() {
    return [new host.apiVersionSupport(1, 9)];
}

(function () {
    var callbackUrl = "http://127.0.0.1:9999/";
    var maxFrames = 100;

    var process = host.currentProcess;
    var result = {
        ProcessID: process.Id,
        ProcessName: process.Name,
        ExceptionCode: "",
        Threads: []
    };

    for (var thread of process.Threads) {
        var threadObj = {
            ThreadID: thread.Id,
            Attributes: { IsFaulting: false, Priority: 0 },
            StackFrames: []
        };
        var frameIdx = 0;
        for (var frame of thread.Stack.Frames) {
            if (frameIdx >= maxFrames) { break; }
            threadObj.StackFrames.push({
                FrameNumber: frameIdx,
                Module: frame.Module ? frame.Module.Name : "Unknown",
                Function: frame.FunctionName || "Unknown",
                Offset: "0x" + frame.Offset.toString(16)
            });
            frameIdx++;
        }
        result.Threads.push(threadObj);
    }

    var payload = JSON.stringify(result);
    var xhr = new ActiveXObject("MSXML2.XMLHTTP");
    xhr.open("POST", callbackUrl, false);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("Content-Length", payload.length.toString());
    xhr.send(payload);
})();
