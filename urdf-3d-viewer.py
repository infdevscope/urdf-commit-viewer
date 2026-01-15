import sys
import threading
import tempfile
import os
import re
from pathlib import Path

try:
    import OpenGL
    OpenGL.ERROR_CHECKING = False
    from OpenGL.GL import *
    from OpenGL.GLU import *
    from OpenGL.GLUT import *
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

class URDF3DViewer:
    def __init__(self, urdf_content, title="URDF 3D Viewer"):
        self.urdf_content = urdf_content
        self.title = title
        self.window = None
        self.window_id = None
        self.running = False

        self.camera_distance = 5.0
        self.camera_angle_x = 45.0
        self.camera_angle_y = 30.0
        self.last_x = 0
        self.last_y = 0
        self.mouse_down = False

        self.links = []
        self.joints = []
        self.parse_urdf()

        self.colors = {
            'base': (0.2, 0.4, 0.8, 1.0),
            'link': (0.4, 0.8, 0.2, 1.0),
            'joint': (0.8, 0.2, 0.2, 1.0),
            'wheel': (0.8, 0.4, 0.2, 1.0),
            'sensor': (0.8, 0.2, 0.8, 1.0),
            'gripper': (0.2, 0.8, 0.8, 1.0),
            'default': (0.7, 0.7, 0.7, 1.0)
        }

    def parse_urdf(self):
        if not self.urdf_content:
            return

        link_pattern = r'<link\s+name="([^"]+)"(.*?)</link>'
        for match in re.finditer(link_pattern, self.urdf_content, re.DOTALL):
            link_name = match.group(1)
            link_content = match.group(2)

            geometry = self.parse_geometry(link_content)

            origin = self.parse_origin(link_content)

            self.links.append({
                'name': link_name,
                'geometry': geometry,
                'origin': origin,
                'type': self.get_link_type(link_name)
            })

        joint_pattern = r'<joint\s+name="([^"]+)"(.*?)</joint>'
        for match in re.finditer(joint_pattern, self.urdf_content, re.DOTALL):
            joint_content = match.group(2)

            parent_match = re.search(r'<parent\s+link="([^"]+)"', joint_content)
            child_match = re.search(r'<child\s+link="([^"]+)"', joint_content)

            if parent_match and child_match:
                origin = self.parse_origin(joint_content)

                self.joints.append({
                    'parent': parent_match.group(1),
                    'child': child_match.group(1),
                    'origin': origin
                })

    def parse_geometry(self, content):
        box_match = re.search(r'<box\s+size="([\d\.\s]+)"', content)
        if box_match:
            sizes = list(map(float, box_match.group(1).split()))
            if len(sizes) >= 3:
                return {'type': 'box', 'size': sizes[:3]}

        cylinder_match = re.search(r'<cylinder\s+radius="([\d\.]+)"\s+length="([\d\.]+)"', content)
        if cylinder_match:
            return {
                'type': 'cylinder',
                'radius': float(cylinder_match.group(1)),
                'length': float(cylinder_match.group(2))
            }

        sphere_match = re.search(r'<sphere\s+radius="([\d\.]+)"', content)
        if sphere_match:
            return {'type': 'sphere', 'radius': float(sphere_match.group(1))}

        return {'type': 'box', 'size': [0.1, 0.1, 0.1]}

    def parse_origin(self, content):
        origin_match = re.search(r'<origin\s+xyz="([-\d\.\s]+)"(?:\s+rpy="([-\d\.\s]+)")?', content)
        if origin_match:
            xyz = list(map(float, origin_match.group(1).split()))
            if len(xyz) < 3:
                xyz = [0.0, 0.0, 0.0]

            if origin_match.group(2):
                rpy = list(map(float, origin_match.group(2).split()))
            else:
                rpy = [0.0, 0.0, 0.0]

            return {'xyz': xyz[:3], 'rpy': rpy[:3]}

        return {'xyz': [0.0, 0.0, 0.0], 'rpy': [0.0, 0.0, 0.0]}

    def get_link_type(self, link_name):
        name_lower = link_name.lower()
        if 'base' in name_lower or 'root' in name_lower:
            return 'base'
        elif 'wheel' in name_lower:
            return 'wheel'
        elif 'camera' in name_lower or 'sensor' in name_lower or 'lidar' in name_lower:
            return 'sensor'
        elif 'gripper' in name_lower or 'hand' in name_lower or 'finger' in name_lower:
            return 'gripper'
        elif 'joint' in name_lower:
            return 'joint'
        else:
            return 'link'

    def init_gl(self):
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)

        light_position = [5.0, 5.0, 5.0, 1.0]
        glLightfv(GL_LIGHT0, GL_POSITION, light_position)

        glMaterialfv(GL_FRONT, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glMaterialfv(GL_FRONT, GL_SHININESS, [50.0])
        glMaterialfv(GL_FRONT, GL_AMBIENT, [0.1, 0.1, 0.1, 1.0])
        glMaterialfv(GL_FRONT, GL_DIFFUSE, [0.7, 0.7, 0.7, 1.0])

    def draw_axis(self):
        glDisable(GL_LIGHTING)
        glBegin(GL_LINES)

        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(1.0, 0.0, 0.0)

        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 1.0, 0.0)

        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 1.0)

        glEnd()
        glEnable(GL_LIGHTING)

    def draw_grid(self, size=10, step=1):
        glDisable(GL_LIGHTING)
        glColor3f(0.5, 0.5, 0.5)
        glBegin(GL_LINES)

        for i in range(-size, size + 1, step):
            glVertex3f(-size, 0.0, i)
            glVertex3f(size, 0.0, i)

            glVertex3f(i, 0.0, -size)
            glVertex3f(i, 0.0, size)

        glEnd()
        glEnable(GL_LIGHTING)

    def draw_box(self, size):
        sx, sy, sz = size[0]/2, size[1]/2, size[2]/2

        glBegin(GL_QUADS)

        glNormal3f(0.0, 0.0, 1.0)
        glVertex3f(-sx, -sy, sz)
        glVertex3f(sx, -sy, sz)
        glVertex3f(sx, sy, sz)
        glVertex3f(-sx, sy, sz)

        glNormal3f(0.0, 0.0, -1.0)
        glVertex3f(-sx, -sy, -sz)
        glVertex3f(-sx, sy, -sz)
        glVertex3f(sx, sy, -sz)
        glVertex3f(sx, -sy, -sz)

        glNormal3f(0.0, 1.0, 0.0)
        glVertex3f(-sx, sy, -sz)
        glVertex3f(-sx, sy, sz)
        glVertex3f(sx, sy, sz)
        glVertex3f(sx, sy, -sz)

        glNormal3f(0.0, -1.0, 0.0)
        glVertex3f(-sx, -sy, -sz)
        glVertex3f(sx, -sy, -sz)
        glVertex3f(sx, -sy, sz)
        glVertex3f(-sx, -sy, sz)

        glNormal3f(1.0, 0.0, 0.0)
        glVertex3f(sx, -sy, -sz)
        glVertex3f(sx, sy, -sz)
        glVertex3f(sx, sy, sz)
        glVertex3f(sx, -sy, sz)

        glNormal3f(-1.0, 0.0, 0.0)
        glVertex3f(-sx, -sy, -sz)
        glVertex3f(-sx, -sy, sz)
        glVertex3f(-sx, sy, sz)
        glVertex3f(-sx, sy, -sz)

        glEnd()

    def draw_cylinder(self, radius, height, slices=16):
        import math

        glPushMatrix()
        glTranslatef(0.0, 0.0, -height/2)

        glBegin(GL_QUAD_STRIP)
        for i in range(slices + 1):
            angle = 2.0 * math.pi * i / slices
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            nx = math.cos(angle)
            ny = math.sin(angle)

            glNormal3f(nx, ny, 0.0)
            glVertex3f(x, y, 0.0)
            glVertex3f(x, y, height)
        glEnd()

        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, height)
        for i in range(slices + 1):
            angle = 2.0 * math.pi * i / slices
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            glVertex3f(x, y, height)
        glEnd()

        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0.0, 0.0, -1.0)
        glVertex3f(0.0, 0.0, 0.0)
        for i in range(slices + 1):
            angle = 2.0 * math.pi * i / slices
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            glVertex3f(x, y, 0.0)
        glEnd()

        glPopMatrix()

    def draw_sphere(self, radius, slices=16, stacks=16):
        import math

        for i in range(stacks):
            lat0 = math.pi * (-0.5 + float(i) / stacks)
            z0 = math.sin(lat0)
            zr0 = math.cos(lat0)

            lat1 = math.pi * (-0.5 + float(i + 1) / stacks)
            z1 = math.sin(lat1)
            zr1 = math.cos(lat1)

            glBegin(GL_QUAD_STRIP)
            for j in range(slices + 1):
                lng = 2 * math.pi * float(j) / slices
                x = math.cos(lng)
                y = math.sin(lng)

                glNormal3f(x * zr0, y * zr0, z0)
                glVertex3f(x * zr0 * radius, y * zr0 * radius, z0 * radius)
                glNormal3f(x * zr1, y * zr1, z1)
                glVertex3f(x * zr1 * radius, y * zr1 * radius, z1 * radius)
            glEnd()

    def draw_link(self, link):
        glPushMatrix()

        origin = link.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
        x, y, z = origin['xyz']
        roll, pitch, yaw = origin['rpy']

        glTranslatef(x, y, z)
        glRotatef(yaw * 180.0 / 3.14159, 0, 0, 1)
        glRotatef(pitch * 180.0 / 3.14159, 0, 1, 0)
        glRotatef(roll * 180.0 / 3.14159, 1, 0, 0)

        link_type = link.get('type', 'default')
        color = self.colors.get(link_type, self.colors['default'])
        glColor4f(*color)

        geometry = link.get('geometry', {'type': 'box', 'size': [0.1, 0.1, 0.1]})

        if geometry['type'] == 'box':
            self.draw_box(geometry['size'])
        elif geometry['type'] == 'cylinder':
            self.draw_cylinder(geometry['radius'], geometry['length'])
        elif geometry['type'] == 'sphere':
            self.draw_sphere(geometry['radius'])
        else:
            self.draw_box([0.1, 0.1, 0.1])

        glPopMatrix()

    def display(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        gluLookAt(
            self.camera_distance * 1.5,
            self.camera_distance,
            self.camera_distance * 0.5,
            0.0, 0.0, 0.0,
            0.0, 1.0, 0.0
        )

        glRotatef(self.camera_angle_y, 1.0, 0.0, 0.0)
        glRotatef(self.camera_angle_x, 0.0, 1.0, 0.0)

        self.draw_grid()
        self.draw_axis()

        for link in self.links:
            self.draw_link(link)

        glutSwapBuffers()

    def reshape(self, width, height):
        if height == 0:
            height = 1

        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, float(width)/float(height), 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    def keyboard(self, key, x, y):
        key = key.decode('utf-8').lower()

        if key == 'q' or key == '\x1b':
            self.running = False
            glutDestroyWindow(self.window_id)
        elif key == '+':
            self.camera_distance = max(1.0, self.camera_distance - 0.5)
        elif key == '-':
            self.camera_distance += 0.5
        elif key == 'r':
            self.camera_distance = 5.0
            self.camera_angle_x = 45.0
            self.camera_angle_y = 30.0
        elif key == 'w':
            self.camera_angle_y -= 5.0
        elif key == 's':
            self.camera_angle_y += 5.0
        elif key == 'a':
            self.camera_angle_x -= 5.0
        elif key == 'd':
            self.camera_angle_x += 5.0

        glutPostRedisplay()

    def mouse(self, button, state, x, y):
        if button == GLUT_LEFT_BUTTON:
            if state == GLUT_DOWN:
                self.mouse_down = True
                self.last_x = x
                self.last_y = y
            else:
                self.mouse_down = False

    def motion(self, x, y):
        if self.mouse_down:
            dx = x - self.last_x
            dy = y - self.last_y
            self.last_x = x
            self.last_y = y

            self.camera_angle_x += dx * 0.5
            self.camera_angle_y += dy * 0.5

            glutPostRedisplay()

    def idle(self):
        glutPostRedisplay()

    def run(self):
        if not OPENGL_AVAILABLE:
            print("ОШИБКА: PyOpenGL не установлен. Установите: pip install PyOpenGL PyOpenGL-accelerate")
            return False

        if not NUMPY_AVAILABLE:
            print("ОШИБКА: NumPy не установлен. Установите: pip install numpy")
            return False

        glutInit(sys.argv)
        glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
        glutInitWindowSize(800, 600)
        glutInitWindowPosition(100, 100)

        self.window_id = glutCreateWindow(self.title.encode('utf-8'))

        self.init_gl()

        glutDisplayFunc(self.display)
        glutReshapeFunc(self.reshape)
        glutKeyboardFunc(self.keyboard)
        glutMouseFunc(self.mouse)
        glutMotionFunc(self.motion)
        glutIdleFunc(self.idle)

        self.running = True

        print(f"3D просмотрщик запущен. Окно: {self.title}")
        print("Управление:")
        print("  Мышь: вращение камеры")
        print("  W/A/S/D: вращение камеры")
        print("  +/-: приближение/отдаление")
        print("  R: сброс камеры")
        print("  Q/ESC: выход")

        try:
            glutMainLoop()
        except:
            pass

        return True

def visualize_urdf_3d(urdf_content, title="URDF 3D Viewer"):
    viewer = URDF3DViewer(urdf_content, title)

    thread = threading.Thread(target=viewer.run, daemon=True)
    thread.start()

    return viewer

if __name__ == "__main__":
    test_urdf = """
    <robot name="test_robot">
        <link name="base_link">
            <visual>
                <geometry>
                    <box size="0.4 0.4 0.1"/>
                </geometry>
            </visual>
        </link>

        <link name="wheel1">
            <visual>
                <geometry>
                    <cylinder radius="0.1" length="0.05"/>
                </geometry>
                <origin xyz="0.2 0.2 -0.1"/>
            </visual>
        </link>

        <joint name="base_to_wheel1" type="fixed">
            <parent link="base_link"/>
            <child link="wheel1"/>
        </joint>
    </robot>
    """

    viewer = URDF3DViewer(test_urdf, "Тестовый URDF")
    viewer.run()
