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
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QListWidget, QListWidgetItem, QSizePolicy
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QPalette, QGuiApplication
from PyQt5.QtCore import Qt, QTimer, QPoint, QTime
from datetime import datetime, timedelta
from pynput import keyboard
import psutil
import threading
import re
import time
import sys
import random
import socket

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
        t.failed()
        t.join()
        init()
        main()

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

def update(refresh):
    global window,loaded,amstempeln,stempelupdate,az,noupdate,timesincereload
    # Refresh if needed and switch to the iframe
    if (refresh and amstempeln == False):
        stempelupdate = False
        loaded = False
        try:
            driver.refresh()
            timesincereload = time.time()
            alert = driver.switch_to.alert
            alert.accept()
        except NoAlertPresentException:
            pass

    #switch to IFrame

    if not enterFrame():
        return [None ,[],False]
    

    # Function Variable cration
    my_list = []
    initial_state = None
    arbeitszeit = None
    kommen = None
    pause = None
    current_time = None


    try:
        # Wait for elements to be present
        elements = WebDriverWait(driver, 50).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "caption"))
        )
        prev_element_text = None
        prev_prev_element_text = None
        first_occurrence = True
        gone = False
        #failsafe to prevent getting bad values
        time.sleep(0.1)
        # Iterate over the elements and extract the required data
        for element in elements:
            text = element.text
            match = re.search(r'\b\d{1,2}:\d{2}\b', text)
            if match:
                if prev_element_text == "Heutige Anwesenheit":
                    arbeitszeit = match.group()
                    prev_element_text = "⏰"
                elif prev_element_text == "Heutige Pause":
                    prev_element_text = "🍔"
                    pause = match.group()
                elif prev_element_text == "Kommen":
                    prev_element_text = "👣"
                    kommen = match.group()
                elif prev_element_text == "Gehen":
                    my_list.append(f"G {match.group()} ({subtract_times(datetime.now().strftime('%H:%M'), match.group())} / {add_times(subtract_times(datetime.now().strftime('%H:%M'), match.group()), pause)}) ")
                    gone = True
                    continue
                elif prev_element_text == "gestempelte Wochen-AZ":
                    if not gone:
                        current_time = add_times(add_times(arbeitszeit, kommen), pause)
                        pause2 = "1:00" if datetime.strptime(pause, "%H:%M") < datetime.strptime("1:00", "%H:%M") else pause
                        pause3 = "0:30" if datetime.strptime(pause, "%H:%M") < datetime.strptime("0:30", "%H:%M") else pause
                        my_list.append(f"G : {add_times(add_times(kommen, '6:00'), pause3)}/{add_times(add_times(kommen, '7:42'), pause2)}/{add_times(add_times(kommen, '8:30'), pause2)}")
                        my_list.append(f"G in h : {checkMinus(subtract_times(add_times(add_times(kommen, '6:00'), pause3), current_time))}/{checkMinus(subtract_times(add_times(add_times(kommen, '7:42'), pause2), current_time))}/{checkMinus(subtract_times(add_times(add_times(kommen, '8:30'), pause2), current_time))}")
                    continue
                elif prev_element_text == "Arbeitszeitkonto":
                    prev_element_text = "🌙"
                    üs = text+" ("+ add_times(subtract_times(arbeitszeit, "7:42"),text)+")" if datetime.strptime(arbeitszeit, "%H:%M") < datetime.strptime("7:42", "%H:%M") else add_times(subtract_times(arbeitszeit, "7:42"),text)+" +" + subtract_times(arbeitszeit, "7:42")
                    my_list.append(f"{prev_element_text} {üs}")
                    continue
                elif prev_element_text == "AZK_Auszahlung":
                    continue
                if first_occurrence and prev_prev_element_text:
                    initial_state = prev_prev_element_text
                    first_occurrence = False
                if prev_element_text:
                    my_list.append(f"{prev_element_text} {match.group()}")
            prev_prev_element_text = prev_element_text
            prev_element_text = text
    finally:
        # Switch back to the main content
        driver.switch_to.default_content()

        # Check if the information is valid
        badcheck = initial_state is not None and arbeitszeit is not None
        
        # Check of information is out of sync
        if arbeitszeit == az and amstempeln == False and initial_state == "Anwesend":
            #noupdate = True
            my_list.append("Desynced")
            window.label.setText(window.label.text() + " ⟳")
            QApplication.processEvents()
            stuff = update(True)
            initial_state = stuff[0]
            my_list = stuff[1]
            badcheck = stuff[2]
        else:
            if not amstempeln:
                az = arbeitszeit

        # Return the extracted data
        loaded = True
        return [initial_state, my_list, badcheck]
    

def stempeln(Pause):
    global amstempeln, window, stempelupdate
    amstempeln = True
    value = "Pause"
    if Pause == False:
        value = "Anwesenheitsbeginn"
    window.label.setText("Versuch "+value+" zu Stempeln")
    if Pause == False and (time.time() - timesincereload)> 60:
        reload()
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
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "info-element-button"))
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
                driver.switch_to.default_content()
                break
    except (TimeoutException,StaleElementReferenceException):
        stempeln(Pause)
    finally:
        #delay to prevent false values (please update in the future to be static)
        time.sleep(0.5)
        stempelupdate = True
        window.update_list(False)
        amstempeln = False
        stempelupdate = False

def add_times(time1, time2):
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

def subtract_times(time1, time2):
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

def checkMinus(input_string):
    if "-" in input_string:
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

class Window(QWidget):
    #Window to display the values
    def __init__(self, initial_state, my_list):
        super().__init__()

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
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
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
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        h_layout.addWidget(self.label)

        layout.addLayout(h_layout)

        self.setLayout(layout)

        # Create a QTimer object
        self.timer = QTimer()

        # Connect the timeout signal to the update_list function
        def update_and_count():
            global noupdate
            # Refresh if out of sync
            if noupdate == True:
                self.update_list(True)
                noupdate = False
            else:
                self.update_list(False)

        # Update Values every Minute
        self.timer.timeout.connect(update_and_count if not amstempeln else None)

        # Start the timer to trigger at the next minute
        self.timer.start((61 - QTime.currentTime().second()) * 1000)

        # After the first timeout, set the timer to trigger every 60 seconds
        self.timer.timeout.connect(lambda: self.timer.start((61 - QTime.currentTime().second()) * 1000))


    def update_list(self, refresh):
        # Generate updated values

        stuff = update(refresh)
        if stuff[2]:  # If the data is valid
            # Set circle color
            self.circle.update_color(stuff[0])

            # Update the label with the new information
            infostr = "   |   ".join(stuff[1])
            self.label.setText(infostr)
        else:
            self.label.setText(self.label.text() + " old")

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

    # Move the window (those 2 functions are not needed anymore)
    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        globalpos = event.globalPos()
        delta = QPoint(globalpos - self.oldPos)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPos = globalpos

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
    if time.time() - last_time_pressed > 5:
        if COMBINATION1.issubset(current_keys):
            if loaded == False or initialized == False or amstempeln == True:
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

class WindowThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(WindowThread, self).__init__(*args, **kwargs)
        self.initwindow = None
        self.label = None

    def run(self):

        # Create the application object
        initapp = QApplication(sys.argv)
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(19, 19, 19))
        palette.setColor(QPalette.WindowText, Qt.red)
        initapp.setPalette(palette)

        # Create the main initwindow
        self.initwindow = QWidget()
        self.initwindow.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint)

        # Set the layout and label
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        layout.setSpacing(0)  # Remove spacing
        self.label = QLabel("Das Programm wird gestartet")
        layout.addWidget(self.label)
        self.initwindow.setLayout(layout)

        # Set initwindow size and display the initwindow
        screen = initapp.primaryScreen()
        size = screen.size()
        height = int(size.height()/48)
        self.initwindow.setGeometry(int(size.width()/19.2), screen.geometry().topLeft().y(), height, height)
        self.initwindow.show()

        # Execute the application
        sys.exit(initapp.exec_())

    def close(self):
        if self.initwindow is not None:
            self.initwindow.close()
    def failed(self):
        try:
            self.label.setText("Start nicht möglich versuche es erneut!")
        except RuntimeError as e:
            print(f"Es ist ein Fehler aufgetreten prgramm startet möglicherweise nicht neu: {e}")
        time.sleep(1)
        if self.initwindow is not None:
            self.initwindow.close()
t = None
def init():
    global t
    t = WindowThread()
    t.start()
init()
driver = None

def wait_for_process(process_name):
    while True:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == process_name:
                print(f"{process_name} is running.")
                return
        time.sleep(0.1)
wait_for_process("ZSTray")

window = None
screen = None
scripttime = 0
while time.time()- psutil.boot_time() < 150 and scripttime < 3:
    time.sleep(1)
    scripttime += 1
    print(scripttime)

def main():
    global  window, screen,t,timesincereload,driver,debug,initialized

    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--user-data-dir=selenium")  # Path to your chrome profile
    if not debug:
        chrome_options.add_argument("--headless")  # Run in headless mode

    # Setup WebDriver
    while driver is None:
        try:
            s = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=s, options=chrome_options)
        except WebDriverException:
            pass  

    # Open the website
    driver.get('https://hoffmann-group.atoss.com/hoffmanngroupprod/html?security.sso=true')
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

    #wait for userlogin
    #time.sleep(60)
#✔️
    # Get the body element
    body = driver.find_element(By.TAG_NAME, 'body')

    # Check if the body has the class "neterror"
    if 'neterror' in body.get_attribute('class').split():
        t.failed()
        t.join()
        #print("failed to initialize")
        init()
        main()
    else:
        timesincereload = time.time()
        stuff = update(False)
        if stuff[2]:  # If the data is valid
            t.close()
            
            # Wait for the window thread to finish
            t.join()
            initial_state = stuff[0]
            my_list = stuff[1]
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

            window = Window(initial_state, my_list)
            window.show()
            initialized = True
            sys.exit(app.exec_())
        else:
            t.failed()
            t.join()
            #print("failed to initialize")
            init()
            main()
            #make it so it will alsop reinit when other fail

if __name__ == "__main__":
    main()
    