import time
import sys
sys.path.append('/usr/local/lib/python2.7/site-packages')
import os
import cv2
import numpy as np
import subprocess
import socket
import smbus
import requests
import getpass
import datetime
import RPi.GPIO as GPIO
from datetime import timedelta
from threading import Thread, current_thread
from PIL import Image
from functools import wraps
from flask import Flask, render_template, redirect, request, Response
app = Flask(__name__)

# ip cam
cam_adres = "88.53.197.250/axis-cgi/mjpg/video.cgi?resolution=320x240"
#Datacom 172.23.49.1/axis-cgi/com/ptz.cgi
#Italie 88.53.197.250/axis-cgi/mjpg/video.cgi?resolution=320x240
#GoPro 10.5.5.9:8080/live/amba.m3u8
user = None
passw = None
camera = 1

image_path= "/home/pi/Webservice/static/images/ipcam/"

# lcd variablen
display = None

# lcd adres
adres = 0x3f

# commands
lcd_cleardisplay = 0x01
lcd_home = 0x02
lcd_entrymode = 0x04
lcd_displaycontrol = 0x08
lcd_functionset = 0x20

# flags for display entry mode
lcd_entry = 0x02

# flags for display on/off control
lcd_on = 0x04
lcd_off = 0x00

# flags for function set
lcd_4bitmode = 0x00
lcd_2lines = 0x08
lcd_5x8dots = 0x00

# flags for backlight control
lcd_backlighton = 0x08
lcd_nobacklightoff = 0x00

En = 0b00000100 # Enable bit
Rw = 0b00000010 # Read/Write bit
Rs = 0b00000001 # Register select bit

# pin variables
button_pin = 18
led_pin = 21

# cv variables
win_stride = eval("(8, 8)")
padding = eval("(16, 16)")
mean_shift = False
scale = 1.05

def check_auth(username, password):
    return username == user and password == passw

def authenticate():
    return Response(
    'You have no authority to acces this page.\n'
    'Acces denied 401!', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(a):
    @wraps(a)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return a(*args, **kwargs)
    return decorated


@app.route('/')
@requires_auth
def index():
    splitted = cam_adres.split("/")
    ip = splitted[0]
    return render_template(
        'index.html',
        url = cam_no_cred,
        ip = ip
        )

@app.route('/accept')
@app.route('/accept/<message>')
def accept(message = 'Please Enter'):
    message = message.replace('+',' ')
    security_status['current_status'] = message
    security_status['door_open'] = True
    security_status['waiting_response'] = False
    return redirect('/')

@app.route('/denied')
@app.route('/denied/<message>')
def denied(message = 'Acces Denied'):
    message = message.replace('+',' ')
    security_status['current_status'] = message
    security_status['waiting_response'] = False
    return redirect('/')

@app.route('/picture')
def picture():
    security_status['take_picture'] = True
    return redirect('/')


@app.route('/gallery')
def gallery():
    images = []
    images = os.listdir(os.path.join(app.static_folder, 'images/ipcam'))
    splitted = cam_adres.split("/")
    ip = splitted[0]
    return render_template(
        'gallery.html',
        images = images,
        ip = ip
        )

def web_service():
    app.run(host= '0.0.0.0')
    


def exec_command(command):
    try:
        requests.get("{0}&{1}".format(cam_url,command),timeout = 2)
    except requests.exceptions.RequestException as e:
        print 'Could not connect login might be incorrect:'
        print e

def main_logic():
    while security_status['init'] == False:
        time.sleep(2)     
    
    while True:
        if security_status['current_status'] == 'Scanning':
            if security_status['scanning'] != True:
                update_status('Scanning')
                security_status['scanning'] = True
                print 'Command start scanning'
                exec_command("continuouspantiltmove=10,0")

        if security_status['doorbell_pressed'] == True:
             update_status('Welcome')
             security_status['scanning'] = False
             security_status['doorbell_pressed'] = False 
             security_status['waiting_response'] = True
             print 'Command go to home'
             exec_command("move=home")
             i = 0
             while  security_status['waiting_response']:
                if security_status['door_open'] == True:
                    break
                time.sleep(1)
                i += 1
                if i == 10:
                    break

        if security_status['door_open'] == True:
            GPIO.output(led_pin,True)
            time.sleep(10)
            GPIO.output(led_pin,False)
            security_status['door_open'] = False

        if security_status['current_status'] != 'Scanning' and security_status['door_open'] == False:
            security_status['scanning'] = False
            time.sleep(10)
            update_status('Scanning')
        time.sleep(1)

class i2c:
   def __init__(self, addr, port=1):
      self.addr = addr
      self.bus = smbus.SMBus(port)

   def write_command(self, cmd):
      self.bus.write_byte(self.addr, cmd)
      time.sleep(0.0001)


class lcd:
   #initializes objects and lcd
   def __init__(self):
      self.lcd_device = i2c(adres)

      self.lcd_write(0x03)
      self.lcd_write(0x03)
      self.lcd_write(0x03)
      self.lcd_write(0x02)

      self.lcd_write(lcd_functionset | lcd_2lines | lcd_5x8dots | lcd_4bitmode)
      self.lcd_write(lcd_displaycontrol | lcd_on)
      self.lcd_write(lcd_cleardisplay)
      self.lcd_write(lcd_entrymode | lcd_entry)
      time.sleep(0.2)

   def lcd_strobe(self, data):
      self.lcd_device.write_command(data | En | lcd_backlighton)
      time.sleep(.0005)
      self.lcd_device.write_command(((data & ~En) | lcd_backlighton))
      time.sleep(.0001)

   def lcd_on(self):
       self.lcd_write(lcd_displaycontrol | lcd_on)

   def lcd_off(self):
       self.lcd_write(lcd_displaycontrol | lcd_off)

   def lcd_backlighton_off(self):
       self.lcd_device.write_command(lcd_nobacklightoff)

   def lcd_backlighton_on(self):
       self.lcd_device.write_command(lcd_backlighton)

   def lcd_write_four_bits(self, data):
      self.lcd_device.write_command(data | lcd_backlighton)
      self.lcd_strobe(data)

   # write a command to lcd
   def lcd_write(self, cmd, mode=0):
      self.lcd_write_four_bits(mode | (cmd & 0xF0))
      self.lcd_write_four_bits(mode | ((cmd << 4) & 0xF0))

   # put string function
   def lcd_display_string(self, string, line):
      if line == 1:
         self.lcd_write(0x80)
      if line == 2:
         self.lcd_write(0xC0)
      if line == 3:
         self.lcd_write(0x94)
      if line == 4:
         self.lcd_write(0xD4)

      for char in string:
         self.lcd_write(ord(char), Rs)

   # clear lcd and set to home
   def lcd_clear(self):
      self.lcd_write(lcd_cleardisplay)
      self.lcd_write(lcd_home)



def button_pressed(channel):
    security_status['doorbell_pressed'] = True

def update_status(status):
    #Update security status
    if status != security_status['current_status']:
        security_status['previous_status'] = security_status['current_status']
        security_status['current_status'] = status
        security_status['last_status_change'] = time.time()
        
def video_monitor():

    while security_status['init'] == False:
        time.sleep(1)

    capture_isopen = False
    #GoPro stream 
    capture = cv2.VideoCapture(cam_url)
    #IpCam stream
    #capture = cv2.VideoCapture('http://student:tasjekoffie@172.23.49.1/axis-cgi/com/ptz.cgi?camera=1&move=home')
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    if not capture.isOpened():
        print "Error opening capture device"
        capture.release()
        capture_isopen = False
       
    if capture.isOpened():
        print "Device captured correctly",capture
        capture_isopen = True

    try:
        while True:
            if capture.isOpened():
                if capture_isopen == False:
                    print "Device captured correctly",capture
                    capture_isopen = True
                try:
                    ret, frame = capture.read()
                    (rects, weights) = hog.detectMultiScale(frame, winStride=win_stride,padding=padding, scale=scale, useMeanshiftGrouping=mean_shift)
                    if security_status['take_picture'] == True:
                        filename = image_path + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%d%m-%H%M%S')+".jpeg"
                        cv2.imwrite(filename,frame)
                        security_status['take_picture'] = False
                        print 'Picture taken'
                    for (x, y, w, h) in rects:
                    
                            if security_status['person_detected'] == False:
                                filename = image_path + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%d%m-%H%M%S')+".jpeg"
                                cv2.imwrite(filename,frame)
                                print 'Picture taken'
                                security_status['person_detected'] = True
                                time.sleep(10)
                                security_status['person_detected'] = False
                    
                    time.sleep(1)
                except Exception as e:
                        print str(e)
                        capture.release()
            if not capture.isOpened():
                print "Connection capturing device lost"
                capture.release()
                capture_isopen = False
                time.sleep(10)
                print "Retry connecting"
                capture = cv2.VideoCapture(cam_url)
    except KeyboardInterrupt:
        capture.release()
        

def exit_out(message):
    print message
    GPIO.output(led_pin,False)    
    GPIO.cleanup()
    sys.exit(0)

if __name__ == "__main__":

    print 'Initializing...'
    
    # lcd init
    display = lcd()
    display.lcd_on()
    display.lcd_clear()

    # GPIO init
    GPIO.setmode(GPIO.BCM)
    
    # GPIO button init
    GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(led_pin, GPIO.OUT)
    GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=button_pressed, bouncetime=1000)

    security_status = {
        'time_start': time.time(),
        'current_status': 'Scanning',
        'previous_status': 'Off',
        'last_status_change': time.time(),
        'person_detected': False,
        'doorbell_pressed': False,
        'scanning': False,
        'take_picture': False,
        'init': False,
        'door_open': False,
        'waiting_response': False,
        'override_controls': False
        }

    

    web_service_thread = Thread(name='web_service',target=web_service)
    web_service_thread.daemon = True
    web_service_thread.start()

    #Video monitor
    video_monitor_thread = Thread(name='video_monitor',target=video_monitor)
    video_monitor_thread.daemon = True
    video_monitor_thread.start()

    main_logic_thread = Thread(name='main_logic',target=main_logic)
    main_logic_thread.daemon = True
    main_logic_thread.start()

    login_correct = False

    cam_url = ""
   
    time.sleep(1)
    user = raw_input("Username:")
    passw = getpass.getpass("Password for " + user + ":")
    cam_url = "http://{0}:{1}@{2}?camera={3}".format(str(user),str(passw),cam_adres,str(camera))
    cam_no_cred = "http://{0}?camera={1}".format(cam_adres,str(camera))
    exec_command("move=home")
    

    security_status['init'] = True
    
    try:
       while True:      
           timestamp = datetime.datetime.fromtimestamp(time.time()).strftime('%d/%m/%y %H:%M')
           display.lcd_display_string(str(timestamp).center(16), 1)
           display.lcd_display_string(security_status['current_status'].center(16),2)
           time.sleep(0.1)
               
    except KeyboardInterrupt:
        display.lcd_clear()
        display.lcd_backlighton_off()
        exit_out('Security system stopping...')


    