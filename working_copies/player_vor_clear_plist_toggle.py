#!/usr/bin/env python3
# coding: utf-8

import musicpd
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import re
import time
import daemon
from contextlib import contextmanager

client = musicpd.MPDClient()

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
            client.clear()
            client.add(file)
            client.play(0)
        except Exception as e:
            print(e)
        except mpd.CommandError:
            print("fehler in addnplay()")

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
                        elif state == "pause":
                            client.play()
                        else:
                            print("nix")
                    except mpd.CommandError:
                        print("fehler bei status()")

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
