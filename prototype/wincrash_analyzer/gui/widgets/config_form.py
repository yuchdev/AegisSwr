from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QCheckBox, QComboBox, QSpinBox, 
    QLabel, QPushButton, QHBoxLayout, QFileDialog
)
from PySide6.QtCore import Qt
from wincrash_analyzer.config.app_config import get_option, ConfigOption

class ConfigForm(QWidget):
    def __init__(self, option_ids: list[str], initial_values: dict = None, parent=None):
        super().__init__(parent)
        self.option_ids = option_ids
        self.widgets = {}
        self.initial_values = initial_values or {}
        self.layout = QFormLayout(self)
        self.init_ui()

    def init_ui(self):
        for opt_id in self.option_ids:
            option = get_option(opt_id)
            if not option:
                continue

            widget = self._create_widget(option)
            self.widgets[opt_id] = widget
            
            label = QLabel(option.readable_name)
            label.setToolTip(option.help)
            
            # Handle path fields with a browse button
            if self._is_path_option(option):
                container = QWidget()
                hbox = QHBoxLayout(container)
                hbox.setContentsMargins(0, 0, 0, 0)
                hbox.addWidget(widget)
                browse_btn = QPushButton("Browse...")
                browse_btn.clicked.connect(lambda checked=False, o=option, w=widget: self._browse_path(o, w))
                hbox.addWidget(browse_btn)
                self.layout.addRow(label, container)
            else:
                self.layout.addRow(label, widget)

    def _is_path_option(self, option: ConfigOption) -> bool:
        path_keywords = ["path", "dump", "sym", "source", "config"]
        return any(kw in option.id.lower() for kw in path_keywords) and option.options is None

    def _create_widget(self, option: ConfigOption) -> QWidget:
        value = self.initial_values.get(option.id, option.default)
        
        if option.options:
            widget = QComboBox()
            for val, name in option.options.items():
                widget.addItem(name, val)
            
            index = widget.findData(value)
            if index >= 0:
                widget.setCurrentIndex(index)
            return widget
        
        if option.type == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(value))
            return widget
        
        if option.type == "int":
            widget = QSpinBox()
            widget.setRange(0, 65535)
            if value is not None:
                widget.setValue(int(value))
            return widget
        
        # Default to LineEdit for str or unknown
        widget = QLineEdit()
        if value is not None:
            widget.setText(str(value))
        return widget

    def _browse_path(self, option: ConfigOption, widget: QLineEdit):
        if "dump" in option.id.lower():
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Dump File", "", "Dump Files (*.dmp);;All Files (*)")
        elif "sym" in option.id.lower() or "source" in option.id.lower() or "config" in option.id.lower():
            # For symbols or logs, it might be a directory or file. 
            # Given the help text, sym is symbol path, log_source is file or directory.
            file_path = QFileDialog.getExistingDirectory(self, f"Select {option.readable_name}")
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, f"Select {option.readable_name}")
            
        if file_path:
            widget.setText(file_path)

    def get_values(self) -> dict:
        values = {}
        for opt_id, widget in self.widgets.items():
            if isinstance(widget, QComboBox):
                values[opt_id] = widget.currentData()
            elif isinstance(widget, QCheckBox):
                values[opt_id] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                values[opt_id] = widget.value()
            elif isinstance(widget, QLineEdit):
                val = widget.text()
                values[opt_id] = val if val else None
        return values
