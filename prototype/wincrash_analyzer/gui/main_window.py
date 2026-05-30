from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget
from wincrash_analyzer.gui.tabs.analyze_tab import AnalyzeTab
from wincrash_analyzer.gui.tabs.export_tab import ExportTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WinCrash AI Analyzer")
        self.resize(800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.tabs = QTabWidget()
        self.tabs.addTab(AnalyzeTab(), "Analyze")
        self.tabs.addTab(ExportTab(), "Export")
        
        self.layout.addWidget(self.tabs)
