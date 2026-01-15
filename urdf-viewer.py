import os
import re
import math
import difflib
import tempfile
import subprocess
import threading
from datetime import datetime
from urllib.parse import urlparse
from collections import Counter
from io import BytesIO

try:
    import streamlit as st
    import streamlit.components.v1 as components
except ImportError:
    print("ОШИБКА: Streamlit не установлен")
    exit(1)

LIBRARIES = {}

try:
    import git
    LIBRARIES['git'] = True
except ImportError:
    LIBRARIES['git'] = False

try:
    import requests
    LIBRARIES['requests'] = True
except ImportError:
    LIBRARIES['requests'] = False

try:
    import plotly.graph_objects as go
    import plotly.express as px
    LIBRARIES['plotly'] = True
except ImportError:
    LIBRARIES['plotly'] = False

try:
    import numpy as np
    LIBRARIES['numpy'] = True
except ImportError:
    LIBRARIES['numpy'] = False

try:
    import networkx as nx
    LIBRARIES['networkx'] = True
except ImportError:
    LIBRARIES['networkx'] = False

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Rectangle, FancyBboxPatch
    from matplotlib.collections import PatchCollection
    LIBRARIES['matplotlib'] = True
except ImportError:
    LIBRARIES['matplotlib'] = False

try:
    import OpenGL
    OpenGL.ERROR_CHECKING = False
    LIBRARIES['opengl'] = True
except ImportError:
    LIBRARIES['opengl'] = False

def create_3d_viewer_script(urdf_content, title):
    script = f'''
import sys
import os
import re
import math
import threading

try:
    import OpenGL
    OpenGL.ERROR_CHECKING = False
    from OpenGL.GL import *
    from OpenGL.GLU import *
    from OpenGL.GLUT import *
    import numpy as np
except ImportError as e:
    print(f"ОШИБКА: Не удалось импортировать OpenGL: {{e}}")
    print("Установите: pip install PyOpenGL PyOpenGL-accelerate numpy")
    sys.exit(1)

class URDF3DViewer:
    def __init__(self, urdf_content, title="URDF 3D Viewer"):
        self.urdf_content = urdf_content
        self.title = title
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

        self.colors = {{
            'base': (0.2, 0.4, 0.8, 1.0),
            'link': (0.4, 0.8, 0.2, 1.0),
            'joint': (0.8, 0.2, 0.2, 1.0),
            'wheel': (0.8, 0.4, 0.2, 1.0),
            'sensor': (0.8, 0.2, 0.8, 1.0),
            'gripper': (0.2, 0.8, 0.8, 1.0),
            'default': (0.7, 0.7, 0.7, 1.0)
        }}

    def parse_urdf(self):
        if not self.urdf_content:
            return

        link_pattern = r'<link\\s+name="([^"]+)"(.*?)</link>'
        for match in re.finditer(link_pattern, self.urdf_content, re.DOTALL):
            link_name = match.group(1)
            link_content = match.group(2)

            visual_pattern = r'<visual>(.*?)</visual>'
            visual_match = re.search(visual_pattern, link_content, re.DOTALL | re.IGNORECASE)

            geometry = {{'type': 'box', 'size': [0.1, 0.1, 0.1]}}
            origin = {{'xyz': [0.0, 0.0, 0.0], 'rpy': [0.0, 0.0, 0.0]}}

            if visual_match:
                visual_content = visual_match.group(1)

                visual_origin = self.parse_origin(visual_content)
                if visual_origin['xyz'] != [0.0, 0.0, 0.0]:
                    origin = visual_origin

                visual_geometry = self.parse_geometry(visual_content)
                if visual_geometry['type'] != 'box' or visual_geometry['size'] != [0.1, 0.1, 0.1]:
                    geometry = visual_geometry

            self.links.append({{
                'name': link_name,
                'geometry': geometry,
                'origin': origin,
                'type': self.get_link_type(link_name)
            }})

        joint_pattern = r'<joint\\s+name="([^"]+)"(.*?)</joint>'
        for match in re.finditer(joint_pattern, self.urdf_content, re.DOTALL):
            joint_content = match.group(2)

            parent_match = re.search(r'<parent\\s+link="([^"]+)"', joint_content)
            child_match = re.search(r'<child\\s+link="([^"]+)"', joint_content)

            if parent_match and child_match:
                origin = self.parse_origin(joint_content)

                self.joints.append({{
                    'name': match.group(1),
                    'parent': parent_match.group(1),
                    'child': child_match.group(1),
                    'origin': origin
                }})

    def parse_geometry(self, content):
        box_match = re.search(r'<box\\s+size="([\\d\\.\\s]+)"', content, re.IGNORECASE)
        if box_match:
            sizes = list(map(float, box_match.group(1).split()))
            if len(sizes) >= 3:
                return {{'type': 'box', 'size': sizes[:3]}}

        cylinder_match = re.search(r'<cylinder\\s+radius="([\\d\\.]+)"\\s+length="([\\d\\.]+)"', content, re.IGNORECASE)
        if cylinder_match:
            return {{
                'type': 'cylinder',
                'radius': float(cylinder_match.group(1)),
                'length': float(cylinder_match.group(2))
            }}

        sphere_match = re.search(r'<sphere\\s+radius="([\\d\\.]+)"', content, re.IGNORECASE)
        if sphere_match:
            return {{'type': 'sphere', 'radius': float(sphere_match.group(1))}}

        return {{'type': 'box', 'size': [0.1, 0.1, 0.1]}}

    def parse_origin(self, content):
        origin_match = re.search(r'<origin\\s+xyz="([-\\d\\.\\s]+)"(?:\\s+rpy="([-\\d\\.\\s]+)")?', content, re.IGNORECASE)
        if origin_match:
            xyz = list(map(float, origin_match.group(1).split()))
            if len(xyz) < 3:
                xyz = [0.0, 0.0, 0.0]

            if origin_match.group(2):
                rpy = list(map(float, origin_match.group(2).split()))
                if len(rpy) < 3:
                    rpy = [0.0, 0.0, 0.0]
            else:
                rpy = [0.0, 0.0, 0.0]

            return {{'xyz': xyz[:3], 'rpy': rpy[:3]}}

        return {{'xyz': [0.0, 0.0, 0.0], 'rpy': [0.0, 0.0, 0.0]}}

    def get_link_type(self, link_name):
        name_lower = link_name.lower()
        if 'base' in name_lower or 'root' in name_lower or 'chassis' in name_lower:
            return 'base'
        elif 'wheel' in name_lower or 'caster' in name_lower:
            return 'wheel'
        elif 'camera' in name_lower or 'sensor' in name_lower or 'lidar' in name_lower:
            return 'sensor'
        elif 'gripper' in name_lower or 'hand' in name_lower or 'finger' in name_lower:
            return 'gripper'
        elif 'joint' in name_lower:
            return 'joint'
        elif 'link' in name_lower:
            return 'link'
        else:
            return 'default'

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
        glLineWidth(2.0)
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
        glColor3f(0.3, 0.3, 0.3)
        glLineWidth(0.5)
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

        origin = link.get('origin', {{'xyz': [0, 0, 0], 'rpy': [0, 0, 0]}})
        x, y, z = origin['xyz']
        roll, pitch, yaw = origin['rpy']

        glTranslatef(x, y, z)

        if yaw != 0:
            glRotatef(yaw * 180.0 / math.pi, 0, 0, 1)
        if pitch != 0:
            glRotatef(pitch * 180.0 / math.pi, 0, 1, 0)
        if roll != 0:
            glRotatef(roll * 180.0 / math.pi, 1, 0, 0)

        link_type = link.get('type', 'default')
        color = self.colors.get(link_type, self.colors['default'])
        glColor4f(*color)

        geometry = link.get('geometry', {{'type': 'box', 'size': [0.1, 0.1, 0.1]}})

        if geometry['type'] == 'box':
            self.draw_box(geometry['size'])
        elif geometry['type'] == 'cylinder':
            self.draw_cylinder(geometry['radius'], geometry['length'])
        elif geometry['type'] == 'sphere':
            self.draw_sphere(geometry['radius'])
        else:
            self.draw_box([0.1, 0.1, 0.1])

        glDisable(GL_LIGHTING)
        glColor3f(1.0, 1.0, 1.0)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glLineWidth(1.0)

        if geometry['type'] == 'box':
            self.draw_box(geometry['size'])
        elif geometry['type'] == 'cylinder':
            self.draw_cylinder(geometry['radius'], geometry['length'])
        elif geometry['type'] == 'sphere':
            self.draw_sphere(geometry['radius'])

        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_LIGHTING)

        glPopMatrix()

    def display(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        cam_x = self.camera_distance * math.cos(math.radians(self.camera_angle_x)) * math.cos(math.radians(self.camera_angle_y))
        cam_y = self.camera_distance * math.sin(math.radians(self.camera_angle_x)) * math.cos(math.radians(self.camera_angle_y))
        cam_z = self.camera_distance * math.sin(math.radians(self.camera_angle_y))

        gluLookAt(
            cam_x, cam_z, cam_y,
            0.0, 0.0, 0.0,
            0.0, 1.0, 0.0
        )

        self.draw_grid(size=5, step=1)
        self.draw_axis()

        for link in self.links:
            self.draw_link(link)

        glDisable(GL_LIGHTING)
        glColor3f(1.0, 0.5, 0.0)
        glLineWidth(2.0)
        glBegin(GL_LINES)

        for joint in self.joints:
            parent_link = next((link for link in self.links if link['name'] == joint['parent']), None)
            child_link = next((link for link in self.links if link['name'] == joint['child']), None)

            if parent_link and child_link:
                parent_pos = parent_link['origin']['xyz']
                child_pos = child_link['origin']['xyz']

                glVertex3f(parent_pos[0], parent_pos[2], parent_pos[1])
                glVertex3f(child_pos[0], child_pos[2], child_pos[1])

        glEnd()
        glEnable(GL_LIGHTING)

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

        if key == 'q' or key == '\\x1b':
            self.running = False
            glutDestroyWindow(self.window_id)
            return
        elif key == '+':
            self.camera_distance = max(1.0, self.camera_distance - 0.5)
        elif key == '-':
            self.camera_distance += 0.5
        elif key == 'r':
            self.camera_distance = 5.0
            self.camera_angle_x = 45.0
            self.camera_angle_y = 30.0
        elif key == 'w':
            self.camera_angle_y += 5.0
        elif key == 's':
            self.camera_angle_y -= 5.0
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

            self.camera_angle_y = max(-89.0, min(89.0, self.camera_angle_y))

            glutPostRedisplay()

    def idle(self):
        glutPostRedisplay()

    def run(self):
        glutInit(sys.argv)
        glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
        glutInitWindowSize(1024, 768)
        glutInitWindowPosition(100, 100)

        self.window_id = glutCreateWindow(self.title.encode('utf-8', 'ignore'))

        self.init_gl()

        glutDisplayFunc(self.display)
        glutReshapeFunc(self.reshape)
        glutKeyboardFunc(self.keyboard)
        glutMouseFunc(self.mouse)
        glutMotionFunc(self.motion)
        glutIdleFunc(self.idle)

        self.running = True

        print(f"\\n=== URDF 3D Viewer ===")
        print(f"Файл: {{self.title}}")
        print(f"Компонентов: {{len(self.links)}} линков, {{len(self.joints)}} соединений")
        print("\\nУправление:")
        print("  ЛКМ + мышь: вращение камеры")
        print("  W/S: вращение по вертикали")
        print("  A/D: вращение по горизонтали")
        print("  +/-: приближение/отдаление")
        print("  R: сброс камеры")
        print("  Q/ESC: выход\\n")

        try:
            glutMainLoop()
        except:
            pass

def main():
    import sys
    import json

    if len(sys.argv) < 3:
        print("Использование: python 3d_viewer.py <urdf_content_file> <title>")
        return

    urdf_file = sys.argv[1]
    title = sys.argv[2]

    try:
        with open(urdf_file, 'r', encoding='utf-8') as f:
            urdf_content = f.read()

        viewer = URDF3DViewer(urdf_content, title)
        viewer.run()

    except Exception as e:
        print(f"Ошибка запуска 3D просмотрщика: {{e}}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
'''

    import tempfile
    script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
    script_file.write(script)
    script_file.close()

    urdf_file = tempfile.NamedTemporaryFile(mode='w', suffix='.urdf', delete=False, encoding='utf-8')
    urdf_file.write(urdf_content)
    urdf_file.close()

    return script_file.name, urdf_file.name

def visualize_urdf_3d_separate_process(urdf_content, title="URDF 3D Viewer"):
    try:
        script_path, urdf_path = create_3d_viewer_script(urdf_content, title)

        import sys
        python_exec = sys.executable

        process = subprocess.Popen(
            [python_exec, script_path, urdf_path, title],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        def read_output():
            for line in process.stdout:
                print(line, end='')

        output_thread = threading.Thread(target=read_output, daemon=True)
        output_thread.start()

        import time
        time.sleep(1)

        return process

    except Exception as e:
        print(f"Ошибка запуска 3D просмотрщика: {e}")
        return None

def parse_github_url(url):
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) >= 2:
            return path_parts[0], path_parts[1]
    except:
        pass
    return None, None

def search_github_files(owner, repo):
    if not LIBRARIES.get('requests'):
        return []

    files = []

    try:
        with st.spinner(f"Поиск файлов в {owner}/{repo}..."):
            common_paths = ["", "urdf/", "urdf_tutorial/urdf/", "robots/", "urdf/models/", "description/urdf/"]

            for path in common_paths:
                try:
                    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
                    response = requests.get(api_url, timeout=10)

                    if response.status_code == 200:
                        items = response.json()
                        for item in items:
                            if isinstance(item, dict) and item.get('type') == 'file':
                                filename = item.get('name', '').lower()
                                if filename.endswith(('.urdf', '.xacro')):
                                    files.append({
                                        'path': item['path'],
                                        'name': item['name'],
                                        'url': item.get('html_url', '')
                                    })

                except:
                    continue

    except Exception as e:
        st.error(f"Ошибка поиска: {str(e)}")

    return sorted(files, key=lambda x: x['path'])

def get_github_commits(owner, repo, file_path):
    if not LIBRARIES.get('requests'):
        return []

    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {'path': file_path, 'per_page': 20}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            commits_data = response.json()
            commits = []
            for commit in commits_data:
                commits.append({
                    'sha': commit['sha'][:8],
                    'full_sha': commit['sha'],
                    'message': commit['commit']['message'].strip(),
                    'date': datetime.strptime(
                        commit['commit']['committer']['date'][:19],
                        '%Y-%m-%dT%H:%M:%S'
                    ),
                    'author': commit['commit']['author']['name']
                })
            return commits

    except Exception as e:
        st.error(f"Ошибка: {str(e)}")

    return []

def get_github_file_content(owner, repo, sha, file_path):
    if not LIBRARIES.get('requests'):
        return None

    try:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{file_path}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            return response.text

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={sha}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if 'content' in data:
                import base64
                return base64.b64decode(data['content']).decode('utf-8')

    except:
        pass

    return None

def find_local_files(path):
    if not os.path.exists(path):
        return []

    files = []
    for root, dirs, filenames in os.walk(path):
        for filename in filenames:
            if filename.lower().endswith(('.urdf', '.xacro')):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, path)
                files.append({
                    'path': rel_path,
                    'name': filename,
                    'full_path': full_path
                })

    return sorted(files, key=lambda x: x['path'])

def get_local_commits(repo_path, file_path):
    if not LIBRARIES.get('git'):
        return []

    try:
        repo = git.Repo(repo_path)
        commits = list(repo.iter_commits(paths=file_path, max_count=20))

        return [{
            'sha': c.hexsha[:8],
            'full_sha': c.hexsha,
            'message': c.message.strip(),
            'date': c.committed_datetime,
            'author': c.author.name
        } for c in commits]

    except Exception as e:
        st.error(f"Ошибка Git: {str(e)}")
        return []

def get_local_file_content(repo_path, sha, file_path):
    try:
        repo = git.Repo(repo_path)
        return repo.git.show(f"{sha}:{file_path}")
    except:
        try:
            with open(os.path.join(repo_path, file_path), 'r') as f:
                return f.read()
        except:
            return None

def parse_urdf_structure(content):
    if not content:
        return {'links': [], 'joints': [], 'graph': None}

    links = re.findall(r'<link\s+name="([^"]+)"', content)

    joints = []
    joint_pattern = r'<joint\s+name="([^"]+)".*?<parent\s+link="([^"]+)".*?<child\s+link="([^"]+)"'
    for match in re.finditer(joint_pattern, content, re.DOTALL):
        joints.append({
            'name': match.group(1),
            'parent': match.group(2),
            'child': match.group(3)
        })

    G = None
    if LIBRARIES.get('networkx') and (links or joints):
        G = nx.DiGraph()

        for link in links:
            G.add_node(link, type='link')

        for joint in joints:
            if joint['parent'] in links and joint['child'] in links:
                G.add_edge(joint['parent'], joint['child'],
                          label=joint['name'], type='joint')

    return {
        'links': links,
        'joints': joints,
        'graph': G
    }

def create_hierarchical_diagram(structure, title="Иерархия URDF"):
    if not LIBRARIES.get('matplotlib') or not structure['links']:
        return None

    try:
        fig, ax = plt.subplots(figsize=(10, 8), facecolor='white')

        links = structure['links']
        joints = structure['joints']

        all_parents = set(j['parent'] for j in joints)
        all_children = set(j['child'] for j in joints)
        root_nodes = [link for link in links if link not in all_children]

        if not root_nodes and links:
            root_nodes = [links[0]]

        hierarchy = {}

        def build_hierarchy(node, depth=0):
            if depth > 10:
                return

            if node not in hierarchy:
                hierarchy[node] = {'depth': depth, 'children': []}

            for joint in joints:
                if joint['parent'] == node:
                    child = joint['child']
                    hierarchy[node]['children'].append(child)
                    build_hierarchy(child, depth + 1)

        for root in root_nodes:
            build_hierarchy(root)

        positions = {}
        y_positions = {}

        max_depth = max(h.get('depth', 0) for h in hierarchy.values()) if hierarchy else 0
        for node, info in hierarchy.items():
            depth = info['depth']
            y_positions[node] = max_depth - depth

        nodes_by_depth = {}
        for node, info in hierarchy.items():
            depth = info['depth']
            if depth not in nodes_by_depth:
                nodes_by_depth[depth] = []
            nodes_by_depth[depth].append(node)

        for depth, nodes in nodes_by_depth.items():
            x_spacing = 10.0 / (len(nodes) + 1)
            for i, node in enumerate(sorted(nodes)):
                positions[node] = ((i + 1) * x_spacing - 5, y_positions[node])

        for node, (x, y) in positions.items():
            node_lower = node.lower()
            if 'base' in node_lower or 'root' in node_lower:
                color = '#3498db'
            elif 'wheel' in node_lower:
                color = '#e74c3c'
            elif 'camera' in node_lower or 'sensor' in node_lower:
                color = '#9b59b6'
            elif 'gripper' in node_lower or 'hand' in node_lower:
                color = '#1abc9c'
            elif 'link' in node_lower:
                color = '#2ecc71'
            else:
                color = '#7f8c8d'

            rect = Rectangle((x - 0.4, y - 0.15), 0.8, 0.3,
                           facecolor=color, edgecolor='#2c3e50',
                           linewidth=2, alpha=0.9, zorder=3)
            ax.add_patch(rect)

            ax.text(x, y, node, ha='center', va='center',
                   fontsize=9, fontweight='bold', color='white',
                   zorder=4)

        for joint in joints:
            parent = joint['parent']
            child = joint['child']

            if parent in positions and child in positions:
                x1, y1 = positions[parent]
                x2, y2 = positions[child]

                ax.plot([x1, x2], [y1 + 0.15, y2 - 0.15],
                       color='#e74c3c', linewidth=2,
                       alpha=0.7, zorder=1)

                ax.annotate('', xy=(x2, y2 - 0.15), xytext=(x1, y1 + 0.15),
                           arrowprops=dict(arrowstyle='->',
                                         color='#e74c3c',
                                         linewidth=2,
                                         alpha=0.7))

                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2

                joint_name_short = joint['name'][:15] + '...' if len(joint['name']) > 15 else joint['name']
                ax.text(mid_x, mid_y - 0.1, joint_name_short,
                       ha='center', va='center',
                       fontsize=8, color='#c0392b',
                       bbox=dict(boxstyle='round,pad=0.2',
                                facecolor='white',
                                edgecolor='none',
                                alpha=0.8),
                       zorder=2)

        ax.set_xlim(-6, 6)
        ax.set_ylim(-1, max_depth + 2 if max_depth > 0 else 3)
        ax.set_aspect('equal')
        ax.axis('off')

        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)

        stats_text = f"Корневых узлов: {len(root_nodes)}\nВсего узлов: {len(hierarchy)}"
        ax.text(0.02, 0.98, stats_text,
               transform=ax.transAxes,
               fontsize=10,
               verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        st.error(f"Ошибка создания иерархической диаграммы: {str(e)}")
        return None

def create_component_visualization(content, title="Визуализация компонентов URDF"):
    if not LIBRARIES.get('matplotlib'):
        return None

    try:
        links = re.findall(r'<link\s+name="([^"]+)"', content)
        joints = re.findall(r'<joint\s+name="([^"]+)"', content)
        visuals = re.findall(r'<visual>', content, re.IGNORECASE)
        collisions = re.findall(r'<collision>', content, re.IGNORECASE)

        fig, ax = plt.subplots(figsize=(10, 6), facecolor='white')

        categories = ['Линки', 'Соединения', 'Визуалы', 'Коллизии']
        values = [len(links), len(joints), len(visuals), len(collisions)]
        colors = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6']

        bars = ax.bar(categories, values, color=colors, edgecolor='#2c3e50', linewidth=2)

        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                   f'{value}', ha='center', va='bottom',
                   fontweight='bold', fontsize=11)

        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.set_ylabel('Количество', fontsize=12)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)

        total_elements = sum(values)
        info_text = f"Всего элементов: {total_elements}\n"

        joint_types = {
            'revolute': len(re.findall(r'type="revolute"', content, re.IGNORECASE)),
            'prismatic': len(re.findall(r'type="prismatic"', content, re.IGNORECASE)),
            'fixed': len(re.findall(r'type="fixed"', content, re.IGNORECASE)),
            'continuous': len(re.findall(r'type="continuous"', content, re.IGNORECASE))
        }

        if sum(joint_types.values()) > 0:
            info_text += "\nТипы соединений:\n"
            for j_type, count in joint_types.items():
                if count > 0:
                    info_text += f"  {j_type}: {count}\n"

        geometries = {
            'box': len(re.findall(r'<box', content, re.IGNORECASE)),
            'cylinder': len(re.findall(r'<cylinder', content, re.IGNORECASE)),
            'sphere': len(re.findall(r'<sphere', content, re.IGNORECASE)),
            'mesh': len(re.findall(r'<mesh', content, re.IGNORECASE))
        }

        if sum(geometries.values()) > 0:
            info_text += "\nГеометрии:\n"
            for geom, count in geometries.items():
                if count > 0:
                    info_text += f"  {geom}: {count}\n"

        ax.text(1.05, 0.95, info_text,
               transform=ax.transAxes,
               fontsize=9,
               verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='#f8f9fa',
                        edgecolor='#dee2e6', alpha=0.9))

        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        st.error(f"Ошибка создания визуализации компонентов: {str(e)}")
        return None

def get_file_content_for_commit(source, repo_info, sha, file_path):
    if source == "local":
        repo_path = repo_info
        return get_local_file_content(repo_path, sha, file_path)
    else:
        owner, repo = repo_info
        return get_github_file_content(owner, repo, sha, file_path)

def compare_commits(old_content, new_content, old_sha, new_sha):
    if not old_content or not new_content:
        return None

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{old_sha[:8]}",
        tofile=f"b/{new_sha[:8]}",
        lineterm=""
    ))

    return diff

def analyze_code_changes(old_content, new_content):
    if not old_content or not new_content:
        return {}

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    diff = list(difflib.ndiff(old_lines, new_lines))

    changes = {
        'added_lines': 0,
        'removed_lines': 0,
        'modified_lines': 0,
        'unchanged_lines': 0,
        'changes_by_type': Counter(),
        'line_changes': []
    }

    for line in diff:
        if line.startswith('+ ') and not line.startswith('++'):
            changes['added_lines'] += 1
            changes['line_changes'].append(('+', line[2:]))
        elif line.startswith('- ') and not line.startswith('--'):
            changes['removed_lines'] += 1
            changes['line_changes'].append(('-', line[2:]))
        elif line.startswith('  '):
            changes['unchanged_lines'] += 1
        elif line.startswith('? '):
            changes['modified_lines'] += 1

    for change_type, line in changes['line_changes'][:100]:
        line_lower = line.lower()
        if '<link' in line_lower:
            changes['changes_by_type']['link'] += 1
        elif '<joint' in line_lower:
            changes['changes_by_type']['joint'] += 1
        elif '<visual' in line_lower:
            changes['changes_by_type']['visual'] += 1
        elif '<collision' in line_lower:
            changes['changes_by_type']['collision'] += 1
        elif '<origin' in line_lower:
            changes['changes_by_type']['origin'] += 1
        elif '<geometry' in line_lower:
            changes['changes_by_type']['geometry'] += 1
        elif '<material' in line_lower:
            changes['changes_by_type']['material'] += 1
        elif 'name="' in line_lower:
            changes['changes_by_type']['name'] += 1
        elif 'xyz="' in line_lower or 'rpy="' in line_lower:
            changes['changes_by_type']['pose'] += 1

    return changes

def create_diff_html(diff_lines, max_lines=200):
    if not diff_lines:
        return "<div style='padding: 20px; background: #f8f9fa; border-radius: 5px;'>Нет изменений</div>"

    html_lines = []
    line_count = 0

    for line in diff_lines:
        if line_count >= max_lines:
            html_lines.append("<div style='color: #666; padding: 5px; font-weight: bold;'>...</div>")
            break

        if line.startswith('---') or line.startswith('+++'):
            html_lines.append(f"<div style='color: #6c757d; padding: 5px; font-family: monospace;'>{line}</div>")
        elif line.startswith('@@'):
            html_lines.append(f"<div style='background: #e9ecef; color: #495057; padding: 5px; font-family: monospace; font-weight: bold;'>{line}</div>")
        elif line.startswith('+'):
            html_lines.append(f"<div style='background: #d4edda; color: #155724; padding: 5px; font-family: monospace; border-left: 3px solid #28a745; margin-left: 10px;'>{line}</div>")
        elif line.startswith('-'):
            html_lines.append(f"<div style='background: #f8d7da; color: #721c24; padding: 5px; font-family: monospace; border-left: 3px solid #dc3545; margin-left: 10px;'>{line}</div>")
        else:
            html_lines.append(f"<div style='color: #212529; padding: 5px; font-family: monospace;'>{line}</div>")

        line_count += 1

    return f"<div style='max-height: 500px; overflow-y: auto; border: 1px solid #dee2e6; border-radius: 5px;'>{''.join(html_lines)}</div>"

def create_change_stats_chart(changes):
    if not changes:
        return None

    labels = ['Добавлено', 'Удалено', 'Изменено', 'Без изменений']
    values = [
        changes.get('added_lines', 0),
        changes.get('removed_lines', 0),
        changes.get('modified_lines', 0),
        changes.get('unchanged_lines', 0)
    ]

    colors = ['#28a745', '#dc3545', '#ffc107', '#6c757d']

    fig = go.Figure(data=[
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=values,
            textposition='auto',
        )
    ])

    fig.update_layout(
        title=dict(
            text="Статистика изменений строк",
            font=dict(size=14)
        ),
        xaxis_title="Тип изменения",
        yaxis_title="Количество строк",
        height=300,
        plot_bgcolor='white',
        paper_bgcolor='white'
    )

    return fig

def create_element_changes_chart(changes):
    if not changes or not changes.get('changes_by_type'):
        return None

    element_changes = changes['changes_by_type']
    if not element_changes:
        return None

    elements = list(element_changes.keys())
    counts = list(element_changes.values())

    element_names_ru = {
        'link': 'Линки',
        'joint': 'Соединения',
        'visual': 'Визуалы',
        'collision': 'Коллизии',
        'origin': 'Позиции',
        'geometry': 'Геометрии',
        'material': 'Материалы',
        'name': 'Имена',
        'pose': 'Позы'
    }

    elements_ru = [element_names_ru.get(elem, elem) for elem in elements]

    fig = go.Figure(data=[
        go.Pie(
            labels=elements_ru,
            values=counts,
            hole=.3,
            marker=dict(colors=px.colors.qualitative.Set3)
        )
    ])

    fig.update_layout(
        title=dict(
            text="Изменения по элементам URDF",
            font=dict(size=14)
        ),
        height=400,
        showlegend=True,
        legend=dict(
            x=1.05,
            y=0.5
        )
    )

    return fig

def create_commit_graph(commits, selected_idx):
    if not LIBRARIES.get('plotly'):
        return None

    try:
        dates = [c['date'] for c in commits]
        authors = [c['author'] for c in commits]
        messages = [c['message'][:50] + "..." if len(c['message']) > 50 else c['message']
                   for c in commits]
        shas = [c['sha'] for c in commits]

        unique_authors = list(set(authors))
        color_map = {}
        colors = px.colors.qualitative.Plotly

        for i, author in enumerate(unique_authors):
            color_map[author] = colors[i % len(colors)]

        colors = [color_map[author] for author in authors]

        sizes = [12 if i == selected_idx else 8 for i in range(len(commits))]

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=dates,
            y=[1] * len(commits),
            mode='markers+text',
            marker=dict(
                size=sizes,
                color=colors,
                line=dict(width=2, color='white')
            ),
            text=shas,
            textposition="top center",
            hovertext=[f"{c['sha']}: {c['message']}<br>Автор: {c['author']}"
                      for c in commits],
            hoverinfo='text',
            name="Коммиты"
        ))

        for i in range(len(dates)-1):
            fig.add_trace(go.Scatter(
                x=[dates[i], dates[i+1]],
                y=[1, 1],
                mode='lines',
                line=dict(color='gray', width=2, dash='dash'),
                showlegend=False,
                hoverinfo='none'
            ))

        if 0 <= selected_idx < len(commits):
            fig.add_trace(go.Scatter(
                x=[dates[selected_idx]],
                y=[1],
                mode='markers',
                marker=dict(
                    size=20,
                    color='gold',
                    symbol='star',
                    line=dict(width=3, color='black')
                ),
                name="Выбранный коммит",
                hoverinfo='none'
            ))

        fig.update_layout(
            title=dict(
                text=f"История коммитов ({len(commits)} коммитов)",
                font=dict(size=16, color='#2c3e50')
            ),
            xaxis=dict(
                title="Дата",
                gridcolor='lightgray',
                showgrid=True
            ),
            yaxis=dict(
                title="",
                showticklabels=False,
                range=[0.5, 1.5]
            ),
            height=400,
            showlegend=True,
            hovermode='closest',
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=50, r=50, t=50, b=50)
        )

        return fig

    except Exception as e:
        st.error(f"Ошибка создания графика: {str(e)}")
        return None

def create_author_stats(commits):
    if not commits:
        return None

    author_counts = {}
    for commit in commits:
        author = commit['author']
        author_counts[author] = author_counts.get(author, 0) + 1

    sorted_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)

    if LIBRARIES.get('plotly'):
        authors = [a[0] for a in sorted_authors]
        counts = [a[1] for a in sorted_authors]

        fig = go.Figure(data=[
            go.Bar(
                x=authors,
                y=counts,
                marker_color=px.colors.qualitative.Plotly[:len(authors)]
            )
        ])

        fig.update_layout(
            title=dict(
                text="Коммиты по авторам",
                font=dict(size=14)
            ),
            xaxis_title="Автор",
            yaxis_title="Количество коммитов",
            height=300,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )

        return fig
    else:
        return sorted_authors

def create_commit_frequency_chart(commits):
    if not LIBRARIES.get('plotly') or not commits:
        return None

    dates = [c['date'] for c in commits]

    date_counts = {}
    for date in dates:
        date_str = date.strftime('%Y-%m-%d')
        date_counts[date_str] = date_counts.get(date_str, 0) + 1

    sorted_dates = sorted(date_counts.items())

    if len(sorted_dates) < 2:
        return None

    dates_list = [d[0] for d in sorted_dates]
    counts_list = [d[1] for d in sorted_dates]

    fig = go.Figure(data=[
        go.Scatter(
            x=dates_list,
            y=counts_list,
            mode='lines+markers',
            line=dict(color='#3498db', width=3),
            marker=dict(size=8, color='#2980b9')
        )
    ])

    fig.update_layout(
        title=dict(
            text="Частота коммитов по времени",
            font=dict(size=14)
        ),
        xaxis_title="Дата",
        yaxis_title="Коммитов в день",
        height=300,
        plot_bgcolor='white',
        paper_bgcolor='white'
    )

    return fig

def analyze_urdf(content):
    stats = {
        'links': len(re.findall(r'<link\s', content)),
        'joints': len(re.findall(r'<joint\s', content)),
        'visuals': len(re.findall(r'<visual>', content, re.IGNORECASE)),
        'collisions': len(re.findall(r'<collision>', content, re.IGNORECASE)),
        'lines': len(content.splitlines()),
        'size': 'Не указан',
        'structure': parse_urdf_structure(content)
    }

    size_match = re.search(r'size="([\d\.\s]+)"', content)
    if size_match:
        try:
            sizes = list(map(float, size_match.group(1).split()))
            if len(sizes) >= 3:
                stats['size'] = f"{sizes[0]:.2f} × {sizes[1]:.2f} × {sizes[2]:.2f}"
        except:
            pass

    mass_match = re.search(r'mass\s*value\s*=\s*"([\d\.]+)"', content)
    if mass_match:
        try:
            mass = float(mass_match.group(1))
            stats['mass'] = f"{mass:.2f} кг"
        except:
            stats['mass'] = "Не указана"

    joint_types = {
        'revolute': len(re.findall(r'type="revolute"', content, re.IGNORECASE)),
        'prismatic': len(re.findall(r'type="prismatic"', content, re.IGNORECASE)),
        'fixed': len(re.findall(r'type="fixed"', content, re.IGNORECASE)),
        'continuous': len(re.findall(r'type="continuous"', content, re.IGNORECASE))
    }
    stats['joint_types'] = joint_types

    geometries = {
        'box': len(re.findall(r'<box', content, re.IGNORECASE)),
        'cylinder': len(re.findall(r'<cylinder', content, re.IGNORECASE)),
        'sphere': len(re.findall(r'<sphere', content, re.IGNORECASE)),
        'mesh': len(re.findall(r'<mesh', content, re.IGNORECASE))
    }
    stats['geometries'] = geometries

    return stats

def main():
    st.set_page_config(
        page_title="URDF Commit Viewer",
        layout="wide",
        page_icon="📊",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': 'https://github.com/urdf-viewer',
            'Report a bug': None,
            'About': "URDF Commit Viewer - Графическое представление истории коммитов URDF моделей"
        }
    )

    st.title("URDF Commit Viewer")
    st.markdown("**Графическое представление истории коммитов URDF моделей роботов**")

    with st.sidebar:
        st.header("Настройки")

        st.caption(f"Версия: 3.0 | Библиотеки: {sum(LIBRARIES.values())}/{len(LIBRARIES)}")

        if LIBRARIES.get('opengl'):
            st.success("3D визуализация доступна")
        else:
            st.warning("⚠ 3D визуализация недоступна")

        source = st.radio("Источник данных:", ["Локальный репозиторий", "GitHub репозиторий"])

        if source == "Локальный репозиторий":
            if not LIBRARIES.get('git'):
                st.error("GitPython не установлен")
                st.info("Установите: `pip install gitpython`")
            else:
                path = st.text_input("Путь к репозиторию:", ".")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Найти файлы", type="primary", use_container_width=True):
                        files = find_local_files(path)
                        if files:
                            st.session_state.files = files
                            st.session_state.repo_path = path
                            st.session_state.source = "local"
                            st.success(f"Найдено: {len(files)} файлов")
                        else:
                            st.warning("URDF файлы не найдены")
                with col2:
                    if st.button("Очистить", use_container_width=True):
                        if 'files' in st.session_state:
                            del st.session_state.files

        else:
            if not LIBRARIES.get('requests'):
                st.error("Requests не установлен")
                st.info("Установите: `pip install requests`")
            else:
                url = st.text_input("URL репозитория:",
                                   "https://github.com/ros/urdf_tutorial",
                                   help="Пример: https://github.com/owner/repo")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Найти файлы", type="primary", use_container_width=True):
                        owner, repo = parse_github_url(url)
                        if owner and repo:
                            files = search_github_files(owner, repo)
                            if files:
                                st.session_state.files = files
                                st.session_state.repo_info = (owner, repo)
                                st.session_state.source = "github"
                                st.success(f"Найдено: {len(files)} файлов")
                            else:
                                st.warning("URDF файлы не найдены")
                with col2:
                    if st.button("Очистить", use_container_width=True):
                        if 'files' in st.session_state:
                            del st.session_state.files

        if 'files' in st.session_state and st.session_state.files:
            st.divider()
            st.subheader("Выбор файла")

            if st.session_state.source == "local":
                file_options = [f["path"] for f in st.session_state.files]
            else:
                file_options = [f"{f['path']}" for f in st.session_state.files]

            selected_file = st.selectbox("Выберите URDF файл:", file_options)

            if st.button("Загрузить историю коммитов", type="primary", use_container_width=True):
                if st.session_state.source == "local":
                    repo_path = st.session_state.repo_path
                    commits = get_local_commits(repo_path, selected_file)
                else:
                    owner, repo = st.session_state.repo_info
                    commits = get_github_commits(owner, repo, selected_file)

                if commits:
                    st.session_state.selected_file = selected_file
                    st.session_state.commits = commits
                    st.success(f"Загружено коммитов: {len(commits)}")
                else:
                    st.warning("Не удалось загрузить историю коммитов")

    if 'commits' in st.session_state:
        commits = st.session_state.commits
        selected_file = st.session_state.selected_file

        st.header(f"Файл: `{selected_file}`")

        st.subheader("Визуализация структуры URDF")

        col_viz1, col_viz2, col_viz3 = st.columns(3)

        with col_viz1:
            viz_commit_idx = st.selectbox(
                "Выберите коммит для визуализации:",
                range(len(commits)),
                format_func=lambda i: (
                    f"{commits[i]['sha']} - "
                    f"{commits[i]['message'][:30]}..."
                ),
                key="viz_commit_selector"
            )

        with col_viz2:
            st.write("")
            viz_clicked = st.button("Визуализировать структуру", type="primary", use_container_width=True)

        with col_viz3:
            st.write("")
            if LIBRARIES.get('opengl'):
                viz_3d_clicked = st.button("Открыть 3D модель", type="secondary", use_container_width=True)
            else:
                viz_3d_clicked = False
                st.button("Открыть 3D модель", disabled=True, help="Требуется PyOpenGL", use_container_width=True)

        if viz_clicked:
            selected_commit = commits[viz_commit_idx]

            with st.spinner(f"Загрузка и визуализация коммита {selected_commit['sha']}..."):
                if st.session_state.source == "local":
                    repo_info = st.session_state.repo_path
                else:
                    repo_info = st.session_state.repo_info

                content = get_file_content_for_commit(
                    st.session_state.source,
                    repo_info,
                    selected_commit['full_sha'],
                    selected_file
                )

                if content:
                    st.session_state.viz_commit = selected_commit
                    st.session_state.viz_content = content
                    st.session_state.show_viz = True

        if viz_3d_clicked and LIBRARIES.get('opengl'):
            selected_commit = commits[viz_commit_idx]

            with st.spinner(f"Запуск 3D визуализации коммита {selected_commit['sha']}..."):
                if st.session_state.source == "local":
                    repo_info = st.session_state.repo_path
                else:
                    repo_info = st.session_state.repo_info

                content = get_file_content_for_commit(
                    st.session_state.source,
                    repo_info,
                    selected_commit['full_sha'],
                    selected_file
                )

                if content:
                    try:
                        title = f"URDF 3D - {selected_file} - {selected_commit['sha'][:8]}"
                        process = visualize_urdf_3d_separate_process(content, title)
                        if process:
                            st.success("3D окно запущено в отдельном процессе!")
                            st.info("""
                            **Инструкция:**
                            1. Откроется отдельное системное окно с 3D-моделью
                            2. Управление в 3D-окне:
                               - ЛКМ + мышь: вращение камеры
                               - W/S: вращение по вертикали
                               - A/D: вращение по горизонтали
                               - +/-: приближение/отдаление
                               - R: сброс камеры
                               - Q/ESC: выход
                            3. Проверьте панель задач/док для нового окна
                            """)

                            st.code(f"3D просмотрщик запущен для коммита: {selected_commit['sha']}", language="bash")
                    except Exception as e:
                        st.error(f"Ошибка запуска 3D просмотрщика: {str(e)}")
                        st.info("Проверьте, что установлены все зависимости:\n```bash\npip install PyOpenGL PyOpenGL-accelerate\n```")
        elif viz_3d_clicked and not LIBRARIES.get('opengl'):
            st.error("Для 3D визуализации требуется PyOpenGL")
            st.info("Установите: `pip install PyOpenGL PyOpenGL-accelerate`")

        if 'show_viz' in st.session_state and st.session_state.show_viz:
            selected_commit = st.session_state.viz_commit
            content = st.session_state.viz_content

            st.info(f"**Визуализация коммита:** {selected_commit['sha']} - {selected_commit['message'][:100]}...")

            structure = parse_urdf_structure(content)
            stats = analyze_urdf(content)

            viz_tab1, viz_tab2 = st.tabs(["Иерархия", "Компоненты"])

            with viz_tab1:
                st.subheader("Иерархическая структура")
                st.caption("Древовидное представление связей")

                hierarchy_diagram = create_hierarchical_diagram(
                    structure,
                    f"Иерархия URDF - Коммит {selected_commit['sha'][:8]}"
                )
                if hierarchy_diagram:
                    st.image(hierarchy_diagram, use_column_width=True)
                else:
                    st.info("Не удалось создать иерархическую диаграмму")

            with viz_tab2:
                st.subheader("Статистика компонентов")
                st.caption("Количественный анализ элементов URDF")

                component_diagram = create_component_visualization(
                    content,
                    f"Компоненты URDF - Коммит {selected_commit['sha'][:8]}"
                )
                if component_diagram:
                    st.image(component_diagram, use_column_width=True)

                col_stat1, col_stat2 = st.columns(2)

                with col_stat1:
                    st.metric("Всего линков", stats['links'])
                    st.metric("Всего соединений", stats['joints'])
                    st.metric("Визуалов", stats['visuals'])
                    st.metric("Коллизий", stats['collisions'])

                with col_stat2:
                    st.write("**Типы соединений:**")
                    for j_type, count in stats['joint_types'].items():
                        if count > 0:
                            st.write(f"- {j_type}: {count}")

                    st.write("**Типы геометрий:**")
                    for geom, count in stats['geometries'].items():
                        if count > 0:
                            st.write(f"- {geom}: {count}")

        st.divider()
        st.subheader("Сравнение коммитов")

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            old_commit_idx = st.selectbox(
                "Старый коммит (база для сравнения):",
                range(len(commits)),
                format_func=lambda i: (
                    f"{commits[i]['sha']} - "
                    f"{commits[i]['message'][:40]}... - "
                    f"{commits[i]['date'].strftime('%Y-%m-%d')}"
                ),
                key="old_commit_selector"
            )

        with col2:
            new_commit_idx = st.selectbox(
                "Новый коммит (сравниваемый):",
                range(len(commits)),
                format_func=lambda i: (
                    f"{commits[i]['sha']} - "
                    f"{commits[i]['message'][:40]}... - "
                    f"{commits[i]['date'].strftime('%Y-%m-%d')}"
                ),
                index=0 if len(commits) > 0 else 0,
                key="new_commit_selector"
            )

        with col3:
            st.write("")
            compare_clicked = st.button("Сравнить коммиты", type="primary", use_container_width=True)

        if old_commit_idx != new_commit_idx and compare_clicked:
            old_commit = commits[old_commit_idx]
            new_commit = commits[new_commit_idx]

            if old_commit['date'] > new_commit['date']:
                old_commit, new_commit = new_commit, old_commit
                old_commit_idx, new_commit_idx = new_commit_idx, old_commit_idx

            with st.spinner(f"Загрузка и сравнение коммитов..."):
                if st.session_state.source == "local":
                    repo_info = st.session_state.repo_path
                else:
                    repo_info = st.session_state.repo_info

                old_content = get_file_content_for_commit(
                    st.session_state.source,
                    repo_info,
                    old_commit['full_sha'],
                    selected_file
                )

                new_content = get_file_content_for_commit(
                    st.session_state.source,
                    repo_info,
                    new_commit['full_sha'],
                    selected_file
                )

                if old_content and new_content:
                    st.session_state.old_commit = old_commit
                    st.session_state.new_commit = new_commit
                    st.session_state.old_content = old_content
                    st.session_state.new_content = new_content
                    st.session_state.show_comparison = True

        if 'show_comparison' in st.session_state and st.session_state.show_comparison:
            old_commit = st.session_state.old_commit
            new_commit = st.session_state.new_commit
            old_content = st.session_state.old_content
            new_content = st.session_state.new_content

            col_info1, col_info2 = st.columns(2)

            with col_info1:
                with st.expander(f"Старый коммит: {old_commit['sha']}", expanded=True):
                    st.metric("Хэш", old_commit['sha'])
                    st.metric("Автор", old_commit['author'])
                    st.metric("Дата", old_commit['date'].strftime('%Y-%m-%d %H:%M'))
                    st.info(f"**Сообщение:** {old_commit['message']}")

                    old_stats = analyze_urdf(old_content)
                    st.metric("Линков", old_stats['links'])
                    st.metric("Соединений", old_stats['joints'])

            with col_info2:
                with st.expander(f"Новый коммит: {new_commit['sha']}", expanded=True):
                    st.metric("Хэш", new_commit['sha'])
                    st.metric("Автор", new_commit['author'])
                    st.metric("Дата", new_commit['date'].strftime('%Y-%m-%d %H:%M'))
                    st.info(f"**Сообщение:** {new_commit['message']}")

                    new_stats = analyze_urdf(new_content)
                    st.metric("Линков", new_stats['links'])
                    st.metric("Соединений", new_stats['joints'])

            st.subheader("Разница в статистике")

            diff_cols = st.columns(4)
            with diff_cols[0]:
                diff_links = new_stats['links'] - old_stats['links']
                st.metric(
                    "Линков",
                    new_stats['links'],
                    delta=f"{diff_links:+d}"
                )

            with diff_cols[1]:
                diff_joints = new_stats['joints'] - old_stats['joints']
                st.metric(
                    "Соединений",
                    new_stats['joints'],
                    delta=f"{diff_joints:+d}"
                )

            with diff_cols[2]:
                diff_visuals = new_stats['visuals'] - old_stats['visuals']
                st.metric(
                    "Визуалов",
                    new_stats['visuals'],
                    delta=f"{diff_visuals:+d}"
                )

            with diff_cols[3]:
                diff_collisions = new_stats['collisions'] - old_stats['collisions']
                st.metric(
                    "Коллизий",
                    new_stats['collisions'],
                    delta=f"{diff_collisions:+d}"
                )

            changes = analyze_code_changes(old_content, new_content)
            diff_result = compare_commits(old_content, new_content,
                                         old_commit['sha'], new_commit['sha'])

            tab1, tab2, tab3 = st.tabs(["Графики изменений", "Diff изменений", "Полный код"])

            with tab1:
                col_graph1, col_graph2 = st.columns(2)

                with col_graph1:
                    changes_chart = create_change_stats_chart(changes)
                    if changes_chart:
                        st.plotly_chart(changes_chart, use_container_width=True)
                    else:
                        st.info("Нет данных для построения графика изменений")

                with col_graph2:
                    element_chart = create_element_changes_chart(changes)
                    if element_chart:
                        st.plotly_chart(element_chart, use_container_width=True)
                    else:
                        st.info("Нет изменений элементов URDF")

                if changes:
                    st.subheader("Детальная статистика изменений")

                    stats_cols = st.columns(4)
                    with stats_cols[0]:
                        st.metric("Добавлено строк", changes.get('added_lines', 0))
                    with stats_cols[1]:
                        st.metric("Удалено строк", changes.get('removed_lines', 0))
                    with stats_cols[2]:
                        st.metric("Изменено строк", changes.get('modified_lines', 0))
                    with stats_cols[3]:
                        st.metric("Всего строк", changes.get('unchanged_lines', 0))

                    if changes.get('changes_by_type'):
                        st.write("**Изменения по элементам URDF:**")
                        element_changes = changes['changes_by_type']
                        for elem_type, count in sorted(element_changes.items(), key=lambda x: x[1], reverse=True):
                            st.write(f"- **{elem_type}**: {count} изменений")

            with tab2:
                st.subheader("Разница между коммитами")
                st.caption(f"Сравнение {old_commit['sha']} → {new_commit['sha']}")

                if diff_result:
                    diff_html = create_diff_html(diff_result)
                    components.html(diff_html, height=500, scrolling=True)
                else:
                    st.info("Нет различий между коммитами или не удалось загрузить данные")

            with tab3:
                col_code1, col_code2 = st.columns(2)

                with col_code1:
                    st.subheader(f"Код коммита {old_commit['sha']}")
                    st.code(old_content, language="xml", line_numbers=True)

                with col_code2:
                    st.subheader(f"Код коммита {new_commit['sha']}")
                    st.code(new_content, language="xml", line_numbers=True)

        st.divider()
        st.subheader("Временная линия коммитов")

        timeline_fig = create_commit_graph(commits, old_commit_idx if 'old_commit_idx' in locals() else 0)
        if timeline_fig:
            st.plotly_chart(timeline_fig, use_container_width=True)

        col_stats1, col_stats2 = st.columns(2)

        with col_stats1:
            st.subheader("Статистика по авторам")
            author_stats = create_author_stats(commits)
            if isinstance(author_stats, go.Figure):
                st.plotly_chart(author_stats, use_container_width=True)
            elif author_stats:
                st.write("**Количество коммитов по авторам:**")
                for author, count in author_stats:
                    st.write(f"- **{author}**: {count} коммитов")

        with col_stats2:
            st.subheader("Частота коммитов")
            freq_chart = create_commit_frequency_chart(commits)
            if freq_chart:
                st.plotly_chart(freq_chart, use_container_width=True)
            else:
                st.info("Недостаточно данных для построения графика частоты")

        st.subheader("Все коммиты")

        commit_data = []
        for i, c in enumerate(commits):
            is_old = "⬅️" if i == (old_commit_idx if 'old_commit_idx' in locals() else -1) else ""
            is_new = "➡️" if i == (new_commit_idx if 'new_commit_idx' in locals() else -1) else ""

            commit_data.append({
                "№": i + 1,
                "Сравнение": f"{is_old} {is_new}".strip(),
                "Хэш": c['sha'],
                "Дата": c['date'].strftime('%Y-%m-%d %H:%M'),
                "Автор": c['author'],
                "Сообщение": c['message'][:80] + "..." if len(c['message']) > 80 else c['message']
            })

        st.dataframe(
            commit_data,
            column_config={
                "Сравнение": st.column_config.TextColumn("Сравнение", width="small"),
                "Хэш": st.column_config.TextColumn("Хэш", width="small"),
                "Дата": st.column_config.TextColumn("Дата", width="medium"),
                "Автор": st.column_config.TextColumn("Автор", width="medium"),
                "Сообщение": st.column_config.TextColumn("Сообщение", width="large")
            },
            hide_index=True,
            use_container_width=True
        )

    else:
        st.info("**Начните с выбора источника данных в боковой панели**")

        with st.expander("Примеры GitHub репозиториев с URDF"):
            st.markdown("""
            ### Популярные репозитории с моделями роботов:

            **Для обучения:**
            - `https://github.com/ros/urdf_tutorial` - Учебные примеры URDF (рекомендуется)
            - `https://github.com/ros-industrial/universal_robot` - Промышленные роботы UR
            - `https://github.com/ros-simulation/gazebo_ros_demos` - Демо для Gazebo

            **Готовые модели:**
            - `https://github.com/ros-industrial/fanuc` - Роботы Fanuc
            - `https://github.com/PR2/pr2_common` - PR2 робот
            - `https://github.com/turtlebot/turtlebot` - TurtleBot

            **Примеры файлов для просмотра:**
            - `urdf/01-myfirst.urdf` - Простейший робот
            - `urdf/03-origins.urdf` - Сложная геометрия
            - `urdf/08-macroed.urdf.xacro` - XACRO файлы
            """)

        with st.expander("Статус библиотек"):
            lib_cols = st.columns(3)
            for i, (lib_name, is_available) in enumerate(LIBRARIES.items()):
                with lib_cols[i % 3]:
                    if is_available:
                        st.success(f"{lib_name}")
                    else:
                        st.error(f"{lib_name}")

            st.info("""
            **Для полной функциональности (включая 3D):**
            ```bash
            pip install streamlit gitpython requests plotly numpy networkx matplotlib PyOpenGL PyOpenGL-accelerate
            ```

            **Минимальный набор для работы:**
            ```bash
            pip install streamlit gitpython requests
            ```
            """)

        with st.expander("Инструкция"):
            st.markdown("""
            1. Вставьте URL GitHub репозитория (например `https://github.com/ros/urdf_tutorial`)
            2. Нажмите "Найти URDF файлы"
            3. Выберите файл из списка
            4. Нажмите "Показать историю коммитов"
            5. Выберите два коммита для сравнения или один для визуализации
            """)
        with st.expander("Функционал"):
            st.markdown("""
            - 3D визуализация URDF моделей в отдельном системном окне
            - 2D визуализация структуры URDF
            - Иерархические диаграммы
            - Статистика компонентов
            - Сравнение двух коммитов
            - Графики изменений кода
            - Анализ по авторам
            - График частоты коммитов
            - Diff между коммитами
            - Полные коды версий для сравненияч
            """)

if __name__ == "__main__":
    main()
