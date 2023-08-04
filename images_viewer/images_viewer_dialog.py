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
from dataclasses import dataclass
from typing import List

from PIL import Image as PILImage
from PyQt5 import uic
from PyQt5.QtCore import QSettings, QSize, Qt, QThread, QVariant, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QPushButton
from qgis.core import (
    QgsApplication,
    QgsExpression,
    QgsExpressionContext,
    QgsFeature,
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


class PageDataWorker(QThread):
    page_ready = pyqtSignal(int, int, list)

    def __init__(
        self,
        layer,
        feature_ids,
        features_data_map,
        image_field,
        field_type,
        page_start,
        page_size,
        relation,
        reverse=False,
    ):
        QThread.__init__(self)
        self.layer = layer
        self.feature_ids = feature_ids
        self.features_data_map = features_data_map
        self.image_field = image_field
        self.field_type = field_type
        self.page_start = page_start
        self.page_size = page_size
        self.relation = relation
        self.reverse = reverse
        self.abandon = False

    def run(self):
        start_time = time.time()  # Start time before the operation
        print("Page data worker starting work ...")

        display_expression = self.layer.displayExpression()
        feature_title_expression = QgsExpression(display_expression)
        context = QgsExpressionContext()

        # although it is not expected the page_start to be less than 0 but this is a safeguard
        # if for some error page_start is less than 0
        # or field changed and that messed up page_start and next_page_start
        if self.page_start < 0:
            self.reverse = False
            self.page_start == 0

        # we will always have one element int the range
        if not self.reverse or self.page_start == 0:
            feature_range = range(self.page_start, len(self.feature_ids), 1)
        else:
            feature_range = range(self.page_start - 1, -1, -1)

        page_f_ids = []
        count = 0

        for i in feature_range:
            if self.abandon:
                print("!!!abondoning page worker")
                return

            if len(page_f_ids) >= self.page_size:
                break

            count += 1
            f_id = self.feature_ids[i]

            if f_id in self.features_data_map:  # do not extract data again
                if self.features_data_map[f_id]:  # if value is None it mean we don't need to have it on page
                    page_f_ids.append(f_id)
                continue
            try:
                feature = self.layer.getFeature(f_id)

                # doing this at the top so that if this fails we short circuit
                data = None
                field_content = None
                child_features = []

                if not self.relation:
                    field_content = feature[self.image_field]
                else:
                    # get features from the child layer and get the first one
                    child_features = [f for f in self.relation.getRelatedFeatures(feature)]
                    if child_features:
                        first_child_feature = child_features[0]  # take first child feature
                        field_content = first_child_feature[self.image_field]

                data = ImageFactory.extract_data(field_content, self.field_type)

                if not data:
                    f_data = None
                else:
                    context.setFeature(feature)
                    f_data = FeatureData(feature, feature_title_expression.evaluate(context), data, child_features)
                    page_f_ids.append(f_id)

                self.features_data_map[f_id] = f_data

            except Exception as e:
                import traceback

                traceback.print_tb(e.__traceback__)
                print(
                    "Image Viewer Page Worker", f"{e.__class__.__name__}: Feature # {f_id}: {str(e)}"
                )  # to do convert it to log

        if self.reverse:
            page_f_ids.reverse()
            self.page_start -= count

        next_page_start = self.page_start + count

        print("Page Data [{}]: {} meiliseconds".format(count, (time.time() - start_time) * 1000))

        if not self.abandon:  # Check if the thread should be abandoned
            print("current lenght of data_store", len(self.features_data_map))
            self.page_ready.emit(self.page_start, next_page_start, page_f_ids)
        else:
            print("!!!abondoning page worker")


@dataclass
class FeatureData:
    """Stores feature data needed to create a frame"""

    feature: QgsFeature
    title: str
    data: PILImage
    children: List[QgsFeature]


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
        self.page_data_worker = None
        self.page_ids = []
        self.features_data_map = {}

        self.layer.displayExpressionChanged.connect(self.handleDisplayExpressionChange)

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
        self.page_start = 0  # inclusive
        self.page_size = 9  # change this to conrol how many frames per page
        self.next_page_start = 0

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
        self.features_data_map.clear()  # clear all cached data

        self.page_data_worker = PageDataWorker(
            self.layer,
            self.feature_ids,
            self.features_data_map,
            self.image_field,
            self.field_type,
            self.page_start,
            self.page_size,
            self.relation,
        )
        self.page_data_worker.page_ready.connect(self.onPageReady)
        self.page_data_worker.start()
        self.page_data_worker.finished.connect(self.page_data_worker.deleteLater)

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
        self.abondonWorkers()

        self.features_worker = FeaturesWorker(self.layer, self.canvas, self.ff_combo_box_index)
        self.features_worker.features_ready.connect(self.onFeaturesReady)
        self.features_worker.start()
        self.features_worker.finished.connect(self.features_worker.deleteLater)

    def onFeaturesReady(self, feature_ids):
        if feature_ids == self.feature_ids:
            return

        self.next_page_start, self.page_start = 0, 0
        self.feature_ids = feature_ids

        self.setWindowTitle(
            f"{self.layer.name()} -- Features Total: {self.layer.featureCount()}, Filtered: {len(self.feature_ids)}"
        )

        self.page_data_worker = PageDataWorker(
            self.layer,
            self.feature_ids,
            self.features_data_map,
            self.image_field,
            self.field_type,
            self.page_start,
            self.page_size,
            self.relation,
        )
        self.page_data_worker.page_ready.connect(self.onPageReady)
        self.page_data_worker.start()
        self.page_data_worker.finished.connect(self.page_data_worker.deleteLater)

    def onPageReady(self, page_start, next_page_start, page_f_ids):
        print("I am here")
        print(page_f_ids)
        self.page_start = page_start
        self.next_page_start = next_page_start

        if self.page_ids != page_f_ids:
            self.page_ids = page_f_ids
            self.refreshGrid()

    def refreshGrid(self):
        # should run in main thread
        start_time = time.time()  # Start time before the operation
        print("Refreshing Grid...")

        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            self.gridLayout.removeWidget(widget)
            widget.deleteLater()

        frames = []

        for f_id in self.page_ids:
            try:
                f_data = self.features_data_map[f_id]

                if not self.relation:
                    frame = FeatureFrame(self.iface, self.canvas, self.layer, f_data.feature, f_data.title)
                else:
                    frame = ChildrenFeatureFrame(
                        self.iface,
                        self.canvas,
                        self.layer,
                        f_data.feature,
                        f_data.title,
                        self.relations[self.relation_index - 1].referencingLayer(),
                        self.image_field,
                        self.field_type,
                        f_data.children,
                    )

                frame.buildUI(f_data.data)
                frames.append(frame)

            except Exception as e:
                import traceback

                traceback.print_tb(e.__traceback__)
                self.iface.messageBar().pushMessage(
                    "Image Viewer", f"{e.__class__.__name__}: Feature # {f_id}: {str(e)}", level=1, duration=3
                )

        print("len of frames", len(frames))
        row = 0
        col = 0
        for frame in frames:
            self.gridLayout.addWidget(frame, row, col)

            col += 1
            if col > 2:  # Change this number to adjust how many images per row
                col = 0
                row += 1

        if self.page_start == 0 and len(frames) < self.page_size:  # no pagination required
            self.removePageButtons()
        else:
            self.addPageButtons()

        self.show()
        print("Grid: {} meiliseconds".format((time.time() - start_time) * 1000))  # Print out the time it took

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

        self.previousPageButton.setEnabled(self.page_start > 0)

        if not self.nextPageButton:
            self.nextPageButton = QPushButton("Next ", self)
            self.nextPageButton.setIcon(QgsApplication.getThemeIcon("/mActionArrowRight.svg"))
            self.nextPageButton.setLayoutDirection(Qt.RightToLeft)
            self.nextPageButton.clicked.connect(self.displayNextPage)
            self.paginationButtonsLayout.addWidget(self.nextPageButton)
            self.nextPageButton.setMaximumSize(150, 50)

        self.nextPageButton.setEnabled(self.next_page_start < len(self.feature_ids))

    def displayPrevPage(self):
        self.page_data_worker = PageDataWorker(
            self.layer,
            self.feature_ids,
            self.features_data_map,
            self.image_field,
            self.field_type,
            self.page_start,
            self.page_size,
            self.relation,
            True,
        )
        self.page_data_worker.page_ready.connect(self.onPageReady)
        self.page_data_worker.start()
        self.page_data_worker.finished.connect(self.page_data_worker.deleteLater)

    def displayNextPage(self):
        self.page_start = self.next_page_start
        self.page_data_worker = PageDataWorker(
            self.layer,
            self.feature_ids,
            self.features_data_map,
            self.image_field,
            self.field_type,
            self.page_start,
            self.page_size,
            self.relation,
        )
        self.page_data_worker.page_ready.connect(self.onPageReady)
        self.page_data_worker.start()
        self.page_data_worker.finished.connect(self.page_data_worker.deleteLater)

    def abondonWorkers(self, features=True, page_data=True):
        if features and self.features_worker:
            self.features_worker.abandon = True
            self.features_worker = None

        if page_data and self.page_data_worker:
            self.page_data_worker.abandon = True
            self.page_data_worker = None

    def closeEvent(self, event):
        """Extends the super.closeEvent"""
        self.abondonWorkers()

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
