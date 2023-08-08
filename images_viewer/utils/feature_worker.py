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
        feature_ids = []
        if self.ff_index == 0:
            extent = self.canvas.extent()
            request = QgsFeatureRequest().setFilterRect(extent)
            for feat in self.layer.getFeatures(request):
                if self.abandon:
                    print("!!!abondoning features worker")
                    return
                feature_ids.append(feat.id())
        elif self.ff_index == 1:
            feature_ids = self.layer.selectedFeatureIds()
        elif self.ff_index == 2:
            selected_ids = set(self.layer.selectedFeatureIds())
            extent = self.canvas.extent()
            request = QgsFeatureRequest().setFilterRect(extent)
            for feat in self.layer.getFeatures(request):
                if self.abandon:
                    print("!!!abondoning features worker")
                    return
                if feat.id() in selected_ids:
                    feature_ids.append(feat.id())
        elif self.ff_index == 3:
            for feat in self.layer.getFeatures():
                if self.abandon:
                    print("!!!abondoning features worker")
                    return
                feature_ids.append(feat.id())

        print("Features [{}]: {} meiliseconds".format(len(feature_ids), (time.time() - start_time) * 1000))

        if not self.abandon:  # Check if the thread should be abandoned
            feature_ids.sort()
            self.features_ready.emit(feature_ids)
        else:
            print("!!!abondoning features worker")
