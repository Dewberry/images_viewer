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
    def __init__(self, image, direction, map_manager, angle_degrees, x, y, params, instance):
        super().__init__()
        self.instance = instance
        self.show_crosshair = False
        self.url = ''
        self.x = x
        self.y = y
        self.prev_dx = 0
        self.prev_dy = 0
        self.inertia_timer = QtCore.QTimer()
        self.inertia_timer.timeout.connect(self.apply_inertia)
        self.inertia_timer.setInterval(16)
        self.direction = direction
        self.angle_degrees = angle_degrees
        self.params = params
        self.image = image
        self.image_width, self.image_height = self.image.size
        self.yaw = 90 - (direction - ((450 - angle_degrees) % 360))
        self.pitch = 0
        self.prev_dx = 0
        self.prev_dy = 0
        self.fov = 60
        self.moving = False
        self.direction = angle_degrees
        self.map_manager = map_manager

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
        if self.show_crosshair: # Display the crosshair
            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            gluOrtho2D(0, self.width(), self.height(), 0)
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glLoadIdentity()
            glDisable(GL_DEPTH_TEST)
            glColor3f(1.0, 1, 1)
            glLineWidth(4.0)
            glBegin(GL_LINES)
            glVertex2f(self.width()/2 - 10, self.height()/2)
            glVertex2f(self.width()/2 + 10, self.height()/2)
            glVertex2f(self.width()/2, self.height()/2 - 10)
            glVertex2f(self.width()/2, self.height()/2 + 10)
            glEnd()
            glEnable(GL_DEPTH_TEST)
            glPopMatrix()
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)

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
        if self.moving == False :
            self.setCursor(QtCore.Qt.WaitCursor)
            try :
                x, y = self.recalculate_coordinates(self.x, self.y, self.direction, 6)
                self.x = x
                self.y = y
                if self.img != self.url and self.img != 0 :
                    self.url  = self.img
                    self.yaw = 90 - (float(self.dir) - ((450 - self.direction) % 360))
                    if "http" in self.url :
                        response = requests.get(self.url)
                        self.image = Image.open(BytesIO(response.content))
                    else :
                        if self.url.startswith('./'):
                            self.url = self.url[1:]
                            project_path = os.path.dirname(QgsProject.instance().fileName())
                            self.url = project_path + self.url
                        self.image = Image.open(self.url)
                    self.image_width, self.image_height = self.image.size
                    self.initializeGL()
                    self.paintGL()
                    self.resizeGL(self.width(), self.height())
                    self.update()
                else :
                    x, y = self.recalculate_coordinates(self.x, self.y, self.direction, -6)
                    self.x = x
                    self.y = y
            except Exception as e :
                print("Error")
            finally :
                self.setCursor(QtCore.Qt.OpenHandCursor)
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

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.fov -= delta * 0.1
        self.fov = max(30, min(self.fov, 90))
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(self.fov, self.width()/self.height(), 0.1, 1000)
        self.update()

    def recalculate_coordinates(self, x, y, angle, distance):
        angle_rad = math.radians(angle)
        point = QgsPointXY(x, y)
        if QgsProject.instance().crs().mapUnits() == QgsUnitTypes.DistanceDegrees:
            src_crs = QgsCoordinateReferenceSystem('EPSG:4326')
            dst_crs = QgsCoordinateReferenceSystem('EPSG:3857')
            transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
            untransform = QgsCoordinateTransform(dst_crs, src_crs, QgsProject.instance())
            point = transform.transform(point)

        x_new = point.x() + (distance * math.cos(angle_rad))
        y_new = point.y() + (distance * math.sin(angle_rad))
        if QgsProject.instance().crs().mapUnits() == QgsUnitTypes.DistanceDegrees:
            point = QgsPointXY(x_new, y_new)
            point = untransform.transform(point)
            x_new = point.x()
            y_new = point.y()
        return x_new, y_new

    def apply_inertia(self):
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