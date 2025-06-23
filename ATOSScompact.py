#do to
#TimeoutException wenn des element nicht gefunden wird bitte irgendwann fix (bei allen elementen)

from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException, NoSuchElementException, WebDriverException,TimeoutException,UnexpectedAlertPresentException,StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QListWidget, QListWidgetItem, QSizePolicy, QPushButton
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QPalette, QGuiApplication
from PyQt5.QtCore import Qt, QTimer, QPoint, QTime, QMetaObject, Q_ARG
from datetime import datetime, timedelta
from pynput import keyboard
import psutil
import threading
import re
import time
import sys
import random
import socket
import json


debug = False

#wait for internet connection
def is_connected():
    try:
        socket.create_connection(("8.8.8.8", 80))
        return True
    except OSError:
        pass
    return False

#while True:
#    if is_connected():
#        break
#    else:
#        time.sleep(0.1)


#driver.set_network_conditions(
#    offline=False,
#    latency=5,  # additional latency (ms)
#    download_throughput=500 * 1024,  # maximal throughput
#    upload_throughput=500 * 1024  # maximal throughput
#)
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
driver = None
window = None
screen = None

def wait_for_process(process_name):
    while True:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == process_name:
                print(f"{process_name} is running.")
                return
        time.sleep(0.1)


def wait_after_boot():
    scripttime = 0
    while time.time()- psutil.boot_time() < 150 and scripttime < 3:
        time.sleep(1)
        scripttime += 1
        print(scripttime)


def setEmojiFontForText(text, emoji):
    style = f"font-size: 15px;"
    if emoji:
        style += " font-family: 'notocoloremoji';"
    return f'<span style="{style}">{text}</span>'


def process_response(driver, request_id):
    """
    Get response body for a specific request
    """
    try:
        response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
        if 'body' in response_body:
            return response_body['body']
        return None
    except Exception as e:
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

    return info




def monitor_network(driver):
    global initialized,loaded
    """
    Monitor and print network responses including bodies
    """

    request_ids = set()
    antidesync_time = time.time()
    
    while True:
        logs = driver.get_log('performance')
        
        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']
                
                if log['method'] == 'Network.responseReceived':
                    params = log['params']
                    request_id = params['requestId']
                    
                    if request_id not in request_ids:
                        request_ids.add(request_id)
                        response = params['response']
                        url = response['url']
                        status = response['status']
                        mime_type = response['mimeType']
                        if mime_type == "text/plain" and status == 200 and "zkauA10" in url:
                            #print(f"\nNetwork Response:")
                            #print(f"URL: {url}")
                            #print(f"Status: {status}")
                            #print(f"Type: {mime_type}")
                            #print("Headers:", json.dumps(response['headers'], indent=2))
                            #print(params["requestId"])
                            
                            # Get response body
                            body = process_response(driver, request_id)
                            if body:
                                extract_connection = extract_connections(body)
                                if len(extract_connection) != 0:
                                    #print("\nResponse Body:")
                                    extracted_data.update(extract_connection)
                                    if len(extracted_data) == 8:
                                    #    print(extracted_data)
                                        window.update_list(extracted_data["Status"],sortListAndCalculateAdditionalValues(extracted_data))
                                    #    print("Desync time: "+str(time.time() - antidesync_time))
                                        antidesync_time = time.time()
                                        initialized = True
                                        loaded = True
                                    #    print("-" * 80)  # Separator for readability
                        
            except Exception as e:
                print(e)
                pass
        if time.time() - antidesync_time > 65:
            print(time.strftime("%H:%M:%S", time.localtime()) + "| Desync detected reloading page: " + str(time.time() - antidesync_time))
            loaded = False
            reload()
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

def stempeln(Pause):
    global amstempeln, window, stempelupdate,timesincereload
    amstempeln = True
    value = "Pause"
    if Pause == False:
        value = "Anwesenheitsbeginn"
    window.label.setText("Versuch "+value+" zu Stempeln")
    stempelState = window.circle.color.name() == "#00ff00"
    # Switch to the iframe
    enterFrame()
    # Loop trough the elements to "Stempel"
    try:
        # Wait for button to be active
        elements = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".action-item"))
        )
        for element in elements:
            if element.text.startswith("Zeiterfassung (Kommen"):
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".action-item"))
                )
                WebDriverWait(driver, 30).until(
                    lambda d: not element.get_attribute("disabled") == "disabled"
                )
                element.click()
                break
        elements = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "info-element-button"))
        )
        for element in elements:
                WebDriverWait(driver, 30).until(
                    lambda d: not element.get_attribute("disabled") == "disabled"
                )
        elements = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".title-element"))
        )
            

        for element in elements:
            if element.text.startswith(value):
                #print("stempel " + value)
                if stempelState == Pause:
                    #print("click?")
                    element.click()
                    window.label.setText("Stempel "+value+" hat geklappt")
                else:
                    window.label.setText("Du hast versucht gleich zu stempeln bitte mach das nicht")
                    time.sleep(0.5)
                    print(extracted_data)
                    window.update_list(extracted_data["Status"],sortListAndCalculateAdditionalValues(extracted_data))
                driver.switch_to.default_content()
                break
    except (TimeoutException,StaleElementReferenceException):
        stempeln(Pause)
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
    # Circle to display Anwesendheitsstatus
    def __init__(self, initial_state):
        self.circle_height = int(screen.size().height() / 48)
        super().__init__()
        self.color = QColor(Qt.green) if initial_state == "Anwesend" else QColor(Qt.red)
        self.setMinimumSize(int(self.circle_height * 1.2), self.circle_height)

    def paintEvent(self, event):
        # Draw the circle with the current color
        painter = QPainter(self)
        painter.setPen(QPen(Qt.black, 2, Qt.SolidLine))
        painter.setBrush(QBrush(self.color, Qt.SolidPattern))
        painter.drawEllipse(0, 0, self.circle_height , self.circle_height )


    def update_color(self, state):
        # Update the color based on the state and repaint the widget
        self.color = QColor(Qt.green) if state == "Anwesend" else QColor(Qt.red)
        self.setMinimumSize(int(self.circle_height * 1.2), self.circle_height)
        self.update()
# Unused
class NoFocusListWidget(QListWidget):
    def focusInEvent(self, event):
        pass

class ClockInButton(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)
        
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create button
        self.button = QPushButton("Einspempeln")
        self.button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)
        self.button.clicked.connect(lambda: (stempeln(False), window.hide_clock_button()))
        layout.addWidget(self.button)
        
        self.setLayout(layout)
        
    def adjustSize(self):
        screen = QGuiApplication.primaryScreen()
        size = screen.size()
        height = int(size.height() / 48)
        button_width = int(size.width() / 19.2)
        self.setGeometry(int(size.width() / 19.2), screen.geometry().topLeft().y() + height + 5, button_width, height)


class Window(QWidget):
    def __init__(self, initial_state, my_list):
        super().__init__()
        self.clock_button = None
        self.initUI(initial_state, my_list)

    def initUI(self, initial_state, my_list):
        for v in QGuiApplication.screens():
            v.geometryChanged.connect(self.adjustSize)
        self.setWindowTitle("ATOSS Compact")
        size = screen.size()
        height = int(size.height()/48)
        self.setGeometry(int(size.width()/19.2), screen.geometry().topLeft().y(), height, height) #Position and size of the window
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 2, 0, 0)  # Remove margins
        layout.setSpacing(0)  # Remove spacing

        # Create a horizontal layout for the circle and the button
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        h_layout.setSpacing(0)  # Remove spacing
        
        self.circle = Circle(initial_state)
        h_layout.addWidget(self.circle)

        infostr = "   |   ".join(my_list) # Build the string to display in the lable

        # Update the circle and lable
        self.label = QLabel(infostr)
        self.label.setTextFormat(Qt.RichText)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        h_layout.addWidget(self.label)

        layout.addLayout(h_layout)

        self.setLayout(layout)

    def update_list(self, status, extraced_data):
        self.circle.update_color(status)
        infostr = "   |   ".join(extraced_data)
        update_label_from_thread(self.label, infostr)
        if status != "Anwesend":
            self.show_clock_button()
        else:
            self.hide_clock_button()
    
    def show_clock_button(self):
        if not self.clock_button:
            self.clock_button = ClockInButton()
            self.clock_button.adjustSize()
            self.clock_button.show()

    def hide_clock_button(self):
        if self.clock_button:
            self.clock_button.hide()
            self.clock_button = None

    def adjustSize(self):
        while True:
            if QGuiApplication.primaryScreen().availableGeometry().height() != 0:
                break
            else:
                time.sleep(0.1)
                QApplication.processEvents()

        screenNow = QGuiApplication.primaryScreen()  # Update the screen variable
        size = screenNow.size()
        height = int(size.height() / 48)
        self.circle.circle_height = height
        self.label.setMinimumSize(int(height * 1.2), height)
        self.setGeometry(int(size.width() / 19.2), screenNow.geometry().topLeft().y(), self.width(), height)  # Set y-coordinate to 0
        if self.clock_button:
            self.clock_button.adjustSize()

    # Move the window (those 2 functions are not needed anymore)
    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        globalpos = event.globalPos()
        delta = QPoint(globalpos - self.oldPos)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPos = globalpos

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

    listener_thread = threading.Thread(target=start_keyboard_listener)
    listener_thread.start()

def main():
    global  window, screen,t,timesincereload,driver,debug,initialized

    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--user-data-dir=selenium")  # Path to your chrome profile
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    if not debug:
        chrome_options.add_argument("--headless")  # Run in headless mode

    wait_for_process("ZSTray")
    wait_after_boot()

    # Setup WebDriver
    while driver is None:
        try:
            s = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=s, options=chrome_options)
        except WebDriverException:
            pass  
    # Open the website
    driver.get('https://hoffmann-group.atoss.com/hoffmanngroupprod/html?security.sso=true')
    #WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    
    #wait for userlogin
    #time.sleep(60)

    
    monitor_thread = threading.Thread(target=monitor_network, args=(driver,))
    monitor_thread.start()

    setup_keybinds()

    app = QApplication(sys.argv)

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
    screen = app.primaryScreen()

    window = Window("Abwesend", ['<span style="font-size:14pt;">Programm wird gestartet</span>'])
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
    







            #     function updatePage(){
            #     let InformationElements = [];
            #     const checkElement = setInterval(() => {
            #         InformationElements = iframeDocument.querySelectorAll('.data-list-body-cell.dataCell.labelValueCell');
            #         if (InformationElements.length > 0) {
            #             clearInterval(checkElement);

            #             // The rest of your code runs here after the interval is finished
            #             let extractedData = {};
            #             let key;
            #             let value;
            #             let gehen;
            #             InformationElements.forEach(function(InformationElement) {
            #                 key = InformationElement.children[0].children[0].innerHTML;
            #                 if (key === "Gehen") {
            #                     gehen = InformationElement.children[0].children[2];
            #                 }
            #                 if (InformationElement.children[0].children[2].childElementCount > 0) {
            #                     value = InformationElement.children[0].children[2].textContent;
            #                 } else {
            #                     value = InformationElement.children[0].children[2].innerHTML;
            #                 }
            #                 extractedData[key] = value;
            #             });

            #             const pause = extractedData["Heutige Pause"];
            #             if (extractedData.Status === "Annwesend") {
            #                 const [hours, minutes] = pause.split(":").map(Number);
            #                 let pause2 = pause;
            #                 if (GM_getValue('18+') === true) {
            #                     if (minutes < 30 && hours < 0) {
            #                         pause2 = "0:30";
            #                     }
            #                 } else {
            #                     if (hours < 1) {
            #                         pause2 = "1:00";
            #                     }
            #                 }
            #                 gehen.innerHTML = addTimes(addTimes(extractedData.Kommen, '7:42'), pause2);
            #             } else {
            #                 const possibleOverrideSpots = iframeDocument.querySelectorAll('.data-list-body-cell-wrapper');
            #                 const currentTime = getCurrentTime();
            #                 gehen = "15:20";
            #                 const currentPause = subtractTimes(currentTime, gehen);
            #                 if (pause === "0:00") {
            #                     possibleOverrideSpots[4].children[0].innerHTML = currentPause;
            #                 } else {
            #                     const newpause = addTimes(subtractTimes(currentTime, gehen), pause);
            #                     possibleOverrideSpots[4].children[0].innerHTML = currentPause + " | " + newpause;
            #                 }
            #                 console.log(possibleOverrideSpots);
            #             }
            #         }
            #     }, 1000);
            # }