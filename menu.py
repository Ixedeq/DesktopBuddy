from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QFile

class CustomMenu(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Load CSS from file
        css_file = QFile("menu.css")
        if css_file.open(QFile.ReadOnly | QFile.Text):
            self.setStyleSheet(str(css_file.readAll(), 'utf-8'))
            css_file.close()

    def addButton(self, text, callback):
        button = QPushButton(text)
        button.setFlat(True)
        button.clicked.connect(callback)
        button.clicked.connect(self.hide)
        self.layout.addWidget(button)
        return button

    def showMenu(self, pos):
        self.move(pos)
        self.show()
