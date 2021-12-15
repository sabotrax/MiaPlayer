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
def connection():
    try:
        client.connect()
        yield
    finally:
        client.close()
        client.disconnect()

def addnplay(title):
    with connection():
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
        except mpd.CommandError:
            print("fehler in addnplay()")

def kitt():
    pixels.fill((0 ,0 ,0))
    pixels.show()

    i, j, k, l = 0, 8, 1, 0
    while l < 2:
        #print(l)
        for x in range(i, j, k):
            #print(" "  + str(x))
            pixels[x] = GREEN
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
    if not roman_led:
        # get actual (not total) length of playlist from mpd
        status = client.status()
        yet_to_play = int(status["playlistlength"]) - int(status["song"])
        # can only display this many numbers with 8 leds
        if yet_to_play > 48:
            yet_to_play = 48
        if yet_to_play > 0:
            # convert to roman numbers represented by colored leds
            # color code is modified zelda rubee color standard
            roman_led = into_roman_led(yet_to_play)

    if roman_led:
        # display
        pixels.fill((0 ,0 ,0))
        pixels.show()
        i = 0
        for j in roman_led:
            pixels[i] = j
            i = i + 1
        #print(roman_led)
        pixels.show()
        # save led state
        player_status["led"] = roman_led

def into_roman_led(number):
    # non-subtraction notation
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

def main():
    reader = SimpleMFRC522()
    while True:
        try:
            id, text = reader.read()
            text = text.strip()
            #print(id)
            print("+" + text + "+")

            if text == "toggle_pause":
                with connection():
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
                show_playlist(player_status["led"])

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
