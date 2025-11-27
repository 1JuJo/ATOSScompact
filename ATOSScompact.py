import sys
import os
import time
import json
import threading
import signal
import traceback
import argparse
import socket
import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Set, Tuple

import psutil
from pynput import keyboard

from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QPalette, QGuiApplication
from PyQt5.QtCore import Qt, QTimer, QMetaObject, Q_ARG, pyqtSignal, QObject

from selenium import webdriver
from selenium.common.exceptions import (
    NoAlertPresentException, NoSuchElementException, WebDriverException,
    TimeoutException, UnexpectedAlertPresentException, StaleElementReferenceException
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("urllib3").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

REQUIRED_DATA_KEYS = {
    "Status", "Heutige Anwesenheit", "Heutige Pause",
    "Kommen", "Gehen", "Arbeitszeitkonto"
}

class TimeUtils:
    @staticmethod
    def add_times(time1: str, time2: str) -> str:
        try:
            negative1 = time1.startswith("-")
            negative2 = time2.startswith("-")
            t1 = time1[1:] if negative1 else time1
            t2 = time2[1:] if negative2 else time2

            dt1 = datetime.strptime(t1, "%H:%M")
            dt2 = datetime.strptime(t2, "%H:%M")

            mins1 = dt1.hour * 60 + dt1.minute
            mins2 = dt2.hour * 60 + dt2.minute

            if negative1: mins1 = -mins1
            if negative2: mins2 = -mins2

            total = mins1 + mins2
            hours, minutes = divmod(abs(total), 60)
            formatted = "{:02d}:{:02d}".format(hours, minutes)
            return "-" + formatted if total < 0 else formatted
        except Exception:
            return "00:00"

    @staticmethod
    def subtract_times(time1: str, time2: str) -> str:
        try:
            negative1 = time1.startswith("-")
            negative2 = time2.startswith("-")
            t1 = time1[1:] if negative1 else time1
            t2 = time2[1:] if negative2 else time2

            dt1 = datetime.strptime(t1, "%H:%M")
            dt2 = datetime.strptime(t2, "%H:%M")

            mins1 = dt1.hour * 60 + dt1.minute
            mins2 = dt2.hour * 60 + dt2.minute

            if negative1: mins1 = -mins1
            if negative2: mins2 = -mins2

            total = mins1 - mins2
            hours, minutes = divmod(abs(total), 60)
            formatted = "{:02d}:{:02d}".format(hours, minutes)
            return "-" + formatted if total < 0 else formatted
        except Exception:
            return "00:00"

    @staticmethod
    def check_minus(input_string: str) -> str:
        return "✔️" if "-" in input_string or input_string == "00:00" else input_string

    @staticmethod
    def set_emoji_font(text: str, emoji: bool = False) -> str:
        style = "font-size: 15px;"
        if emoji:
            style += " font-family: 'notocoloremoji';"
        return f'<span style="{style}">{text}</span>'

class DataProcessor:
    @staticmethod
    def find_starting_points(response_body: Dict) -> Tuple[int, int, int]:
        startingpoints = {
            "gestempelte Wochen-AZ": -1,
            "Kommen": -1,
            "Status": -1
        }

        if "rs" in response_body:
            for i in range(len(response_body["rs"])):
                try:
                    # Deep access with error handling
                    row = response_body["rs"][i]
                    if len(row) > 1 and len(row[1]) > 1:
                        val_container = row[1][1]
                        if val_container and len(val_container) > 0:
                            val = val_container[0][4][0][4][0][2].get("value")
                            if val in startingpoints and startingpoints[val] == -1:
                                startingpoints[val] = i
                                if all(v != -1 for v in startingpoints.values()):
                                    break
                except (IndexError, KeyError, TypeError):
                    continue

        return startingpoints["gestempelte Wochen-AZ"], startingpoints["Kommen"], startingpoints["Status"]

    @staticmethod
    def extract_connections(response_body_str: str) -> Dict[str, Any]:
        # Fix single quotes and other syntax issues
        data_fixed = response_body_str.replace("'", '"')
        data_fixed = re.sub(r'(?<=\{|,)\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'"\1":', data_fixed)
        data_fixed = data_fixed.replace('\\', '\\\\')

        try:
            response_body = json.loads(data_fixed)
        except json.JSONDecodeError:
            return {}

        key = 0
        key2 = 2
        info = {}

        sp_az, sp_kommen, sp_status = DataProcessor.find_starting_points(response_body)
        
        try:
            if sp_status != -1:
                for value2 in range(1, 6):
                    if value2 % 2 == 0 or value2 == 1:
                        k = response_body["rs"][sp_status][1][value2][0][4][0][4][key][2]["value"]
                        v = response_body["rs"][sp_status][1][value2][0][4][0][4][key2][2]["value"]
                        info[k] = v
            
            if sp_kommen != -1:
                for value2 in range(1, 4):
                    if value2 % 2 == 0 or value2 == 1:
                        k = response_body["rs"][sp_kommen][1][value2][0][4][0][4][key][2]["value"]
                        v = response_body["rs"][sp_kommen][1][value2][0][4][0][4][key2][2]["value"]
                        info[k] = v
            
            if sp_az != -1:
                for value2 in range(1, 7):
                    if not value2 % 2 == 0:
                        k = response_body["rs"][sp_az][1][value2][0][4][0][4][key][2]["value"]
                        v = str(response_body["rs"][sp_az][1][value2][0][4][0][4][key2][2]["value"])
                        if k == "Arbeitszeitkonto":
                            info[k] = v.replace("\\u200B", "")
                        else:
                            info[k] = v
        except Exception:
            pass

        return info

    @staticmethod
    def format_display_data(data: Dict[str, Any]) -> list:
        def format_line(emoji, text):
            return f"{TimeUtils.set_emoji_font(emoji, True)}{TimeUtils.set_emoji_font(text, False)}"

        final_list = []
        arbeitszeit = data.get("Heutige Anwesenheit", "0:00")
        pause = data.get("Heutige Pause", "0:00")
        kommen = data.get("Kommen", "0:00")
        gehen = data.get("Gehen", "k.A.")
        ueberstunden = data.get("Arbeitszeitkonto", "0:00")
        
        current_time = TimeUtils.add_times(TimeUtils.add_times(arbeitszeit, kommen), pause)
        
        # Pause calculations
        p_dt = datetime.strptime(pause, "%H:%M") if pause != "k.A." else datetime.strptime("0:00", "%H:%M")
        pause2 = "0:30" if p_dt < datetime.strptime("0:30", "%H:%M") else pause
        
        final_list.append(format_line("⏰", arbeitszeit))
        final_list.append(format_line("🍔", pause))
        final_list.append(format_line("👣", kommen))

        if gehen == "k.A.":
            g1 = TimeUtils.add_times(TimeUtils.add_times(kommen, '6:00'), pause)
            g2 = TimeUtils.add_times(TimeUtils.add_times(kommen, '7:42'), pause2)
            g3 = TimeUtils.add_times(TimeUtils.add_times(kommen, '9:00'), pause2)
            
            diff1 = TimeUtils.check_minus(TimeUtils.subtract_times(g1, current_time))
            diff2 = TimeUtils.check_minus(TimeUtils.subtract_times(g2, current_time))
            diff3 = TimeUtils.check_minus(TimeUtils.subtract_times(g3, current_time))
            
            final_list.append(TimeUtils.set_emoji_font(f"G : {g1}/{g2}/{g3}", False))
            final_list.append(TimeUtils.set_emoji_font(f"G in h : {diff1}/{diff2}/{diff3}", False))
        else:
            now_str = datetime.now().strftime('%H:%M')
            diff_now = TimeUtils.subtract_times(now_str, gehen)
            diff_pause = TimeUtils.add_times(diff_now, pause)
            final_list.append(TimeUtils.set_emoji_font(f"G{gehen}({diff_now}/{diff_pause})", False))

        # Overtime calculation
        az_dt = datetime.strptime(arbeitszeit, '%H:%M')
        target_dt = datetime.strptime('7:42', '%H:%M')
        
        diff_az = TimeUtils.subtract_times(arbeitszeit, '7:42')
        
        if az_dt < target_dt:
            ot_calc = TimeUtils.add_times(diff_az, ueberstunden)
            ot_str = f"{ueberstunden} ({ot_calc})"
        else:
            ot_calc = TimeUtils.add_times(diff_az, ueberstunden)
            ot_str = f"{ot_calc} +{diff_az}"
            
        final_list.append(format_line("🌙", ot_str))
        
        return final_list

class Circle(QWidget):
    def __init__(self, initial_state="Abwesend"):
        super().__init__()
        self.diameter = 18
        self.color = QColor(Qt.red)
        self.update_color(initial_state)
        self.setFixedSize(self.diameter, self.diameter)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(QBrush(self.color, Qt.SolidPattern))
        painter.drawEllipse(0, 0, self.diameter, self.diameter)

    def update_color(self, state):
        self.color = QColor(Qt.green if state == "Anwesend" else Qt.red)
        self.update()

class ClockInButton(QWidget):
    clicked_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton("Einstempeln")
        self.button.setStyleSheet(
            """
            QPushButton { background-color: #333; color: white; border: none; padding: 6px; }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #222; }
            """
        )
        self.button.clicked.connect(self.clicked_signal.emit)
        layout.addWidget(self.button)

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ATOSS Compact")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.circle = Circle()
        layout.addWidget(self.circle)

        self.label = QLabel("Programm wird gestartet")
        self.label.setTextFormat(Qt.RichText)
        layout.addWidget(self.label)

        self.clock_button = ClockInButton()
        self.clock_button.hide()
        
        self.oldPos = None
        self.resize(420, self.circle.height() + 8)
        
        # Setup palette
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(19, 19, 19))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        self.setPalette(palette)

    def update_status(self, status, text_lines):
        self.circle.update_color(status)
        self.label.setText("   |   ".join(text_lines))
        self.adjust_position()
        
        if status != "Anwesend":
            self.show_clock_button()
        else:
            self.clock_button.hide()

    def set_message(self, message):
        self.label.setText(message)
        self.adjust_position()

    def adjust_position(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            screens = QGuiApplication.screens()
            if screens:
                screen = screens[0]
        
        if screen:
            geo = screen.geometry()
            self.move(geo.x(), geo.y())
            if not self.clock_button.isHidden():
                self.clock_button.move(geo.x() + 12, geo.y() + 48)

    def show_clock_button(self):
        self.clock_button.show()
        self.adjust_position()

    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.oldPos:
            delta = event.globalPos() - self.oldPos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPos()

class BrowserController(QObject):
    update_ui = pyqtSignal(str, list)
    update_msg = pyqtSignal(str)
    
    def __init__(self, debug=False):
        super().__init__()
        self.debug = debug
        self.driver = None
        self.running = True
        self.extracted_data = {}
        self.last_reload = time.time()
        self.initialized = False
        self.amstempeln = False
        self.driver_lock = threading.Lock()
        self.antidesync_time = time.time()
        self.loaded = False

    def start(self):
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _bootstrap(self):
        self.update_msg.emit("Warte auf Internet...")
        self._wait_for_internet()
        
        self.update_msg.emit("Starte Browser...")
        self._init_driver()
        
        while self.running:
            self.update_msg.emit("Lade ATOSS...")
            if self._load_page():
                threading.Thread(target=self._monitor_network, daemon=True).start()
                threading.Thread(target=self._watchdog, daemon=True).start()
                self.update_msg.emit("ATOSS geladen | Warte auf Daten...")
                break
            
            self.update_msg.emit("Fehler beim Laden. Neuer Versuch in 100ms...")
            time.sleep(0.1)

    def _wait_for_internet(self, host="8.8.8.8", port=53, timeout=5):
        while self.running:
            try:
                socket.setdefaulttimeout(timeout)
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
                return
            except OSError:
                time.sleep(2)

    def _clean_stale_locks(self, user_data_dir):
        try:
            lock_file = os.path.join(user_data_dir, "SingletonLock")
            if os.path.islink(lock_file):
                target = os.readlink(lock_file)
                # target format: hostname-pid
                pid_str = target.split("-")[-1]
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if not psutil.pid_exists(pid):
                        logger.info(f"Removing stale lock file: {lock_file} (PID {pid} not found)")
                        os.unlink(lock_file)
                        for name in ["SingletonCookie", "SingletonSocket"]:
                            p = os.path.join(user_data_dir, name)
                            if os.path.exists(p) or os.path.islink(p):
                                try:
                                    os.unlink(p)
                                except OSError:
                                    pass
        except Exception as e:
            logger.warning(f"Failed to clean locks: {e}")

    def _init_driver(self):
        opts = Options()
        opts.binary_location = "/usr/bin/google-chrome"
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--ignore-certificate-errors")
        opts.add_argument("--ignore-ssl-errors")
        
        base_path = os.path.dirname(os.path.abspath(__file__))
        selenium_path = os.path.join(base_path, "selenium")
        
        self._clean_stale_locks(selenium_path)
        opts.add_argument(f"--user-data-dir={selenium_path}")
        
        opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        if not self.debug:
            opts.add_argument("--headless")
        
        try:
            with self.driver_lock:
                self.driver = webdriver.Chrome(options=opts)
        except Exception as e:
            logger.error(f"Driver init failed: {e}")
            traceback.print_exc()

    def _load_page(self):
        url = 'https://hoffmann-group.atoss.com/hoffmanngroupprod/html?security.sso=true'
        with self.driver_lock:
            if not self.driver: return False
            return self._robust_get(url)

    def _robust_get(self, url, retries=6):
        for attempt in range(1, retries + 1):
            try:
                self.driver.get(url)
                
                # Check for error page content
                try:
                    if "ERR_" in self.driver.page_source:
                        raise WebDriverException("Network error page detected")
                except Exception:
                    pass

                # Simple wait for body
                WebDriverWait(self.driver, 5).until(
                    lambda d: d.execute_script("return document.body && document.body.childElementCount > 0")
                )
                return True
            except Exception as e:
                logger.warning(f"Load attempt {attempt} failed: {e}")
                time.sleep(1)
        return False

    def _monitor_network(self):
        interesting_requests = {}
        
        while self.running:
            with self.driver_lock:
                if not self.driver:
                    time.sleep(0.5)
                    continue
                
                try:
                    logs = self.driver.get_log('performance')
                    for entry in logs:
                        message = json.loads(entry['message'])['message']
                        method = message['method']
                        params = message['params']
                        
                        if method == 'Network.responseReceived':
                            response = params['response']
                            url = response['url']
                            if 'zkauA10' in url and response['status'] == 200:
                                if response.get('mimeType', '').startswith('text/plain'):
                                    interesting_requests[params['requestId']] = url
                                    
                        elif method == 'Network.loadingFinished':
                            req_id = params['requestId']
                            if req_id in interesting_requests:
                                try:
                                    res = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                                    body = res['body']
                                    if res.get('base64Encoded', False):
                                        import base64
                                        body = base64.b64decode(body).decode('utf-8')
                                    
                                    info = DataProcessor.extract_connections(body)
                                    if info:
                                        self.extracted_data.update(info)
                                        if REQUIRED_DATA_KEYS.issubset(self.extracted_data.keys()):
                                            formatted = DataProcessor.format_display_data(self.extracted_data)
                                            self.update_ui.emit(self.extracted_data["Status"], formatted)
                                            self.loaded = True
                                            self.antidesync_time = time.time()
                                            self.initialized = True
                                except Exception:
                                    pass
                                del interesting_requests[req_id]
                except Exception:
                    pass
            time.sleep(0.2)

    def _enter_frame(self):
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "applicationIframe"))
            )
            iframe = self.driver.find_element(By.TAG_NAME, 'iframe')
            self.driver.switch_to.frame(iframe)
            return True
        except Exception:
            self._reload_page()
            return False

    def _reload_page(self):
        self.loaded = False
        try:
            self.update_msg.emit(self.extracted_data.get("Status", "Abwesend") + " ⟳")
            self.driver.refresh()
            try:
                self.driver.switch_to.alert.accept()
            except NoAlertPresentException:
                pass
        except Exception:
            pass

    def stempeln(self, is_break):
        if self.amstempeln: return
        self.amstempeln = True
        
        action_name = "Pause" if is_break else "Anwesenheitsbeginn"
        
        while self.running:
            if not self.loaded:
                self.update_msg.emit(f"Warte auf Seite für {action_name}...")
                while not self.loaded and self.running:
                    time.sleep(0.2)
            
            if not self.running:
                self.amstempeln = False
                return

            with self.driver_lock:
                if not self.loaded:
                    continue

                if not self.driver:
                    self.amstempeln = False
                    return

                self.update_msg.emit(f"Versuch {action_name} zu Stempeln")

                if not self._enter_frame():
                    continue

                try:
                    # Try to find title elements (submenu) directly first
                    found_submenu = False
                    try:
                        titles = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".title-element"))
                        )
                        for title in titles:
                            if title.text.startswith(action_name):
                                self._perform_click(title, action_name, is_break)
                                found_submenu = True
                                break
                    except TimeoutException:
                        pass

                    if found_submenu:
                        self.driver.switch_to.default_content()
                        self.amstempeln = False
                        return

                    # Find action items (main menu)
                    elements = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".action-item"))
                    )
                    
                    clicked_action = False
                    for el in elements:
                        if "Zeiterfassung (Kommen" in el.text:
                            el.click()
                            clicked_action = True
                            break
                    
                    if clicked_action:
                        # Wait for info buttons
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_all_elements_located((By.CLASS_NAME, "info-element-button"))
                        )
                        
                        # Find title element
                        titles = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".title-element"))
                        )
                        
                        for title in titles:
                            if title.text.startswith(action_name):
                                self._perform_click(title, action_name, is_break)
                                break
                                
                    self.driver.switch_to.default_content()
                    self.amstempeln = False
                    return

                except StaleElementReferenceException:
                    logger.warning("Stale element detected during stempeln, retrying...")
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                    continue

                except Exception as e:
                    logger.error(f"Stempeln failed: {e}")
                    self.update_msg.emit("Fehler beim Stempeln")
                    self.amstempeln = False
                    return

    def _perform_click(self, element, action_name, is_break):
        current_status = self.extracted_data.get("Status", "Abwesend")
        is_present = current_status == "Anwesend"
        
        if is_present == is_break:
            element.click()
            #print("Clicking element")
            self.update_msg.emit(f"Stempel {action_name} hat geklappt")
        else:
            self.update_msg.emit("Du hast versucht gleich zu stempeln bitte mach das nicht")
            time.sleep(0.5)
            logger.info(self.extracted_data)
            if REQUIRED_DATA_KEYS.issubset(self.extracted_data.keys()):
                formatted = DataProcessor.format_display_data(self.extracted_data)
                self.update_ui.emit(current_status, formatted)

    def _watchdog(self):
        while self.running:
            if self.loaded and time.time() - self.antidesync_time > 65:
                logger.info("Desync detected, reloading")
                self.loaded = False
                with self.driver_lock:
                    if self.driver:
                        try:
                            self.driver.get(self.driver.current_url)
                        except Exception as e:
                            logger.error(f"Watchdog reload failed. Browser session closed?: {e}")
                self.antidesync_time = time.time()
            time.sleep(1)

    def close(self):
        self.running = False
        with self.driver_lock:
            if self.driver:
                try:
                    self.driver.quit()
                except: pass
                self.driver = None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    
    # Setup UI
    window = OverlayWindow()
    window.show()
    
    controller = BrowserController(debug=args.debug)
    
    # Connect signals
    controller.update_ui.connect(window.update_status)
    controller.update_msg.connect(window.set_message)
    window.clock_button.clicked_signal.connect(lambda: threading.Thread(target=controller.stempeln, args=(False,), daemon=True).start())
    
    # Keyboard listener
    def setup_keyboard():
        COMBINATION1 = {keyboard.Key.alt, keyboard.KeyCode.from_char('q'), keyboard.KeyCode.from_char('g')}
        COMBINATION2 = {keyboard.Key.alt, keyboard.KeyCode.from_char('q'), keyboard.KeyCode.from_char('k')}
        current_keys = set()
        last_press = 0

        def on_press(key):
            nonlocal last_press
            if key in COMBINATION1 or key in COMBINATION2:
                current_keys.add(key)
            
            if time.time() - last_press > 3:
                if COMBINATION1.issubset(current_keys):
                    threading.Thread(target=controller.stempeln, args=(True,), daemon=True).start()
                    last_press = time.time()
                elif COMBINATION2.issubset(current_keys):
                    threading.Thread(target=controller.stempeln, args=(False,), daemon=True).start()
                    last_press = time.time()

        def on_release(key):
            try: current_keys.remove(key)
            except KeyError: pass

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    threading.Thread(target=setup_keyboard, daemon=True).start()
    
    controller.start()

    # Timer to allow Ctrl+C to be processed by Python interpreter
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(1000)
    
    def cleanup():
        controller.close()
        
    app.aboutToQuit.connect(cleanup)
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
