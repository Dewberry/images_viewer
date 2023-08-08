# import time

from PyQt5.QtCore import QThread, pyqtSignal
from qgis.core import QgsFeatureRequest


class FeaturesWorker(QThread):
    """Thread to get feature ids based on filter"""

    features_ready = pyqtSignal(list)
    message_dispatched = pyqtSignal(str, int)

    def __init__(self, layer, extent, ff_index):
        super(QThread, self).__init__()
        self.layer = layer
        self.extent = extent
        self.abandon = False
        self.ff_index = ff_index

    def run(self):
        try:
            feature_ids = []
            if self.ff_index == 0:
                request = QgsFeatureRequest().setFilterRect(self.extent)
                for feat in self.layer.getFeatures(request):
                    if self.abandon:
                        # print("!!!abondoning features worker")
                        return
                    feature_ids.append(feat.id())
            elif self.ff_index == 1:
                feature_ids = self.layer.selectedFeatureIds()
            elif self.ff_index == 2:
                selected_ids = set(self.layer.selectedFeatureIds())
                request = QgsFeatureRequest().setFilterRect(self.extent)
                for feat in self.layer.getFeatures(request):
                    if self.abandon:
                        return
                    if feat.id() in selected_ids:
                        feature_ids.append(feat.id())
            elif self.ff_index == 3:
                for feat in self.layer.getFeatures():
                    if self.abandon:
                        return
                    feature_ids.append(feat.id())

            if not self.abandon:  # Check if the thread should be abandoned
                feature_ids.sort()
                self.features_ready.emit(feature_ids)

        except Exception as e:  # Catch any exception
            self.message_dispatched.emit("Features Worker: " + repr(e), 2)
