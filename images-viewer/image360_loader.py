from PyQt5 import QtCore
from PyQt5.QtOpenGL import QGLWidget
from qgis.core import Qgis, QgsProject, QgsUnitTypes, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY
from OpenGL.GL import *
from OpenGL.GLU import *
from PIL import Image
from io import BytesIO
import os
import math
import requests

class Image360Widget(QGLWidget):
    def __init__(self, image, direction, angle_degrees, x, y):
        super().__init__()
        self.x = x
        self.y = y
        self.prev_dx = 0
        self.prev_dy = 0
        self.inertia_timer = QtCore.QTimer()
        self.inertia_timer.timeout.connect(self.apply_inertia)
        self.inertia_timer.setInterval(16)
        self.image = image
        self.image_width, self.image_height = self.image.size
        self.yaw = 90 - (direction - ((450 - angle_degrees) % 360))
        self.pitch = 0
        self.prev_dx = 0
        self.prev_dy = 0
        self.fov = 60
        self.moving = False
        self.direction = angle_degrees

    def initializeGL(self): # Sets up the OpenGL state
        glClearColor(1.0, 1.0, 1.0, 1.0) # Clear color buffer and set it color to white
        glEnable(GL_TEXTURE_2D) # Enable the 2D texturing
        self.texture = glGenTextures(1) # Generate the texture ID
        glBindTexture(GL_TEXTURE_2D, self.texture) # Binds the texture ID above to a 2D texture target
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, self.image_width, self.image_height, 0, GL_RGB, GL_UNSIGNED_BYTE, self.image.tobytes()) # Upload the image data to the GPU
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR) # Set the texture's magnification filter to linear filtering
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR) # Set the texture's minification filter to linear filtering
        self.sphere = gluNewQuadric() # Creates a new quadric to draw a sphere
        glMatrixMode(GL_PROJECTION) # Set up the projection matrix to project image to the sphere
        glLoadIdentity()
        gluPerspective(90, self.width()/self.height(), 0.1, 1000)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def paintGL(self): # Renders the texture
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glPushMatrix()
        glRotatef(self.pitch, 1, 0, 0) # Rotating the model around axes
        glRotatef(self.yaw, 0, 1, 0)
        glRotatef(90, 1, 0, 0)
        glRotatef(90, 0, 0, 1)
        gluQuadricTexture(self.sphere, True) # Enable texturing for the sphere
        gluSphere(self.sphere, 1, 100, 100) # Draw the sphere
        glPopMatrix()

    def resizeGL(self, width, height): # Logic for when the window is resized
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(self.fov, self.width()/self.height(), 0.1, 1000) # Perspective projection with new aspect

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.mouse_x, self.mouse_y = event.pos().x(), event.pos().y()
            self.setCursor(QtCore.Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.setCursor(QtCore.Qt.OpenHandCursor)
            self.moving = False

    def mouseMoveEvent(self, event): #Track the coordinate change rate and inertia for rotating
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

    def wheelEvent(self, event): # Changes the zoom on the 360 image, set view accordingly
        delta = event.angleDelta().y()
        self.fov -= delta * 0.1
        self.fov = max(30, min(self.fov, 90))
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(self.fov, self.width()/self.height(), 0.1, 1000)
        self.update()

    def apply_inertia(self): # Account for how hard the view is rotated
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