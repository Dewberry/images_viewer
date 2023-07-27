from typing import List
from PyQt5.QtWidgets import  QToolBar
from PyQt5.QtCore import QSize
from qgis.core import QgsFeature

from PIL import Image as PILImage
from functools import partial

from .utils import create_tool_button
from .feature_frame import FeatureFrame

from .image_factory import ImageFactory


class ChildrenFeatureFrame(FeatureFrame):

    def __init__(self, iface, canvas, feature_layer, feature, feature_title="", image_field = "", field_type = None, children: List[QgsFeature]= [], parent=None):
        super().__init__(iface, canvas, feature_layer, feature, feature_title, parent)

        self.image_field = image_field
        self.field_type = field_type
        self.children_features = children
        self.current_child_index = 0
        self.prevButton = None
        self.nextButton = None


    def buildUI(self, data: PILImage):
        # we get first time data from ouside, so that it can be generated outside of main thread
        self.frame_layout.addWidget(self.createTitleLabel(self.feature_title))
        self.frame_layout.addWidget(self.createTitleLabel(self.feature_title)) # to do make it subfeature title

        self.frame_layout.addWidget(self.createImageWidget(data))
        self.toolbar_layout.addWidget(self.createFeatureToolBar())
        self.toolbar_layout.addStretch()
        self.toolbar_layout.addWidget(self._createChildrenToolBar())
        self.frame_layout.addLayout(self.toolbar_layout)

    # def getChildTitle(self, )

    def _createChildrenToolBar(self) -> QToolBar:
        self.prevButton = create_tool_button('mActionArrowLeft.svg', "Previous",  partial(self._switch_child, -1))
        self.prevButton.setEnabled(False)
        self.nextButton = create_tool_button('mActionArrowRight.svg', "Next", partial(self._switch_child, 1))
        if  len(self.children_features) == 1:
            self.nextButton.setEnabled(False)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(20, 20))
        toolbar.addWidget(self.prevButton)
        toolbar.addWidget(self.nextButton)

        return toolbar

    def _switch_child(self,  direction):
        # function to switch between child features
        new_index = (self.current_child_index  + direction)
        self.prevButton.setEnabled(new_index > 0)
        self.nextButton.setEnabled(new_index < len(self.children_features) - 1)
        data = self._get_child_image_data(new_index)

        new_image_widget = self.createImageWidget(data)
        old_image_widget = self.frame_layout.itemAt(2).widget()
        self.frame_layout.replaceWidget(old_image_widget, new_image_widget)
        # # Remove the old widget from the layout
        # self.frame_layout.removeWidget(old_image_widget)



        # self.frame_layout.insertWidget(2, new_image_widget)
        self.current_child_index = new_index

        # Delete the old widget
        old_image_widget.setParent(None)
        old_image_widget.deleteLater()


    def _get_child_image_data(self, index):
        data = None
        child_feature = self.children_features[index]  # take first child feature
        field_content = child_feature[self.image_field]

        data = ImageFactory.extract_data(field_content, self.field_type)

        return data