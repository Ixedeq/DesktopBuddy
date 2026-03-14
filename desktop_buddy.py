#!/usr/bin/env python3
import os
import objc
from PyQt5.QtWidgets import QApplication, QLabel, QMenu, QWidgetAction, QSlider, QHBoxLayout, QWidget, QLabel as QLabelWidget, QMessageBox
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QFile, QSettings, QPoint

from Cocoa import (
    NSApplication,
    NSApp,
    NSFloatingWindowLevel,
    NSApplicationActivationPolicyAccessory,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSColor,
    NSImage,
)
from Quartz import CGWindowLevelForKey, kCGMaximumWindowLevelKey

from image_utils import prepare_pixmap

import sys
import subprocess
import shutil
import tempfile
from PIL import Image
from typing import Tuple


class DesktopBuddy(QLabel):
    def __init__(self, image_path, scale=1.0):
        super().__init__()
        self.scale = scale

        # Load persisted settings (remember last character & scale)
        self.settings = QSettings("Ixedeq", "DesktopBuddy")
        saved_scale = self.settings.value("scale", None)
        if saved_scale is not None:
            try:
                self.scale = float(saved_scale)
            except Exception:
                pass
        saved_char = self.settings.value("character", "")
        if saved_char:
            saved_char = str(saved_char)
            # prefer an existing path as saved, otherwise try Characters/<basename>
            if os.path.exists(saved_char):
                image_path = saved_char
            else:
                candidate = os.path.join("Characters", os.path.basename(saved_char))
                if os.path.exists(candidate):
                    image_path = candidate
        # track current character path for menu checks
        self.current_character = image_path

        # Keep the original (base) pixmap so scaling is always high-quality
        self._base_pixmap = QPixmap(image_path)

        # Initialize display from the base pixmap using the (possibly persisted) scale
        # (use set_scale so saved scale is applied on startup)
        self.set_scale(self.scale)

        # keep a copy of the currently displayed pixmap so we can re-render on interaction
        if hasattr(self, '_current_pixmap'):
            self._current_pixmap = self._current_pixmap.copy()
        else:
            self._current_pixmap = QPixmap()

        # Ensure the QLabel scales properly with the image
        self.setScaledContents(True)

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

        # Restore saved position (if any)
        try:
            self._restore_position()
        except Exception:
            pass

        # Update app icon to the current character (if any)
        try:
            if getattr(self, 'current_character', None):
                self._update_app_icon(self.current_character)
        except Exception:
            pass

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

        # Disable the window shadow and ensure background is transparent to avoid OS-level compositing artifacts
        try:
            nswindow.setHasShadow_(False)
        except Exception:
            pass
        try:
            nswindow.setBackgroundColor_(NSColor.clearColor())
            nswindow.setOpaque_(False)
        except Exception:
            pass

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
            # reapply prepared pixmap and repaint immediately (works around artefacts that appear on focus/click)
            try:
                if hasattr(self, '_current_pixmap'):
                    self.setPixmap(prepare_pixmap(self._current_pixmap))
            except Exception:
                pass
            self.repaint()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        # Save placement when drag ends
        try:
            self._save_position()
        except Exception:
            pass
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def set_scale(self, scale: float):
        """Rescale the buddy from the original base pixmap and update display."""
        # Clamp scale to a sensible range (max 100%)
        scale = max(0.1, min(1.0, float(scale)))
        self.scale = scale
        if hasattr(self, '_base_pixmap') and not self._base_pixmap.isNull():
            base = self._base_pixmap
            # scale from base to avoid quality loss from repeated scaling
            w = int(base.width() * scale)
            h = int(base.height() * scale)
            scaled = base.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pix = prepare_pixmap(scaled)
            self.setPixmap(pix)
            self.setFixedSize(pix.size())
            self._current_pixmap = pix.copy()
        # persist updated scale
        try:
            self.settings.setValue("scale", self.scale)
        except Exception:
            pass

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        css_file = QFile("menu.css")
        if css_file.open(QFile.ReadOnly | QFile.Text):
            menu.setStyleSheet(str(css_file.readAll(), 'utf-8'))
            css_file.close()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.close_app)

        # Scale submenu with embedded slider
        scale_menu = menu.addMenu("Scale")
        slider_widget = QWidget()
        hbox = QHBoxLayout(slider_widget)
        hbox.setContentsMargins(8, 4, 8, 4)
        hbox.setSpacing(8)
        slider_label = QLabelWidget(f"{min(int(self.scale * 100), 100)}%")
        scale_slider = QSlider(Qt.Horizontal)
        scale_slider.setRange(10, 100)  # 10%..100%
        scale_slider.setValue(min(int(self.scale * 100), 100))
        scale_slider.setTickInterval(10)
        scale_slider.setTickPosition(QSlider.TicksBelow)
        scale_slider.setFixedWidth(140)
        hbox.addWidget(scale_slider)
        hbox.addWidget(slider_label)
        scale_action = QWidgetAction(menu)
        scale_action.setDefaultWidget(slider_widget)
        scale_menu.addAction(scale_action)

        # Connect slider to live scale update
        def _on_scale_change(value):
            slider_label.setText(f"{value}%")
            try:
                self.set_scale(value / 100.0)
            except Exception:
                pass

        scale_slider.valueChanged.connect(_on_scale_change)

        settings_menu = menu.addMenu("Settings")
        # Action to overwrite the app bundle icon with the current character
        set_icon_action = settings_menu.addAction("Use current character as app icon")
        set_icon_action.triggered.connect(lambda: self._confirm_and_overwrite_icon())
        characters = [f for f in os.listdir("Characters/") if f.endswith('.png')]
        for char in characters:
            path = "Characters/" + char
            display_name = os.path.splitext(char)[0]
            action = settings_menu.addAction(display_name)
            action.setCheckable(True)
            if getattr(self, 'current_character', '') == path:
                action.setChecked(True)
            action.triggered.connect(lambda checked, p=path: self.change_character(p))
        menu.exec_(event.globalPos())
 
    def _confirm_and_overwrite_icon(self):
        if not getattr(self, 'current_character', None):
            QMessageBox.warning(self, "No character", "No character is selected to use as app icon.")
            return
        reply = QMessageBox.question(
            self,
            "Overwrite App Icon",
            f"Replace the app bundle icon with '{os.path.basename(self.current_character)}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            ok, msg = self._overwrite_bundle_icon(self.current_character)
            if ok:
                QMessageBox.information(self, "Done", "App bundle icon updated. You may need to restart Finder to see the change in Finder.")
            else:
                QMessageBox.critical(self, "Failed", f"Failed to update icon: {msg}")

    def _overwrite_bundle_icon(self, image_path: str) -> Tuple[bool, str]:
        """Create an .icns from image_path and overwrite .icns files inside the running bundle (or dist/DesktopBuddy.app).

        Returns (success: bool, message: str).
        """
        try:
            if not os.path.exists(image_path):
                return False, f"Image not found: {image_path}"

            # Determine target .app bundle to modify
            bundle_paths = []
            # If running frozen (PyInstaller) find the bundle containing the executable
            if getattr(sys, 'frozen', False):
                bundle_dir = os.path.dirname(os.path.dirname(sys.executable))
                bundle_paths.append(bundle_dir)
            # Also attempt repo's dist bundle if present
            repo_bundle = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dist', 'DesktopBuddy.app'))
            bundle_paths.append(repo_bundle)

            # Create iconset in temp dir
            tmpdir = tempfile.mkdtemp(prefix="db_icon_")
            iconset_dir = tmpdir + ".iconset"
            os.makedirs(iconset_dir, exist_ok=True)

            src = Image.open(image_path).convert('RGBA')
            # ensure square by padding
            maxdim = max(src.width, src.height)
            if src.width != src.height:
                bg = Image.new('RGBA', (maxdim, maxdim), (0, 0, 0, 0))
                bg.paste(src, ((maxdim - src.width) // 2, (maxdim - src.height) // 2), src)
                src = bg

            sizes = {
                'icon_16x16.png': (16, 16),
                'icon_16x16@2x.png': (32, 32),
                'icon_32x32.png': (32, 32),
                'icon_32x32@2x.png': (64, 64),
                'icon_128x128.png': (128, 128),
                'icon_128x128@2x.png': (256, 256),
                'icon_256x256.png': (256, 256),
                'icon_256x256@2x.png': (512, 512),
                'icon_512x512.png': (512, 512),
                'icon_512x512@2x.png': (1024, 1024),
            }

            for name, (w, h) in sizes.items():
                dst = src.resize((w, h), Image.LANCZOS)
                dst.save(os.path.join(iconset_dir, name), format='PNG')

            icns_path = os.path.join(tmpdir, 'app_icon.icns')
            # Use iconutil to build .icns (macOS)
            try:
                subprocess.run(['iconutil', '-c', 'icns', iconset_dir, '-o', icns_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                shutil.rmtree(tmpdir, ignore_errors=True)
                return False, f"iconutil failed: {e}"

            overwritten = []
            for bundle_dir in bundle_paths:
                resources = os.path.join(bundle_dir, 'Contents', 'Resources')
                if not os.path.isdir(resources):
                    continue
                # common icns filenames generated by PyInstaller
                candidates = ['icon-windowed.icns', 'icon.icns']
                for name in candidates:
                    target = os.path.join(resources, name)
                    try:
                        if os.path.exists(target):
                            # backup
                            shutil.copy2(target, target + '.bak')
                        shutil.copy2(icns_path, target)
                        overwritten.append(target)
                    except Exception:
                        # try to write anyway
                        try:
                            shutil.copy2(icns_path, target)
                            overwritten.append(target)
                        except Exception:
                            pass

            # attempt to refresh Finder/Dock icon cache
            try:
                # update Dock icon for running app immediately
                ns_image = NSImage.alloc().initWithContentsOfFile_(os.path.abspath(image_path))
                if ns_image:
                    NSApp.setApplicationIconImage_(ns_image)
                # tell Finder to update icon for repo bundle (best-effort)
                for b in bundle_paths:
                    if os.path.isdir(b):
                        subprocess.run(['osascript', '-e', f'tell application "Finder" to update POSIX file "{b}"'], check=False)
                # reset quicklook cache
                subprocess.run(['qlmanage', '-r'], check=False)
            except Exception:
                pass

            shutil.rmtree(tmpdir, ignore_errors=True)
            if overwritten:
                return True, f"Overwrote: {', '.join(overwritten)}"
            else:
                return False, "No target bundle found to overwrite"
        except Exception as exc:
            return False, str(exc)

    def close_app(self):
        # persist position before quitting
        try:
            self._save_position()
        except Exception:
            pass
        QApplication.quit()

    def _update_app_icon(self, image_path: str):
        """Update the Qt window icon and macOS Dock icon to the given image file.

        Falls back silently if the image can't be loaded.
        """
        try:
            if not image_path:
                return
            if not os.path.exists(image_path):
                return

            # Qt window/icon (cross-platform)
            QApplication.setWindowIcon(QIcon(image_path))

            # macOS Dock icon (NSApp)
            try:
                ns_image = NSImage.alloc().initWithContentsOfFile_(os.path.abspath(image_path))
                if ns_image:
                    NSApp.setApplicationIconImage_(ns_image)
            except Exception:
                pass
        except Exception:
            pass

    def change_character(self, image_path):
        # update base pixmap then reapply current scale
        self._base_pixmap = QPixmap(image_path)
        self.current_character = image_path
        try:
            self.settings.setValue("character", image_path)
        except Exception:
            pass
        # update app icon to the new character
        try:
            self._update_app_icon(image_path)
        except Exception:
            pass
        self.set_scale(self.scale)

    def _save_position(self):
        try:
            # save the window's top-left in global coordinates
            p = self.frameGeometry().topLeft()
            self.settings.setValue("pos", f"{p.x()},{p.y()}")
        except Exception:
            pass

    def _restore_position(self):
        try:
            val = self.settings.value("pos", None)
            if not val:
                return
            x = y = None
            from PyQt5.QtCore import QPoint
            if isinstance(val, QPoint):
                x, y = val.x(), val.y()
            else:
                s = str(val)
                if ',' in s:
                    parts = [p.strip() for p in s.split(',')]
                    if len(parts) >= 2:
                        # allow saved floats as well
                        x = int(float(parts[0]))
                        y = int(float(parts[1]))
            if x is None or y is None:
                return

            # Move to the exact saved coordinates (do NOT clamp) so off-screen placement is preserved
            super().move(x, y)
        except Exception:
            pass


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    # Force Qt to use the Fusion style for consistent rendering
    app.setStyle("Fusion")

    buddy = DesktopBuddy("Characters/Rikka.png", scale=0.5)
    sys.exit(app.exec_())
