from PyQt5 import uic
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt
from PIL import Image
import numpy as np
import io

Ui_Dialog, QtBaseClass = uic.loadUiType("images_dialog.ui")

class ImageDialog(QtBaseClass, Ui_Dialog):
    def __init__(self, layer, parent=None):
        super(ImageDialog, self).__init__(parent)
        self.setupUi(self)

        self.layer = layer
        self.canvas = iface.mapCanvas()

        self.prev_button.clicked.connect(self.previous_feature)
        self.next_button.clicked.connect(self.next_feature)

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


layer = iface.activeLayer()
dlg = ImageDialog(layer)
dlg.show()
