import sys
import os
from PyQt5.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout, QPushButton, QMenu
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QFile
import objc
from Cocoa import (
    NSApplication,
    NSApp,
    NSFloatingWindowLevel,
    NSApplicationActivationPolicyAccessory,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
)
from Quartz import CGWindowLevelForKey, kCGMaximumWindowLevelKey

class DesktopBuddy(QLabel):
    def __init__(self, image_path, scale=1.0):
        super().__init__()
        self.scale = scale

        # Load and optionally scale image
        pixmap = QPixmap(image_path)
        if scale != 1.0:
            pixmap = pixmap.scaled(
                int(pixmap.width() * scale),
                int(pixmap.height() * scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        self.setPixmap(pixmap)

        # Window setup: frameless, translucent, and request top-most behavior
        # Use a normal top-level window (not a Qt.Tool) so it stays visible when other apps are active.
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Show without taking focus so clicking elsewhere doesn't hide it
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # Don't accept focus from mouse/keyboard
        self.setFocusPolicy(Qt.NoFocus)

        self._drag_pos = None
        self.show()

        # macOS specific: make always-on-top even above fullscreen apps
        self._make_always_on_top_macos()

    def _make_always_on_top_macos(self):
        # Make the app dockless / background (accessory)
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # Prefer the system maximum window level so the window appears above fullscreen apps
        try:
            max_level = CGWindowLevelForKey(kCGMaximumWindowLevelKey)
        except Exception:
            max_level = NSFloatingWindowLevel

        from ctypes import c_void_p

        # Get the NSWindow for this PyQt window
        nsview = objc.objc_object(c_void_p=int(self.winId()))
        nswindow = nsview.window()

        # Allow showing on all Spaces and mark as full-screen auxiliary so it can appear above fullscreen windows
        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        nswindow.setCollectionBehavior_(behavior)

        # Set window level to maximum (or fallback)
        try:
            nswindow.setLevel_(max_level)
        except Exception:
            nswindow.setLevel_(NSFloatingWindowLevel)

        # Force front ordering
        try:
            nswindow.orderFrontRegardless()
        except Exception:
            nswindow.makeKeyAndOrderFront_(None)

        # Raise and activate the Qt window as well
        self.raise_()
        self.activateWindow()

    # Dragging handlers
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        css_file = QFile("menu.css")
        if css_file.open(QFile.ReadOnly | QFile.Text):
            menu.setStyleSheet(str(css_file.readAll(), 'utf-8'))
            css_file.close()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.close_app)
        settings_menu = menu.addMenu("Settings")
        characters = [f for f in os.listdir("Characters/") if f.endswith('.png')]
        for char in characters:
            action = settings_menu.addAction(char)
            action.triggered.connect(lambda checked, path="Characters/" + char: self.change_character(path))
        menu.exec_(event.globalPos())

    def close_app(self):
        QApplication.quit()

    def change_character(self, image_path):
        pixmap = QPixmap(image_path)
        if self.scale != 1.0:
            pixmap = pixmap.scaled(
                int(pixmap.width() * self.scale),
                int(pixmap.height() * self.scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        self.setPixmap(pixmap)

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

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Force Qt to use the Fusion style for consistent rendering
    app.setStyle("Fusion")

    buddy = DesktopBuddy("Characters/Rikka.png", scale=0.5)
    sys.exit(app.exec_())
