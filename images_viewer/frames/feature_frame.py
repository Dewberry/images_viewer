from PIL import Image as PILImage
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
)

from images_viewer.utils import ImageFactory, create_tool_button


class FeatureFrame(QFrame):
    def __init__(self, iface, canvas, feature_layer, feature, feature_title="", parent=None):
        super().__init__(parent)

        self.iface = iface
        self.canvas = canvas
        self.layer = feature_layer

        self.feature = feature
        self.feature_title = feature_title

        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setStyleSheet("QFrame {color: #BEBEBE;}")
        self.setMinimumSize(400, 600)

        self.frame_layout = QVBoxLayout(self)
        self.frame_layout.setContentsMargins(0, 0, 0, 0)  # (left, top, right, bottom)
        self.frame_layout.setSpacing(0)  # (left, top, right, bottom) # we will add manual space when we need it

        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)  # (left, top, right, bottom)

    def buildUI(self, data: PILImage):
        self.frame_layout.addWidget(self.createTitleLabel(self.feature_title))
        self.frame_layout.addWidget(self.createImageWidget(data))
        self.toolbar_layout.addWidget(self.createFeatureToolBar())
        self.toolbar_layout.addStretch()
        self.frame_layout.addSpacing(2)
        self.frame_layout.addLayout(self.toolbar_layout)

    def createTitleLabel(self, text: str, font_size: int = 13, bg_color: str = "white", min_height=35) -> QLabel:
        title_label = QLabel()
        title_label.setText(str(text))
        title_label.setStyleSheet(
            f"text-align:center; font-size:{font_size}px; font: bold; color: black; background-color: {bg_color};  padding: 5px; border-bottom: 1px solid #BEBEBE;"
        )
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setMinimumHeight(min_height)
        title_label.setWordWrap(True)

        return title_label

    def createImageWidget(self, data: PILImage):
        imageWidget = ImageFactory.create_widget(data)
        imageWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        return imageWidget

    def createFeatureToolBar(self) -> QToolBar:
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(20, 20))

        selectButton = create_tool_button("mIconSelected.svg", "Select this feature", self.select_feature)
        toolbar.addWidget(selectButton)

        zoomButton = create_tool_button("mActionZoomTo.svg", "Zoom to this feature", self.zoom_to_feature)
        toolbar.addWidget(zoomButton)

        panButton = create_tool_button("mActionPanTo.svg", "Pan to this feature", self.pan_to_feature)
        toolbar.addWidget(panButton)

        panFlashButton = create_tool_button(
            "mActionPanHighlightFeature.svg", "Pan and Flash this feature", self.pan_flash_feature
        )
        toolbar.addWidget(panFlashButton)

        flashButton = create_tool_button("mActionHighlightFeature.svg", "Flash this feature", self.flash_feature)
        toolbar.addWidget(flashButton)

        return toolbar

    def flash_feature(self):
        self.canvas.flashFeatureIds(self.layer, [self.feature.id()])

    def select_feature(self):
        self.layer.selectByIds([self.feature.id()])

    def pan_flash_feature(self):
        self.canvas.setExtent(self.feature.geometry().boundingBox())
        self.canvas.refresh()
        self.canvas.flashFeatureIds(self.layer, [self.feature.id()])

    def pan_to_feature(self):
        self.canvas.setExtent(self.feature.geometry().boundingBox())
        self.canvas.refresh()

    def zoom_to_feature(self):
        self.canvas.zoomToFeatureIds(self.layer, [self.feature.id()])

    # Other functions such as flash_feature, select_feature, pan_flash_feature, pan_to_feature, zoom_to_feature should be moved to this class as well.
