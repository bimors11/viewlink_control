"""Dashboard presentation adapted from the local zt30sdk project."""

import math
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt5.QtWidgets import QWidget, QFrame, QToolButton, QVBoxLayout, QApplication


class CockpitBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QColor("#000000"))

        wash = QLinearGradient(QPointF(0, rect.height()), QPointF(rect.width(), 0))
        wash.setColorAt(0.0, QColor(0, 176, 190, 88))
        wash.setColorAt(0.26, QColor(0, 54, 65, 66))
        wash.setColorAt(0.58, QColor(2, 12, 15, 118))
        wash.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, wash)

        sweep = QLinearGradient(QPointF(rect.width() * 0.2, 0), QPointF(rect.width(), rect.height()))
        sweep.setColorAt(0.0, QColor(0, 238, 255, 28))
        sweep.setColorAt(0.45, QColor(0, 120, 140, 18))
        sweep.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, sweep)

        horizon = QPen(QColor(255, 255, 255, 18), 1)
        painter.setPen(horizon)
        y = int(rect.height() * (0.52 + 0.015 * math.sin(self._phase / 40.0)))
        painter.drawLine(0, y, rect.width(), y)
        painter.end()


class CollapsibleSection(QFrame):
    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("collapsibleSection")

        self.header = QToolButton()
        self.header.setObjectName("sectionHeader")
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.header.clicked.connect(self.set_expanded)

        self.body = QFrame()
        self.body.setObjectName("sectionBody")
        self.body.setVisible(expanded)

        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(14, 10, 14, 14)
        self._body_layout.setSpacing(10)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.body)

    def set_expanded(self, expanded: bool):
        self.header.setChecked(expanded)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.body.setVisible(expanded)

    def layout(self):
        return self._body_layout


def apply_style():
    QApplication.instance().setStyleSheet(
        """
        QWidget {
            background: transparent;
            color: #f2f2ef;
            font-family: "Liberation Sans", "Inter", "Segoe UI", Arial, sans-serif;
            font-size: 13px;
        }

        QMainWindow {
            background: #000000;
        }

        QFrame#toolbar,
        QFrame#sidePanel,
        QFrame#controlWrapper,
        QFrame#collapsibleSection {
            background: rgba(6, 10, 11, 188);
            border: 1px solid rgba(93, 129, 130, 118);
            border-radius: 8px;
        }

        QFrame#toolbar {
            max-height: 58px;
        }

        QFrame#sidePanel {
            background: rgba(5, 9, 10, 205);
        }

        QFrame#collapsibleSection {
            font-weight: 900;
        }

        QFrame#sectionBody {
            border: none;
            background: transparent;
            border-top: 1px solid rgba(93, 129, 130, 70);
            border-radius: 0px;
        }

        QToolButton#sectionHeader {
            color: #f2f2ef;
            background: rgba(7, 12, 13, 190);
            border: none;
            border-radius: 8px;
            padding: 10px 12px;
            font-weight: 900;
            text-align: left;
        }

        QToolButton#sectionHeader:hover {
            background: rgba(13, 25, 26, 220);
            border: none;
        }

        QLineEdit,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox {
            color: #f2f2ef;
            background: rgba(6, 9, 10, 220);
            border: 1px solid rgba(98, 122, 122, 125);
            border-radius: 6px;
            padding: 7px 9px;
            min-height: 20px;
            selection-background-color: #58f7e8;
        }

        QLineEdit:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus,
        QComboBox:focus {
            border-color: rgba(207, 255, 251, 220);
            background: rgba(9, 18, 19, 230);
        }

        QComboBox::drop-down {
            border: none;
            width: 24px;
        }

        QComboBox QAbstractItemView {
            color: #f2f2ef;
            background: #071012;
            border: 1px solid rgba(130, 190, 190, 150);
            selection-background-color: #58f7e8;
            selection-color: #061010;
        }

        QPushButton, QToolButton {
            color: #f2f2ef;
            background: rgba(10, 14, 15, 205);
            border: 1px solid rgba(98, 122, 122, 112);
            border-radius: 6px;
            padding: 9px 13px;
            font-weight: 900;
            min-height: 32px;
        }

        QPushButton:hover, QToolButton:hover {
            color: #ffffff;
            background: #1a1f1f;
            border-color: #d7dbdb;
        }

        QPushButton:pressed, QToolButton:pressed {
            color: #061010;
            background: #ffffff;
            border-color: #ffffff;
        }

        QPushButton:disabled, QToolButton:disabled {
            color: #657171;
            background: #101515;
            border-color: #252d2d;
        }

        QCheckBox {
            color: #dce8e8;
            spacing: 8px;
        }

        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid rgba(170, 205, 205, 160);
            background: rgba(0, 0, 0, 155);
        }

        QCheckBox::indicator:hover {
            border-color: #ffffff;
        }

        QCheckBox::indicator:checked {
            background: #58f7e8;
            border-color: #cffffb;
        }

        QTableWidget {
            color: #f2f2ef;
            background: rgba(6, 9, 10, 185);
            border: 1px solid rgba(98, 122, 122, 112);
            border-radius: 6px;
            gridline-color: rgba(93, 129, 130, 90);
            selection-background-color: rgba(88, 247, 232, 190);
            selection-color: #061010;
        }

        QHeaderView::section {
            color: #061010;
            background: #58f7e8;
            border: none;
            padding: 5px 7px;
            font-weight: 900;
        }

        QScrollArea,
        QFrame#controlScroll {
            background: transparent;
            border: none;
        }

        #sidebarToggle {
            color: #aebbbb;
            background: rgba(6, 10, 11, 190);
            border: 1px solid rgba(93, 129, 130, 118);
            padding: 8px 10px;
        }

        #sidebarToggle:hover {
            color: #ffffff;
            border-color: rgba(207, 255, 252, 190);
        }

        #videoStage {
            background: rgba(0, 0, 0, 185);
            border-radius: 8px;
            border: 1px solid rgba(112, 160, 160, 130);
        }

        #mainVideo {
            background: #000000;
            color: #86a2a2;
            border-radius: 8px;
            font-size: 18px;
        }

        #pipVideo {
            background: #000000;
            color: #f2f2ef;
            border: 2px solid #f2f2ef;
            border-radius: 7px;
            margin: 18px;
        }

        #statusBadge {
            color: #061010;
            background: #58f7e8;
            border-radius: 5px;
            padding: 5px 9px;
            font-weight: 900;
        }

        #recordIndicator {
            color: #8fa3a3;
            background: rgba(6, 9, 10, 175);
            border: 1px solid rgba(98, 122, 122, 112);
            border-radius: 5px;
            padding: 7px 9px;
            font-weight: 900;
        }

        #recordIndicator[recording="true"] {
            color: #ffffff;
            background: #c62828;
            border-color: #ff8a80;
        }

        #thermalResult {
            color: #ffffff;
            background: rgba(10, 35, 38, 220);
            border: 1px solid #40c4ff;
            border-radius: 5px;
            padding: 8px 10px;
            font-weight: 900;
        }

        #metricLabel {
            color: #aebbbb;
            font-size: 12px;
        }

        #metricValue {
            color: #ffffff;
            font-size: 20px;
            font-weight: 900;
        }

        #log {
            color: #aebbbb;
            background: rgba(6, 9, 10, 220);
            border: 1px solid rgba(98, 122, 122, 112);
            border-radius: 6px;
        }

        QScrollBar:vertical {
            background: rgba(4, 7, 8, 160);
            width: 12px;
            margin: 0px;
        }

        QScrollBar::handle:vertical {
            background: rgba(134, 162, 162, 150);
            border-radius: 5px;
            min-height: 30px;
        }

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QSlider::groove:horizontal {
            height: 6px;
            background: rgba(6, 9, 10, 220);
            border: 1px solid rgba(98, 122, 122, 112);
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #58f7e8;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QToolTip {
            color: #f2f2ef;
            background: #071012;
            border: 1px solid #58f7e8;
            padding: 6px;
        }
        """
    )


