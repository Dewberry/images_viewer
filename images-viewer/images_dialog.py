from PyQt5 import uic
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt
from qgis.core import QgsFeatureRequest
from PIL import Image
import numpy as np
import io
import os

Ui_Dialog, QtBaseClass = uic.loadUiType(os.path.join(os.path.dirname(__file__), "images_dialog.ui"))

class ImageDialog(QtBaseClass, Ui_Dialog):
    def __init__(self, iface, parent=None):
        super(ImageDialog, self).__init__(parent)
        self.setupUi(self)

        self.iface = iface
        self.layer = self.iface.activeLayer()
        print(self.layer.name())
        self.canvas = self.iface.mapCanvas()

        self.prev_button.clicked.connect(self.previous_feature)
        self.next_button.clicked.connect(self.next_feature)

        # Connect the extentsChanged signal from the canvas to the refresh_on_move slot
        self.canvas.extentsChanged.connect(self.refresh_on_move)

        self.refresh_images()

    def refresh_on_move(self):
        # This method will be called when the canvas extent is changed
        self.refresh_images()

    def refresh_images(self):
        print("Refreshing images...")

        while self.feature_stacked_widget.count():
            self.feature_stacked_widget.removeWidget(self.feature_stacked_widget.widget(0))

        extent = self.canvas.extent()
        request = QgsFeatureRequest().setFilterRect(extent)
        features = self.layer.getFeatures(request)

        for feature in features:
            blob = feature["bytes"]
            image = Image.open(io.BytesIO(blob))

            qimage = QImage(np.array(image), image.size[0], image.size[1], image.size[0] * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage)
            label = QLabel()
            label.setPixmap(pixmap)

            self.feature_stacked_widget.addWidget(label)

        self.show()

    def previous_feature(self):
        index = self.feature_stacked_widget.currentIndex()
        if index > 0:
            self.feature_stacked_widget.setCurrentIndex(index - 1)

    def next_feature(self):
        index = self.feature_stacked_widget.currentIndex()
        if index < self.feature_stacked_widget.count() - 1:
            self.feature_stacked_widget.setCurrentIndex(index + 1)

    def closeEvent(self, event):
        # When window is closed, disconnect extentsChanged signal
        self.canvas.extentsChanged.disconnect(self.refresh_on_move)
        super().closeEvent(event)