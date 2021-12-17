#!/usr/bin/env python3
# coding: utf-8

import board
from contextlib import contextmanager
#import daemon
from mfrc522 import SimpleMFRC522
import musicpd
import neopixel
import re
import RPi.GPIO as GPIO
import threading
import time

ORDER = neopixel.GRBW
pixels = neopixel.NeoPixel(board.D12, 10, brightness=0.1, auto_write=False, pixel_order=ORDER)

RED = (255, 0, 0)
YELLOW = (255, 150, 0)
GREEN = (0, 255, 0)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
PURPLE = (180, 0, 255)

client = musicpd.MPDClient()
config = {
        # clear playlist before new song is added
        # or append otherwise
        "clr_plist": True,
}
player_status = {
        "led": [],
}

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

def addnplay(title):
    with connection(client):
        try:
            song = client.find("title", title)
            #print(song)
            if not song:
                raise Exception("file not found")
            file = song[0]["file"]
            print("file: " + file)
            if config["clr_plist"] == True:
                client.clear()
                client.add(file)
                client.play(0)
            else:
                client.add(file)
                plist = client.playlistinfo()
                if len(plist) == 1:
                    client.play(0)
                else:
                    kitt()

            show_playlist()

        except Exception as e:
            print(e)
            kitt(RED)
            show_playlist(player_status["led"])
        except mpd.CommandError:
            print("fehler in addnplay()")

def kitt(color = GREEN):
    pixels.fill((0 ,0 ,0))
    pixels.show()

    i, j, k, l = 0, 8, 1, 0
    while l < 2:
        #print(l)
        for x in range(i, j, k):
            #print(" "  + str(x))
            #pixels[x] = GREEN
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

def show_playlist(roman_led = []):
    print("in show_playlist()")
    # clear leds
    pixels.fill((0 ,0 ,0))
    pixels.show()

    if not roman_led:
        # get actual (not total) length of playlist from mpd
        status = client.status()
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

def show_playlist2(clx, roman_led = []):
    print("in show_playlist2()")
    # clear leds
    pixels.fill((0 ,0 ,0))
    pixels.show()

    if not roman_led:
        # get actual (not total) length of playlist from mpd
        status = clx.status()
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
    :return: list of list of color values in GRBW like (255,0,0)
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
            show_playlist()
        except mpd.CommandError:
            print("fehler bei setup()")

def idler():
    print("thread starting")
    client2 = musicpd.MPDClient()
    while True:
        with connection(client2):
            try:
                this_happened = client2.idle("player","playlist")
                print(this_happened)
                print(client2.status())
                show_playlist2(client2)
            except mpd.CommandError:
                print("fehler bei idle()")

        time.sleep(1)

def main():
    reader = SimpleMFRC522()
    setup()
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
                # restore
                if player_status["led"]:
                    show_playlist(player_status["led"])
                else:
                    with connection(client):
                        try:
                            show_playlist()
                        except mpd.CommandError:
                            print("fehler bei toggle_clr_plist")

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
