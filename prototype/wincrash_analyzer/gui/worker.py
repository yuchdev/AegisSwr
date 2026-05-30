import sys
import logging
from PySide6.QtCore import QThread, Signal, QObject

class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    log = Signal(str)

class GuiLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

class StdoutRedirector:
    def __init__(self, signal):
        self.signal = signal

    def write(self, text):
        if text.strip():
            self.signal.emit(text.strip())

    def flush(self):
        pass

class Worker(QThread):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        # Setup logging redirection for this thread
        handler = GuiLogHandler(self.signals.log)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(handler)
        
        # Redirect stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StdoutRedirector(self.signals.log)
        sys.stderr = StdoutRedirector(self.signals.log)
        
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            logging.getLogger().removeHandler(handler)
            self.signals.finished.emit()
