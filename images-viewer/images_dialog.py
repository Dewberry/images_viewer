from PyQt5 import uic
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon


from PyQt5.QtWidgets import QVBoxLayout, QFrame, QHBoxLayout, QToolButton, QToolBar

from qgis.core import QgsFeatureRequest, QgsApplication
from PIL import Image as PILImage
import io
import os
from functools import partial

from .image_factory import ImageFactory

Ui_Dialog, QtBaseClass = uic.loadUiType(os.path.join(os.path.dirname(__file__), "images_dialog.ui"))


def create_tool_button(icon_name, tooltip_text, callback):
    button = QToolButton()
    button.setIcon(QgsApplication.getThemeIcon(icon_name))
    button.setToolTip(tooltip_text)
    button.setAutoRaise(True)
    button.clicked.connect(callback)

    return button

class ImageDialog(QtBaseClass, Ui_Dialog):
    def __init__(self, iface, parent=None):
        super(ImageDialog, self).__init__(parent)
        self.setupUi(self)

        self.settings = QSettings("QGIS3", "Images Viewer")


        self.iface = iface
        self.layer = self.iface.activeLayer()
        print(self.layer.name())
        self.canvas = self.iface.mapCanvas()

        self.comboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTableVisible.svg')), 'Show Visible Features') # index 0
        self.comboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTableSelected.svg')), 'Show Selected Features') # index 1
        self.comboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTable.svg')), 'Show All Features') # index 2
        self.comboBox.setIconSize(QSize(20, 20))  # set icon

        self.comboBox.currentIndexChanged.connect(self.handle_combobox_change)
        self.combo_box_index = 0 # Start with visible
        self.canvas.extentsChanged.connect(self.refresh_images)

        # restore the dialog's position and size if exists
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        self.refresh_images()

    def handle_combobox_change(self, index):
        if self.combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refresh_images)
        elif self.combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refresh_images)

        if index == 0:
            self.canvas.extentsChanged.connect(self.refresh_images)
        elif index == 1:
            self.layer.selectionChanged.connect(self.refresh_images)

        self.combo_box_index = index
        self.refresh_images()

    def refresh_images(self):
        print("Refreshing images...")

        # Clear all widgets from the grid layout
        for i in reversed(range(self.gridLayout.count())):
            self.gridLayout.itemAt(i).widget().setParent(None)


        if self.combo_box_index == 0:
            extent = self.canvas.extent()
            request = QgsFeatureRequest().setFilterRect(extent)
            features = self.layer.getFeatures(request)
        elif self.combo_box_index == 1:
            selected_ids = self.layer.selectedFeatureIds()
            features = self.layer.getFeatures(QgsFeatureRequest().setFilterFids(selected_ids))
        elif self.combo_box_index == 2:
            features = self.layer.getFeatures()

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

            # Create a QFrame, add the label layout to it, and set a fixed size
            frame = QFrame()
            frame.setFrameStyle(QFrame.Box | QFrame.Plain)
            frame.setStyleSheet("QFrame {color: #BEBEBE;}")
            frame.setMinimumSize(400, 600)  # Set the fixed size of the frame

            frame_layout = QVBoxLayout(frame)
            frame_layout.addWidget(imageWidget)
            frame_layout.setContentsMargins(0, 0, 0, 0) # (left, top, right, bottom)
            frame_layout.setSpacing(2) # (left, top, right, bottom)

            toolbar_layout = QHBoxLayout()
            toolbar_layout.setContentsMargins(0, 0, 0, 0) # (left, top, right, bottom)

            toolbar = QToolBar()
            toolbar.setIconSize(QSize(20, 20))

            selectButton = create_tool_button('mIconSelected.svg', "Select this feature", partial(self.select_feature, feature))
            toolbar.addWidget(selectButton)

            zoomButton = create_tool_button('mActionZoomTo.svg', "Zoom to this feature", partial(self.zoom_to_feature, feature))
            toolbar.addWidget(zoomButton)

            panButton = create_tool_button('mActionPanTo.svg', "Pan to this feature", partial(self.pan_to_feature, feature))
            toolbar.addWidget(panButton)

            panFlashButton = create_tool_button('mActionPanHighlightFeature.svg', "Pan and Flash this feature", partial(self.pan_flash_feature, feature))
            toolbar.addWidget(panFlashButton)

            flashButton = create_tool_button('mActionHighlightFeature.svg', "Flash this feature", partial(self.flash_feature, feature))
            toolbar.addWidget(flashButton)

            toolbar_layout.addWidget(toolbar)
            toolbar_layout.addStretch()

            frame_layout.addLayout(toolbar_layout)

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

    def flash_feature(self, feature):
        self.canvas.flashFeatureIds(self.layer, [feature.id()])

    def select_feature(self, feature):
        self.layer.selectByIds([feature.id()])

    def pan_flash_feature(self, feature):
        self.canvas.setExtent(feature.geometry().boundingBox())
        self.canvas.refresh()
        self.canvas.flashFeatureIds(self.layer, [feature.id()])

    def pan_to_feature(self, feature):
        self.canvas.setExtent(feature.geometry().boundingBox())
        self.canvas.refresh()

    def zoom_to_feature(self, feature):
        self.canvas.zoomToFeatureIds(self.layer, [feature.id()])

    def closeEvent(self, event):
        # When window is closed, disconnect  signals
        if self.combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refresh_images)
        elif self.combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refresh_images)

        # save the dialog's position and size
        self.settings.setValue("geometry", self.saveGeometry())

        super().closeEvent(event)
