from PyQt5 import uic
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt
from qgis.core import QgsFeatureRequest
from PIL import Image
from PIL.ExifTags import TAGS
import numpy as np
import io
import os
from .image360_loader import Image360Widget

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

        self.refresh_images()

    def refresh_images(self):
        print("Refreshing images...")

        while self.feature_stacked_widget.count():
            self.feature_stacked_widget.removeWidget(self.feature_stacked_widget.widget(0))

        extent = self.canvas.extent()
        request = QgsFeatureRequest().setFilterRect(extent)
        features = self.layer.getFeatures(request)

        for feature in features:
            image_source = "bytes" # or "link360"
            if image_source == "bytes":
                blob = feature["bytes"]
                image = Image.open(io.BytesIO(blob))
            else:
                url = feature['link360']
                image = Image.open(url)

            if self.is_360(blob):
                direction = 0
                map_manager = None
                angle_degrees = 0
                x = 0
                y = 0
                params = {}
                gl_widget = Image360Widget(image, float(direction), map_manager, angle_degrees, x, y, params, 1)
                self.feature_stacked_widget.addWidget(gl_widget)
            else:
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

    def is_360(self, photo):
        '''Takes in a bytes representation of a photo, returns a boolean indicating whether that photo is a 360 photo or not'''
        image_stream = io.BytesIO(photo)
        image = Image.open(image_stream)
        width, height = image.size

        exifdata = image.getexif()
        # looping through all the tags present in exifdata
        has_gpano = False
        for tagid in exifdata:
            # getting the tag name instead of tag id
            tagname = TAGS.get(tagid, tagid)
            # passing the tagid to get its respective value
            value = exifdata.get(tagid)
            if tagname == "XMLPacket":
                xml = value.decode("utf-8")
                if "GPano" in xml or "XMP-GPano" in xml:
                    has_gpano = True
                break
        has_360_dimensions = True if width >= height * 2 else False
        if has_360_dimensions and not has_gpano:
            #raise ValueError("Unclear whether photo is regular or 360")
            return True
        elif has_gpano and not has_360_dimensions:
            #raise ValueError("Unclear whether photo is regular or 360")
            return True
        elif has_360_dimensions and has_gpano:
            return True
        else:
            return False