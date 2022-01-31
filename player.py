#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MiaPlayer - RFID audio player
Copyright 2021 Marcus Schommer <marcus@dankesuper.de>
Distributed under the New BSD License, see LICENSE.txt
"""

import board
import configparser
from contextlib import contextmanager
import ctypes
#import daemon
from gpiozero import Button
from mfrc522 import SimpleMFRC522
import musicpd
import neopixel
import os
from pyky040 import pyky040
import queue
import re
import RPi.GPIO as GPIO
import schedule
import threading
import time
import sys, signal

# starting volume (max 100)
VOLUME = 20
# songs longer than this (seconds) will have shown
# their duration instead of the playlist
LONG_SONG = 600
# brightness (1 = 100 %)
LED_BRIGHTNESS = 0.05

# you normally don't need to change
# options below here
MAX_VOLUME = 100
CFILE = "config.ini"

# BCM pin assignment
FBUTTON = 27
BBUTTON = 22
PBUTTON = 5
ROTARY_CLOCK=4
ROTARY_DATA=17
ROTARY_SWITCH=26

# NeoPixel LED strip
LEDS = 8
LED_ORDER = neopixel.GRB
RED = (255, 0, 0)
YELLOW = (255, 150, 0)
GREEN = (0, 255, 0)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
PURPLE = (180, 0, 255)
OFF = (0, 0, 0)

GPIO.setmode(GPIO.BCM)
pconfig = configparser.ConfigParser()
pixels = neopixel.NeoPixel(board.D12, LEDS + 2, brightness=LED_BRIGHTNESS,
                           auto_write=False, pixel_order=LED_ORDER)
rotary = pyky040.Encoder(CLK=ROTARY_CLOCK, DT=ROTARY_DATA, SW=ROTARY_SWITCH)
client = musicpd.MPDClient()
q = queue.Queue()
_shutdown = object()

# player state
# overwritten by the contents
# of CFILE in read_config()
pstate = {
    # clear playlist before new song is added
    # or append otherwise
    "clr_plist": True,
    # party mode is consume() in MPD,
    # songs get removed from the playlist after they've been played
    "party_mode": False,
    "led": [],
    "volume": VOLUME,
    "max_volume": MAX_VOLUME,
    # pre-shutdown state
    "ps_state": "",
}

run = {
    "set_max_volume": False,
    "smv_pre_state": "",
    "smv_pre_vol": False,
    "fpressed": time.time(),
    "fpressed2": 0,
    "fheld": 0,
    "fheld2": 0,
    "fbutton": 0,
    "bpressed": time.time(),
    "bpressed2": 0,
    "bbutton": 0,
    "ppressed": time.time(),
    "ppressed2": 0,
    "pbutton": 0,
}

class thread_with_exception(threading.Thread):
    def __init__(self, name, status, in_q):
        threading.Thread.__init__(self)
        self.name = name
        self.status = status
        self.in_q = in_q

    def run(self):

        # target function of the thread class
        try:
            #print('>> running ' + self.name)
            print(">> im duration thread")
            #print(">> duration " + str(self.status["duration"]))
            #print(">> elapsed " + str(self.status["elapsed"]))
            duration = float(self.status["duration"])
            elapsed = float(self.status["elapsed"])

            led_factor = duration / LEDS
            print(">> factor " + str(led_factor))
            led_elapsed, led_remainder, loop_start = 0, 0, 0

            pixels.fill(OFF)
            pixels.show()

            if elapsed > 1:
                #print(">> vorherige wiederherstellen")
                led_elapsed = int(elapsed // led_factor)
                #print(">> led_elapsed: " + str(led_elapsed))
                if led_elapsed > 0:
                    #print(">> ..ganze")
                    for i in range(led_elapsed):
                        pixels[i] = YELLOW
                    pixels.show()
                    loop_start = led_elapsed
                #else:
                    #print(">> nix ganzes")

                #print(">> rest wiederherstellen")
                led_remainder = led_factor - (elapsed % led_factor)
                #print(">> led_remainder: " + str(led_remainder))
                if led_remainder > 1:
                    #print(">> ..bis naechste led " + str(led_remainder))
                    time.sleep(led_remainder)
                    pixels[led_elapsed] = YELLOW
                    pixels.show()
                    loop_start = loop_start + 1
                #else:
                    #print(">> nix rest")

            for i in range(loop_start, LEDS):
                #print(">> vor schleifenschlafen")
                time.sleep(led_factor - 0.3)
                pixels[i] = YELLOW
                try:
                    qdata = self.in_q.get(False)
                except queue.Empty:
                    qdata = None
                if qdata is _shutdown:
                    print(">>> _shutdown in run()")
                    self.in_q.put(_shutdown)
                    return
                pixels.show()
                #print(">> pixel " + str(i) + " gezeigt")

        finally:
            print('>> ended')

    def get_id(self):

        # returns id of the respective thread
        if hasattr(self, '_thread_id'):
            return self._thread_id
        for id, thread in threading._active.items():
            if thread is self:
                return id

    def raise_exception(self):
        print("kill me!")
        thread_id = self.get_id()
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id,
              ctypes.py_object(SystemExit))
        if res > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
            print('Exception raise failure')

@contextmanager
def connection(mpdclient):
    """
    creates a context for a safe connection to MPD

    :param mpdclient: MPDClient()
    """

    try:
        mpdclient.connect()
        yield
    finally:
        mpdclient.close()
        mpdclient.disconnect()

def addnplay(tag):
    """
    looks up song or album in MPD, adds them to the playlist,
    plays them if the playlist has been empty.
    adheres to toggle_clr_plist.

    :param tag: string of song or album title, case sensitive
    """

    with connection(client):
        try:
            hit = client.find("title", tag)
            if not hit:
                hit = client.find("album", tag)
            if not hit:
                print(tag)
                client.load(tag)
            if not hit:
                raise Exception("file not found")

            if pstate["clr_plist"] == True:
                client.clear()

            for i in hit:
                client.add(i["file"])

            if pstate["clr_plist"] == True:
                client.play()
            else:
                plist = client.playlistinfo()
                if len(plist) == len(hit):
                    client.play(0)
                else:
                    kitt()
                    trigger_idler()

        except Exception as e:
            print(e)
            kitt(RED)
            show_playlist(client, pstate["led"])
        except musicpd.CommandError as e:
            print("error in addnplay(): " + str(e))

def kitt(color = GREEN):
    """
    creates a LED effect after the car K.I.T.T
    of the 80ies TV show Knight Rider

    :param color: list of GRBW values like (255, 0, 0), default GREEN

    """

    pixels.fill(OFF)
    pixels.show()

    i, j, k, l = 0, LEDS, 1, 0
    while l < 2:
        for x in range(i, j, k):
            pixels[x] = color
            pixels.show()
            time.sleep(0.03)
            if l == 0 and x > 0:
                pixels[x-1] = (0, 0, 0)
            elif l > 0 and x < LEDS:
                pixels[x+1] = (0, 0, 0)
            pixels.show()
        i = LEDS
        j = -1
        k = -1
        l = l + 1

    pixels[0] = (OFF)
    pixels.show()
    # sleep for a short while to allow the animation to end
    # and also to prevent conflicts with following LED code
    time.sleep(0.5)

def show_playlist(mpdclient, roman_led = []):
    """
    creates a visual representation of the playlist on the PIXEL strip

    :param mdpclient: musicpd object connected to MPD
    :param roman_led: list of led values, cached for ressource reasons
    """

    print("in show_playlist()")
    # clear leds
    pixels.fill(OFF)
    pixels.show()

    if not roman_led:
        # get actual (not total) length of playlist from MPD
        status = mpdclient.status()
        #print(status)
        # only non-empty playlists have status["song"]
        if "song" in status:
            yet_to_play = int(status["playlistlength"]) - int(status["song"])
        else:
            yet_to_play = int(status["playlistlength"])
        # can only display this many numbers with 8 leds
        #print("into roman: " + str(yet_to_play))
        if yet_to_play > 48:
            yet_to_play = 48
        if yet_to_play > 0:
            roman_led = into_roman_led(yet_to_play)

    if roman_led:
        # display
        i = 0
        for j in roman_led:
            pixels[i] = j
            i = i + 1
        pixels.show()
        # save led state
        pstate["led"] = roman_led

def into_roman_led(number):
    """
    converts integer to roman numerals represented by colored leds
    color code is modified zelda rubee color-value standard
    yes, that's a thing

    :param number: integer value
    :return: list of list of color values in GRBW like (255, 0, 0)
    """

    # non-subtraction notation, so 4 is IIII and not IV
    num = [1, 5, 10, 50, 100, 500, 1000]
    clr = [GREEN, BLUE, RED, PURPLE, CYAN, YELLOW, CYAN]
    i = 6

    roman_number = ""
    roman_led = []
    while number:
        div = number // num[i]
        number %= num[i]

        while div:
            roman_led.append(clr[i])
            div -= 1
        i -= 1
    return roman_led

def setup():
    """
    reads configuration file
    displays initial playlist
    """

    print("in setup()")
    read_config()
    set_party(client, pstate["party_mode"])
    set_volume(client, pstate["volume"])
    restore_state(client)
    # so the playlist is displayed
    trigger_idler()
    #with connection(client):
        #try:
            ## this is a hack to trigger idler()
            #client.crossfade(0)
        #except musicpd.CommandError as e:
            #print("error in setup(): " + str(e))

def idler(in_q):
    """
    updates the playlist or song duration timer via callback
    by maintaining an idle connection to MPD
    is running in a thread
    """

    print("starting idler() thread")
    client2 = musicpd.MPDClient()
    while True:
        try:
            qdata = in_q.get(False)
        except queue.Empty:
            qdata = None
        if qdata is _shutdown:
            print("_shutdown in idler()")
            in_q.put(_shutdown)
            break
        with connection(client2):
            try:
                #this_happened = client2.idle("options", "player", "playlist")
                this_happened = client2.idle("options", "player")
                print("idle() said: " + str(this_happened))
                status = client2.status()
                print(status)
                # status() is rather empty before the first song is played
                # when toggle_clr_plist is off, so we have to repeat status()
                if not "duration" in status:
                    print("status incomplete")
                    time.sleep(0.5)
                    status = client2.status()
                else:
                    print("status ok")

                if "duration" in status and float(status["duration"]) > LONG_SONG:
                    show_duration(status)
                else:
                    print("vor show_playlist() in idler()")
                    show_playlist(client2)
            except musicpd.CommandError as e:
                print("error in idler(): " + str(e))

        time.sleep(1)

def hello_and_goodbye(say = "hello"):
    """
    plays animations on the PIXEL strip for startup and shutdown

    :param say: string "hello" for startup, anything else for shutdown
    """

    pixels.fill(OFF)
    pixels.show()
    if say == "hello":
        i, j, k, led = 3, -1, -1, GREEN
    else:
        pixels.fill(GREEN)
        i, j, k, led = -1, 4, 1, OFF
    pixels.show()

    rightmost = 7
    for x in range(i, j, k):
        pixels[x] = led
        pixels[rightmost-x] = led
        pixels.show()
        time.sleep(0.6)

    time.sleep(0.3)
    pixels.fill(OFF)
    pixels.show()

def timer():
    print("starting timer() thread")
    while True:
        schedule.run_pending()
        time.sleep(1)

def shutdown(signum = None, frame = None):
    """
    handles program shutdown for /sbin/halt (systemctl nowadays)
    invoked by shutdown_in_XX and button (through shutdown.sh)
    writes configuration to disk
    kill threads
    plays shutdown animation

    """
    print("bye!")
    save_state(client)
    pause(client)
    write_config()
    # so LEDs keep off
    q.put(_shutdown)
    trigger_idler()
    time.sleep(1)
    hello_and_goodbye("bye")
    os.system("/usr/sbin/shutdown --poweroff now")
    #sys.exit(1)

def check_forward_button(in_q):
    """
    handles timed presses for the forward button
    the time frame for connected presses is 1 s
    a single press moves the playlist one song forward
    a double press moves the song 30 s forward
    holding the button for longer than 1 s moves to the next artist

    """

    print("starting check_forward_button() thread")
    button = Button(FBUTTON, hold_time=1)
    while True:
        try:
            qdata = in_q.get(False)
        except queue.Empty:
            qdata = None
        if qdata is _shutdown:
            print("_shutdown in check_forward_button()")
            in_q.put(_shutdown)
            break
        if button.is_held:
            print("forward held")
            if run["fheld"] == 0:
                run["fheld"] = time.time()
            run["fbutton"] = 3
        elif button.is_pressed:
            print("forward pressed")
            run["fpressed"] = time.time()
            # wurde button gedrueckt vor > 1 s
            if run["fpressed"] - run["fpressed2"] > 1.0:
                print("forward reset")
                run["fpressed2"] = 0
                # fbutton = 1
                run["fbutton"] = 1
            # vor weniger als 1 s und button < 2?
            # fbutton += 1
            elif run["fbutton"] < 2:
                print("forward again")
                run["fbutton"] += 1
            # reset fheld2
            if run["fpressed"] - run["fheld2"] > 2.0:
                print("fheld2 reset")
                run["fheld2"] = 0
        else:
            if run["fpressed2"] == 0:
                print("copy forward time")
                run["fpressed2"] = run["fpressed"]
            if run["fheld2"] == 0:
                print("fheld2 zugewiesen")
                run["fheld2"] = run["fpressed"]

            # button gehalten
            if run["fbutton"] == 3:
                # einmal gehalten
                if run["fheld"] - run["fheld2"] < 1.0:
                    next_album(client)
                # gehalten mit einem druck davor
                else:
                    print("sonst was")
                run["fheld"] = 0
                run["fbutton"] = 0
            # button vor weniger als 2 s gedrueckt?
            # fbutton = 2? dann "30 s vor"
            elif run["fpressed"] - run["fpressed2"] <= 1.0 and \
            run["fbutton"] == 2:
                seekcur_song(client, "+30")
                run["fbutton"] = 0
            # fbutton = 1? dann "song vor"
            elif time.time() - run["fpressed"] > 1.0 and \
            run["fbutton"] == 1:
                next_song(client)
                run["fbutton"] = 0

        time.sleep(0.1)

def signal_handler(signum = None, frame = None):
    """
    handles program shutdown
    invoked mostly by sigint
    writes configuration to disk
    kills threads
    turns off LEDs

    :param signum: signal
    :param frame: stack frame

    """
    print('Signal handler called with signal', signum)
    write_config()
    if "dthread" in run:
        run["dthread"].raise_exception()
        print("in handler(): bye thread!")
    else:
        print("in handler(): no thread stopped")
    q.put(_shutdown)
    trigger_idler()
    time.sleep(1)
    pixels.fill(OFF)
    pixels.show()
    print('Wait done')
    sys.exit(0)

def show_duration(status):
    """
    controls the LED visualisation of the song duration
    by starting and stopping the thread that's doing
    the actual work

    """
    print("in show_duration()")
    if status["state"] == "pause" or status["state"] == "stop":
        print("pause or stop")
        if "dthread" in run:
            run["dthread"].raise_exception()
            # commented out because of the blocking nature of join()
            #run["dthread"].join()
            print("bye thread!")
        else:
            print("no thread stopped")
    else:
        print(status["state"])
        run["dthread"] = thread_with_exception('Thread 1', status, q)
        run["dthread"].start()
        print("led_duration thread started")

def trigger_idler():
    """
    sometimes the playlist/duration timer managed by idler()
    needs to be updated actively
    """

    print("in trigger_idler()")
    reconnect = False
    try:
        client.ping()
    except musicpd.ConnectionError as e:
        print(e)
        reconnect = True

    # this is ugly
    if reconnect:
        print("reconnect")
        with connection(client):
            try:
                client.crossfade(0)
            except musicpd.CommandError as e:
                print("error in trigger_idler(): " + str(e))
    else:
        print("still connected")
        client.crossfade(0)

def rotary_switch_callback():
    """
    handles presses of the volume dial

    """
    toggle_pause(client)

def init_rotary():
    """
    attaches callback methods for
    turning the volume dial left and right
    and pressing it

    """
    rotary.setup(scale_min=0, scale_max=100, step=1,
                    # left is right
                    # right is left
                    # war is peace
                    # freedom is slavery
                    # ignorance is strength
                    inc_callback=rotary_dec_callback,
                    dec_callback=rotary_inc_callback,
                    sw_callback=rotary_switch_callback, polling_interval=500,
                    sw_debounce_time=300)
    rotary.watch()

def toggle_pause(mpdclient):
    """
    toggles play/pause but also starts playback
    if state is stop

    :param mpdclient: MPDClient()

    """
    with connection(mpdclient):
        try:
            status = mpdclient.status()
            state = status["state"]
            if state == "play":
                mpdclient.pause()
            elif state == "pause" or state == "stop":
                mpdclient.play()
            else:
                print("unsure in toggle_pause()")
        except musicpd.CommandError as e:
            print("error in toggle_pause(): " + str(e))

def toggle_party(mpdclient):
    """
    toggles party mode which is consume() in MPD

    :param mpdclient: MPDClient()

    """
    with connection(mpdclient):
        try:
            # call kitt() here because consume() will trigger
            # the update of playlist/duration in idler()
            kitt()
            if pstate["party_mode"] == True:
                pstate["party_mode"] = False
                mpdclient.consume(0)
                print("party mode off")
            else:
                pstate["party_mode"] = True
                mpdclient.consume(1)
                print("party mode on")

        except musicpd.CommandError as e:
            print("error in toggle_party(): " + str(e))

def read_config():
    """
    reads the configuration from disk
    sets the running options accordingly

    """
    print("in read_config()")
    pconfig.read(CFILE)
    try:
        pstate["clr_plist"] = pconfig.getboolean("main", "clr_plist")
        pstate["party_mode"] = pconfig.getboolean("main", "party_mode")
        pstate["volume"] = pconfig.getint("main", "volume")
        pstate["max_volume"] = pconfig.getint("main", "max_volume")
        pstate["ps_state"] = pconfig["main"]["ps_state"]
        print(pstate)
    except configparser.Error as e:
        print("Error in " + CFILE)

def write_config():
    """
    writes the configuration to disk

    """
    print("in write_config()")
    pconfig["main"] = {
            "clr_plist": pstate["clr_plist"],
            "party_mode": pstate["party_mode"],
            "volume": pstate["volume"],
            "max_volume": pstate["max_volume"],
            "ps_state": pstate["ps_state"]
    }
    with open(CFILE, "w") as configfile:
        pconfig.write(configfile)

def set_volume(mpdclient, volume):
    """
    does what it says

    :param mpdclient: MPDClient()
    :param volume: 0 < int value <= 100

    """
    if volume < 0 or volume > 100:
        raise ValueError("0 <= volume <= 100 expected")

    with connection(mpdclient):
        try:
            mpdclient.setvol(volume)
        except musicpd.CommandError as e:
            print("error in set_volume(): " + str(e))

def set_party(mpdclient, switch):
    """
    sets party mode, which is consume in MPD.

    :param mpdclient: MPDClient()
    :param switch: boolean on/off
    """

    print("in set_party()")
    if switch == True:
        switch = 1
    elif switch == False:
        switch = 0
    else:
        raise ValueError("boolean value expected")

    with connection(mpdclient):
        try:
            mpdclient.consume(switch)
        except musicpd.CommandError as e:
            print("error in set_party(): " + str(e))

def rotary_inc_callback(scale_position):
    vol = pstate["volume"]
    if vol >= pstate["max_volume"]:
        pstate["volume"] = pstate["max_volume"]
        return
    vol += 1
    run["smv_pre_vol"] = True
    try:
        set_volume(client, vol)
        pstate["volume"] = vol
    except Exception as e:
        print(e)
        kitt(RED)
        show_playlist(client, pstate["led"])

def rotary_dec_callback(scale_position):
    vol = pstate["volume"]
    if vol <= 0:
        pstate["volume"] = 0
        return
    vol -= 1
    run["smv_pre_vol"] = True
    try:
        set_volume(client, vol)
        pstate["volume"] = vol
    except Exception as e:
        print(e)
        kitt(RED)
        show_playlist(client, pstate["led"])

def next_song(mpdclient):
    """
    moves forward to the next song in the playlist
    also cycles from last to first song
    keeps state play/stop/pause

    :param mpdclient: MPDClient()

    """

    with connection(mpdclient):
        try:
            status = mpdclient.status()
            if status["state"] != "play":
                if "nextsong" in status:
                    mpdclient.seek(int(status["nextsong"]), 0)
                elif "playlistlength" in status and "song" in status \
                and int(status["playlistlength"]) - int(status["song"]) == 1:
                    mpdclient.seek(0, 0)
            else:
                mpdclient.next()
                if "playlistlength" in status and "song" in status \
                and int(status["playlistlength"]) - int(status["song"]) == 1:
                    mpdclient.play()
        except musicpd.CommandError as e:
            print("error in next_song(): " + str(e))

def previous_song(mpdclient):
    """
    moves backward to the previous song in the playlist
    also cycles from first to last song
    keeps state play/stop/pause

    :param mpdclient: MPDClient()

    """

    with connection(mpdclient):
        try:
            status = mpdclient.status()
            if status["state"] != "play":
                if "playlistlength" in status and "song" in status:
                    if int(status["song"]) > 0:
                        mpdclient.seek(int(status["song"]) - 1, 0)
                    else:
                        mpdclient.seek(int(status["playlistlength"]) - 1, 0)
            else:
                if "playlistlength" in status and "song" in status \
                and int(status["song"]) == 0:
                    mpdclient.seek(int(status["playlistlength"]) - 1, 0)
                else:
                    mpdclient.previous()
        except musicpd.CommandError as e:
            print("error in previous_song(): " + str(e))

def seekcur_song(mpdclient, delta):
    print("in seekcur_song()")
    with connection(mpdclient):
        try:
            print(delta)
            mpdclient.seekcur(delta)
        except musicpd.CommandError as e:
            print("error in seekcur_song(): " + str(e))

def next_album(mpdclient):
    print("in next_album()")
    with connection(mpdclient):
        try:
            status = mpdclient.status()
            plist = mpdclient.playlistinfo(str(status["song"]) + ":" +
                                           str(status["playlistlength"]))
            this_album = plist[0]["album"]
            for song in plist:
                if song["album"] == this_album:
                    continue
                else:
                    mpdclient.seek(song["pos"], 0)
                    break
        except musicpd.CommandError as e:
            print("error in next_album(): " + str(e))

def check_backward_button(in_q):
    """
    handles timed presses for the backward button
    the time frame for connected presses is 1 s
    a single press moves the playlist one song backward
    a double press moves the song 30 s backward
    holding the button for longer than 1 s moves to the previous artist

    """
    print("starting check_backward_button() thread")
    button = Button(BBUTTON, hold_time=1)
    while True:
        try:
            qdata = in_q.get(False)
        except queue.Empty:
            qdata = None
        if qdata is _shutdown:
            print("_shutdown in check_backward_button()")
            in_q.put(_shutdown)
            break
        if button.is_held:
            print("backward held")
            run["bbutton"] = 3
        elif button.is_pressed:
            print("backward pressed")
            run["bpressed"] = time.time()
            if run["bpressed"] - run["bpressed2"] > 1.0:
                print("backward reset")
                run["bpressed2"] = 0
                run["bbutton"] = 1
            elif run["bbutton"] < 2:
                print("backward again")
                run["bbutton"] += 1
        else:
            if run["bpressed2"] == 0:
                print("copy backward time")
                run["bpressed2"] = run["bpressed"]

            if run["bbutton"] == 3:
                previous_album(client)
                run["bbutton"] = 0
            elif run["bpressed"] - run["bpressed2"] <= 1.0 and \
                run["bbutton"] == 2:
                print("30 s zurueck")
                seekcur_song(client, "-30")
                run["bbutton"] = 0
            elif time.time() - run["bpressed"] > 1.0 and \
                run["bbutton"] == 1:
                previous_song(client)
                run["bbutton"] = 0

        time.sleep(0.1)

def previous_album(mpdclient):
    #print("in previous_album()")
    with connection(mpdclient):
        try:
            status = mpdclient.status()
            if "nextsong" in status:
                plist = mpdclient.playlistinfo("0" + ":" + str(status["nextsong"]))
            else:
                plist = mpdclient.playlistinfo("0" + ":" +
                                               str(status["playlistlength"]))
            plist.reverse()
            this_album = plist[0]["album"]
            for song in plist:
                if song["album"] == this_album:
                    continue
                else:
                    mpdclient.seek(song["pos"], 0)
                    break
        except musicpd.CommandError as e:
            print("error in next_album(): " + str(e))

def check_playlist_button(in_q):
    print("in check_playlist_button()")
    button = Button(PBUTTON, hold_time=1)
    while True:
        try:
            qdata = in_q.get(False)
        except queue.Empty:
            qdata = None
        if qdata is _shutdown:
            print("_shutdown in check_playlist_button()")
            in_q.put(_shutdown)
            break
        if button.is_held:
            print("playlist held")
            run["pbutton"] = 3
        elif button.is_pressed:
            print("playlist pressed")
            run["ppressed"] = time.time()
            # wurde button gedrueckt vor > 1 s
            if run["ppressed"] - run["ppressed2"] > 1.0:
                print("playlist reset")
                run["ppressed2"] = 0
                # pbutton = 1
                run["pbutton"] = 1
            # vor weniger als 1 s und button < 2?
            # fbutton += 1
            elif run["pbutton"] < 2:
                print("playlist again")
                run["pbutton"] += 1
        else:
            if run["ppressed2"] == 0:
                print("copy playlist time")
                run["ppressed2"] = run["ppressed"]

            if run["pbutton"] == 3:
                print("clear playlist")
                clear_playlist(client)
                run["pbutton"] = 0
            elif run["ppressed"] - run["ppressed2"] <= 1.0 and \
            run["pbutton"] == 2:
                print("remove album")
                remove_album(client)
                run["pbutton"] = 0
            elif time.time() - run["ppressed"] > 1.0 and \
            run["pbutton"] == 1:
                print("remove song")
                remove_song(client)
                run["pbutton"] = 0

        time.sleep(0.1)

def clear_playlist(mpdclient):
    print("in clear_playlist()")
    with connection(mpdclient):
        try:
            mpdclient.clear()
            #trigger_idler()
        except musicpd.CommandError as e:
            print("error in clear_playlist(): " + str(e))

def remove_album(mpdclient):
    print("in remove_album()")
    with connection(mpdclient):
        try:
            status = mpdclient.status()
            # XXX funktioniert das beim letzten song?
            plist = mpdclient.playlistinfo("0:" +
                                           str(status["playlistlength"]))
            if not "song" in status:
                return
            pos = int(status["song"])
            this_album = plist[pos]["album"]
            # remove previous song down to the first
            i = pos - 1
            while i >= 0:
                if plist[i]["album"] == this_album:
                    mpdclient.delete(i)
                    print("geloescht")
                i -= 1
            time.sleep(1)

            # the playlist will have changed by now
            # so we have to do this again
            status = mpdclient.status()
            #print(status)
            plist = mpdclient.playlistinfo(status["song"] + ":" +
                                           str(status["playlistlength"]))
            #print(plist)
            # remove last song down to the current
            this_list = []
            for song in plist:
                if song["album"] == this_album:
                    this_list.append(song["pos"])
            # reverse, so the playlist doesn't change
            this_list.reverse()
            for i in this_list:
                mpdclient.delete(i)
        except musicpd.CommandError as e:
            print("error in remove_album(): " + str(e))

def remove_song(mpdclient):
    print("in remove_song")
    with connection(mpdclient):
        try:
            status = mpdclient.status()
            if "song" in status:
                mpdclient.delete(status["song"])
        except musicpd.CommandError as e:
            print("error in remove_song(): " + str(e))

def pause(mpdclient):
    """
    pauses the playback

    :param mpdclient: MPDClient()

    """
    print("in pause()")
    with connection(mpdclient):
        try:
            status = mpdclient.status()
            state = status["state"]
            if state == "play":
                mpdclient.pause()
        except musicpd.CommandError as e:
            print("error in stop(): " + str(e))

def save_state(mpdclient):
    """
    saves the "play" playback state
    to the player state hash
    used to transport the state between restart

    """
    print("in save_state()")
    with connection(mpdclient):
        try:
            status = mpdclient.status()
            state = status["state"]
            if state == "play":
                pstate["ps_state"] = state
        except musicpd.CommandError as e:
            print("error in save_state(): " + str(e))

def restore_state(mpdclient):
    """
    restores the "play" backback state
    and starts playback accordingly
    used to transport the state between restart

    """
    print("in restore_state()")
    with connection(mpdclient):
        try:
            if pstate["ps_state"] == "play":
                mpdclient.play()
            pstate["ps_state"] = ""
        except musicpd.CommandError as e:
            print("error in restore_state(): " + str(e))

def main():
    # install signal handler
    signal.signal(signal.SIGUSR1, shutdown)
    for sig in [signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT]:
        signal.signal(sig, signal_handler)

    reader = SimpleMFRC522()
    hello_and_goodbye("hello")
    t3 = threading.Thread(target=check_forward_button, args=(q, ))
    t3.start()
    t5 = threading.Thread(target=check_backward_button, args=(q, ))
    t5.start()
    t6 = threading.Thread(target=check_playlist_button, args=(q, ))
    t6.start()
    t4 = threading.Thread(target=init_rotary)
    # t4 is daemonized so shutdown is easier
    # we don't need to control it anyway
    t4.daemon = True
    t4.start()
    # start MPD callback thread
    t = threading.Thread(target=idler, args=(q, ))
    t.start()
    setup()

    while True:
        try:
            id, text = reader.read()
            text = text.strip()
            #print(id)
            print("+" + text + "+")

            if text == "toggle_pause":
                toggle_pause(client)

            elif text == "toggle_clr_plist" and run["set_max_volume"] == False:
                if pstate["clr_plist"] == True:
                    pstate["clr_plist"] = False
                else:
                    pstate["clr_plist"] = True
                kitt()
                trigger_idler()

            elif text == "toggle_party_mode" and run["set_max_volume"] == False:
                toggle_party(client)

            elif re.match("^shutdown_in_(\d\d?)$", text) and \
            run["set_max_volume"] == False:
                m = re.match("^shutdown_in_(\d\d?)$", text)
                try:
                    minutes = int(m.group(1))
                    if minutes < 1:
                        raise Exception("wrong time format")
                except Exception as e:
                    print(e)
                    continue

                jobs = schedule.get_jobs()
                if jobs:
                    print(jobs)
                    schedule.clear()
                    print("shutdown cancelled")
                else:
                    now = time.localtime()
                    #print(time.strftime("%H:%M", now))
                    epoch = time.mktime(now)
                    then = epoch + minutes * 60
                    shutdown_at = time.strftime("%H:%M", time.localtime(then))
                    #print(shutdown_at)
                    schedule.every().day.at(shutdown_at).do(shutdown)
                    # start timer thread
                    t2 = threading.Thread(target=timer)
                    t2.start()

                kitt()
                trigger_idler()

            elif text == "set_max_volume":
                print("in set_max_volume")
                with connection(client):
                    try:
                        # start setting max volume
                        if run["set_max_volume"] == False:
                            print("set..")
                            # check playlist
                            # return error if empty
                            status = client.status()
                            state = status["state"]
                            if int(status["playlistlength"]) == 0:
                                kitt(RED)
                                show_playlist(client, pstate["led"])
                                continue
                            kitt()
                            # play otherwise
                            # but remember the previous state
                            if state != "play":
                                run["smv_pre_state"] = state
                                client.play()
                            else:
                                show_playlist(client, pstate["led"])
                            pstate["max_volume"] = MAX_VOLUME
                            run["set_max_volume"] = True
                            run["smv_pre_vol"] = False


                        # confirm setting
                        else:
                            print("confirm..")
                            # set max volume to new value
                            # only if it has been changed
                            # leave at MAX_VOLUME otherwise
                            if run["smv_pre_vol"]:
                                pstate["max_volume"] = pstate["volume"]
                            run["set_max_volume"] = False
                            kitt()
                            if run["smv_pre_state"] == "pause":
                                client.pause()
                            elif run["smv_pre_state"] == "stop":
                                client.stop()
                            else:
                                show_playlist(client, pstate["led"])
                            run["smv_pre_state"] = ""

                    except musicpd.CommandError as e:
                        print("error in set_max_volume: " + str(e))

            else:
                try:
                    addnplay(text)
                except Exception as e:
                    print(e)

        finally:
            pass

        time.sleep(1)

#with daemon.DaemonContext():
    #main()

main()
GPIO.cleanup()
