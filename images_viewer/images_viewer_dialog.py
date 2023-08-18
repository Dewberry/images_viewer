# -*- coding: utf-8 -*-
"""
This file stores Main Dialog class for Images Viewer. Only functionality related to the main dialog should go here.
Static UI components must reside in the .ui file.
Dynamic components should not be in the .ui file but here.
All methods should be camelCase to follow QTs conventions.
Variables should be snake_case to follow python's guidlines
"""


import os

from PyQt5 import uic
from PyQt5.QtCore import QSettings, QSize, QThread, QVariant
from PyQt5.QtGui import QIcon, QPalette
from qgis.core import QgsApplication, QgsFields, QgsProject, QgsVectorLayer

from images_viewer.frames import ChildrenFeatureFrame, FeatureFrame
from images_viewer.utils import (
    FRAMES_CACHE_CAPACITY,
    FeatureDataLRUCache,
    FeaturesWorker,
    PageDataWorker,
    WidgetLRUCache,
    create_tool_button,
)

# import time


Ui_Dialog, QtBaseClass = uic.loadUiType(os.path.join(os.path.dirname(__file__), "images_viewer_dialog.ui"))

current_dir = os.path.dirname(os.path.abspath(__file__))
visible_selection_icon_path = os.path.join(current_dir, "resources/mActionOpenTableVisbileSelected.svg")


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

        # set inactive color to active, this is necessary because we expect users to work
        # in main QGIS window, and this window may remain inactive
        palette = self.busyBar.palette()
        active_color = palette.color(QPalette.Active, QPalette.Highlight)
        palette.setColor(QPalette.Inactive, QPalette.Highlight, active_color)
        self.busyBar.setPalette(palette)

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
        self.busy_bar_count = 0
        self.features_worker = None
        self.feature_ids = []
        self.page_data_worker = None
        self.page_ids = []
        self.page_size = 9  # change this to conrol how many frames per page
        self.features_none_data_cache = set()
        self.features_broken_data_cache = set()
        self.features_data_cache = FeatureDataLRUCache(self.page_size * 2)
        self.features_frames_cache = WidgetLRUCache(FRAMES_CACHE_CAPACITY)

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
            QIcon(visible_selection_icon_path), "Show Selected Visible Features"
        )  # index 2
        self.featuresFilterComboBox.addItem(
            QIcon(QgsApplication.getThemeIcon("mActionOpenTable.svg")), "Show All Features"
        )  # index 3
        self.featuresFilterComboBox.setIconSize(QSize(20, 20))  # set icon

        if self.layer.isSpatial():
            self.ff_combo_box_index = 0  # Start with visible
            self.canvas.extentsChanged.connect(self.refreshFeatures)
        else:
            for index in [0, 2]:
                item = self.featuresFilterComboBox.model().item(index)
                item.setEnabled(False)
            self.ff_combo_box_index = 3
            self.featuresFilterComboBox.setCurrentIndex(3)
        self.featuresFilterComboBox.currentIndexChanged.connect(self.handleFFComboboxChange)

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
        self.feature_ids = []
        self.refreshFeatures()

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
        # this will be useful when a layer has images in two fields
        self.startPageWorker(self.page_start)

    def handleDisplayExpressionChange(self):
        # we are not calling features refresh because we don't want to lose the current page start
        # this will be useful when a layer has images in two fields
        self.clearGrid()
        self.clearCaches()
        self.startPageWorker(self.page_start)

    def handleFFComboboxChange(self, index):
        if self.ff_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refreshFeatures)
        elif self.ff_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refreshFeatures)
        elif self.ff_combo_box_index == 2:
            self.layer.selectionChanged.disconnect(self.refreshFeatures)
            self.canvas.extentsChanged.disconnect(self.refreshFeatures)

        if index == 0:
            self.canvas.extentsChanged.connect(self.refreshFeatures)
        elif index == 1:
            self.layer.selectionChanged.connect(self.refreshFeatures)
        elif index == 2:
            self.layer.selectionChanged.connect(self.refreshFeatures)
            self.canvas.extentsChanged.connect(self.refreshFeatures)

        self.ff_combo_box_index = index

        self.refreshFeatures()

    def refreshFeatures(self):
        self.abondonWorkers(True, True)

        extent = self.canvas.extent()
        self.features_thread = QThread()
        self.features_worker = FeaturesWorker(self.layer, extent, self.ff_combo_box_index)
        self.features_worker.moveToThread(self.features_thread)
        self.features_thread.started.connect(self.features_worker.run)
        self.features_worker.finished.connect(self.busyBarDecrement)
        self.features_worker.finished.connect(self.features_thread.quit)
        self.features_worker.finished.connect(self.features_worker.deleteLater)
        self.features_thread.finished.connect(self.features_thread.deleteLater)
        self.features_worker.features_ready.connect(self.onFeaturesReady)
        self.features_worker.message_dispatched.connect(self.handleWorkersMessage)
        self.busyBarIncrement()
        self.features_worker.start()  # this should be feautures_thread.start() but that is crashing QGIS

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
            self.clearGrid()
            self.refreshPageButtons()
            return

        self.abondonWorkers(page_data=True)
        self.page_data_worker = PageDataWorker(
            self.layer,
            self.feature_ids,
            self.features_none_data_cache,
            self.features_broken_data_cache,
            self.features_data_cache,
            self.features_frames_cache,
            self.image_field,
            self.field_type,
            page_start,
            self.page_size,
            self.relation,
            reverse,
        )
        if connect:
            self.busyBarIncrement()
            self.page_data_worker.page_ready.connect(self.onPageReady)
            self.page_data_worker.finished.connect(self.busyBarDecrement)
        self.page_data_worker.message_dispatched.connect(self.handleWorkersMessage)
        self.page_data_worker.finished.connect(self.page_data_worker.deleteLater)
        self.page_data_worker.start()

    def onPageReady(self, page_start, next_page_start, page_f_ids, error_f_ids):
        if error_f_ids:
            self.iface.messageBar().pushMessage(
                "Images Viewer: Extracting Data:", f"Error on {len(error_f_ids)} features. Ids: {error_f_ids}", level=1
            )
        self.page_start = page_start
        self.next_page_start = next_page_start

        # we can do a check here that if page_ids is same as previous and fields are also same
        # then do not refresh, but that is not worth the effort since refeshing grid would take few meiliseconds
        # data would already be in cache
        self.page_ids = page_f_ids
        self.refreshGrid()
        self.refreshPageButtons()

        # get data for the next page in anticipation of user clicking next soon
        # do not connect to its signal, so that it doesn't actually display the next page
        self.startPageWorker(self.next_page_start, connect=False)

    def handleWorkersMessage(self, message: str, level: int):
        self.iface.messageBar().pushMessage(message, level)

    def busyBarIncrement(self):
        self.busy_bar_count += 1
        self.busyBar.setVisible(True)
        self.busyBar.setToolTip(f"Running Tasks: {self.busy_bar_count}")

    def busyBarDecrement(self):
        self.busy_bar_count -= 1
        if self.busy_bar_count == 0:
            self.busyBar.setVisible(False)
        self.busyBar.setToolTip(f"Running Tasks: {self.busy_bar_count}")

    def clearGrid(self):
        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            self.gridLayout.removeWidget(widget)
            widget.hide()  # hide it for now, we will delete through cache

    def refreshGrid(self):
        # should run in main thread
        # start_time = time.time()  # Start time before the operation
        # print("Refreshing Grid...")

        self.clearGrid()

        frames = []
        error_f_ids = []

        for f_id in self.page_ids:
            try:
                if self.features_frames_cache.keyExist(f_id):  # cache hit
                    frame = self.features_frames_cache.get(f_id)
                    frame.show()
                else:  # cache miss
                    f_data = self.features_data_cache.get(f_id)

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
                    self.features_frames_cache.put(f_id, frame)

                frames.append(frame)

            except Exception as e:
                # import traceback
                # traceback.print_tb(e.__traceback__)
                # print(repr(e))
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

        # print("Grid: {} meiliseconds".format((time.time() - start_time) * 1000))  # Print out the time it took
        # print("current length of frames store", self.features_frames_cache.length())

    def refreshPageButtons(self):
        self.previousPageButton.setEnabled(self.page_start > 0)
        self.nextPageButton.setEnabled(self.next_page_start and self.next_page_start < len(self.feature_ids))

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
            self.features_worker.stop()
            self.features_thread = None
            self.features_worker = None

        if page_data and self.page_data_worker:
            self.page_data_worker.stop()
            self.page_data_worker = None

    def clearCaches(self):
        self.features_frames_cache.clear()
        self.features_none_data_cache.clear()
        self.features_broken_data_cache.clear()
        self.features_data_cache.clear()  # clear all cached data

    def closeEvent(self, event):
        """Extends the super.closeEvent"""
        self.abondonWorkers(True, True)
        self.clearCaches()  # release resources

        # When window is closed, disconnect  signals
        self.layer.displayExpressionChanged.disconnect(self.handleDisplayExpressionChange)
        if self.ff_combo_box_index == 0:
            self.canvas.extentsChanged.disconnect(self.refreshFeatures)
        elif self.ff_combo_box_index == 1:
            self.layer.selectionChanged.disconnect(self.refreshFeatures)
        elif self.ff_combo_box_index == 2:
            self.layer.selectionChanged.disconnect(self.refreshFeatures)
            self.canvas.extentsChanged.disconnect(self.refreshFeatures)

        # save the dialog's position and size
        self.settings.setValue("geometry", self.saveGeometry())
        self.default_settings.setValue("geometry", self.saveGeometry())

        # remember configuration
        self.settings.setValue("imageField", self.image_field)
        self.settings.setValue("relationIndex", self.relation_index)

        super().closeEvent(event)
