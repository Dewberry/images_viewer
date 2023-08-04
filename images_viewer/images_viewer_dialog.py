# -*- coding: utf-8 -*-
"""
This file stores Main Dialog class for Images Viewer. Only functionality related to the main dialog should go here.
Static UI components must reside in the .ui file.
Dynamic components should not be in the .ui file but here.
All methods should be camelCase to follow QTs conventions.
Variables should be snake_case to follow python's guidlines
"""


import os
import time

from PyQt5 import uic
from PyQt5.QtCore import QSettings, QSize, Qt, QThread, QVariant, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QPushButton
from qgis.core import (
    QgsApplication,
    QgsExpression,
    QgsExpressionContext,
    QgsFeatureRequest,
    QgsFields,
    QgsProject,
)

from images_viewer.frames import ChildrenFeatureFrame, FeatureFrame
from images_viewer.utils import ImageFactory, create_tool_button

Ui_Dialog, QtBaseClass = uic.loadUiType(os.path.join(os.path.dirname(__file__), "images_viewer_dialog.ui"))


class FeaturesWorker(QThread):
    features_ready = pyqtSignal(list)

    def __init__(self, layer, canvas, ff_index):
        QThread.__init__(self)
        self.layer = layer
        self.canvas = canvas
        self.abandon = False
        self.ff_index = ff_index

    def run(self):
        start_time = time.time()  # Start time before the operation
        print("Feature worker starting work ...")
        if self.ff_index == 0:
            extent = self.canvas.extent()
            request = QgsFeatureRequest().setFilterRect(extent)
            feature_ids = [f.id() for f in self.layer.getFeatures(request)]
        elif self.ff_index == 1:
            selected_ids = self.layer.selectedFeatureIds()
            feature_ids = selected_ids
        elif self.ff_index == 2:
            feature_ids = [f.id() for f in self.layer.getFeatures()]

        print("Features [{}]: {} meiliseconds".format(len(feature_ids), (time.time() - start_time) * 1000))

        if not self.abandon:  # Check if the thread should be abandoned
            feature_ids.sort()
            self.features_ready.emit(list(feature_ids))
        else:
            print("!!!abondoning")


class ImagesViewerDialog(QtBaseClass, Ui_Dialog):
    """Main window for Images Viewer"""

    def __init__(self, iface, parent=None):
        super(ImagesViewerDialog, self).__init__(parent)
        self.setupUi(self)

        self.iface = iface
        self.layer = self.iface.activeLayer()
        if not self.layer:
            raise ValueError("Layer is not defined")
        self.setWindowTitle(self.layer.name())

        # Restore previous settings
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
        self.features_worker = None
        self.feature_ids = []
        self.data_worker = None

        display_expression = self.layer.displayExpression()
        self.layer.displayExpressionChanged.connect(self.handleDisplayExpressionChange)
        self.feature_title_expression = QgsExpression(display_expression)

        # Top tool bar
        refreshButton = create_tool_button("mActionRefresh.svg", "Refresh", self.refreshFeatures)
        self.topToolBar.setIconSize(QSize(20, 20))
        self.topToolBar.addWidget(refreshButton)

        # Feature Filter
        self.featuresFilterComboBox.addItem(
            QIcon(QgsApplication.getThemeIcon("mActionOpenTableVisible.svg")), "Show Visible Features"
        )  # index 0
        self.featuresFilterComboBox.addItem(
            QIcon(QgsApplication.getThemeIcon("mActionOpenTableSelected.svg")), "Show Selected Features"
        )  # index 1
        self.featuresFilterComboBox.addItem(
            QIcon(QgsApplication.getThemeIcon("mActionOpenTable.svg")), "Show All Features"
        )  # index 2
        self.featuresFilterComboBox.setIconSize(QSize(20, 20))  # set icon
        self.featuresFilterComboBox.currentIndexChanged.connect(self.handleFFComboboxChange)

        self.ff_combo_box_index = 0  # Start with visible
        self.canvas.extentsChanged.connect(self.refreshFeatures)

        # Realtions
        self.relations = QgsProject.instance().relationManager().referencedRelations(self.layer)
        relation_names = [""] + [rel.name() for rel in self.relations]
        # Relation combobox
        rel_icon = QIcon(QgsApplication.getThemeIcon("relation.svg"))
        for item in relation_names:
            self.relationComboBox.addItem(rel_icon, item)
        self.relationComboBox.currentIndexChanged.connect(self.handelRelationChange)

        # Field combobox
        self.filtered_fields = QgsFields()
        self.fieldComboBox.setAllowEmptyFieldName(True)
        self.fieldComboBox.fieldChanged.connect(self.handleFieldChange)

        # Pagination
        self.offset = 0  # inclusive
        self.limit = 9  # change this to conrol how many frames per page
        self.next_offset = 0

        self.previousPageButton = None
        self.nextPageButton = None

        # Instantiate GUI
        self.relation = None
        if relation_index == 0 or relation_index > len(
            self.relations
        ):  # if index 0 or not within len of relations, this can happen if settings are incorrectly read:
            # manually call handelRelationChange() as setCurrentIndex wont call it as signal hasn't chaged
            self.handelRelationChange(0)
        else:
            self.relationComboBox.setCurrentIndex(relation_index)

    def handelRelationChange(self, index):
        """
        Set self.realtion to relation at current index.
        Regenerate field comboBox.
        Call handleFieldChange method at the end.
        """
        self.filtered_fields.clear()
        self.fieldComboBox.clear()
        self.relation_index = index

        if index == 0:
            image_layer = self.layer
            self.relation = None
        else:
            image_layer = self.relations[index - 1].referencingLayer()
            self.relation = self.relations[index - 1]

        # can't use builtin QgsFieldProxyModel.filters because there is no binary filter
        # https://github.com/qgis/QGIS/issues/53940
        for field in image_layer.fields():
            if field.type() in (QVariant.String, QVariant.ByteArray):
                self.filtered_fields.append(field=field)
        self.fieldComboBox.setFields(self.filtered_fields)

        if self.image_field not in [f.name() for f in self.filtered_fields]:
            self.image_field = ""
            self.handleFieldChange("")  # this will call referesh method
        else:
            self.fieldComboBox.setField(self.image_field)  # this will call referesh method

    def handleFieldChange(self, fieldName):
        self.image_field = fieldName
        if not fieldName:
            self.fieldComboBox.setStyleSheet("QComboBox { background-color: #3399ff; }")
        else:
            self.fieldComboBox.setStyleSheet("")
            field_index = self.filtered_fields.indexFromName(fieldName)
            field = self.filtered_fields[field_index]
            self.field_type = field.type()

        self.refreshFeatures()

    def handleDisplayExpressionChange(self):
        display_expression = self.layer.displayExpression()
        self.feature_title_expression = QgsExpression(display_expression)
        # todo: clear frames
        self.refreshFrames()

    def handleFFComboboxChange(self, index):
        if self.ff_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refreshFeatures)
        elif self.ff_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refreshFeatures)

        if index == 0:
            self.canvas.extentsChanged.connect(self.refreshFeatures)
        elif index == 1:
            self.layer.selectionChanged.connect(self.refreshFeatures)

        self.ff_combo_box_index = index

        self.refreshFeatures()

    def refreshFeatures(self):
        if self.features_worker:  # If there is a running loader
            self.features_worker.abandon = True  # Signal it to abandon
            # self.data_worker.abondon = True  # Signal it to abandon

        self.features_worker = FeaturesWorker(self.layer, self.canvas, self.ff_combo_box_index)
        self.features_worker.features_ready.connect(self.onFeaturesReady)
        self.features_worker.start()
        self.features_worker.finished.connect(self.features_worker.deleteLater)

    def onFeaturesReady(self, feature_ids):
        if feature_ids != self.feature_ids:
            self.next_offset, self.offset = 0, 0
            self.feature_ids = feature_ids
            self.refreshFrames()

    def refreshFrames(self, reverse=False):
        start_time = time.time()  # Start time before the operation
        print("Refreshing frames...")

        context = QgsExpressionContext()

        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            self.gridLayout.removeWidget(widget)
            widget.deleteLater()

        filtered_count = len(self.feature_ids)
        total_count = self.layer.featureCount()

        self.setWindowTitle(f"{self.layer.name()} -- Features Total: {total_count}, Filtered: {filtered_count}")

        if not self.image_field or not self.feature_ids:
            self.removePageButtons()
            print("Frames: {} meiliseconds".format((time.time() - start_time) * 1000))  # Print out the time it took
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
            feature_range = range(self.offset - 1, -1, -1)

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
                    frame = ChildrenFeatureFrame(
                        self.iface,
                        self.canvas,
                        self.layer,
                        feature,
                        feature_title,
                        self.relations[self.relation_index - 1].referencingLayer(),
                        self.image_field,
                        self.field_type,
                        child_features,
                    )

                frame.buildUI(data)
                frames.append(frame)

            except Exception as e:
                import traceback

                traceback.print_tb(e.__traceback__)
                self.iface.messageBar().pushMessage(
                    "Image Viewer", f"{e.__class__.__name__}: Feature # {f_id}: {str(e)}", level=1, duration=3
                )

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

        if self.offset == 0 and len(frames) < 9:  # no pagination required
            self.removePageButtons()
        else:
            self.addPageButtons()

        self.show()
        print("Frames: {} meiliseconds".format((time.time() - start_time) * 1000))  # Print out the time it took

    def removePageButtons(self):
        if self.previousPageButton:
            self.paginationButtonsLayout.removeWidget(self.previousPageButton)
            self.previousPageButton.deleteLater()
            self.previousPageButton = None

        if self.nextPageButton:
            self.paginationButtonsLayout.removeWidget(self.nextPageButton)
            self.nextPageButton.deleteLater()
            self.nextPageButton = None

    def addPageButtons(self):
        if not self.previousPageButton:
            self.previousPageButton = QPushButton(" Previous", self)
            self.previousPageButton.setIcon(QgsApplication.getThemeIcon("/mActionArrowLeft.svg"))
            self.previousPageButton.clicked.connect(self.displayPrevPage)
            self.paginationButtonsLayout.addWidget(self.previousPageButton)
            self.previousPageButton.setMaximumSize(150, 50)

        self.previousPageButton.setEnabled(self.offset > 0)

        if not self.nextPageButton:
            self.nextPageButton = QPushButton("Next ", self)
            self.nextPageButton.setIcon(QgsApplication.getThemeIcon("/mActionArrowRight.svg"))
            self.nextPageButton.setLayoutDirection(Qt.RightToLeft)
            self.nextPageButton.clicked.connect(self.displayNextPage)
            self.paginationButtonsLayout.addWidget(self.nextPageButton)
            self.nextPageButton.setMaximumSize(150, 50)

        self.nextPageButton.setEnabled(self.next_offset < len(self.feature_ids))

    def displayPrevPage(self):
        self.refreshFrames(reverse=True)

    def displayNextPage(self):
        self.offset = self.next_offset
        self.refreshFrames()

    def closeEvent(self, event):
        """Extends the super.closeEvent"""

        # When window is closed, disconnect  signals
        self.layer.displayExpressionChanged.disconnect(self.handleDisplayExpressionChange)
        if self.ff_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refreshFeatures)
        elif self.ff_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refreshFeatures)

        # save the dialog's position and size
        self.settings.setValue("geometry", self.saveGeometry())
        self.default_settings.setValue("geometry", self.saveGeometry())

        # remember configuration
        self.settings.setValue("imageField", self.image_field)
        self.settings.setValue("relationIndex", self.relation_index)

        super().closeEvent(event)
