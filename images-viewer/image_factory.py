from PIL.ExifTags import TAGS
from .image360_widget import Image360Widget
from .image_widget import ImageWidget

class ImageFactory:
    @classmethod
    def create_widget(cls, data):
        if cls.is_360(data):
            return Image360Widget(data)
        else:
            return ImageWidget(data)

    @staticmethod
    def is_360(image):
        '''Takes in an image object, returns a boolean indicating whether that image is a 360 image or not'''
        width, height = image.size
        exifdata = image.getexif()
        # looping through all the tags present in exifdata
        has_gpano = False
        for tagid in exifdata:
            # getting the tag name instead of tag id
            tagname = TAGS.get(tagid, tagid)
            # passing the tagid to get its respective value
            value = exifdata.get(tagid)
            #print(f"{tagname:25}: {value}")
            if tagname == "XMLPacket":
                xml = value.decode("utf-8")
                if "GPano" in xml or "XMP-GPano" in xml:
                    has_gpano = True
                break
        has_360_dimensions = True if width >= height * 2 else False
        if has_360_dimensions and not has_gpano:
            #raise ValueError("Unclear whether image is regular or 360")
            return True
        elif has_gpano and not has_360_dimensions:
            #raise ValueError("Unclear whether image is regular or 360")
            return True
        elif has_360_dimensions and has_gpano:
            return True
        else:
            return False