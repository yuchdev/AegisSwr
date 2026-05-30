from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QPlainTextEdit, QScrollArea
)
from wincrash_analyzer.gui.widgets.config_form import ConfigForm
from wincrash_analyzer.gui.worker import Worker
from wincrash_analyzer.config.app_config import save_config, read_config
from wincrash_analyzer.actions.export import run_export
import argparse

class ExportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        self.form_layout = QVBoxLayout(form_container)

        export_options = [
            "store", "store_config", "to_store", "to_store_config"
        ]
        
        config = read_config()
        initial_values = config.get("export", {})
        # Merge global values
        for k, v in config.items():
            if k not in ["analyze", "export"]:
                if k not in initial_values:
                    initial_values[k] = v
        
        self.form = ConfigForm(export_options, initial_values=initial_values)
        self.form_layout.addWidget(self.form)
        self.form_layout.addStretch()
        
        scroll.setWidget(form_container)
        self.layout.addWidget(scroll)
        
        self.btn_export = QPushButton("Export")
        self.btn_export.clicked.connect(self.on_export_clicked)
        self.layout.addWidget(self.btn_export)
        
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.layout.addWidget(self.output)
        
        self.worker = None

    def on_export_clicked(self):
        values = self.form.get_values()
        
        # Save config on click
        config = read_config()
        config["export"] = values
        save_config(config)
        
        self.output.clear()
        self.output.appendPlainText("Starting export...")
        self.btn_export.setEnabled(False)
        
        args = argparse.Namespace(**values)
        args.action = "export"
        
        self.worker = Worker(run_export, args)
        self.worker.signals.log.connect(self.append_log)
        self.worker.signals.error.connect(self.on_error)
        self.worker.signals.finished.connect(self.on_finished)
        self.worker.start()

    def append_log(self, text):
        self.output.appendPlainText(text)

    def on_error(self, err):
        self.output.appendPlainText(f"ERROR: {err}")

    def on_finished(self):
        self.btn_export.setEnabled(True)
        self.output.appendPlainText("Export finished.")
