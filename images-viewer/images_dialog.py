from PyQt5 import uic
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QFrame, QHBoxLayout
from qgis.core import QgsFeatureRequest
from PIL import Image as PILImage
import io
import os
from .image_factory import ImageFactory

Ui_Dialog, QtBaseClass = uic.loadUiType(os.path.join(os.path.dirname(__file__), "images_dialog.ui"))

class ImageDialog(QtBaseClass, Ui_Dialog):
    def __init__(self, iface, parent=None):
        super(ImageDialog, self).__init__(parent)
        self.setupUi(self)

        self.settings = QSettings("QGIS3", "Images Viewer")


        self.iface = iface
        self.layer = self.iface.activeLayer()
        print(self.layer.name())
        self.canvas = self.iface.mapCanvas()

        # Connect the extentsChanged signal from the canvas to the refresh_on_move slot
        self.canvas.extentsChanged.connect(self.refresh_on_move)

        # restore the dialog's position and size if exists
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

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
        filtered_count = 0


        row = 0
        col = 0
        for feature in features:
            image_source = "bytes" # or "link360"
            if image_source == "bytes":
                blob = feature["bytes"]
                data = PILImage.open(io.BytesIO(blob))
            else:
                url = feature['link360']
                data = PILImage.open(url)

            imageWidget = ImageFactory.create_widget(data)

            scrollArea = QScrollArea()
            scrollArea.setWidget(imageWidget)

            # Create a QHBoxLayout and add QLabel to it, with stretches on both sides
            innerLayout = QHBoxLayout()
            innerLayout.addStretch(1)
            innerLayout.addWidget(scrollArea)
            innerLayout.addStretch(1)

            # Create a QWidget and a QVBoxLayout to align QLabel at the top
            labelLayout = QVBoxLayout()
            labelLayout.addLayout(innerLayout)
            labelLayout.addStretch(1)  # Add stretch at the bottom to push QLabel up

            # Create a QFrame, add the label layout to it, and set a fixed size
            frame = QFrame()
            frame.setFrameStyle(QFrame.Box | QFrame.Plain)
            frame.setStyleSheet("QFrame {color: #BEBEBE;}")
            frame.setMinimumSize(400, 600)  # Set the fixed size of the frame

            frame_layout = QVBoxLayout(frame)
            frame_layout.addLayout(labelLayout)

            self.gridLayout.addWidget(frame, row, col)
            filtered_count += 1

            # Change the row and column for the next image
            col += 1
            if col > 2:  # Change this number to adjust how many images per row
                col = 0
                row += 1

        total_count = self.layer.featureCount()

        # Set window title
        self.setWindowTitle(f"{self.layer.name()} -- Features Total: {total_count}, Filtered: {filtered_count}")


        self.show()


    def closeEvent(self, event):
        # When window is closed, disconnect extentsChanged signal
        self.canvas.extentsChanged.disconnect(self.refresh_on_move)

        # save the dialog's position and size
        self.settings.setValue("geometry", self.saveGeometry())

        super().closeEvent(event)
