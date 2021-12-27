#!/usr/bin/env python3
# coding: utf-8

import board
from contextlib import contextmanager
import ctypes
#import daemon
from gpiozero import Button
from mfrc522 import SimpleMFRC522
import musicpd
import neopixel
import os
import re
import RPi.GPIO as GPIO
import schedule
import threading
import time
import sys, signal

ORDER = neopixel.GRBW
pixels = neopixel.NeoPixel(board.D12, 10, brightness=0.1, auto_write=False, pixel_order=ORDER)

RED = (255, 0, 0)
YELLOW = (255, 150, 0)
GREEN = (0, 255, 0)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
PURPLE = (180, 0, 255)
OFF = (0, 0, 0)

client = musicpd.MPDClient()
config = {
        # clear playlist before new song is added
        # or append otherwise
        "clr_plist": True,
        # party mode is consume()
        "party_mode": False,
}
player_status = {
        "led": [],
}
run = {}

class thread_with_exception(threading.Thread):
    def __init__(self, name, duration):
        threading.Thread.__init__(self)
        self.name = name
        self.duration = duration

    def run(self):

        # target function of the thread class
        try:
            #while True:
            print('running ' + self.name)
            print("im duration thread")
            print(self.duration)
            pixels.fill(OFF)
            pixels.show()
            for i in range(8):
                time.sleep(self.duration)
                pixels[i] = YELLOW
                pixels.show()
                print("pixel " + str(i) + " gezeigt")
            #time.sleep(0.5)
        finally:
            print('ended')

    def get_id(self):

        # returns id of the respective thread
        if hasattr(self, '_thread_id'):
            return self._thread_id
        for id, thread in threading._active.items():
            if thread is self:
                return id

    def raise_exception(self):
        thread_id = self.get_id()
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id,
              ctypes.py_object(SystemExit))
        if res > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
            print('Exception raise failure')

@contextmanager
def connection(mpdclient):
    """
    connection creates an context for a safe connection to mpd

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
    addnplay() looks up song or album, adds them to the playlist,
    plays them if playlist has been empty.
    adheres to toggle_clr_plist.

    :param tag: string of song or album title, case sensitive
    """

    with connection(client):
        try:
            hit = client.find("title", tag)
            if not hit:
                hit = client.find("album", tag)
            if not hit:
                raise Exception("file not found")

            if config["clr_plist"] == True:
                client.clear()

            for i in hit:
                client.add(i["file"])

            if config["clr_plist"] == True:
                client.play()
            else:
                plist = client.playlistinfo()
                if len(plist) == len(hit):
                    client.play(0)
                else:
                    kitt()

            show_playlist(client)

        except Exception as e:
            print(e)
            kitt(RED)
            show_playlist(client, player_status["led"])
        except mpd.CommandError:
            print("fehler in addnplay()")

def kitt(color = GREEN):
    """
    kitt creates a LED effect after the car K.I.T.T
    of the 80ies TV show Knight Rider

    :param color: list of GRBW values like (255, 0, 0), default GREEN

    """

    pixels.fill((0 ,0 ,0))
    pixels.show()

    i, j, k, l = 0, 8, 1, 0
    while l < 2:
        for x in range(i, j, k):
            pixels[x] = color
            pixels.show()
            time.sleep(0.03)
            if l == 0 and x > 0:
                pixels[x-1] = (0, 0, 0)
            elif l > 0 and x < 8:
                pixels[x+1] = (0, 0, 0)
            pixels.show()
        i = 8
        j = -1
        k = -1
        l = l + 1

    pixels[0] = (0, 0, 0)
    pixels.show()

def show_playlist(mpdclient, roman_led = []):
    # clear leds
    pixels.fill((0 ,0 ,0))
    pixels.show()

    if not roman_led:
        # get actual (not total) length of playlist from mpd
        status = mpdclient.status()
        # only non-empty playlists have status["song"]
        if "song" in status:
            yet_to_play = int(status["playlistlength"]) - int(status["song"])
        else:
            yet_to_play = int(status["playlistlength"])
        # can only display this many numbers with 8 leds
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
        player_status["led"] = roman_led

def into_roman_led(number):
    """
    into_roman_led converts integer to roman numbers represented by colored leds
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
    with connection(client):
        try:
            print("setup")
            show_playlist(client)
        except mpd.CommandError:
            print("fehler bei setup()")

def idler():
    print("starting idler() thread")
    client2 = musicpd.MPDClient()
    while True:
        with connection(client2):
            try:
                this_happened = client2.idle("player","playlist")
                print(this_happened)
                status = client2.status()
                print(status)
                # status() is rather empty before first song
                # when toggle_clr_plist is off
                if not "duration" in status:
                    print("status incomplete")
                    client2.pause()
                    client2.play()
                    status = client2.status()
                else:
                    print("status ok")
                if float(status["duration"]) > 59:
                    show_duration(status)
                else:
                    show_playlist(client2)
            except mpd.CommandError:
                print("error in idler()")

        time.sleep(1)

def hello_and_goodbye(say = "hello"):
    if say == "hello":
        pixels.fill(OFF)
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
        time.sleep(0.8)

    time.sleep(0.5)
    pixels.fill(OFF)
    pixels.show()

def timer():
    print("starting timer() thread")
    while True:
        schedule.run_pending()
        time.sleep(1)

def shutdown():
    print("bye!")
    client3 = musicpd.MPDClient()
    with connection(client3):
        try:
            status = client3.status()
            state = status["state"]
            if state == "play":
                client3.pause()
        except mpd.CommandError:
            print("error in shutdown()")

    time.sleep(1)
    hello_and_goodbye("bye")
    os.system("/usr/sbin/shutdown --poweroff now")
    #schedule.CancelJob

def check_button():
    print("starting check_button() thread")
    button = Button(2)
    while True:
        if button.is_pressed:
            print("pressed")
            shutdown()
        time.sleep(1)

def handler(signum = None, frame = None):
    print('Signal handler called with signal', signum)
    hello_and_goodbye("bye")
    time.sleep(1)  #here check if process is done
    print('Wait done')
    sys.exit(0)

def show_duration(status):
    print("in show_duration()")
    print(status)
    led_duration = round(float(status["duration"]) / 8)
    print("duration: " + str(led_duration))
    if status["state"] == "pause" or status["state"] == "stop":
        print("pause oder stop")
        run["dthread"].raise_exception()
        run["dthread"].join()
        print("tschuess thread!")
    else:
        print(status["state"])
        run["dthread"] = thread_with_exception('Thread 1', led_duration)
        run["dthread"].start()
        print("led_duration thread gestartet")
    print("gruesse aus show_duration()")

def duration_thread(led_duration):
    print("im duration thread")
    print(led_duration)
    pixels.fill(OFF)
    pixels.show()
    for i in range(8):
        time.sleep(led_duration)
        pixels[i] = YELLOW
        pixels.show()
        print("pixel " + str(i) + " gezeigt")
    time.sleep(0.5)
    return

def main():
    for sig in [signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT]:
        signal.signal(sig, handler)

    reader = SimpleMFRC522()
    #t3 = threading.Thread(target=check_button)
    #t3.start()
    hello_and_goodbye("hello")
    setup()
    # start mpd callback thread
    t = threading.Thread(target=idler)
    t.start()

    while True:
        try:
            id, text = reader.read()
            text = text.strip()
            #print(id)
            print("+" + text + "+")

            if text == "toggle_pause":
                with connection(client):
                    try:
                        status = client.status()
                        state = status["state"]
                        if state == "play":
                            client.pause()
                        elif state == "pause" or state == "stop":
                            client.play()
                        else:
                            print("nix")
                    except mpd.CommandError:
                        print("fehler bei status()")

            elif text == "toggle_clr_plist":
                if config["clr_plist"] == True:
                    config["clr_plist"] = False
                else:
                    config["clr_plist"] = True
                kitt()
                # restore led playlist
                if player_status["led"] and not config["party_mode"]:
                    show_playlist(client, player_status["led"])
                else:
                    with connection(client):
                        try:
                            show_playlist(client)
                        except mpd.CommandError:
                            print("fehler bei toggle_clr_plist")

            elif text == "toggle_party_mode":
                with connection(client):
                    try:
                        if config["party_mode"] == True:
                            config["party_mode"] = False
                            client.consume(0)
                            print("party mode off")
                        else:
                            config["party_mode"] = True
                            client.consume(1)
                            print("party mode on")

                        kitt()

                        # restore led playlist
                        if player_status["led"] and not config["party_mode"]:
                            show_playlist(client, player_status["led"])
                        else:
                            show_playlist(client)

                    except mpd.CommandError:
                        print("error in toggle_party_mode")

            elif re.match("^shutdown_in_(\d\d?)$", text):
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
                # restore led playlist
                if player_status["led"] and not config["party_mode"]:
                    show_playlist(client, player_status["led"])
                else:
                    with connection(client):
                        try:
                            show_playlist(client)
                        except mpd.CommandError:
                            print("error in shutdown_in_XX")

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
