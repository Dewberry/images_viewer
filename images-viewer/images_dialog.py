from PyQt5.QtCore import Qt

from PyQt5 import uic
from PyQt5.QtCore import QSettings, QVariant, QSize
from PyQt5.QtGui import QIcon
from qgis.core import QgsExpression, QgsExpressionContext, QgsFields

import time

from PyQt5.QtWidgets import QVBoxLayout, QFrame, QHBoxLayout, QToolButton, QToolBar, QLabel, QSizePolicy

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

        self.iface = iface
        self.layer = self.iface.activeLayer()
        if not self.layer:
            raise ValueError("Layer is not defined")
        print(self.layer.name())

        # restore the dialog's position and size if exists, also restore image_field for this layer
        self.settings = QSettings("QGIS3 - Images Viewer", self.layer.name())
        self.default_settings = QSettings("QGIS3 - Images Viewer", "")
        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
            self.image_field = self.settings.value("imageField", "")
        else:
            self.image_field = ""
            if self.default_settings.contains("geometry"):
                self.restoreGeometry(self.default_settings.value("geometry"))

        self.canvas = self.iface.mapCanvas()

        refreshButton = create_tool_button('mActionRefresh.svg', "Refresh", self.refresh_images)
        self.topToolBar.setIconSize(QSize(20, 20))
        self.topToolBar.addWidget(refreshButton)

        self.bottomComboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTableVisible.svg')), 'Show Visible Features') # index 0
        self.bottomComboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTableSelected.svg')), 'Show Selected Features') # index 1
        self.bottomComboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTable.svg')), 'Show All Features') # index 2
        self.bottomComboBox.setIconSize(QSize(20, 20))  # set icon

        self.bottomComboBox.currentIndexChanged.connect(self.handle_b_combobox_change)
        self.b_combo_box_index = 0 # Start with visible
        self.canvas.extentsChanged.connect(self.refresh_images)

        display_expression = self.layer.displayExpression()
        self.layer.displayExpressionChanged.connect(self.refresh_display_expression)
        self.feature_title_expression = QgsExpression(display_expression)

        # can't use builtin QgsFieldProxyModel.filters because there is no binary filter
        # https://github.com/qgis/QGIS/issues/53940
        filtered_fields = QgsFields()
        for field in self.layer.fields():
            print(type(field))
            if field.type() in (QVariant.String, QVariant.ByteArray):
                filtered_fields.append(field=field)

        self.fieldComboBox.setFields(filtered_fields)
        self.fieldComboBox.setAllowEmptyFieldName(True)
        self.fieldComboBox.fieldChanged.connect(self.fieldChanged)

        self.fieldComboBox.setField(self.image_field) # this will call referesh method

    def fieldChanged(self, fieldName):
        self.image_field = fieldName
        print(not self.image_field)
        if not self.image_field:
            self.fieldComboBox.setStyleSheet("QComboBox { background-color: #3399ff; }")
            self.fieldComboBox.setToolTip('Select field containing image data or url')
        else:
            self.fieldComboBox.setStyleSheet("")

        self.refresh_images()

    def refresh_display_expression(self):
        display_expression = self.layer.displayExpression()
        self.feature_title_expression = QgsExpression(display_expression)
        self.refresh_images()

    def handle_b_combobox_change(self, index):
        if self.b_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refresh_images)
        elif self.b_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refresh_images)

        if index == 0:
            self.canvas.extentsChanged.connect(self.refresh_images)
        elif index == 1:
            self.layer.selectionChanged.connect(self.refresh_images)

        self.b_combo_box_index = index
        self.refresh_images()

    def refresh_images(self):

        start_time = time.time()  # Start time before the operation
        print("Refreshing images...")

        context = QgsExpressionContext()

        # Clear all widgets from the grid layout
        for i in reversed(range(self.gridLayout.count())):
            self.gridLayout.itemAt(i).widget().setParent(None)


        if self.b_combo_box_index == 0:
            extent = self.canvas.extent()
            request = QgsFeatureRequest().setFilterRect(extent)
            features = self.layer.getFeatures(request)
        elif self.b_combo_box_index == 1:
            selected_ids = self.layer.selectedFeatureIds()
            features = self.layer.getFeatures(QgsFeatureRequest().setFilterFids(selected_ids))
        elif self.b_combo_box_index == 2:
            features = self.layer.getFeatures()

        filtered_count = 0

        row = 0
        col = 0
        for feature in features:
            filtered_count += 1

            if not self.image_field:
                continue

            try:

                # doing this at the top so that if this fails we short circuit
                data = None
                blob = feature[self.image_field]
                if blob:
                    data = PILImage.open(io.BytesIO(blob))

                if not data:
                    continue

                frame = QFrame()
                frame.setFrameStyle(QFrame.Box | QFrame.Plain)
                frame.setStyleSheet("QFrame {color: #BEBEBE;}")
                frame.setMinimumSize(400, 600)

                frame_layout = QVBoxLayout(frame)
                frame_layout.setContentsMargins(0, 0, 0, 0) # (left, top, right, bottom)
                frame_layout.setSpacing(2) # (left, top, right, bottom)

                context.setFeature(feature)
                feature_title = self.feature_title_expression.evaluate(context)

                feature_title_label = QLabel()
                feature_title_label.setText(str(feature_title))
                feature_title_label.setStyleSheet("text-align:center; font-size:13px; font: bold; color: black; background-color: white;  padding: 5px;")
                feature_title_label.setAlignment(Qt.AlignCenter)
                feature_title_label.setMinimumHeight(35)
                feature_title_label.setWordWrap(True)

                frame_layout.addWidget(feature_title_label)

                imageWidget = ImageFactory.create_widget(data)
                imageWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

                frame_layout.addWidget(imageWidget)

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

                col += 1
                if col > 2:  # Change this number to adjust how many images per row
                    col = 0
                    row += 1

            except Exception as e:
                self.iface.messageBar().pushMessage("Image Viewer", f"Feature: {feature.id()}: {str(e)}", level=1, duration=3)


        total_count = self.layer.featureCount()

        # Set window title
        self.setWindowTitle(f"{self.layer.name()} -- Features Total: {total_count}, Filtered: {filtered_count}")

        self.show()
        print("Refresh operation took: %s seconds" % (time.time() - start_time))  # Print out the time it took


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
        self.layer.displayExpressionChanged.disconnect(self.refresh_display_expression)
        if self.b_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refresh_images)
        elif self.b_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refresh_images)

        # save the dialog's position and size
        self.settings.setValue("geometry", self.saveGeometry())
        self.default_settings.setValue("geometry", self.saveGeometry())

        # remember field name
        self.settings.setValue("imageField", self.image_field)

        super().closeEvent(event)
