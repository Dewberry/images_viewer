from PyQt5 import QtCore
from PyQt5.QtOpenGL import QGLWidget
from qgis.core import Qgis, QgsProject, QgsUnitTypes, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY
import OpenGL.GL as GL
import OpenGL.GLU as GLU
from PIL import Image
from io import BytesIO
import os
import math
import requests

class Image360Widget(QGLWidget):
    """
    The Image360Widget class inherits from QGLWidget and is initialized using an Image object.
    It overwrites the initializeGL, paintGL, and resizeGL methods.
    """
    def __init__(self, image):
        super().__init__()
        self.x = 0
        self.y = 0
        self.prev_dx = 0
        self.prev_dy = 0
        self.inertia_timer = QtCore.QTimer()
        self.inertia_timer.timeout.connect(self.apply_inertia)
        self.inertia_timer.setInterval(16)
        self.image = image
        self.image_width, self.image_height = self.image.size
        self.yaw = 90 - (0 - ((450) % 360))
        self.pitch = 0
        self.prev_dx = 0
        self.prev_dy = 0
        self.fov = 60
        self.moving = False
        self.direction = 0.0

    def initializeGL(self):
        """
        Sets up the OpenGL state
        """
        GL.glClearColor(1.0, 1.0, 1.0, 1.0) # Clear color buffer and set it color to white
        GL.glEnable(GL.GL_TEXTURE_2D) # Enable the 2D texturing
        self.texture = GL.glGenTextures(1) # Generate the texture ID
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture) # Binds the texture ID above to a 2D texture target
        if self.image.mode == "RGBA":
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, self.image_width, self.image_height, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, self.image.tobytes())
        elif self.image.mode == "RGB":
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGB, self.image_width, self.image_height, 0, GL.GL_RGB, GL.GL_UNSIGNED_BYTE, self.image.tobytes()) # Upload the image data to the GPU
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR) # Set the texture's magnification filter to linear filtering
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR) # Set the texture's minification filter to linear filtering
        self.sphere = GLU.gluNewQuadric() # Creates a new quadric to draw a sphere
        GL.glMatrixMode(GL.GL_PROJECTION) # Set up the projection matrix to project image to the sphere
        GL.glLoadIdentity()
        GLU.gluPerspective(90, self.width()/self.height(), 0.1, 1000)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()

    def paintGL(self):
        """
        Renders the texture
        """
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glPushMatrix()
        GL.glRotatef(self.pitch, 1, 0, 0) # Rotating the model around axes
        GL.glRotatef(self.yaw, 0, 1, 0)
        GL.glRotatef(90, 1, 0, 0)
        GL.glRotatef(90, 0, 0, 1)
        GLU.gluQuadricTexture(self.sphere, True) # Enable texturing for the sphere
        GLU.gluSphere(self.sphere, 1, 100, 100) # Draw the sphere
        GL.glPopMatrix()

        # Crosshair
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GLU.gluOrtho2D(0, self.width(), self.height(), 0)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glColor3f(1.0, 1, 1)
        GL.glLineWidth(4.0)
        GL.glBegin(GL.GL_LINES)
        GL.glVertex2f(self.width()/2 - 10, self.height()/2)
        GL.glVertex2f(self.width()/2 + 10, self.height()/2)
        GL.glVertex2f(self.width()/2, self.height()/2 - 10)
        GL.glVertex2f(self.width()/2, self.height()/2 + 10)

        # posx, posy = 0,0
        # sides = 32
        # radius = 1
        # GL.glBegin(GL.GL_POLYGON)
        # for i in range(32, -1 -1):
        #     cosine= radius * math.cos(i*2*math.pi/sides) + posx
        #     sine  = radius * math.sin(i*2*math.pi/sides) + posy
        #     GL.glVertex2f(cosine,sine)

        GL.glEnd()
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)

    def resizeGL(self, width, height):
        """
        Logic for when the window is resized
        """
        GL.glViewport(0, 0, width, height)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(self.fov, self.width()/self.height(), 0.1, 1000) # Perspective projection with new aspect

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.mouse_x, self.mouse_y = event.pos().x(), event.pos().y()
            self.setCursor(QtCore.Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.setCursor(QtCore.Qt.OpenHandCursor)
            self.moving = False

    def mouseMoveEvent(self, event):
        """
        Track the coordinate change rate and inertia for rotating
        """
        self.moving = True
        if self.moving:
            dx = event.pos().x() - self.mouse_x
            dy = event.pos().y() - self.mouse_y
            dx *= 0.05
            dy *= 0.05
            self.yaw -= dx
            self.pitch -= dy
            self.pitch = min(max(self.pitch, -90), 90)
            self.mouse_x, self.mouse_y = event.pos().x(), event.pos().y()
            self.direction += dx
            self.update()
        self.prev_dx = dx
        self.prev_dy = dy
        self.inertia_timer.start(10)

    def wheelEvent(self, event):
        """
        Changes the zoom on the 360 image, set view accordingly
        """
        event.accept()  # Consume the event here to prevent propagation
        delta = event.angleDelta().y()
        self.fov -= delta * 0.1
        self.fov = max(30, min(self.fov, 90))
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(self.fov, self.width()/self.height(), 0.1, 1000)
        self.update()

    def apply_inertia(self):
        """
        Account for how hard the view is rotated
        """
        inertia_factor = 0.9
        self.yaw -= self.prev_dx
        self.pitch -= self.prev_dy
        self.pitch = min(max(self.pitch, -90), 90)
        self.direction += self.prev_dx
        self.update()
        self.prev_dx *= inertia_factor
        self.prev_dy *= inertia_factor
        if abs(self.prev_dx) < 0.01 and abs(self.prev_dy) < 0.01:
            self.inertia_timer.stop()