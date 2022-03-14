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
import json
from mfrc522 import SimpleMFRC522
import musicpd
import neopixel
import os
from pyky040 import pyky040
import queue
import re
import RPi.GPIO as GPIO
import schedule
import signal
import sys
import threading
import time
from vcgencmd import Vcgencmd

# starting volume (max 100)
VOLUME = 20
# songs longer than this (seconds) will have shown
# their duration instead of the playlist
# (disabled until the return of some coding enthusiasm
# because of the complexity of the show_duration() thread
# and it's integration into the button controls)
LONG_SONG = 6000
# brightness (1 = 100 %)
LED_BRIGHTNESS = 0.05
# percent of the songs duration
# for seeking within songs
# 0 < SEEK_DELTA < 0.99
SEEK_DELTA = 0.25
# turn off the player after idling for AUTO_OFF minutes
AUTO_OFF = 60

# you normally don't need to change
# options below here
MAX_VOLUME = 100
CFILE = "config.ini"
BFILE = "bookmark.json"
# seconds
BREPLAY = 15.0

# BCM pin assignment
FBUTTON = 27
BBUTTON = 5
PBUTTON = 22
ROTARY_CLOCK=4
ROTARY_DATA=17
ROTARY_SWITCH=2

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
_dthread_shutdown = object()
dt_lock = threading.Lock()
t_local = threading.local()
vcgm = Vcgencmd()

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
    "bheld": 0,
    "bheld2": 0,
    "bbutton": 0,
    "ppressed": time.time(),
    "ppressed2": 0,
    "pbutton": 0,
    "dthreads": [],
    "sleep_mode": False,
    "threads": { "cfb": { "target": "check_forward_button" },
                 "cbb": { "target": "check_backward_button" },
                 "cpb": { "target": "check_playlist_button" },
                 "ir": { "target": "init_rotary" }, # volume/play/pause
                 "mj": { "target": "monitor_jobs" },
                 "idler": { "target": "idler" }, # MPD callback
                 "crr": { "target": "check_rfid_reader" },
                 "mv": { "target": "monitor_voltage" },
               },
}

@contextmanager
def connection(mpdclient):
    """
    creates a context for a safe connection to MPD

    :param mpdclient: MPDClient()
    """

    reconnect = False
    try:
        try:
            mpdclient.ping()
        except musicpd.ConnectionError as e:
            #print("in connection(): " + str(e))
            mpdclient.connect()
            reconnect = True
            yield
        else:
            yield
    finally:
        if reconnect:
            mpdclient.close()
            mpdclient.disconnect()

def addnplay(tag):
    """
    looks up song or album in MPD, adds them to the playlist,
    plays them if the playlist has been empty.
    adheres to toggle_clr_plist.

    :param tag: string of song, album title, case sensitive
                format: /^(s|a):[\w\s]+/
    """

    with connection(client):
        try:
            m = re.match("^(t|a):(.+)", tag)
            if not m:
                raise ValueError("wrong card format")

            tag, value = m.group(1), m.group(2)
            if tag == "t":
                hit = client.find("title", value)
            elif tag == "a":
                hit = client.find("album", value)

            if not hit:
                raise Exception("file not found")

            if pstate["clr_plist"] == True:
                client.clear()

            for i in hit:
                client.add(i["file"])

            if pstate["clr_plist"] == True:
                client.play()
            else:
                # wenn die pl vorher leer war,
                # dann spielen?
                # TESTEN, sonst wie in load_playlist()
                plist = client.playlistinfo()
                if len(plist) == len(hit):
                    client.play(0)
                else:
                    kitt()
                    trigger_idler()

        except ValueError as e:
            print(e)
            kitt(BLUE)
            if not run["sleep_mode"]:
                show_playlist(client)
        except Exception as e:
            print(e)
            kitt(RED)
            if not run["sleep_mode"]:
                show_playlist(client)
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
    reads the configuration file
    set options read from the file
    displays the initial playlist
    """

    print("in setup()")
    read_config()
    set_party(client, pstate["party_mode"])
    set_volume(client, pstate["volume"])
    restore_state(client)
    # so the playlist is displayed
    trigger_idler()

def idler(in_q):
    """
    updates the playlist or song duration timer via callback
    by maintaining an idle connection to MPD
    is running in a thread

    :param in_q: Queue()

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
        elif qdata is _dthread_shutdown:
            #print("_dts -> q in idler()")
            in_q.put(_dthread_shutdown)
        with connection(client2):
            try:
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

                if not run["sleep_mode"]:
                    if "duration" in status and float(status["duration"]) > LONG_SONG:
                        show_duration(status)
                    else:
                        print("vor show_playlist() in idler()")
                        show_playlist(client2)

                # handling auto-off
                jobs = schedule.get_jobs("auto_off")
                if status["state"] == "play":
                    remove_auto_shutdown_jobs()
                elif not jobs:
                    add_auto_shutdown_job()

            except musicpd.CommandError as e:
                print("error in idler(): " + str(e))

        # this actually looks like Ruby
        dt_lock.acquire()
        run["dthreads"][:] = [d for d in run["dthreads"] if d["thread"].is_alive()]
        for d in run["dthreads"]:
            print(d)
        dt_lock.release()

        time.sleep(0.25)

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

def shutdown(signum = None, frame = None):
    """
    handles program shutdown for /sbin/halt (systemctl nowadays)
    invoked by shutdown_in_XX and button (through shutdown.sh)
    writes configuration to disk
    kill threads
    plays shutdown animation (most times it doesn't)

    """
    print("bye!")
    pixels.fill(OFF)
    pixels.show()
    save_state(client)
    pause(client)
    write_config()
    # shutdown all threads
    # so LEDs keep off
    q.put(_shutdown)
    trigger_idler()
    # the shutdown animation doesn't work consistently
    # when called by systemctl
    #time.sleep(1)
    #hello_and_goodbye("bye")
    # so we just try to turn the LEDs off
    # see above
    os.system("/usr/sbin/shutdown --poweroff now")
    #sys.exit(1)

def check_forward_button(in_q):
    """
    handles timed presses for the forward button
    the time frame for connected presses is 1 s
    a single press moves the playlist one song forward
    a double press moves the song 30 s forward
    holding the button for longer than 1 s moves to the next artist

    :param in_q: Queue()

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
        elif qdata is _dthread_shutdown:
            #print("_dts -> q in check_forward_button()")
            in_q.put(_dthread_shutdown)
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
                    recall_bookmark()
                run["fheld"] = 0
                run["fbutton"] = 0
            # button vor weniger als 2 s gedrueckt?
            # fbutton = 2? dann "30 s vor"
            elif run["fpressed"] - run["fpressed2"] <= 1.0 and \
            run["fbutton"] == 2:
                seekcur_song(client, SEEK_DELTA)
                run["fbutton"] = 0
            # fbutton = 1? dann "song vor"
            elif time.time() - run["fpressed"] > 1.0 and \
            run["fbutton"] == 1:
                kill_duration_thread()
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
    #if "dthread" in run:
        #run["dthread"].raise_exception()
        #print("in handler(): bye thread!")
    #else:
        #print("in handler(): no thread stopped")
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
    print(status["state"])
    if status["state"] == "pause" or status["state"] == "stop":
        kill_duration_thread()
    else:
        t = threading.Thread(name="ld", target=led_duration, args=(status, q, ))
        t.start()
        dt_lock.acquire()
        run["dthreads"].append({
            "thread": t,
            "killed": False
        })
        dt_lock.release()
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

def init_rotary(in_q):
    """
    attaches callback methods for
    turning the volume dial left and right
    and pressing it

    :param in_q: Queue(), unused

    """
    rotary.setup(scale_min=0, scale_max=100, step=1,
                    # left is right
                    # right is left
                    # war is peace
                    # freedom is slavery
                    # ignorance is strength
                    inc_callback=rotary_inc_callback,
                    dec_callback=rotary_dec_callback,
                    sw_callback=rotary_switch_callback, polling_interval=200,
                    sw_debounce_time=100)
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
    # XX auch auf int pruefen
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
        if not run["sleep_mode"]:
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
        if not run["sleep_mode"]:
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
                if is_long_song(status):
                    turn_off_leds()
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
                if is_long_song(status):
                    turn_off_leds()
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

    :param in_q: Queue()

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
        elif qdata is _dthread_shutdown:
            #print("_dts -> q in check_backward_button()")
            in_q.put(_dthread_shutdown)
        if button.is_held:
            print("backward held")
            if run["bheld"] == 0:
                run["bheld"] = time.time()
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
            # reset fheld2
            if run["bpressed"] - run["bheld2"] > 2.0:
                print("bheld2 reset")
                run["bheld2"] = 0
        else:
            if run["bpressed2"] == 0:
                print("copy backward time")
                run["bpressed2"] = run["bpressed"]
            if run["bheld2"] == 0:
                print("bheld2 zugewiesen")
                run["bheld2"] = run["bpressed"]

            if run["bbutton"] == 3:
                if run["bheld"] - run["bheld2"] < 1.0:
                    previous_album(client)
                else:
                    save_bookmark()
                run["bheld"] = 0
                run["bbutton"] = 0
            elif run["bpressed"] - run["bpressed2"] <= 1.0 and \
            run["bbutton"] == 2:
                seekcur_song(client, SEEK_DELTA * -1)
                run["bbutton"] = 0
            elif time.time() - run["bpressed"] > 1.0 and \
            run["bbutton"] == 1:
                kill_duration_thread()
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
    print("starting check_playlist_button() thread")
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
        elif qdata is _dthread_shutdown:
            #print("_dts -> q in check_playlist_button()")
            in_q.put(_dthread_shutdown)
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
            # XX funktioniert das beim letzten song?
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

def seekcur_song(mpdclient, delta):
    """
    dynamic seek
    jumps forward/backward by a fraction of the songs duration (duration/delta seconds)
    jumps to the next/previous song if the jump crosses the songs boundaries
    works also if the playback is paused/stopped

    :param mpdclient: MPDClient()
    :param delta: floating value != 0 and -0.99 < delta < 0.99

    """
    print("in seekcur_song()")
    with connection(mpdclient):
        try:
            #print(delta)
            if not isinstance(delta, float) or delta == 0 or delta < -0.99 or delta > 0.99:
                raise ValueError("(-0.9 > delta < 0.9) and delta != 0 expected")
            status = mpdclient.status()
            #print(status)
            if not "song" in status:
                return
            # calculate step
            duration = float(status["duration"])
            elapsed = float(status["elapsed"])
            step = duration * delta
            #print(step)
            # when seek would be crossing song boundaries
            # jump backwards to the beginning of the current song
            if elapsed + step <= 0:
                mpdclient.seek(int(status["song"]), 0)
            # jump to the beginning of the next song
            elif elapsed + step >= duration:
                next_song(mpdclient)
            # if not
            # seek within song
            else:
                mpdclient.seek(int(status["song"]), elapsed + step)

        except musicpd.CommandError as e:
            print("error in seekcur_song(): " + str(e))

def led_duration(status, in_q):
    print(">> in led_duration()")
    t_local.pixels = neopixel.NeoPixel(board.D12, LEDS + 2, brightness=LED_BRIGHTNESS,
        auto_write=False, pixel_order=LED_ORDER)
    t_local.duration = float(status["duration"])
    t_local.elapsed = float(status["elapsed"])

    t_local.led_factor = t_local.duration / LEDS
    print(">> factor " + str(t_local.led_factor))
    t_local.led_elapsed, t_local.led_remainder, t_local.loop_start = 0, 0, 0
    t_local.pixels.fill(OFF)
    t_local.pixels.show()

    if t_local.elapsed > 1:
        #print(">> vorherige wiederherstellen")
        t_local.led_elapsed = int(t_local.elapsed // t_local.led_factor)
        #print(">> led_elapsed: " + str(led_elapsed))
        if t_local.led_elapsed > 0:
            #print(">> ..ganze")
            for i in range(t_local.led_elapsed):
                t_local.pixels[i] = YELLOW
            print(">> 1")
            t_local.pixels.show()
            t_local.loop_start = t_local.led_elapsed
        #else:
            #print(">> nix ganzes")

        #print(">> rest wiederherstellen")
        t_local.led_remainder = t_local.led_factor - (t_local.elapsed % \
                                                      t_local.led_factor)
        #print(">> led_remainder: " + str(led_remainder))
        if t_local.led_remainder > 1:
            #print(">> ..bis naechste led " + str(led_remainder))
            time.sleep(t_local.led_remainder)
            t_local.pixels[t_local.led_elapsed] = YELLOW
            try:
                t_local.qdata = in_q.get(False)
                print("was in der queue 1")
            except queue.Empty:
                t_local.qdata = None
            if t_local.qdata is _shutdown:
                print(">>> _shutdown 2 in led_duration()")
                in_q.put(_shutdown)
                return
            elif t_local.qdata is _dthread_shutdown:
                print(">>> _dthread_shutdown 1 in led_duration()")
                return
            print(">> 2")
            t_local.pixels.show()
            t_local.loop_start = t_local.loop_start + 1
        #else:
            #print(">> nix rest")

    for i in range(t_local.loop_start, LEDS):
        print(">> vor schleifenschlafen")
        time.sleep(t_local.led_factor - 0.3)
        t_local.pixels[i] = YELLOW
        try:
            t_local.qdata = in_q.get(False)
            print("was in der queue 2")
        except queue.Empty:
            t_local.qdata = None
        if t_local.qdata is _shutdown:
            print(">>> _shutdown 2 in led_duration()")
            in_q.put(_shutdown)
            return
        elif t_local.qdata is _dthread_shutdown:
            print(">>> _dthread_shutdown 2 in led_duration()")
            return
        print(">> 3")
        t_local.pixels.show()
        #print(">> pixel " + str(i) + " gezeigt")

def kill_duration_thread():
    """
    could check for status["state"] to do this smarter,
    but maintaining connections to MPD here or
    in the caller seems clostly

    """
    print("in kill_duration_thread()")
    dt_lock.acquire()
    for d in run["dthreads"]:
        if d["thread"].is_alive() and d["killed"] == False:
            print("bye thread:")
            print(d["thread"].getName())
            q.put(_dthread_shutdown)
            d["killed"] = True
    dt_lock.release()

def is_long_song(status):
    print("in is_long_song()")
    if "duration" in status and float(status["duration"]) > LONG_SONG:
        return True
    else:
        return False

def turn_off_leds():
    print("in turn_off_leds()")
    pixels.fill(OFF)
    pixels.show()

def load_playlist(tag):
    print("in load_playlist()")

    with connection(client):
        try:
            m = re.match("^(p):(.+)", tag)
            if not m:
                raise ValueError("wrong card format")

            plist_then = client.playlistinfo()

            tag, value = m.group(1), m.group(2)
            if tag == "p":
                client.load(value)

            if pstate["clr_plist"] == True:
                client.clear()
                # this is ugly, but we have to load it twice
                # to check for errors above before clearing the playlist
                client.load(value)

            if pstate["clr_plist"] == True or len(plist_then) == 0:
                client.play()
            else:
                kitt()
                trigger_idler()

        except ValueError as e:
            print(e)
            kitt(BLUE)
            if not run["sleep_mode"]:
                show_playlist(client)
        except Exception as e:
            print(e)
            kitt(RED)
            if not run["sleep_mode"]:
                show_playlist(client)
        except musicpd.CommandError as e:
            print("error in addnplay(): " + str(e))

def save_bookmark():
    """
    creates a bookmark of the current song
    and saves it to the bookmark file

    """
    print("in save_bookmark()")
    with connection(client):
        try:
            status = client.status()
            current_song = client.currentsong()
            bookmark = {
                "title": current_song["title"],
                "album": current_song["album"],
                "elapsed": status["elapsed"],
            }
            with open(BFILE, "w") as outfile:
                json.dump(bookmark, outfile)
        except musicpd.CommandError as e:
            print("error in save_bookmark(): " + str(e))

def recall_bookmark():
    """
    loads the bookmark from the bookmark file
    plays the bookmarked song with a replay time
    or from the beginning
    looks for the song in the playlist first
    loads the album otherwise

    """
    print("in recall_bookmark()")
    with connection(client):
        try:
            with open(BFILE, "r") as openfile:
                bookmark = json.load(openfile)
            plist = client.playlistinfo()
            found_song = None
            # look for the song in the playlist
            for song in plist:
                if song["title"] == bookmark["title"]:
                    found_song = song
                    break
            # load the album otherwise
            if not found_song:
                load_album = client.find("album", bookmark["album"])
                if not load_album:
                    raise FileNotFoundError("album not found")
                if pstate["clr_plist"] == True:
                    client.clear()
                for i in load_album:
                    client.add(i["file"])
                plist = client.playlistinfo()
                # this is ugly because
                # history repeats itself
                for song in plist:
                    if song["title"] == bookmark["title"]:
                        found_song = song
                        break

            # allow replay if possible or play from the beginning
            if float(bookmark["elapsed"]) > BREPLAY \
            and float(bookmark["elapsed"]) <= float(found_song["duration"]):
                client.seek(int(found_song["pos"]), \
                float(bookmark["elapsed"]) - BREPLAY)
            else:
                client.play(int(found_song["pos"]))

        except FileNotFoundError as e:
            print(e)
            kitt(RED)
            if not run["sleep_mode"]:
                show_playlist(client, pstate["led"])
        except musicpd.CommandError as e:
            print("error in recall_bookmark(): " + str(e))

def monitor_jobs(in_q):
    """
    threaded job scheduler

    :param in_q: Queue()

    """
    print("starting monitor_jobs() thread")
    while True:
        try:
            qdata = in_q.get(False)
        except queue.Empty:
            qdata = None
        if qdata is _shutdown:
            print("_shutdown in monitor_jobs()")
            in_q.put(_shutdown)
            break
        elif qdata is _dthread_shutdown:
            print("_dts -> q in monitor_jobs()")
            in_q.put(_dthread_shutdown)
        schedule.run_pending()
        time.sleep(1)

def add_auto_shutdown_job():
    """
    adds the auto shutdown job to the scheduler

    """
    #print("in add_auto_shutdown_job()")
    now = time.localtime()
    #print(time.strftime("%H:%M", now))
    epoch = time.mktime(now)
    then = epoch + AUTO_OFF * 60
    shutdown_at = time.strftime("%H:%M", time.localtime(then))
    print("auto_off: " + str(shutdown_at))
    schedule.every().day.at(shutdown_at).do(shutdown).tag("auto_off")

def remove_auto_shutdown_jobs():
    """
    clears the job scheduler off auto shutdown jobs

    """
    jobs = schedule.get_jobs("auto_off")
    if jobs:
        #print(jobs)
        schedule.clear("auto_off")
        #print("auto shutdown cancelled")

def start_threads(start = "all"):
    """
    starts all or specific threads that are defined in run["threads"]

    :param start: "all" or the token of the thread name, string

    """
    print("in start_threads()")
    if not (start == "all" or start in run["threads"]):
        raise ValueError("valid dict key expected")
    if start == "all":
        for k in run["threads"]:
            #print(k)
            #print(run["threads"][k])
            t = threading.Thread(name=k,
                                 target=globals()[run["threads"][k]["target"]],
                                 args=(q, ))
            if k == "ir":
                #print("daemon thread: " + k)
                t.daemon = True
            t.start()
            run["threads"][k]["thread"] = t
    else:
        t = threading.Thread(name=start,
                             target=globals()[run["threads"][start]["target"]],
                             args=(q, ))
        if start == "ir":
            #print("daemon thread: " + start)
            t.daemon = True
        t.start()
        run["threads"][start]["thread"] = t

def monitor_threads():
    """
    monitors the execution of the threads defined in run["threads"]
    restarts them if they're not running

    """
    #print("in monitor_threads()")
    for t in run["threads"]:
        if not run["threads"][t]["thread"].is_alive():
            print("starting ", t, " again")
            start_threads(t)

def check_rfid_reader(in_q):
    print("starting check_rfid_reader() thread")
    reader = SimpleMFRC522()
    while True:
        try:
            qdata = in_q.get(False)
        except queue.Empty:
            qdata = None
        if qdata is _shutdown:
            print("_shutdown in check_rfid_reader()")
            in_q.put(_shutdown)
            break
        elif qdata is _dthread_shutdown:
            #print("_dts -> q in check_rfid_reader()")
            in_q.put(_dthread_shutdown)
        try:
            id, text = reader.read_no_block()
            if not text:
                continue
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
                with connection(client):
                    try:
                        m = re.match("^shutdown_in_(\d\d?)$", text)
                        try:
                            minutes = int(m.group(1))
                            if minutes < 1:
                                raise ValueError("wrong card format: 1 <= minutes <= 99 expected")
                        except ValueError as e:
                            print(e)
                            kitt(BLUE)
                            if not run["sleep_mode"]:
                                show_playlist(client)
                            continue

                        jobs = schedule.get_jobs("slumber_off")
                        if jobs:
                            print(jobs)
                            schedule.clear("slumber_off")
                            run["sleep_mode"] = False
                            print("shutdown cancelled")
                        else:
                            now = time.localtime()
                            #print(time.strftime("%H:%M", now))
                            epoch = time.mktime(now)
                            then = epoch + minutes * 60
                            shutdown_at = time.strftime("%H:%M", time.localtime(then))
                            #print(shutdown_at)
                            schedule.every().day.at(shutdown_at).do(shutdown).tag("slumber_off")
                            run["sleep_mode"] = True

                        kitt()
                        trigger_idler()
                    except musicpd.CommandError as e:
                        print("error in shutdown_in_XX: " + str(e))

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
                                if not run["sleep_mode"]:
                                    show_playlist(client, pstate["led"])
                                continue
                            kitt()
                            # play otherwise
                            # but remember the previous state
                            if state != "play":
                                run["smv_pre_state"] = state
                                client.play()
                            else:
                                if not run["sleep_mode"]:
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
                                if not run["sleep_mode"]:
                                    show_playlist(client, pstate["led"])
                            run["smv_pre_state"] = ""

                    except musicpd.CommandError as e:
                        print("error in set_max_volume: " + str(e))

            elif text == "_debug":
                print("in _debug")
                jobs = schedule.get_jobs()
                print("jobs:")
                print(jobs)
                print("dthreads:")
                for d in run["dthreads"]:
                    print(d)
                print("threads:")
                for t in run["threads"]:
                    print(t, "->", run["threads"][t])

            elif re.match("^(t|a):(.+)", text):
                addnplay(text)

            elif re.match("^p:(.+)", text):
                load_playlist(text)

            else:
                print("unknown card error")
                kitt(BLUE)
                with connection(client):
                    if not run["sleep_mode"]:
                        try:
                            show_playlist(client)
                        except musicpd.CommandError as e:
                            print("error in unknown card error: " + str(e))

        finally:
            time.sleep(0.5)
            pass

def monitor_voltage(in_q):
    print("starting monitor_voltage() thread")
    while True:
        try:
            qdata = in_q.get(False)
        except queue.Empty:
            qdata = None
        if qdata is _shutdown:
            print("_shutdown in monitor_voltage()")
            in_q.put(_shutdown)
            break
        elif qdata is _dthread_shutdown:
            #print("_dts -> q in monitor_voltage()")
            in_q.put(_dthread_shutdown)
        get_throttled = vcgm.get_throttled()
        if str(get_throttled["raw_data"]) != "0x0":
            print("vcgm:", get_throttled["raw_data"])
        time.sleep(30)

def main():
    # install signal handler
    signal.signal(signal.SIGUSR1, shutdown)
    for sig in [signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT]:
        signal.signal(sig, signal_handler)

    hello_and_goodbye("hello")
    start_threads()
    setup()
    while True:
        time.sleep(1)
        monitor_threads()

#with daemon.DaemonContext():
    #main()

main()
GPIO.cleanup()
