from PyQt5 import uic
from PyQt5.QtCore import QSettings, QVariant, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import Qt

from qgis.core import QgsExpression, QgsExpressionContext, QgsFields, QgsProject

import time

from qgis.core import QgsFeatureRequest, QgsApplication
import os

from .image_factory import ImageFactory
from .feature_frame import FeatureFrame
from .children_feature_frame import ChildrenFeatureFrame

Ui_Dialog, QtBaseClass = uic.loadUiType(os.path.join(os.path.dirname(__file__), "images_dialog.ui"))

from .utils import create_tool_button

class ImageDialog(QtBaseClass, Ui_Dialog):
    def __init__(self, iface, parent=None):
        super(ImageDialog, self).__init__(parent)
        self.setupUi(self)

        self.iface = iface
        self.layer = self.iface.activeLayer()
        if not self.layer:
            raise ValueError("Layer is not defined")
        self.setWindowTitle(self.layer.name())

        # restore the dialog's position and size if exists, also restore image_field for this layer
        self.settings = QSettings("QGIS3 - Images Viewer", self.layer.name())
        self.default_settings = QSettings("QGIS3 - Images Viewer", "")
        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
            self.image_field = self.settings.value("imageField", "")
            relation_index = self.settings.value("relationIndex", 0)
        else:
            self.image_field = ""
            relation_index = 0
            if self.default_settings.contains("geometry"):
                self.restoreGeometry(self.default_settings.value("geometry"))

        self.canvas = self.iface.mapCanvas()

        # mapping from feature.id() to the QFrame it's associated with
        self.feature_to_frame = {}

        refreshButton = create_tool_button('mActionRefresh.svg', "Refresh", self.refresh_features)
        self.topToolBar.setIconSize(QSize(20, 20))
        self.topToolBar.addWidget(refreshButton)

        self.bottomComboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTableVisible.svg')), 'Show Visible Features') # index 0
        self.bottomComboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTableSelected.svg')), 'Show Selected Features') # index 1
        self.bottomComboBox.addItem(QIcon(QgsApplication.getThemeIcon('mActionOpenTable.svg')), 'Show All Features') # index 2
        self.bottomComboBox.setIconSize(QSize(20, 20))  # set icon

        self.bottomComboBox.currentIndexChanged.connect(self.handle_b_combobox_change)
        self.b_combo_box_index = 0 # Start with visible
        self.canvas.extentsChanged.connect(self.refresh_features)

        display_expression = self.layer.displayExpression()
        self.layer.displayExpressionChanged.connect(self.refresh_display_expression)
        self.feature_title_expression = QgsExpression(display_expression)

        self.relations = QgsProject.instance().relationManager().referencedRelations(self.layer)
        self.relationComboBox.addItems([None] + [rel.name() for rel in self.relations])
        self.relationComboBox.currentIndexChanged.connect(self.relationChanged)
        self.relationComboBox.setToolTip('Select relationship')

        self.filtered_fields = QgsFields()

        self.fieldComboBox.setAllowEmptyFieldName(True)
        self.fieldComboBox.fieldChanged.connect(self.fieldChanged)
        self.fieldComboBox.setToolTip('Select field containing image data or url')

        # pagination
        self.offset = 0 # inclusive
        self.limit = 9 # change this to conrol how many frames per page
        self.next_offset = 0

        self.previousPageButton = None
        self.nextPageButton = None

        self.relation = None
        if relation_index == 0 or relation_index > len(self.relations): # if index 0 or not within len of relations, this can happen if settings are incorrectly read:
            # manually call relationChanged() as setCurrentIndex wont call it as signal hasn't chaged
            self.relationChanged(0)
        else:
            self.relationComboBox.setCurrentIndex(relation_index)

    def relationChanged(self, index):

        self.filtered_fields.clear()
        self.fieldComboBox.clear()
        self.relation_index = index

        if index == 0:
            image_layer = self.layer
            self.relation = None
        else:
            image_layer = self.relations[index-1].referencingLayer()
            self.relation = self.relations[index-1]

        # can't use builtin QgsFieldProxyModel.filters because there is no binary filter
        # https://github.com/qgis/QGIS/issues/53940
        for field in image_layer.fields():
            if field.type() in (QVariant.String, QVariant.ByteArray):
                self.filtered_fields.append(field=field)
        self.fieldComboBox.setFields(self.filtered_fields)

        if self.image_field not in [f.name() for f in self.filtered_fields]:
            self.image_field = ""
            self.fieldChanged("") # this will call referesh method
        else:
            self.fieldComboBox.setField(self.image_field) # this will call referesh method

    def fieldChanged(self, fieldName):
        self.image_field = fieldName
        if not fieldName:
            self.fieldComboBox.setStyleSheet("QComboBox { background-color: #3399ff; }")
        else:
            self.fieldComboBox.setStyleSheet("")
            field_index = self.filtered_fields.indexFromName(fieldName)
            field = self.filtered_fields[field_index]
            self.field_type = field.type()

        self.refresh_features()

    def refresh_display_expression(self):
        display_expression = self.layer.displayExpression()
        self.feature_title_expression = QgsExpression(display_expression)
        # todo: clear frames
        self.refresh_images()

    def handle_b_combobox_change(self, index):
        if self.b_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refresh_features)
        elif self.b_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refresh_features)

        if index == 0:
            self.canvas.extentsChanged.connect(self.refresh_features)
        elif index == 1:
            self.layer.selectionChanged.connect(self.refresh_features)

        self.b_combo_box_index = index

        self.refresh_features()


    def refresh_features(self):
        start_time = time.time()  # Start time before the operation
        print("Refreshing features...")

        self.next_offset, self.offset = 0, 0
        if self.b_combo_box_index == 0:
            extent = self.canvas.extent()
            request = QgsFeatureRequest().setFilterRect(extent)
            self.feature_ids = [f.id() for f in self.layer.getFeatures(request)]
        elif self.b_combo_box_index == 1:
            selected_ids = self.layer.selectedFeatureIds()
            self.feature_ids = selected_ids
        elif self.b_combo_box_index == 2:
            self.feature_ids = [f.id() for f in self.layer.getFeatures()]

        self.feature_ids.sort()
        print("Features: {} meiliseconds".format((time.time() - start_time)*1000))

        self.refresh_images()

    def refresh_images(self, reverse=False):

        start_time = time.time()  # Start time before the operation
        print("Refreshing images...")

        context = QgsExpressionContext()

        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            self.gridLayout.removeWidget(widget)
            widget.deleteLater()

        filtered_count = len(self.feature_ids)
        total_count = self.layer.featureCount()

        self.setWindowTitle(f"{self.layer.name()} -- Features Total: {total_count}, Filtered: {filtered_count}")

        if not self.image_field or not self.feature_ids:
            self.remove_page_buttons()
            print("Images: {} meiliseconds".format((time.time() - start_time)*1000))  # Print out the time it took
            return

        frames = []
        count = 0

        # although it is not expected the offset to be less than 0 but this is a safeguard if for some error offset is less than 0
        if self.offset < 0:
            reverse = False
            self.offset == 0

        # we will always have one element int the range
        if not reverse or self.offset == 0:
            feature_range = range(self.offset, len(self.feature_ids), 1)
        else:
            feature_range = range(self.offset-1, -1, -1)

        for i in feature_range:
            if len(frames) >= self.limit:
                break
            count += 1

            f_id = self.feature_ids[i]

            try:
                feature = self.layer.getFeature(f_id)
                # doing this at the top so that if this fails we short circuit
                data = None
                # child_feature_display_name = ""

                if not self.relation:
                    field_content = feature[self.image_field]
                else:
                    # get features from the child layer and get the first one
                    child_features = [f for f in self.relation.getRelatedFeatures(feature)]
                    if child_features:
                        child_feature = child_features[0]  # take first child feature
                        field_content = child_feature[self.image_field]
                        # child_feature_display_name =
                    else:
                        continue


                data = ImageFactory.extract_data(field_content, self.field_type)

                if not data:
                    continue

                context.setFeature(feature)
                feature_title = self.feature_title_expression.evaluate(context)

                if not self.relation:
                    frame = FeatureFrame(self.iface, self.canvas, self.layer, feature, feature_title)
                else:
                    frame = ChildrenFeatureFrame(self.iface, self.canvas, self.layer, feature, feature_title, self.relations[self.relation_index-1].referencingLayer(), self.image_field, self.field_type, child_features)

                frame.buildUI(data)
                frames.append(frame)

            except Exception as e:
                # import traceback
                # traceback.print_tb(e.__traceback__)
                self.iface.messageBar().pushMessage("Image Viewer", f"{e.__class__.__name__}: Feature # {f_id}: {str(e)}", level=1, duration=3)

        if reverse:
            frames.reverse()
            self.offset -= count

        self.next_offset = self.offset + count

        row = 0
        col = 0
        for frame in frames:
            self.gridLayout.addWidget(frame, row, col)

            col += 1
            if col > 2:  # Change this number to adjust how many images per row
                col = 0
                row += 1

        if self.offset == 0 and len(frames) < 9: # no pagination required
            self.remove_page_buttons()
        else:
            self.add_page_buttons()

        self.show()
        print("Images: {} meiliseconds".format((time.time() - start_time)*1000))  # Print out the time it took

    def remove_page_buttons(self):
        if self.previousPageButton:
            self.paginationLayout.removeWidget(self.previousPageButton)
            self.previousPageButton.deleteLater()
            self.previousPageButton = None

        if self.nextPageButton:
            self.paginationLayout.removeWidget(self.nextPageButton)
            self.nextPageButton.deleteLater()
            self.nextPageButton = None

    def add_page_buttons(self):
        if not self.previousPageButton:
            self.previousPageButton = QPushButton(" Previous", self)
            self.previousPageButton.setIcon(QgsApplication.getThemeIcon("/mActionArrowLeft.svg"))
            self.previousPageButton.clicked.connect(self.previous_page)
            self.paginationLayout.addWidget(self.previousPageButton)
            self.previousPageButton.setMaximumSize(150, 50)

        self.previousPageButton.setEnabled(self.offset > 0)


        if not self.nextPageButton:
            self.nextPageButton = QPushButton("Next ", self)
            self.nextPageButton.setIcon(QgsApplication.getThemeIcon("/mActionArrowRight.svg"))
            self.nextPageButton.setLayoutDirection(Qt.RightToLeft)
            self.nextPageButton.clicked.connect(self.next_page)
            self.paginationLayout.addWidget(self.nextPageButton)
            self.nextPageButton.setMaximumSize(150, 50)

        self.nextPageButton.setEnabled(self.next_offset < len(self.feature_ids))


    def previous_page(self):
        self.refresh_images(reverse=True)

    def next_page(self):
        self.offset = self.next_offset
        self.refresh_images()

    def closeEvent(self, event):
        # When window is closed, disconnect  signals
        self.layer.displayExpressionChanged.disconnect(self.refresh_display_expression)
        if self.b_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refresh_features)
        elif self.b_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refresh_features)

        # save the dialog's position and size
        self.settings.setValue("geometry", self.saveGeometry())
        self.default_settings.setValue("geometry", self.saveGeometry())

        # remember configuration
        self.settings.setValue("imageField", self.image_field)
        self.settings.setValue("relationIndex", self.relation_index)

        super().closeEvent(event)
