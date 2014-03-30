#!/usr/bin/python2
# Written by Capane.us

import os, collections, signal, sys, subprocess, socket
import triforcetools
import games_catalog
from systemd import daemon
from Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
from time import sleep

ips = ["10.0.0.2", "10.0.0.3"] # Add or remove as many endpoints as you want
rom_dir = "/home/pi/roms/"  # Set absolute path of rom files ending with trailing /

# Util to help print to LCD
def lcdPrint(message, delay = 0, clear = True):
    if clear:
        lcd.clear()
    lcd.message(message)
    if delay > 0:
        sleep(delay)

class Menu:
    def __init__(self, name, items):
        self.list = items
        self.index = 0
        self.name = name

    def goDown(self):
        if not self.list:
            return None
        self.index = (self.index + 1) % len(self.list)
        return self.getItem()

    def goUp(self):
        if not self.list:
            return None
        self.index = (self.index - 1) % len(self.list)
        return self.getItem()

    def getItem(self):
        if not self.list:
            return None
        return self.list[self.index]

class MenuItem:
    def __init__(self, name, onclick):
        self.name = name
        self.onclick = onclick

def noGamesFoundClick():
    lcdPrint("You need games!", 5)

def changeTargetClick():
    global curr_ip
    global ips
    curr_ip = (curr_ip + 1) % len(ips)
    lcdPrint(ips[curr_ip], 1)

def downloadUpdateClick():
    lcd.clear()
    lcd.message("Downloading...")
    lcd.setCursor(14, 0)
    lcd.ToggleBlink()
    os.system("mount -o rw,remount /")
    try:
        response = subprocess.check_output(["git", "pull"])
    except:
        response = "Update Error:\nCheck Internet"
    os.system("mount -o ro,remount /")
    if response.strip() == "Already up-to-date.":
        message = "No Update Found"
    else:
        message = response.strip()
    lcd.ToggleBlink()
    lcdPrint(message, 2)

def enableDHCPClick():
    os.system("mount -o rw,remount /")
    os.system("cp netctl/ethernet-dhcp /etc/netctl/eth0")
    os.system("mount -o ro,remount /")
    lcdPrint("Obtaining IP...")
    lcd.setCursor(15,0)
    lcd.ToggleBlink()
    os.system("ip link set eth0 down")
    os.system("netctl restart eth0")
    ip = socket.gethostbyname(socket.getfqdn())
    lcd.ToggleBlink()
    lcdPrint("Enabled DHCP:\n"+ip, 2)
    
def enableStaticClick():
    os.system("mount -o rw,remount /")
    os.system("cp netctl/ethernet-static /etc/netctl/eth0")
    os.system("mount -o ro,remount /")
    os.system("ip link set eth0 down")
    os.system("netctl restart eth0")
    ip = socket.gethostbyname(socket.getfqdn())
    lcdPrint("Enabled Static:\n"+ip, 2)

def refreshClick():
    global games
    games = buildGamesMenu()

def shutdownClick():
    lcdPrint("Shutting\nDown", 5)
    os.system("shutdown -h now")
    exit(0)

def restartClick():
    lcdPrint("Restarting", 5)
    os.system("shutdown -r now")
    exit(0)

def pingClick():
    lcdPrint("Pinging\n"+ips[curr_ip])
    response = os.system("ping -c 1 "+ips[curr_ip])
    if response == 0:
        lcdPrint("Netdimm is\nreachable!", 1)
    else:
        lcdPrint("Netdimm is\nunreachable!", 1)

def gameClick(filename):
    lcdPrint("Connecting...")
    
    try:
        triforcetools.connect(ips[curr_ip], 10703)
    except:
        lcdPrint("Error:\nConnect Failed", 1)
        return

    lcdPrint("Sending...")
    lcd.setCursor(10, 0)
    lcd.ToggleBlink()

    triforcetools.HOST_SetMode(0, 1)
    triforcetools.SECURITY_SetKeycode("\x00" * 8)
    triforcetools.DIMM_UploadFile(filename)
    triforcetools.HOST_Restart()
    triforcetools.TIME_SetLimit(10*60*1000)
    triforcetools.disconnect()

    lcd.ToggleBlink()
    lcdPrint("Transfer\nComplete!", 5)

# Build the commands menu
commands = Menu('Commands',[
        MenuItem("Change Target", changeTargetClick),
        MenuItem("Download Update", downloadUpdateClick),
        MenuItem("Refresh Games\nList", refreshClick),
        MenuItem("Shutdown", shutdownClick),
        MenuItem("Restart", restartClick),
        MenuItem("Ping Netdimm", pingClick)
    ])

if os.path.isfile("netctl/ethernet-dhcp"):
    commands.list.append(MenuItem("Enable DHCP", enableDHCPClick))
if os.path.isfile("netctl/ethernet-static"):
    commands.list.append(MenuItem("Enable Static", enableStaticClick))

# Define a signal handler to turn off LCD before shutting down
def handler(signum = None, frame = None):
    lcd = Adafruit_CharLCDPlate()
    lcd.clear()
    lcd.stop()
    sys.exit(0)
signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)

# We are up, so tell systemd
daemon.notify("READY=1")

# Generate list of available games by checking that files exist
def buildGamesMenu():
    lcdPrint("Scanning...")
    available_games = [MenuItem(game_name,(lambda file_name=file_name:gameClick(rom_dir+file_name))) 
                       for game_name,file_name in games_catalog.get_catalog().items() 
                       if os.path.isfile(rom_dir+file_name)]
    available_games.sort(key = lambda x: x.name)
    lcdPrint("\n%d Games" % len(available_games), 1, False)
    if len(available_games) == 0:
        available_games = [{'name':'NO GAMES FOUND',
                            'onclick': noGamesFoundClick}]
    return Menu('Games List', available_games)

def changeMenu(new_menu):
    lcdPrint(new_menu.name, 1)
    lcdPrint(new_menu.getItem().name)
    return new_menu

# Initialize LCD
pressedButtons = []
curr_ip = 0
lcd = Adafruit_CharLCDPlate()
lcd.begin(16, 2)
lcdPrint(" Piforce Tools\n   Ver. 1.1", 2)
# Populate games
games = buildGamesMenu()
curr_menu = changeMenu(games)
selection = curr_menu.getItem()
lcdPrint(selection.name)

while True:
    # Handle SELECT
    if lcd.buttonPressed(lcd.SELECT) and lcd.SELECT not in pressedButtons:
        pressedButtons.append(lcd.SELECT)
        selection.onclick()
        lcdPrint(selection.name)

    # Handle LEFT
    if lcd.buttonPressed(lcd.LEFT) and lcd.LEFT not in pressedButtons:
        pressedButtons.append(lcd.LEFT)
        curr_menu = changeMenu(games)
        selection = curr_menu.getItem()

    # Handle RIGHT
    if lcd.buttonPressed(lcd.RIGHT) and lcd.RIGHT not in pressedButtons:
        pressedButtons.append(lcd.RIGHT)
        curr_menu = changeMenu(commands)
        selection = curr_menu.getItem()

    # Handle UP
    if lcd.buttonPressed(lcd.UP) and lcd.UP not in pressedButtons:
        pressedButtons.append(lcd.UP)
        selection = curr_menu.goUp()
        lcdPrint(selection.name)

    # Handle DOWN
    if lcd.buttonPressed(lcd.DOWN) and lcd.DOWN not in pressedButtons:
        pressedButtons.append(lcd.DOWN)            
        selection = curr_menu.goDown()
        lcdPrint(selection.name)

    # Update pressedButtons by removing those that are no longer pressed
    pressedButtons = [button for button in pressedButtons if lcd.buttonPressed(button)]
