import sys
import subprocess
import socket
import importlib.util
import platform
import time
import os

class ConsoleUI:
    @staticmethod
    def print_header():
        title = " URDF COMMIT VIEWER "
        width = 60

        print("\n" + "=" * width)
        print(title.center(width))
        print("Графическое представление истории коммитов URDF моделей".center(width))
        print("=" * width)

    @staticmethod
    def print_section(title):
        print(f"\n▶ {title}")
        print("-" * 50)

    @staticmethod
    def print_status(message, status="info"):
        icons = {
            'success': '[✓]',
            'error': '[✗]',
            'warning': '[⚠]',
            'info': '[ℹ]',
            'loading': '[↻]'
        }

        icon = icons.get(status, '')

        if status == 'loading':
            print(f"  {icon} {message}", end='\r')
        else:
            print(f"  {icon} {message}")

    @staticmethod
    def print_table(headers, rows):
        if not rows:
            return

        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        header_line = "  "
        separator_line = "  "
        for i, header in enumerate(headers):
            header_line += str(header).ljust(col_widths[i])
            if i < len(headers) - 1:
                header_line += " │ "
                separator_line += "─" * col_widths[i] + "─┼─"
            else:
                separator_line += "─" * col_widths[i]

        print(header_line)
        print(separator_line)

        for row in rows:
            row_line = "  "
            for i, cell in enumerate(row):
                row_line += str(cell).ljust(col_widths[i])
                if i < len(row) - 1:
                    row_line += " │ "
            print(row_line)

def check_python_version():
    if sys.version_info < (3, 7):
        ConsoleUI.print_status("Требуется Python 3.7 или выше", "error")
        return False

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ConsoleUI.print_status(f"Python {version}", "success")
    return True

def check_dependencies():
    dependencies = [
        ('streamlit', 'streamlit', 'Веб-интерфейс'),
        ('git', 'gitpython', 'Работа с Git'),
        ('requests', 'requests', 'HTTP запросы'),
        ('plotly', 'plotly', 'Графики коммитов'),
        ('numpy', 'numpy', 'Математические операции'),
        ('networkx', 'networkx', 'Графовые структуры'),
        ('matplotlib', 'matplotlib', '2D визуализация'),
        ('OpenGL', 'PyOpenGL', '3D визуализация'),
    ]

    ConsoleUI.print_section("ПРОВЕРКА ЗАВИСИМОСТЕЙ")

    missing = []
    installed = []

    for module, package, description in dependencies:
        spec = importlib.util.find_spec(module)
        if spec is None:
            if package == 'PyOpenGL':
                try:
                    import OpenGL
                    spec = importlib.util.find_spec('OpenGL')
                except:
                    spec = None

            if spec is None:
                missing.append((package, description))
                ConsoleUI.print_status(f"{package}: {description}", "error")
            else:
                installed.append((package, description))
                ConsoleUI.print_status(f"{package}: {description}", "success")
        else:
            installed.append((package, description))
            ConsoleUI.print_status(f"{package}: {description}", "success")

    return missing, installed

def install_dependencies(missing):
    if not missing:
        return True

    ConsoleUI.print_section("УСТАНОВКА ЗАВИСИМОСТЕЙ")

    for package, description in missing:
        ConsoleUI.print_status(f"Установка {package}...", "loading")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                capture_output=True,
                text=True,
                check=False
            )

            time.sleep(0.5)

            if result.returncode == 0:
                ConsoleUI.print_status(f"{package} установлен", "success")
            else:
                ConsoleUI.print_status(f"Ошибка установки {package}", "error")
                if result.stderr:
                    error_msg = result.stderr[:100].strip()
                    if error_msg:
                        print(f"      {error_msg}")
                return False

        except Exception as e:
            ConsoleUI.print_status(f"Исключение: {str(e)[:50]}", "error")
            return False

    return True

def get_system_info():
    system = platform.system()
    release = platform.release()
    machine = platform.machine()

    return [
        ("Система", f"{system} {release}"),
        ("Архитектура", machine),
        ("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    ]

def find_free_port(start_port=8501):
    for port in range(start_port, start_port + 20):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()

            if result != 0:
                return port
        except:
            continue
    return start_port

def start_application(port):
    ConsoleUI.print_section("ЗАПУСК ПРИЛОЖЕНИЯ")

    info_rows = [
        ("Порт", str(port)),
        ("URL", f"http://localhost:{port}"),
    ]

    ConsoleUI.print_table(["Параметр", "Значение"], info_rows)

    print(f"\nℹ Для остановки нажмите Ctrl+C")
    print("=" * 50)

    env = os.environ.copy()
    env['STREAMLIT_SERVER_HEADLESS'] = 'true'
    env['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'
    env['STREAMLIT_SERVER_ENABLE_CORS'] = 'false'
    env['STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION'] = 'false'

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        "urdf-viewer.py",
        "--server.port", str(port),
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "light",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--logger.level", "error",
        "--client.showErrorDetails", "false",
        "--global.developmentMode", "false"
    ]

    try:
        with open(os.devnull, 'w') as devnull:
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=devnull,
                text=True,
                bufsize=1
            )

        ConsoleUI.print_status("Приложение запущено", "success")
        print()

        for line in process.stdout:
            if "Network URL" in line or "External URL" in line:
                print(f"  {line.strip()}")
            elif "ERROR" in line or "Exception" in line:
                print(f"  {line.strip()}")

        process.wait()

    except KeyboardInterrupt:
        ConsoleUI.print_status("\nОстановка приложения...", "warning")
        if process:
            process.terminate()
            process.wait(timeout=5)
        ConsoleUI.print_status("Приложение остановлено", "success")

    except Exception as e:
        ConsoleUI.print_status(f"Ошибка запуска: {str(e)}", "error")
        return False

    return True

def main():
    ConsoleUI.print_header()

    system_info = get_system_info()
    ConsoleUI.print_table(["Системная информация", ""], system_info)

    if not check_python_version():
        return

    missing, installed = check_dependencies()

    if missing:
        if not install_dependencies(missing):
            ConsoleUI.print_status("Не удалось установить все зависимости", "error")
            print(f"\nПопробуйте установить вручную:")
            for package, _ in missing:
                print(f"  pip install {package}")
            return
    else:
        ConsoleUI.print_status("Все зависимости установлены", "success")

    port = find_free_port()
    start_application(port)

    print(f"\n✓ Работа завершена")

if __name__ == "__main__":
    main()
