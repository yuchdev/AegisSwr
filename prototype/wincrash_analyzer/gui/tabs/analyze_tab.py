from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QPlainTextEdit, QLabel, QScrollArea
)
from PySide6.QtCore import Qt
from wincrash_analyzer.gui.widgets.config_form import ConfigForm
from wincrash_analyzer.gui.worker import Worker
from wincrash_analyzer.config.app_config import save_config, read_config
from wincrash_analyzer.actions.analyze import run_analyze
from wincrash_analyzer.core.crash_app import CrashApp
import argparse

class AnalyzeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # Scroll area for the form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        self.form_layout = QVBoxLayout(form_container)
        
        analyze_options = [
            "report_severity", "dump", "sym", "log_source", 
            "engine", "ai", "cdb_path", "analyze_history", 
            "store", "store_config", "assumption"
        ]
        
        config = read_config()
        initial_values = config.get("analyze", {})
        # Merge global values
        for k, v in config.items():
            if k not in ["analyze", "export"]:
                if k not in initial_values:
                    initial_values[k] = v
        
        self.form = ConfigForm(analyze_options, initial_values=initial_values)
        self.form_layout.addWidget(self.form)
        self.form_layout.addStretch()
        
        scroll.setWidget(form_container)
        self.layout.addWidget(scroll)
        
        self.btn_analyze = QPushButton("Analyze")
        self.btn_analyze.clicked.connect(self.on_analyze_clicked)
        self.layout.addWidget(self.btn_analyze)
        
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.layout.addWidget(self.output)
        
        self.worker = None

    def on_analyze_clicked(self):
        values = self.form.get_values()
        
        # Save config on click
        config = read_config()
        config["analyze"] = values
        config["report_severity"] = values.get("report_severity", "INFO")
        save_config(config)
        
        self.output.clear()
        self.output.appendPlainText("Starting analysis...")
        self.btn_analyze.setEnabled(False)
        
        # Create a mock args object
        args = argparse.Namespace(**values)
        args.action = "analyze"
        
        # We need to resolve CDB path like CrashApp does
        # Let's use CrashApp's logic
        app = CrashApp(argparse.ArgumentParser())
        try:
            resolved_cdb = app._check_cdb(args.cdb_path)
        except Exception as e:
            self.output.appendPlainText(f"Error: {str(e)}")
            self.btn_analyze.setEnabled(True)
            return

        self.worker = Worker(run_analyze, args, resolved_cdb)
        self.worker.signals.log.connect(self.append_log)
        self.worker.signals.error.connect(self.on_error)
        self.worker.signals.finished.connect(self.on_finished)
        self.worker.start()

    def append_log(self, text):
        self.output.appendPlainText(text)

    def on_error(self, err):
        self.output.appendPlainText(f"ERROR: {err}")

    def on_finished(self):
        self.btn_analyze.setEnabled(True)
        self.output.appendPlainText("Analysis finished.")
