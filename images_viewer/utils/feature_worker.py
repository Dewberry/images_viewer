import time

from PyQt5.QtCore import QThread, pyqtSignal
from qgis.core import QgsFeatureRequest


class FeaturesWorker(QThread):
    """Thread to get feature ids based on filter"""

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
