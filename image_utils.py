"""Image utilities for DesktopBuddy: dematting / premultiplication helpers.

Exposes:
- prepare_pixmap(QPixmap) -> QPixmap

The implementation is a direct extraction of the dematting/premultiplication
logic previously inside DesktopBuddy._prepare_pixmap.
"""
from PyQt5.QtGui import QPixmap
from PyQt5 import QtGui
from PyQt5.QtCore import Qt


def prepare_pixmap(pixmap: QPixmap) -> QPixmap:
    """Return a pixmap with matte removed and converted to premultiplied ARGB.

    This removes colored halos that come from PNGs anti-aliased against a
    matte/background color.
    """
    if pixmap.isNull():
        return QPixmap()

    # Work in a straight (non-premultiplied) format so we can reason about channels.
    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_ARGB32)
    w, h = image.width(), image.height()

    # Collect color statistics from fully-transparent and low-alpha pixels
    transparent_counts = {}
    low_alpha_counts = {}
    low_alpha_total = 0
    for y in range(h):
        for x in range(w):
            px = image.pixel(x, y)
            a = QtGui.qAlpha(px)
            rgb = (QtGui.qRed(px), QtGui.qGreen(px), QtGui.qBlue(px))
            if a == 0:
                transparent_counts[rgb] = transparent_counts.get(rgb, 0) + 1
            elif a <= 30:
                low_alpha_counts[rgb] = low_alpha_counts.get(rgb, 0) + 1
                low_alpha_total += 1

    # Determine candidate mattes
    transparent_mode, transparent_mode_count = ((0, 0, 0), 0)
    if transparent_counts:
        transparent_mode, transparent_mode_count = max(transparent_counts.items(), key=lambda kv: kv[1])

    low_alpha_mode, low_alpha_mode_count = ((0, 0, 0), 0)
    if low_alpha_counts:
        low_alpha_mode, low_alpha_mode_count = max(low_alpha_counts.items(), key=lambda kv: kv[1])

    # Prefer a consistent low-alpha matte (e.g. white anti-alias matte) when present and different
    def color_distance(a_rgb, b_rgb):
        return sum((int(a_rgb[i]) - int(b_rgb[i])) ** 2 for i in range(3)) ** 0.5

    if low_alpha_total >= 50 and low_alpha_mode_count >= max(20, 0.05 * low_alpha_total) and color_distance(low_alpha_mode, transparent_mode) > 30:
        matte_rgb = low_alpha_mode
    elif transparent_mode_count > 0:
        matte_rgb = transparent_mode
    else:
        matte_rgb = (0, 0, 0)

    matte_r, matte_g, matte_b = matte_rgb

    # Dematte / remove matte color from semi-transparent pixels
    for y in range(h):
        for x in range(w):
            px = image.pixel(x, y)
            a = QtGui.qAlpha(px)
            if a == 0:
                # clear RGB on fully transparent pixels to avoid carrying matte color
                image.setPixel(x, y, QtGui.qRgba(0, 0, 0, 0))
            elif a < 255:
                a_f = a / 255.0
                r_obs = QtGui.qRed(px)
                g_obs = QtGui.qGreen(px)
                b_obs = QtGui.qBlue(px)

                # Reverse C_obs = a*C_fore + (1-a)*C_matte  =>  C_fore = (C_obs - (1-a)*C_matte)/a
                def recover(c_obs, c_m):
                    c = (c_obs - (1.0 - a_f) * c_m)
                    if a_f > 0:
                        c = c / a_f
                    # clamp to 0..255
                    c = int(round(max(0, min(255, c))))
                    return c

                r_fore = recover(r_obs, matte_r)
                g_fore = recover(g_obs, matte_g)
                b_fore = recover(b_obs, matte_b)

                image.setPixel(x, y, QtGui.qRgba(r_fore, g_fore, b_fore, a))
            # opaque pixels left unchanged

    # Convert to premultiplied format and composite onto transparent background
    premult = image.convertToFormat(QtGui.QImage.Format_ARGB32_Premultiplied)
    target = QtGui.QImage(premult.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
    target.fill(Qt.transparent)
    painter = QtGui.QPainter(target)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
    painter.drawImage(0, 0, premult)
    painter.end()

    return QPixmap.fromImage(target)
