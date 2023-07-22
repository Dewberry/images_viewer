from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QPainter
from PyQt5.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget
from PIL import Image
from io import BytesIO

class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.myPixmap = QPixmap()

    def setPixmap(self, pixmap):
        self.myPixmap = pixmap
        self.updatePixmap()

    def updatePixmap(self):
        w = min(self.myPixmap.width(), self.width())
        h = min(self.myPixmap.height(), self.height())
        super().setPixmap(self.myPixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setAlignment(Qt.AlignCenter)

    def resizeEvent(self, event):
        if not self.myPixmap.isNull() and self.width() and self.height():
            self.updatePixmap()

class ImageWidget(QWidget):
    def __init__(self, image_data: Image.Image, parent=None):
        super().__init__(parent)
        self.setStyleSheet("border-width: 0px; margin: 0px; background-color: white")

        # Convert the PIL Image object to bytes
        image_io = BytesIO()
        image_data.save(image_io, format='PNG')
        image_data = image_io.getvalue()

        image = QImage.fromData(image_data)

        self.label = ImageLabel()
        self.label.setPixmap(QPixmap.fromImage(image))

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)
