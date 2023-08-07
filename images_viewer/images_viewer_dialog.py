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
from PyQt5.QtCore import QSettings, QSize, QVariant
from PyQt5.QtGui import QIcon
from qgis.core import (
    QgsApplication,
    QgsExpression,
    QgsFields,
    QgsProject,
    QgsVectorLayer,
)

from images_viewer.frames import ChildrenFeatureFrame, FeatureFrame
from images_viewer.utils import FeaturesWorker, PageDataWorker, create_tool_button

Ui_Dialog, QtBaseClass = uic.loadUiType(os.path.join(os.path.dirname(__file__), "images_viewer_dialog.ui"))


class ImagesViewerDialog(QtBaseClass, Ui_Dialog):
    """Main window for Images Viewer"""

    def __init__(self, iface, parent=None):
        self.iface = iface
        self.layer = self.iface.activeLayer()
        if not self.layer:
            raise ValueError("Layer is not defined")
        if not type(self.layer) == QgsVectorLayer:
            raise ValueError("Layer is not a Vector Layer")

        super(ImagesViewerDialog, self).__init__(parent)
        self.setupUi(self)
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
        self.features_frames_map = {}

        self.layer.displayExpressionChanged.connect(self.handleDisplayExpressionChange)

        # Top tool bar
        refreshButton = create_tool_button("mActionRefresh.svg", "Refresh", self.handelHardRefresh)
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
        self.previousPageButton.clicked.connect(self.displayPrevPage)
        self.nextPageButton.clicked.connect(self.displayNextPage)

        # Instantiate GUI
        self.relation = None
        if relation_index == 0 or relation_index > len(
            self.relations
        ):  # if index 0 or not within len of relations, this can happen if settings are incorrectly read:
            # manually call handelRelationChange() as setCurrentIndex wont call it as signal hasn't chaged
            self.handelRelationChange(0)
        else:
            self.relationComboBox.setCurrentIndex(relation_index)

        self.refreshFeatures()

    def handelHardRefresh(self):
        self.abondonWorkers(True, True)
        self.clearCaches()
        self.refreshFeatures()  # this will clear the feature_ids anyways

    def handelRelationChange(self, index):
        """
        Set self.realtion to relation at current index.
        Regenerate field comboBox.
        Call handleFieldChange method at the end.
        """
        self.clearCaches()
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
            self.handleFieldChange("")
        else:
            self.fieldComboBox.setField(self.image_field)

    def handleFieldChange(self, fieldName):
        self.abondonWorkers(True, True)
        self.clearCaches()

        self.image_field = fieldName
        if not fieldName:
            self.fieldComboBox.setStyleSheet("QComboBox { background-color: #3399ff; }")
            self.field_type = QVariant.String
            # the page_data_worker will short circuit without doing anything if not self.image_field
            # this will allow frames to refresh to be empty
        else:
            self.fieldComboBox.setStyleSheet("")
            field_index = self.filtered_fields.indexFromName(fieldName)
            field = self.filtered_fields[field_index]
            self.field_type = field.type()

        # we are not calling features refresh because we don't want to lose the current page start
        # this will be useful when a layer has images in two
        self.startPageWorker(self.page_start)

    def handleDisplayExpressionChange(self):
        display_expression = self.layer.displayExpression()
        self.feature_title_expression = QgsExpression(display_expression)

        # we are not calling features refresh because we don't want to lose the current page start
        # this will be useful when a layer has images in two
        self.startPageWorker(self.page_start)

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
        self.abondonWorkers(True, True)

        self.features_worker = FeaturesWorker(self.layer, self.canvas, self.ff_combo_box_index)
        self.features_worker.features_ready.connect(self.onFeaturesReady)
        self.features_worker.start()
        self.features_worker.finished.connect(self.features_worker.deleteLater)

    def onFeaturesReady(self, feature_ids):
        if feature_ids == self.feature_ids:
            return

        self.next_page_start, self.page_start = 0, 0
        self.feature_ids = feature_ids
        self.startPageWorker(0)

        self.setWindowTitle(
            f"{self.layer.name()} -- Features Total: {self.layer.featureCount()}, Filtered: {len(self.feature_ids)}"
        )

    def startPageWorker(self, page_start, reverse=False, connect=True):
        if not self.feature_ids:
            return

        self.abondonWorkers(page_data=True)
        self.page_data_worker = PageDataWorker(
            self.layer,
            self.feature_ids,
            self.features_data_map,
            self.image_field,
            self.field_type,
            page_start,
            self.page_size,
            self.relation,
            reverse,
        )
        if connect:
            self.page_data_worker.page_ready.connect(self.onPageReady)
        self.page_data_worker.start()
        self.page_data_worker.finished.connect(self.page_data_worker.deleteLater)

    def onPageReady(self, page_start, next_page_start, page_f_ids, error_f_ids):
        if error_f_ids:
            self.iface.messageBar().pushMessage(
                "Images Viewer: Extracting Data:", f"Error on {len(error_f_ids)} features. Ids: {error_f_ids}", level=1
            )
        self.page_start = page_start
        self.next_page_start = next_page_start

        if self.page_ids != page_f_ids:
            self.page_ids = page_f_ids
            self.refreshGrid()
            self.refreshPageButtons()

        # get data for the next page in anticipation of user clicking next soon
        # do not connect to its signal, so that it doesn't actually display the next page
        self.startPageWorker(self.next_page_start, connect=False)

    def refreshGrid(self):
        # should run in main thread
        start_time = time.time()  # Start time before the operation
        print("Refreshing Grid...")

        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            self.gridLayout.removeWidget(widget)
            widget.hide()  # hide it for now, we will delete through cache

        frames = []
        error_f_ids = []

        for f_id in self.page_ids:
            try:
                if f_id in self.features_frames_map:  # cache hit
                    frame = self.features_frames_map[f_id]
                    frame.show()
                else:  # cache miss
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
                    # free up memory by deleting the data from data cache and store frame in frame cache
                    self.features_data_map.pop(f_id, None)
                    self.features_frames_map[f_id] = frame

                frames.append(frame)

            except Exception as e:
                # import traceback
                # traceback.print_tb(e.__traceback__)
                error_f_ids.append(f_id)

        if error_f_ids:
            self.iface.messageBar().pushMessage(
                "Images Viewer: Creating Frames:",
                f"Error on {len(error_f_ids)} features. Ids: {error_f_ids}",
                level=1,
            )

        row = 0
        col = 0
        for frame in frames:
            self.gridLayout.addWidget(frame, row, col)

            col += 1
            if col > 2:  # Change this number to adjust how many images per row
                col = 0
                row += 1

        print("Grid: {} meiliseconds".format((time.time() - start_time) * 1000))  # Print out the time it took
        print("current length of frames store", len(self.features_frames_map))

    def refreshPageButtons(self):
        self.previousPageButton.setEnabled(self.page_start > 0)
        self.nextPageButton.setEnabled(self.next_page_start < len(self.feature_ids))

    def displayPrevPage(self):
        self.previousPageButton.setEnabled(False)
        self.abondonWorkers(page_data=True)
        self.startPageWorker(self.page_start, reverse=True)

    def displayNextPage(self):
        self.nextPageButton.setEnabled(False)  # prevents crashing from multiple clicks
        self.page_start = self.next_page_start
        self.startPageWorker(self.page_start)

    def abondonWorkers(self, features=False, page_data=False):
        if features and self.features_worker:
            self.features_worker.abandon = True
            self.features_worker = None

        if page_data and self.page_data_worker:
            self.page_data_worker.abandon = True
            self.page_data_worker = None

    def clearCaches(self):
        self.features_data_map.clear()  # clear all cached data
        self.features_frames_map.clear()

    def closeEvent(self, event):
        """Extends the super.closeEvent"""
        self.abondonWorkers(True, True)

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
