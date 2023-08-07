import io
import os
from urllib.parse import urlparse

import requests
from PIL import Image as PILImage
from PIL.ExifTags import TAGS
from PyQt5.QtCore import QVariant

from images_viewer.widgets import Image360Widget, ImageWidget


class ImageFactory:
    @classmethod
    def extract_data(cls, field_content, field_type):
        """Given some data and the type of data, convert data to PIL Image"""
        if not field_content:
            return None

        if field_type == QVariant.ByteArray:
            data = PILImage.open(io.BytesIO(field_content))
        elif field_type == QVariant.String:
            if os.path.isfile(field_content):
                data = PILImage.open(field_content)
            elif urlparse(field_content).scheme in ["http", "https"]:
                response = requests.get(field_content)
                data = PILImage.open(io.BytesIO(response.content))
            else:
                raise ValueError("Invalid photo source. Must be file or url")
        else:
            raise ValueError("Unacceptable field type")

        return data

    @classmethod
    def create_widget(cls, data):
        """Creates an Image Widget based on the type of Image Static vs 360"""
        if cls.is_360(data):
            return Image360Widget(data)
        else:
            return ImageWidget(data)

    @staticmethod
    def is_360(image):
        """Takes in an image object, returns a boolean indicating whether that image is a 360 image or not"""
        width, height = image.size
        exifdata = image.getexif()
        # looping through all the tags present in exifdata
        has_gpano = False
        for tagid in exifdata:
            # getting the tag name instead of tag id
            tagname = TAGS.get(tagid, tagid)
            # passing the tagid to get its respective value
            value = exifdata.get(tagid)
            # print(f"{tagname:25}: {value}")
            if tagname == "XMLPacket":
                xml = value.decode("utf-8")
                if "GPano" in xml or "XMP-GPano" in xml:
                    has_gpano = True
                break
        has_360_dimensions = True if width >= height * 2 else False
        if has_360_dimensions and not has_gpano:
            # raise ValueError("Unclear whether image is regular or 360")
            return True
        elif has_gpano and not has_360_dimensions:
            # raise ValueError("Unclear whether image is regular or 360")
            return True
        elif has_360_dimensions and has_gpano:
            return True
        else:
            return False
