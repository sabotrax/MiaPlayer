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
#client.connect()

@contextmanager
def connection():
    try:
        client.connect()
        yield
    finally:
        client.close()
        #client.disconnect()

def addnplay(title):
    song = client.find("title", title)
    #print(song)
    if not song:
        raise Exception("file not found")
    file = song[0]["file"]
    print("file: " + file)
    client.clear()
    client.add(file)
    client.play(0)

def main():
    reader = SimpleMFRC522()
    idle = False
    while True:
        try:
            id, text = reader.read()
            text = text.strip()
            #print(id)
            print("+" + text + "+")
            if idle == True:
                client.noidle()
                idle = False

            if text == "toggle_pause":
                try:
                    client.ping()
                except:
                    print("fehler")
                    #client.disconnect()
                    client.connect()

                status = client.status()
                state = status["state"]
                if state == "play":
                    client.pause()
                elif state == "pause":
                    client.play()
                else:
                    print("nix")
            else:
                try:
                    addnplay(text)
                except Exception as e:
                    print(e)

        finally:
            pass

        if idle == False:
            client.send_idle()
            idle = True

        time.sleep(1)

#with daemon.DaemonContext():
    #main()

main()
GPIO.cleanup()
