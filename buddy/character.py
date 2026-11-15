"""Eigene, mit Qt gezeichnete Roboterfigur ohne externe Bilddateien."""
import math
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

class BuddyCharacter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 230)
        self.setAccessibleName("Freundlicher, animierter Lernroboter")
        self.frame = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(60)

    def animate(self):
        if self.isVisible():
            self.frame += 1
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2 + math.sin(self.frame / 12) * 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#172b42"))
        painter.drawEllipse(QRectF(-78, 80, 156, 15))
        painter.setBrush(QColor("#72e5ca"))
        painter.drawRoundedRect(QRectF(-53, 28, 106, 51), 18, 18)
        painter.drawRoundedRect(QRectF(-83, -64, 166, 104), 28, 28)
        painter.setBrush(QColor("#102838"))
        painter.drawRoundedRect(QRectF(-65, -46, 130, 64), 19, 19)
        painter.setPen(QPen(QColor("#72e5ca"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        blink = self.frame % 65 > 61
        for x in (-31, 31):
            painter.drawLine(x - 6, -20, x + 6, -20 if blink else -12)
        painter.drawArc(QRectF(-14, -13, 28, 22), 190 * 16, 160 * 16)
        painter.setPen(QPen(QColor("#72e5ca"), 4))
        painter.drawLine(0, -64, 0, -82)
        painter.setBrush(QColor("#ffc978"))
        painter.drawEllipse(QRectF(-7, -94, 14, 14))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(-7, 45, 14, 14))
