import sys
import os
import time
import threading
import signal
import argparse
import re
import logging
from datetime import datetime
from html import escape
from typing import Dict, Any

import psutil

from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QPalette, QGuiApplication
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException, WebDriverException, TimeoutException, StaleElementReferenceException
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import HTTPError

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
    def to_minutes(value: str) -> int:
        value = value.replace("\u200b", "").replace("\\u200B", "").replace("−", "-").strip()
        match = re.fullmatch(r"([+-]?)(\d+):([0-5]\d)", value)
        if not match:
            raise ValueError(f"Invalid time: {value!r}")
        sign, hours, minutes = match.groups()
        return (-1 if sign == "-" else 1) * (int(hours) * 60 + int(minutes))

    @staticmethod
    def format_minutes(total: int) -> str:
        hours, minutes = divmod(abs(total), 60)
        return f"{'-' if total < 0 else ''}{hours:02d}:{minutes:02d}"

    @staticmethod
    def add_times(time1: str, time2: str) -> str:
        return TimeUtils.format_minutes(TimeUtils.to_minutes(time1) + TimeUtils.to_minutes(time2))

    @staticmethod
    def subtract_times(time1: str, time2: str) -> str:
        return TimeUtils.format_minutes(TimeUtils.to_minutes(time1) - TimeUtils.to_minutes(time2))

    @staticmethod
    def check_minus(input_string: str) -> str:
        return "✔️" if TimeUtils.to_minutes(input_string) <= 0 else input_string

    @staticmethod
    def set_emoji_font(text: str, emoji: bool = False) -> str:
        style = "font-size: 15px;"
        if emoji:
            style += " font-family: 'notocoloremoji';"
        return f'<span style="{style}">{escape(text)}</span>'

class DataProcessor:
    @staticmethod
    def format_display_data(data: Dict[str, Any]) -> list:
        def format_line(emoji, text):
            return f"{TimeUtils.set_emoji_font(emoji, True)}{TimeUtils.set_emoji_font(text, False)}"

        final_list = []
        arbeitszeit = data["Heutige Anwesenheit"]
        pause = data["Heutige Pause"]
        kommen = data["Kommen"]
        gehen = data["Gehen"]
        ueberstunden = data["Arbeitszeitkonto"]
        
        final_list.append(format_line("⏰", arbeitszeit))
        final_list.append(format_line("🍔", pause))
        final_list.append(format_line("👣", kommen))

        if gehen == "k.A." and "k.A." not in (kommen, arbeitszeit, pause):
            current_time = TimeUtils.add_times(TimeUtils.add_times(arbeitszeit, kommen), pause)
            pause2 = "0:30" if TimeUtils.to_minutes(pause) < 30 else pause
            g1 = TimeUtils.add_times(TimeUtils.add_times(kommen, '6:00'), pause)
            g2 = TimeUtils.add_times(TimeUtils.add_times(kommen, '7:42'), pause2)
            g3 = TimeUtils.add_times(TimeUtils.add_times(kommen, '9:00'), pause2)
            
            diff1 = TimeUtils.check_minus(TimeUtils.subtract_times(g1, current_time))
            diff2 = TimeUtils.check_minus(TimeUtils.subtract_times(g2, current_time))
            diff3 = TimeUtils.check_minus(TimeUtils.subtract_times(g3, current_time))
            
            clocks = [TimeUtils.format_minutes(TimeUtils.to_minutes(g) % 1440) for g in (g1, g2, g3)]
            final_list.append(TimeUtils.set_emoji_font(f"G : {'/'.join(clocks)}", False))
            final_list.append(TimeUtils.set_emoji_font(f"G in h : {diff1}/{diff2}/{diff3}", False))
        elif gehen != "k.A." and pause != "k.A.":
            now_str = datetime.now().strftime('%H:%M')
            diff_now = TimeUtils.format_minutes((TimeUtils.to_minutes(now_str) - TimeUtils.to_minutes(gehen)) % 1440)
            diff_pause = TimeUtils.add_times(diff_now, pause)
            final_list.append(TimeUtils.set_emoji_font(f"G{gehen}({diff_now}/{diff_pause})", False))

        # Overtime calculation
        ot_str = ueberstunden
        if "k.A." not in (arbeitszeit, ueberstunden):
            diff_az = TimeUtils.subtract_times(arbeitszeit, '7:45')
            ot_calc = TimeUtils.add_times(diff_az, ueberstunden)
            if TimeUtils.to_minutes(diff_az) < 0:
                ot_str = f"{ueberstunden} ({ot_calc})"
            else:
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
        self.color = QColor({"Anwesend": Qt.green, "Abwesend": Qt.red}.get(state, Qt.gray))
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
        
        if status == "Abwesend":
            self.show_clock_button()
        else:
            self.clock_button.hide()

    def set_message(self, message):
        self.circle.update_color(None)
        self.clock_button.hide()
        self.label.setText(message)
        self.adjust_position()

    def adjust_position(self):
        self.adjustSize()
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

    def __init__(self, debug=False, read_only=False):
        super().__init__()
        self.debug = debug
        self.read_only = read_only
        self.driver = None
        self.running = True
        self.extracted_data = {}
        self.last_reload = 0
        self.antidesync_time = time.monotonic()
        self.loaded = False
        self.pending_status = None
        self.driver_lock = threading.Lock()
        self.stamp_lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._monitor, daemon=True).start()

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
        
        chrome_bins = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"]
        found_bin = None
        for bin_path in chrome_bins:
            if os.path.exists(bin_path):
                found_bin = bin_path
                break
        
        if found_bin:
            opts.binary_location = found_bin
            logger.info(f"Using Chrome binary at: {found_bin}")
        else:
            logger.warning("No Chrome binary found in standard locations. Letting Selenium decide.")

        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        
        base_path = os.path.dirname(os.path.abspath(__file__))
        selenium_path = os.path.join(base_path, "selenium")
        
        self._clean_stale_locks(selenium_path)
        opts.add_argument(f"--user-data-dir={selenium_path}")
        
        opts.page_load_strategy = "none"
        if not self.debug:
            opts.add_argument("--headless=new")
        
        self.driver = webdriver.Chrome(options=opts)
        self.driver.set_page_load_timeout(30)

    def _enter_frame(self):
        self.driver.switch_to.default_content()
        self.driver.switch_to.frame(self.driver.find_element(By.ID, "applicationIframe"))

    def _read_data(self):
        try:
            self._enter_frame()
            data = self.driver.execute_script("""
                const data = {};
                for (const entry of document.querySelectorAll('[data-test="ws-dash-entry"]')) {
                    const label = entry.querySelector('[data-test="ws-dash-keyfigure-label-value"]');
                    const value = entry.querySelector('[data-test="ws-dash-keyfigure-value"]');
                    if (label && value) data[label.textContent.trim()] = value.textContent.trim();
                }
                return data;
            """)
        finally:
            self.driver.switch_to.default_content()
        if not REQUIRED_DATA_KEYS.issubset(data):
            raise ValueError("ATOSS-Daten fehlen; ggf. mit --debug anmelden")
        data = {key: data[key].replace("\u200b", "").strip() for key in REQUIRED_DATA_KEYS}
        for key, value in data.items():
            if key != "Status" and value != "k.A.":
                minutes = TimeUtils.to_minutes(value)
                if key in {"Kommen", "Gehen"} and not 0 <= minutes < 1440:
                    raise ValueError(f"Invalid clock time: {key}")
                if key in {"Heutige Anwesenheit", "Heutige Pause"} and minutes < 0:
                    raise ValueError(f"Invalid duration: {key}")
        return data

    def _publish_data(self, data):
        if self.pending_status and data["Status"] != self.pending_status:
            raise ValueError("Stempelstatus unklar. Bitte in ATOSS prüfen oder nach Prüfung neu starten.")
        formatted = DataProcessor.format_display_data(data)
        self.pending_status = None
        if data != self.extracted_data:
            self.antidesync_time = time.monotonic()
        self.extracted_data = data
        self.loaded = True
        self.update_ui.emit(data["Status"], formatted)

    def _reload_page(self):
        self.loaded = False
        self.extracted_data.clear()
        self.last_reload = time.monotonic()
        self.antidesync_time = self.last_reload
        self.update_msg.emit("Lade ATOSS...")
        # Always use the entry URL, including after a DNS error or expired SSO session.
        self.driver.get('https://hoffmann-group.atoss.com/hoffmanngroupprod/html?security.sso=true')

    def _poll(self):
        if self.driver is None:
            self.update_msg.emit("Starte Browser...")
            self._init_driver()
            self._reload_page()
        now = time.monotonic()
        retry_after = 1800 if self.loaded else 30
        if now - self.last_reload >= retry_after:
            self._reload_page()
        data = self._read_data()
        self._publish_data(data)
        # ponytail: present time must change every minute; reload after 90s, use a server heartbeat if that cadence changes.
        if data["Status"] == "Anwesend" and now - self.antidesync_time > 90:
            logger.info("ATOSS data stopped changing, reloading")
            self._reload_page()

    def _monitor(self):
        last_error = None
        while self.running:
            with self.driver_lock:
                if not self.running:
                    break
                try:
                    self._poll()
                    last_error = None
                except (NoSuchElementException, StaleElementReferenceException, TimeoutException, ValueError) as exc:
                    self.loaded = False
                    message = str(exc).splitlines()[0]
                    if message != last_error:
                        logger.warning("Waiting for ATOSS: %s", message)
                        self.update_msg.emit(message if self.pending_status else "Warte auf ATOSS-Daten / Anmeldung...")
                        last_error = message
                except (WebDriverException, HTTPError, OSError) as exc:
                    self.loaded = False
                    logger.warning("Browser unavailable: %s", str(exc).splitlines()[0])
                    self.update_msg.emit("Browser / Verbindung unterbrochen. Neuer Versuch...")
                    self._quit_driver()
            time.sleep(2 if self.driver else 5)

    def _clickable(self, locator):
        return WebDriverWait(self.driver, 10, ignored_exceptions=(StaleElementReferenceException,)).until(
            lambda driver: next((element for element in driver.find_elements(*locator)
                                 if element.is_displayed() and element.is_enabled()
                                 and element.get_attribute("aria-disabled") != "true"), False)
        )

    def stempeln(self, is_break):
        if self.read_only or not self.running:
            return
        if not self.stamp_lock.acquire(blocking=False):
            return
        click_attempted = False
        try:
            with self.driver_lock:
                if not self.running or not self.loaded or not self.driver:
                    self.update_msg.emit("ATOSS nicht bereit. Bitte später erneut stempeln.")
                    return
                before = self._read_data()["Status"]
                expected = "Anwesend" if is_break else "Abwesend"
                if before != expected:
                    self.update_msg.emit("Stempeln passt nicht zum aktuellen Status.")
                    return
                self._enter_frame()
                action = "Pause / Anwesenheitsende stempeln" if is_break else "Anwesenheitsbeginn stempeln"
                locator = (By.XPATH, f"//button[@data-test='ws-info-button'][.//*[@data-test='ws-info-button-title' and normalize-space(.)='{action}']]")
                if not any(element.is_displayed() for element in self.driver.find_elements(*locator)):
                    menu = (By.XPATH, "//*[@data-test='ws-frame-block-link'][normalize-space(.)='Zeiterfassung (Kommen & Gehen)']")
                    self._clickable(menu).click()
                button = self._clickable(locator)
                # Re-read attendance after opening the menu; never act on the overlay's cached status.
                if self._read_data()["Status"] != before:
                    self.update_msg.emit("Status hat sich geändert. Bitte erneut prüfen.")
                    return
                self._enter_frame()
                click_attempted = True
                self.loaded = False
                self.pending_status = "Abwesend" if is_break else "Anwesend"
                button.click()
                after = WebDriverWait(self.driver, 15).until(
                    lambda driver: (data if (data := self._read_data())["Status"] ==
                                    ("Abwesend" if is_break else "Anwesend") else False)
                )
                self._publish_data(after)
                logger.info("ATOSS confirmed: %s", action)
        except (WebDriverException, HTTPError, OSError, ValueError) as exc:
            logger.warning("Stempeln failed: %s", str(exc).splitlines()[0])
            self.update_msg.emit("Stempelstatus unklar. Bitte in ATOSS prüfen; kein automatischer Neuversuch."
                                 if click_attempted else "Stempeln fehlgeschlagen. Bitte ATOSS prüfen.")
        finally:
            try:
                if self.driver:
                    with self.driver_lock:
                        self.driver.switch_to.default_content()
            except (WebDriverException, HTTPError, OSError):
                pass
            self.stamp_lock.release()

    def _quit_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except (WebDriverException, HTTPError, OSError):
                pass
            self.driver = None

    def close(self):
        self.running = False
        with self.driver_lock:
            self._quit_driver()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--read-only', action='store_true', help='Disable all clocking actions and hotkeys')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    
    # Setup UI
    window = OverlayWindow()
    window.show()
    
    controller = BrowserController(debug=args.debug, read_only=args.read_only)
    window.clock_button.button.setEnabled(not args.read_only)
    
    # Connect signals
    controller.update_ui.connect(window.update_status)
    controller.update_msg.connect(window.set_message)
    window.clock_button.clicked_signal.connect(lambda: threading.Thread(target=controller.stempeln, args=(False,), daemon=True).start())
    
    listener = None
    if not args.read_only:
        from pynput import keyboard
        listener = keyboard.GlobalHotKeys({
            '<alt>+q+g': lambda: threading.Thread(target=controller.stempeln, args=(True,), daemon=True).start(),
            '<alt>+q+k': lambda: threading.Thread(target=controller.stempeln, args=(False,), daemon=True).start(),
        })
        listener.start()

    controller.start()

    # Timer to allow Ctrl+C to be processed by Python interpreter
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(1000)
    
    def cleanup():
        if listener:
            listener.stop()
        controller.close()
        
    app.aboutToQuit.connect(cleanup)
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
