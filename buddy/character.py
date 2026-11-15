"""A self-drawn animated robot with five distinct tutoring expressions."""
import math
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget
from .analysis import STATES

class BuddyCharacter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 190)
        self.setMaximumHeight(235)
        self.setAccessibleName("Animated learning robot")
        self.frame = 0
        self.state = "neutral"
        self.talking = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(60)

    def set_state(self, state):
        self.state = state if state in STATES else "neutral"
        self.setAccessibleDescription(self.state)
        self.update()

    def set_talking(self, talking):
        self.talking = talking
        self.update()

    def animate(self):
        if self.isVisible():
            self.frame += 1
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 220, self.height() / 220, 1.1)
        p.translate(self.width() / 2, self.height() / 2 + math.sin(self.frame / 12) * 3)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#172b42"))
        p.drawEllipse(QRectF(-78, 80, 156, 15))
        color = {"neutral": "#72e5ca", "thinking": "#a6b8ff", "happy": "#72e5ca",
                 "surprised": "#ffc978", "explaining": "#83baff"}[self.state]
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(-53, 28, 106, 51), 18, 18)
        p.drawRoundedRect(QRectF(-83, -64, 166, 104), 28, 28)
        p.setBrush(QColor("#102838"))
        p.drawRoundedRect(QRectF(-65, -46, 130, 64), 19, 19)
        p.setPen(QPen(QColor(color), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        blink = self.frame % 65 > 61
        for x in (-31, 31):
            if blink:
                p.drawLine(x - 6, -20, x + 6, -20)
            elif self.state == "happy":
                p.drawArc(QRectF(x - 8, -25, 16, 16), 0, 180 * 16)
            elif self.state == "thinking":
                p.drawLine(x - 6, -23, x + 6, -18)
            elif self.state == "surprised":
                p.drawEllipse(QRectF(x - 5, -27, 10, 15))
            else:
                p.drawLine(x, -24, x, -16)
        if self.state == "surprised" or (self.talking and self.frame % 8 < 4):
            p.drawEllipse(QRectF(-8, -4, 16, 15))
        elif self.state == "thinking":
            p.drawLine(-9, 5, 9, 2)
        else:
            p.drawArc(QRectF(-15, -14, 30, 25), 190 * 16, 160 * 16)
        p.setPen(QPen(QColor(color), 4))
        p.drawLine(0, -64, 0, -82)
        if self.state == "explaining":
            p.drawLine(55, 48, 83, 20 + int(math.sin(self.frame / 8) * 4))
        p.setBrush(QColor("#ffc978"))
        p.drawEllipse(QRectF(-7, -94, 14, 14))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(-7, 45, 14, 14))
