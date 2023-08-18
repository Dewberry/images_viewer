from dataclasses import dataclass
from typing import List

from PIL import Image as PILImage
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
from qgis.core import QgsExpression, QgsExpressionContext, QgsFeature

from images_viewer.utils import ImageFactory


@dataclass
class FeatureData:
    """Stores feature data needed to create a frame"""

    feature: QgsFeature
    title: str
    data: PILImage
    children: List[QgsFeature]


class PageDataWorker(QThread):
    """Thread to get data for the page based on page_start index"""

    page_ready = pyqtSignal(int, int, list, list)  # page start, next page start, page_f_ids, error_f_ids
    message_dispatched = pyqtSignal(str, int)

    def __init__(
        self,
        layer,
        feature_ids,
        features_none_data_cache,
        features_broken_data_cache,
        features_data_cache,
        features_frames_cache,
        image_field,
        field_type,
        page_start,
        page_size,
        relation,
        reverse=False,
    ):
        super(QThread, self).__init__()
        self.layer = layer
        self.feature_ids = feature_ids
        self.features_none_data_cache = features_none_data_cache
        self.features_broken_data_cache = features_broken_data_cache
        self.features_data_cache = features_data_cache
        self.features_frames_cache = features_frames_cache
        self.image_field = image_field
        self.field_type = field_type
        self.page_start = page_start
        self.page_size = page_size
        self.relation = relation
        self.reverse = reverse
        self.abandon = False

    def run(self):
        """There must be at least one element in feature_ids"""
        try:
            if not self.image_field:
                self.page_ready.emit(self.page_start, self.page_start, [], [])
                return

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
            error_f_ids = []
            count = 0

            for i in feature_range:
                if self.abandon:
                    # print("!!!abondoning page worker")
                    return

                if len(page_f_ids) >= self.page_size:
                    break

                count += 1
                f_id = self.feature_ids[i]

                if any(
                    [self.features_data_cache.keyExist(f_id), self.features_frames_cache.keyExist(f_id)]
                ):  # cache hit: do not extract data again
                    page_f_ids.append(f_id)
                    continue
                if any(
                    [f_id in self.features_none_data_cache, f_id in self.features_broken_data_cache]
                ):  # cache hit: this feature has no/corrupt data
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

                    if not data:  # feature with no image data
                        self.features_none_data_cache.add(f_id)
                    else:
                        context.setFeature(feature)
                        f_data = FeatureData(feature, feature_title_expression.evaluate(context), data, child_features)
                        page_f_ids.append(f_id)
                        self.features_data_cache.put(f_id, f_data)

                except Exception as e:
                    self.features_broken_data_cache.add(
                        f_id
                    )  # features with corrupt data should not be evaluated again
                    error_f_ids.append(f_id)

            if self.reverse:
                page_f_ids.reverse()
                self.page_start -= count

            next_page_start = self.page_start + count

            if not self.abandon:  # Check if the thread should be abandoned
                self.page_ready.emit(self.page_start, next_page_start, page_f_ids, error_f_ids)

        except Exception as e:  # Catch any exception
            self.message_dispatched.emit("Page Worker: " + repr(e), 2)

    @pyqtSlot()
    def stop(self):
        """Slot to stop the thread's operation safely."""
        self.abandon = True
