from OpenGL.GL import *
from qgis.PyQt.QtWidgets import QOpenGLWidget


class ImageWidget(QOpenGLWidget):
    def __init__(self, image):
        super().__init__()
        self.image = image
        self.image_width, self.image_height = self.image.size
        self.texture_id = 0

    def initializeGL(self):
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(1.0, 1.0, 1.0, 1.0)
        self.texture_id = glGenTextures(1) # Create an OpenGL texture
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        if self.image.mode == 'RGBA':
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.image_width, self.image_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, self.image.tobytes())
        elif self.image.mode == 'RGB':
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)  # Default alignment is 4, each pixel is 3 bytes so pad 1 byte
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, self.image_width, self.image_height, 0, GL_RGB, GL_UNSIGNED_BYTE, self.image.tobytes())  # Upload the image data to the texture

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)

        texture_aspect_ratio = float(self.image_width) / float(self.image_height)
        viewport_aspect_ratio = float(self.width()) / float(self.height())

        # Set up the textured quad with preserved aspect ratio
        if texture_aspect_ratio > viewport_aspect_ratio:
            # Texture is wider than viewport, adjust quad's height
            quad_width = 2.0
            quad_height = (self.width() / texture_aspect_ratio)/self.height() * 2.0
        else:
            # Texture is taller than viewport, adjust quad's width
            quad_height = 2.0
            quad_width = (self.height() * texture_aspect_ratio)/self.width() * 2.0

        quad_left = -quad_width / 2.0
        quad_right = quad_width / 2.0
        quad_bottom = -quad_height / 2.0
        quad_top = quad_height / 2.0

        # Set up the textured quad with adjusted vertex positions
        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 1.0)  # Bottom-left
        glVertex2f(quad_left, quad_bottom)
        glTexCoord2f(1.0, 1.0)  # Bottom-right
        glVertex2f(quad_right, quad_bottom)
        glTexCoord2f(1.0, 0.0)  # Top-right
        glVertex2f(quad_right, quad_top)
        glTexCoord2f(0.0, 0.0)  # Top-left
        glVertex2f(quad_left, quad_top)
        glEnd()

    def resizeGL(self, width, height):
        glViewport(0, 0, width, height)
