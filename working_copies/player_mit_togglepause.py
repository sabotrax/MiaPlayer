#!/usr/bin/env python3
# coding: utf-8

import musicpd
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import re
import time

client = musicpd.MPDClient()
client.connect()

def addnplay(title):
    song = client.find("title", title)
    file = song[0]["file"]
    print(file)
    client.clear()
    client.add(file)
    client.play(0)

reader = SimpleMFRC522()
try:
        id, text = reader.read()
        text = text.strip()
        print(id)
        print(text)

        if text == "toggle_pause":
            status = client.status()
            state = status["state"]
            if state == "play":
                client.pause()
            elif state == "pause":
                client.play()
            else:
                print("nix")

        else:
            addnplay(text)

finally:
        GPIO.cleanup()
