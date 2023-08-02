from PyQt5.QtWidgets import QToolButton
from qgis.core import QgsApplication


def create_tool_button(icon_name, tooltip_text, callback):
    button = QToolButton()
    button.setIcon(QgsApplication.getThemeIcon(icon_name))
    button.setToolTip(tooltip_text)
    button.setAutoRaise(True)
    button.clicked.connect(callback)

    return button
