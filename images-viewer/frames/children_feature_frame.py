from functools import partial
from typing import List

from images_viewer.core.utils import create_tool_button
from images_viewer.frames import FeatureFrame
from images_viewer.frames.image_factory import ImageFactory
from PIL import Image as PILImage
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QToolBar
from qgis.core import QgsExpression, QgsExpressionContext, QgsFeature


class ChildrenFeatureFrame(FeatureFrame):
    def __init__(
        self,
        iface,
        canvas,
        feature_layer,
        feature,
        feature_title="",
        children_layer=None,
        image_field="",
        field_type=None,
        children: List[QgsFeature] = [],
        parent=None,
    ):
        super().__init__(iface, canvas, feature_layer, feature, feature_title, parent)

        self.image_field = image_field
        self.field_type = field_type
        self.children_features = children

        display_expression = children_layer.displayExpression()
        self.child_title_expression = QgsExpression(display_expression)

        self.current_child_index = 0
        self.prevButton = None
        self.nextButton = None

    def buildUI(self, data: PILImage):
        # we get first time data from ouside, so that it can be generated outside of main thread
        self.frame_layout.addWidget(self.createTitleLabel(self.feature_title))

        child_feature = self.children_features[0]
        context = QgsExpressionContext()
        context.setFeature(child_feature)
        child_feature_title = self.child_title_expression.evaluate(context)
        self.frame_layout.addWidget(
            self.createTitleLabel(child_feature_title, 12, "#E9E7E3", 30)
        )  # to do make it subfeature title

        self.frame_layout.addWidget(self.createImageWidget(data))
        self.toolbar_layout.addWidget(self.createFeatureToolBar())
        self.toolbar_layout.addStretch()
        self.toolbar_layout.addWidget(self._createChildrenToolBar())
        self.frame_layout.addLayout(self.toolbar_layout)

    # def getChildTitle(self, )

    def _createChildrenToolBar(self) -> QToolBar:
        self.prevButton = create_tool_button("mActionArrowLeft.svg", "Previous", partial(self._switch_child, -1))
        self.prevButton.setEnabled(False)
        self.nextButton = create_tool_button("mActionArrowRight.svg", "Next", partial(self._switch_child, 1))
        if len(self.children_features) == 1:
            self.nextButton.setEnabled(False)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(20, 20))
        toolbar.addWidget(self.prevButton)
        toolbar.addWidget(self.nextButton)

        return toolbar

    def _switch_child(self, direction):
        # function to switch between child features
        new_index = self.current_child_index + direction
        self.prevButton.setEnabled(new_index > 0)
        self.nextButton.setEnabled(new_index < len(self.children_features) - 1)

        child_feature = self.children_features[new_index]

        context = QgsExpressionContext()
        context.setFeature(child_feature)
        child_feature_title = self.child_title_expression.evaluate(context)
        new_child_title_widget = self.createTitleLabel(child_feature_title, 12, "#E9E7E3")
        old_child_title_widget = self.frame_layout.itemAt(1).widget()
        self.frame_layout.replaceWidget(old_child_title_widget, new_child_title_widget)

        data = self._get_child_image_data(child_feature)
        new_image_widget = self.createImageWidget(data)
        old_image_widget = self.frame_layout.itemAt(2).widget()
        self.frame_layout.replaceWidget(old_image_widget, new_image_widget)

        self.current_child_index = new_index

        # Delete the old widget
        old_image_widget.setParent(None)
        old_image_widget.deleteLater()
        old_child_title_widget.setParent(None)
        old_child_title_widget.deleteLater()

    def _get_child_image_data(self, feature):
        data = None
        field_content = feature[self.image_field]

        data = ImageFactory.extract_data(field_content, self.field_type)

        return data
