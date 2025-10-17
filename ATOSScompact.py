import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="seleniumwire")
from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException, NoSuchElementException, WebDriverException,TimeoutException,UnexpectedAlertPresentException,StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QPalette, QGuiApplication
from PyQt5.QtCore import Qt, QTimer, QPoint, QTime, QMetaObject, Q_ARG
from datetime import datetime, timedelta
from seleniumwire import webdriver
from pynput import keyboard
import argparse
import psutil
import threading
import re
import time
import sys
import random
import socket
import json
import gzip
import io
import logging
# silence selenium-wire / mitmproxy noisy tracebacks unless it's an actual error
logging.getLogger('seleniumwire').setLevel(logging.ERROR)
logging.getLogger('seleniumwire.thirdparty.mitmproxy').setLevel(logging.ERROR)
logging.getLogger('mitmproxy').setLevel(logging.ERROR)

parser = argparse.ArgumentParser(
    description="Skript mit optionalem Debug-Modus ausführen"
)
# definiere das Flag --debug; wenn es auftaucht, wird args.debug True
parser.add_argument('--debug', action='store_true', help='Aktiviere den Debug-Modus')


args = parser.parse_args()
debug = args.debug  # False wenn nicht gesetzt, sonst True

# wait for internet connection
def wait_for_internet(host="8.8.8.8", port=53, timeout=5, max_wait=60):
    """
    Warte bis eine Internetverbindung besteht.
    host/port = DNS von Google (oder anderen stabilen Host).
    """
    start = time.time()
    while time.time() - start < max_wait:
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            print("Internetverbindung hergestellt.")
            return True
        except OSError:
            time.sleep(1)
    print("Warnung: Keine Internetverbindung nach max_wait.")
    return False

def wait_for_nonempty_body(driver, timeout=2.0, poll=0.1):
    """
    Warte bis document.body irgendetwas enthält (Text oder child elements).
    - timeout: maximale Wartezeit in Sekunden (klein wählen, z.B. 1-3s)
    - poll: Poll-Intervall
    Rückgabewerte:
      True      -> body ist nicht-leer und kein 'neterror'
      'neterror'-> body hat class 'neterror'
      False     -> timeout, body blieb leer
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            # Wir fragen in einer JS-Ausführung textContent-Länge + childElementCount ab
            info = driver.execute_script(
                "return {"
                " text: document.body ? (document.body.textContent || '').trim().length : 0,"
                " children: document.body ? document.body.childElementCount : 0,"
                " cls: document.body ? document.body.className : ''"
                "};"
            )
            text_len = int(info.get('text', 0) or 0)
            children = int(info.get('children', 0) or 0)
            cls = (info.get('cls') or '').lower()

            total = text_len + children
            if total > 0:
                if 'neterror' in cls:
                    return 'neterror'
                return True
            # Wenn body leer, kurz warten und nochmal prüfen
        except WebDriverException:
            # kurze swallow, z.B. wenn browser noch navigiert
            pass
        except Exception:
            pass
        time.sleep(poll)
    return False


def robust_get(driver, url, retries=6, nonempty_timeout=2.0, wait_between=0.6):
    """
    Lade URL, prüfe schnell auf non-empty body. Wenn neterror erkannt wird, reload sofort.
    - nonempty_timeout: wie lange wir direkt auf non-empty body warten (kleiner Wert sorgt für schnelle retries)
    - retries: wie oft wir versuchen bevor wir aufgeben
    """
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
        except WebDriverException:
            # falls kurzfristig Navigation fehlschlägt, versuchen wir gleich wieder
            print(f"[robust_get] driver.get() raised, attempt {attempt}")
            time.sleep(wait_between)
            continue

        # statt time.sleep(3) -> dynamisch auf body warten
        status = wait_for_nonempty_body(driver, timeout=nonempty_timeout)
        if status is True:
            # body nicht leer und kein neterror -> Seite ist sichtbar
            # kurze zusätzliche Prüfung: falls chrome-error-URL geladen wurde:
            try:
                cur = driver.current_url
                if cur and cur.startswith("chrome-error://"):
                    print(f"[robust_get] chrome-error URL erkannt ({cur}), retrying")
                    continue
            except Exception:
                pass
            print(f"[robust_get] Seite geladen (attempt {attempt})")
            return True
        elif status == 'neterror':
            # Neterror sofort behandeln: refresh und schneller retry
            print(f"[robust_get] neterror erkannt (attempt {attempt}) -> refresh und retry")
            try:
                driver.refresh()
            except Exception:
                pass
            time.sleep(0.2)  # sehr kurz
            continue
        else:
            # Body blieb leer innerhalb nonempty_timeout
            print(f"[robust_get] body leer nach {nonempty_timeout}s (attempt {attempt}) -> retry")
            continue

    print("[robust_get] Seite konnte nach mehreren Versuchen nicht geladen werden.")
    return False

# while True:
#    if is_connected():
#        break
#    else:
#        time.sleep(0.1)


# driver.set_network_conditions(
#    offline=False,
#    latency=5,  # additional latency (ms)
#    download_throughput=500 * 1024,  # maximal throughput
#    upload_throughput=500 * 1024  # maximal throughput
# )

# Set global variables
amstempeln = False
stempelupdate = False
loaded = False
az = "9:99"
noupdate= False
initialized = False
generalvaluesrecived = False
additionalvaluesrecived = False
timesincereload = time.time()
extracted_data = {}
pending_requests = {}
antidesync_time = time.time()
driver = None
window = None
screen = None


def wait_for_primary_screen(app, timeout=30.0, poll=0.1):
    """Wait until a display is ready so the Qt widgets do not crash on boot."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        scr = app.primaryScreen()
        if scr and scr.size().height() > 0:
            return scr
        screens = QGuiApplication.screens()
        if screens:
            scr = screens[0]
            if scr and scr.size().height() > 0:
                return scr
        app.processEvents()
        time.sleep(poll)
    return None


def primary_screen_fallback():
    """Return a usable screen object when primary screen is momentarily unavailable."""
    scr = QGuiApplication.primaryScreen()
    if scr is None:
        screens = QGuiApplication.screens()
        if screens:
            scr = screens[0]
    return scr

def wait_for_process(process_name):
    while True:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == process_name:
                print(f"{process_name} is running.")
                return
        time.sleep(0.1)


def wait_after_boot():
    scripttime = 0
    while time.time()- psutil.boot_time() < 150 and scripttime < 5:
        time.sleep(1)
        scripttime += 1
        print(scripttime)


def setEmojiFontForText(text, emoji):
    style = f"font-size: 15px;"
    if emoji:
        style += " font-family: 'notocoloremoji';"
    return f'<span style="{style}">{text}</span>'

def process_response(driver, request_id, timeout=5.0):
    """
    Get response body for a specific request, retrying
    until it's actually available or a timeout is reached.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            response_body = driver.execute_cdp_cmd(
                'Network.getResponseBody', {'requestId': request_id}
            )
            if 'body' in response_body:
                return response_body['body']
        except Exception:
            # Body not yet available: swallow and retry
            pass
    # timed out
    print(f"Timed out waiting for body of {request_id}")
    return None

def find_starting_points(response_body):
    startingpoints = {
        "gestempelte Wochen-AZ": -1,
        "Kommen": -1,
        "Status": -1
    }

    for i in range(len(response_body["rs"])):
        try:
            value = response_body["rs"][i][1][1][0][4][0][4][0][2]["value"]
            if value in startingpoints and startingpoints[value] == -1:
                startingpoints[value] = i
                if all(v != -1 for v in startingpoints.values()):
                    break
        except (IndexError, KeyError):
            continue

    return startingpoints["gestempelte Wochen-AZ"], startingpoints["Kommen"], startingpoints["Status"]



def extract_connections(response_body):
    global generalvaluesrecived,additionalvaluesrecived

    # Fix single quotes and other syntax issues
    data_fixed = response_body.replace("'", '"')  
    data_fixed = re.sub(r'(?<=\{|,)\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'"\1":', data_fixed) 
    data_fixed = data_fixed.replace('\\', '\\\\')

    response_body = json.loads(data_fixed)

    key = 0
    key2 = 2
    info = {}

    startingpoint_Arbeitskonto, startingpoint_Kommen, startingpoint_Anwesenheit = find_starting_points(response_body)
    try:
        if startingpoint_Anwesenheit != -1:
            for value2 in range(1,6):
                if value2 % 2 == 0 or value2 == 1:
                    info[response_body["rs"][startingpoint_Anwesenheit][1][value2][0][4][0][4][key][2]["value"]] = response_body["rs"][startingpoint_Anwesenheit][1][value2][0][4][0][4][key2][2]["value"]
        
        if startingpoint_Kommen != -1:
            for value2 in range(1,4):
                if value2 % 2 == 0 or value2 == 1:
                    info[response_body["rs"][startingpoint_Kommen][1][value2][0][4][0][4][key][2]["value"]] = response_body["rs"][startingpoint_Kommen][1][value2][0][4][0][4][key2][2]["value"]
        
        if startingpoint_Arbeitskonto != -1:
            for value2 in range(1,7):
                if not value2 % 2 == 0:
                    keypath = response_body["rs"][startingpoint_Arbeitskonto][1][value2][0][4][0][4][key][2]["value"]
                    valuepath = str(response_body["rs"][startingpoint_Arbeitskonto][1][value2][0][4][0][4][key2][2]["value"])
                    if keypath == "Arbeitszeitkonto":
                        info[keypath] = valuepath.replace("\\u200B","")
                    else:
                        info[keypath] = valuepath
    except Exception as e:
        pass

    return info

def detectDesync():
    global loaded, antidesync_time
    try:
        while True:
            # if you want to auto‑reload after 65s with no new data:
            if loaded and time.time() - antidesync_time > 65:
                print(f"{time.strftime('%H:%M:%S')} | Desync detected; reloading page.")
                loaded = False
                driver.get(driver.current_url)
                antidesync_time = time.time()
            time.sleep(1)
    except KeyboardInterrupt:
        driver.quit()


def interceptor(request, response):
    global extracted_data, initialized, loaded, antidesync_time

    content_type = response.headers.get('Content-Type', '')
    content_encoding = response.headers.get('Content-Encoding', '')

    if (response.status_code == 200
        and content_type.startswith('text/plain')
        and 'zkauA10' in request.url):

        # Check for gzip compression
        if content_encoding == 'gzip':
            try:
                body_bytes = gzip.GzipFile(fileobj=io.BytesIO(response.body)).read()
                body = body_bytes.decode('utf-8')
            except Exception as e:
                print(f"Failed to decompress gzipped response: {e}")
                return
        else:
            try:
                body = response.body.decode('utf-8')
            except Exception as e:
                print(f"Failed to decode response body: {e}")
                return

        # Now parse/extract as before
        info = extract_connections(body)
        if info:
            extracted_data.update(info)
            if len(extracted_data) == 8:
                window.update_list(
                    extracted_data["Status"],
                    sortListAndCalculateAdditionalValues(extracted_data)
                )
                initialized = True
                loaded = True
                antidesync_time = time.time()



def sortListAndCalculateAdditionalValues(data):
    def format_emoji_line(emoji: str, text: str) -> str:
        return f"{setEmojiFontForText(emoji, True)}{setEmojiFontForText(text, False)}"

    finalList =[]
    arbeitszeit = data["Heutige Anwesenheit"]
    pause = data["Heutige Pause"]
    kommen = data["Kommen"]
    gehen = data["Gehen"]
    überstunden = data["Arbeitszeitkonto"]
    current_time = add_times(add_times(arbeitszeit, kommen), pause)
    pause2 = "0:30" if datetime.strptime(pause, "%H:%M") < datetime.strptime("0:30", "%H:%M") else pause
    pause3 = "0:45" if datetime.strptime(pause, "%H:%M") < datetime.strptime("0:45", "%H:%M") else pause
    finalList.append(format_emoji_line("⏰", arbeitszeit))
    finalList.append(format_emoji_line("🍔", pause))
    finalList.append(format_emoji_line("👣", kommen))

    if gehen == "k.A.":
        finalList.append(f"{setEmojiFontForText("G : "+add_times(add_times(kommen, '6:00'), pause)+"/"+add_times(add_times(kommen, '7:42'), pause2)+"/"+add_times(add_times(kommen, '9:00'), pause2),False)}")
        finalList.append(f"{setEmojiFontForText("G in h : " + checkMinus(subtract_times(add_times(add_times(kommen, '6:00'), pause), current_time)) + "/" + checkMinus(subtract_times(add_times(add_times(kommen, '7:42'), pause2), current_time)) + "/" + checkMinus(subtract_times(add_times(add_times(kommen, '9:00'), pause2), current_time)), False)}")
    else:
        finalList.append(f"{setEmojiFontForText("G" + gehen + "(" + subtract_times(datetime.now().strftime('%H:%M'), gehen) + "/" + add_times(subtract_times(datetime.now().strftime('%H:%M'), gehen), pause)+")",False)} ")
    finalList.append(f"{format_emoji_line("🌙", überstunden+ ' (' + add_times(subtract_times(arbeitszeit, '7:42'), überstunden)+ ')' if datetime.strptime(arbeitszeit, '%H:%M') < datetime.strptime('7:42', '%H:%M') else add_times(subtract_times(arbeitszeit, '7:42'), überstunden)+' +'+subtract_times(arbeitszeit, '7:42'))}")          
    
    return finalList


def reload():
    global timesincereload,window
    try:
        window.label.setText(window.label.text() + " ⟳")
        QApplication.processEvents()
        driver.refresh()
        timesincereload = time.time()
        alert = driver.switch_to.alert
        alert.accept()
    except NoAlertPresentException:
        pass
def enterFrame():
    class any_of_conditions(object):
        def __init__(self, *conditions):
            self.conditions = conditions

        def __call__(self, driver):
            for condition in self.conditions:
                try:
                    if condition(driver):
                        return True
                except:
                    pass
            return False

    # Define your conditions
    condition1 = EC.presence_of_element_located((By.ID, "applicationIframe"))
    condition2 = lambda driver: 'neterror' in driver.find_element(By.TAG_NAME, 'body').get_attribute('class')

    # Wait for any of the conditions to be true
    try:
        WebDriverWait(driver, 50).until(any_of_conditions(condition1, condition2))
    except TimeoutException:
        print("melde diesen error an robin(vorher hat hier programm retstarted)")

        # Get the body element
    body = driver.find_element(By.TAG_NAME, 'body')



    try:
        # Check if the body has the class "neterror"
        if 'neterror' in body.get_attribute('class').split():
            return False
        iframe = driver.find_element(By.TAG_NAME, 'iframe')
        driver.switch_to.frame(iframe)
        return True
    except (NoSuchElementException, TimeoutException, UnexpectedAlertPresentException):
        reload()
        return enterFrame()
    
def update_label_from_thread(label, html):

    QMetaObject.invokeMethod(
        label,
        "setText",
        Qt.QueuedConnection,
        Q_ARG(str, html)
    )
def stempeln(Pause, stempeln_already_opened = False):
    global amstempeln, window, stempelupdate, timesincereload
    amstempeln = True
    value = "Pause"
    if Pause == False:
        value = "Anwesenheitsbeginn"
    window.label.setText("Versuch "+value+" zu Stempeln")
    stempelState = window.circle.color.name() == "#00ff00"
    # Switch to the iframe
    enterFrame()

    try:
        if not stempeln_already_opened:
            # Wait for button to be active
            try:
                elements = WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".action-item"))
                )
            except Exception:
                elements = driver.find_elements(By.CSS_SELECTOR, ".action-item")

            # iterate but handle stale elements by refetching if necessary
            clicked_action = False
            for _ in range(3):  # kleine retry-schleife
                try:
                    for element in elements:
                        try:
                            txt = element.text
                        except StaleElementReferenceException:
                            # element stale - refetch and restart outer loop
                            elements = driver.find_elements(By.CSS_SELECTOR, ".action-item")
                            raise StaleElementReferenceException()
                        if txt.startswith("Zeiterfassung (Kommen"):
                            WebDriverWait(driver, 10).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, ".action-item"))
                            )
                            # wait until not disabled (try/catch to handle staleness)
                            try:
                                WebDriverWait(driver, 30).until(
                                    lambda d, e=element: not (e.get_attribute("disabled") == "disabled")
                                )
                            except StaleElementReferenceException:
                                elements = driver.find_elements(By.CSS_SELECTOR, ".action-item")
                                raise
                            element.click()
                            clicked_action = True
                            break
                    if clicked_action:
                        break
                except StaleElementReferenceException:
                    # kleines Delay und retry
                    time.sleep(0.2)
                    continue

        # Wait for the next buttons to appear (info-element-button)
        # attempt a few retries to avoid stale refs
        info_buttons = []
        for _ in range(3):
            try:
                info_buttons = WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "info-element-button"))
                )
                # try a quick attribute read to ensure they're stable
                stable = True
                for b in info_buttons:
                    try:
                        _ = b.get_attribute("disabled")
                    except StaleElementReferenceException:
                        stable = False
                        break
                if stable:
                    break
            except Exception:
                pass
            time.sleep(0.2)

        # now the main loop to find the title-element and click it
        elementClicked = False
        max_retries = 12
        retries = 0
        while not elementClicked and retries < max_retries:
            try:
                elements = WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".title-element"))
                )
            except Exception:
                elements = driver.find_elements(By.CSS_SELECTOR, ".title-element")

            found_in_this_round = False
            for element in elements:
                try:
                    text = element.text
                except StaleElementReferenceException:
                    # went stale - we'll refetch in next while iteration
                    found_in_this_round = False
                    break

                if text.startswith(value):
                    try:
                        print("stempel " + value)
                        if stempelState == Pause:
                            element.click()
                            window.label.setText("Stempel "+value+" hat geklappt")
                        else:
                            window.label.setText("Du hast versucht gleich zu stempeln bitte mach das nicht")
                            time.sleep(0.5)
                            print(extracted_data)
                            window.update_list(extracted_data["Status"], sortListAndCalculateAdditionalValues(extracted_data))
                        driver.switch_to.default_content()
                        elementClicked = True
                        found_in_this_round = True
                        break
                    except StaleElementReferenceException:
                        # element became stale just before click: retry
                        found_in_this_round = False
                        break
                    except Exception as e:
                        # andere Ausnahme beim Klick -> log und retry
                        print("Fehler beim Klick auf title-element:", e)
                        found_in_this_round = False
                        break

            if not found_in_this_round:
                # Falls nicht gefunden: zeige Hinweis und retry (wie vorher, aber ohne Rekursion)
                window.label.setText("Falls du das siehst, gehe zu Robin ;-;")
                retries += 1
                time.sleep(0.25)
                continue

        if not elementClicked:
            print("Konnte das passende .title-element nach mehreren Versuchen nicht klicken.")
            # Optional: raise oder nur loggen
    except Exception as e:
        print("oh no something bad happened:")
        print(e)
        # avoid infinite recursion here: try a single fallback attempt
        try:
            # kleiner Fallback: versuche nochmal rekursiv genau einmal (wie vorher)
            if not stempeln_already_opened:
                stempeln(Pause, True)
        except Exception as e2:
            print("Fallback auch fehlgeschlagen:", e2)
    finally:
        stempelupdate = True
        amstempeln = False
        stempelupdate = False

def add_times(time1, time2):
    try:
        # Check if the times are negative
        negative1 = time1.startswith("-")
        negative2 = time2.startswith("-")

        # Remove the negative sign if present
        if negative1:
            time1 = time1[1:]
        if negative2:
            time2 = time2[1:]

        # Convert the times to datetime objects
        time1 = datetime.strptime(time1, "%H:%M")
        time2 = datetime.strptime(time2, "%H:%M")

        # Calculate total minutes for each time
        total_minutes1 = time1.hour * 60 + time1.minute
        total_minutes2 = time2.hour * 60 + time2.minute

        # Negate the total minutes if the time was negative
        if negative1:
            total_minutes1 = -total_minutes1
        if negative2:
            total_minutes2 = -total_minutes2

        # Add total minutes
        total_minutes = total_minutes1 + total_minutes2

        # Convert total minutes back to hours and minutes
        hours, minutes = divmod(abs(total_minutes), 60)

        # Format the time as a string in the format HH:MM
        formatted_time = "{:02d}:{:02d}".format(hours, minutes)

        # Add a negative sign if the total minutes is negative
        if total_minutes < 0:
            formatted_time = "-" + formatted_time

        return formatted_time
    except:
        return "00:00"

def subtract_times(time1, time2):
    try:
        # Check if the times are negative
        negative1 = time1.startswith("-")
        negative2 = time2.startswith("-")

        # Remove the negative sign if present
        if negative1:
            time1 = time1[1:]
        if negative2:
            time2 = time2[1:]

        # Convert the times to datetime objects
        time1 = datetime.strptime(time1, "%H:%M")
        time2 = datetime.strptime(time2, "%H:%M")

        # Calculate total minutes for each time
        total_minutes1 = time1.hour * 60 + time1.minute
        total_minutes2 = time2.hour * 60 + time2.minute

        # Negate the total minutes if the time was negative
        if negative1:
            total_minutes1 = -total_minutes1
        if negative2:
            total_minutes2 = -total_minutes2

        # Subtract total minutes
        total_minutes = total_minutes1 - total_minutes2

        # Convert total minutes back to hours and minutes
        hours, minutes = divmod(abs(total_minutes), 60)

        # Format the time as a string in the format HH:MM
        formatted_time = "{:02d}:{:02d}".format(hours, minutes)

        # Add a negative sign if the total minutes is negative
        if total_minutes < 0:
            formatted_time = "-" + formatted_time

        return formatted_time
    except:
        return "00:00"

def checkMinus(input_string):
    if "-" in input_string or input_string == "00:00":
        return "✔️"
    else:
        return input_string



class Circle(QWidget):
    def __init__(self, initial_state):
        super().__init__()
        self.diameter = 18
        self.color = QColor(Qt.green if initial_state == "Anwesend" else Qt.red)
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
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton("Einspempeln")
        self.button.setStyleSheet(
            """
            QPushButton { background-color: #333; color: white; border: none; padding: 6px; }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #222; }
            """
        )
        self.button.clicked.connect(self._handle_click)
        layout.addWidget(self.button)

    def _handle_click(self):
        if driver is None:
            if window:
                update_label_from_thread(window.label, "Browser noch nicht bereit")
            return
        stempeln(False)
        if window:
            window.hide_clock_button()

    def show_at_corner(self):
        screen_obj = primary_screen_fallback()
        if screen_obj is None:
            self.show()
            return
        area = screen_obj.geometry()
        self.setGeometry(area.x() + 12, area.y() + 48, 140, 32)
        self.show()


class Window(QWidget):
    def __init__(self, initial_state, info_items):
        super().__init__()
        self.clock_button = None
        self.setWindowTitle("ATOSS Compact")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.circle = Circle(initial_state)
        layout.addWidget(self.circle)

        self.label = QLabel("   |   ".join(info_items))
        self.label.setTextFormat(Qt.RichText)
        layout.addWidget(self.label)

        self.resize(420, self.circle.height() + 8)
        self.move_to_corner()

    def move_to_corner(self):
        screen_obj = primary_screen_fallback()
        if screen_obj is None:
            return
        area = screen_obj.geometry()
        self.move(area.x(), area.y())

    def update_list(self, status, extraced_data):
        self.circle.update_color(status)
        update_label_from_thread(self.label, "   |   ".join(extraced_data))
        self.move_to_corner()
        if status != "Anwesend":
            self.show_clock_button()
        else:
            self.hide_clock_button()

    def show_clock_button(self):
        if not self.clock_button:
            self.clock_button = ClockInButton()
        self.clock_button.show_at_corner()

    def hide_clock_button(self):
        if self.clock_button:
            self.clock_button.hide()
            self.clock_button = None

    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        delta = event.globalPos() - self.oldPos
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPos = event.globalPos()

def setup_keybinds():
    global last_time_pressed,initialized,loaded,amstempeln,stempeln
    print("setting up keybinds")
    # Define the combinations of keys you want to listen for
    COMBINATION1 = {keyboard.Key.alt, keyboard.KeyCode.from_char('q'), keyboard.KeyCode.from_char('g')}
    COMBINATION2 = {keyboard.Key.alt, keyboard.KeyCode.from_char('q'), keyboard.KeyCode.from_char('k')}

    # The set of keys that are currently being pressed
    current_keys = set()

    # Variable to track the last time a combination was pressed
    last_time_pressed = 0

    def on_press(key):
        global last_time_pressed, stempeln, loaded,initialized
        if key in COMBINATION1 or key in COMBINATION2:
            current_keys.add(key)

        # Check if 5 seconds have passed since the last time a combination was pressed
        if time.time() - last_time_pressed > 3:
            if COMBINATION1.issubset(current_keys):
                if loaded == False or initialized == False or amstempeln == True:
                    print(loaded+initialized+amstempeln)
                    while loaded == False or initialized == False or amstempeln == True:
                        time.sleep(0.1)
                stempeln(True)
                last_time_pressed = time.time()
            elif COMBINATION2.issubset(current_keys):
                if loaded == False or initialized == False or amstempeln == True:
                    while loaded == False or initialized == False or amstempeln == True:
                        time.sleep(0.1)
                print("attempting to stempel")
                stempeln(False)
                last_time_pressed = time.time()

    def on_release(key):
        try:
            current_keys.remove(key)
        except KeyError:
            pass  # Deal with a key like shift being released

    # Make a new thread for the keyboard listener
    def start_keyboard_listener():
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    listener_thread = threading.Thread(target=start_keyboard_listener, daemon=True)
    listener_thread.start()

def bootstrap_system():
    global driver, debug

    update_label_from_thread(window.label, "Programm wird gestartet   |   Warte auf Internet...")
    while not wait_for_internet():
        time.sleep(5)

    chrome_options = Options()
    chrome_options.add_argument("--user-data-dir=selenium")
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    if not debug:
        chrome_options.add_argument("--headless")

    seleniumwire_options = {
        'ignore_hosts': ['127.0.0.1', 'localhost', '::1'],
        'connection_timeout': None
    }

    update_label_from_thread(window.label, "Programm wird gestartet   |   Starte Browser...")
    while True:
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options, seleniumwire_options=seleniumwire_options)
            break
        except (WebDriverException, Exception) as exc:
            print(f"Fehler beim Starten von ChromeDriver: {exc}")
            time.sleep(2)

    driver.response_interceptor = interceptor

    update_label_from_thread(window.label, "Programm wird gestartet   |   Lade ATOSS...")
    if not robust_get(driver, 'https://hoffmann-group.atoss.com/hoffmanngroupprod/html?security.sso=true'):
        update_label_from_thread(window.label, "Fehler beim Laden der ATOSS Seite")
        return

    threading.Thread(target=detectDesync, daemon=True).start()
    setup_keybinds()
    update_label_from_thread(window.label, "ATOSS geladen   |   Warte auf Daten...")

def main():
    global  window, screen,driver,debug,initialized

    app = QApplication(sys.argv)

    screen_obj = wait_for_primary_screen(app)
    if screen_obj is None:
        print("Keine Anzeige gefunden. Warte auf Desktop...")
        time.sleep(5)
        screen_obj = wait_for_primary_screen(app, timeout=25.0)
    if screen_obj is None:
        print("Fehler: Desktop nicht bereit. Beende mich.")
        sys.exit(1)
    screen = screen_obj

    # Set the palette to a dark theme
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
    app.setPalette(palette)

    window = Window("Abwesend", ['<span style="font-size:11pt;">Programm wird gestartet</span>'])
    window.show()
    app.processEvents()

    threading.Thread(target=bootstrap_system, daemon=True).start()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
