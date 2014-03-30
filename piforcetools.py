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
    """ Helper function to print to the LCD and clear/delay the output """
    if clear:
        lcd.clear()
    lcd.message(message)
    if delay > 0:
        sleep(delay)

class Menu:
    """ Class that defines a menu """
    def __init__(self, name, items):
        self.list = items
        self.index = 0
        self.name = name

    def goDown(self):
        """ Down means advancing to the next item in the list
        If we reach the end of the list, we go to the beginning.
        New item is returned """
        if not self.list:
            return None
        self.index = (self.index + 1) % len(self.list)
        return self.getItem()

    def goUp(self):
        """ Up means advancing to the previous item in the list
        If we reach the beginning of the list, we go to the end.
        New item is returned """
        if not self.list:
            return None
        self.index = (self.index - 1) % len(self.list)
        return self.getItem()

    def getItem(self):
        """ Get the current item of the menu """
        if not self.list:
            return None
        return self.list[self.index]

class MenuItem:
    """ Defines an item within a Menu.  A menu item has 2 attributes:
    - The name of the menu item
    - The function to run when the menu item is selected
    """
    def __init__(self, name, onclick):
        self.name = name
        self.onclick = onclick

def noGamesFoundClick():
    """ If no games are found and the user clicks on the "No games found" menu item,
    this message is displayed """
    lcdPrint("You need games!", 5)

def changeTargetClick():
    """ Click handler for changing the target IP """
    global curr_ip
    global ips
    curr_ip = (curr_ip + 1) % len(ips)
    lcdPrint(ips[curr_ip], 1)

def downloadUpdateClick():
    """ Click handler for downloading updates """
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
    """ Click handler for Enable DHCP menu item """
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
    """ Click handler for Enable Static menu item """
    os.system("mount -o rw,remount /")
    os.system("cp netctl/ethernet-static /etc/netctl/eth0")
    os.system("mount -o ro,remount /")
    os.system("ip link set eth0 down")
    os.system("netctl restart eth0")
    ip = socket.gethostbyname(socket.getfqdn())
    lcdPrint("Enabled Static:\n"+ip, 2)

def refreshClick():
    """ Click handler for refreshing the games list
    in case a new game has been copied over """
    global games
    games = buildGamesMenu()

def shutdownClick():
    """ Click handler for shutting down """
    lcdPrint("Shutting\nDown", 5)
    os.system("shutdown -h now")
    exit(0)

def restartClick():
    """ Click handler for restarting """
    lcdPrint("Restarting", 5)
    os.system("shutdown -r now")
    exit(0)

def pingClick():
    """ Click handler for pinging the NetDIMM """
    lcdPrint("Pinging\n"+ips[curr_ip])
    response = os.system("ping -c 1 "+ips[curr_ip])
    if response == 0:
        lcdPrint("Netdimm is\nreachable!", 1)
    else:
        lcdPrint("Netdimm is\nunreachable!", 1)

def gameClick(filename):
    """ Click handler for launching a game.  The pull path to the 
    game file must be passed in """
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

# Add DHCP/Static menu items if appropriate files exist
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
    """ Generates a Menu that contains the games found in the defined rom path """
    lcdPrint("Scanning...")
    # Uses the games_catalog to get a list of games, then checks for the existence of the
    # file. If the file is found, a new MenuItem is created the game name and a function
    # is created to call "gameClick" with the right path.
    available_games = [MenuItem(game_name,(lambda file_name=file_name:gameClick(rom_dir+file_name))) 
                       for game_name,file_name in games_catalog.get_catalog().items() 
                       if os.path.isfile(rom_dir+file_name)]
    # Sort the list by name
    available_games.sort(key = lambda x: x.name)
    lcdPrint("\n%d Games" % len(available_games), 1, False)
    # If no games were found, create a new menu that contains a No Games found message
    if len(available_games) == 0:
        available_games = [MenuItem('NO GAMES FOUND', noGamesFoundClick)]
    return Menu('Games List', available_games)

def changeMenu(new_menu):
    """ Handles changing between menus (i.e. Games and Commands) """
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
# Start on the games menu
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
