from PyQt5 import uic
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QFrame
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

        # Connect the extentsChanged signal from the canvas to the refresh_on_move slot
        self.canvas.extentsChanged.connect(self.refresh_on_move)

        self.refresh_images()

    def refresh_on_move(self):
        # This method will be called when the canvas extent is changed
        self.refresh_images()

    def refresh_images(self):
        print("Refreshing images...")

        # Clear all widgets from the grid layout
        for i in reversed(range(self.gridLayout.count())):
            self.gridLayout.itemAt(i).widget().setParent(None)

        extent = self.canvas.extent()
        request = QgsFeatureRequest().setFilterRect(extent)
        features = self.layer.getFeatures(request)

        row = 0
        col = 0
        for feature in features:
            blob = feature["bytes"]
            image = Image.open(io.BytesIO(blob))

            qimage = QImage(np.array(image), image.size[0], image.size[1], image.size[0] * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage)
            label = QLabel()
            label.setPixmap(pixmap)

            # Create a QFrame, add the QLabel to it, and set a fixed size
            frame = QFrame()
            frame.setFrameStyle(QFrame.Box | QFrame.Plain)
            frame.setStyleSheet("QFrame {color: #BEBEBE;}")
            frame_layout = QVBoxLayout(frame)

            # Create a QScrollArea and add the QLabel to it
            scrollArea = QScrollArea()
            scrollArea.setWidget(label)
            scrollArea.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)  # Frame will shrink/grow with its content
            frame_layout.addWidget(scrollArea)

            frame.setMinimumSize(400, 600)  # Set the fixed size of the frame

            self.gridLayout.addWidget(frame, row, col)

            # Change the row and column for the next image
            col += 1
            if col > 2:  # Change this number to adjust how many images per row
                col = 0
                row += 1

        self.show()


    def closeEvent(self, event):
        # When window is closed, disconnect extentsChanged signal
        self.canvas.extentsChanged.disconnect(self.refresh_on_move)
        super().closeEvent(event)
