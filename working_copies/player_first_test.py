#!/usr/bin/env python3
# coding: utf-8

import musicpd
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import re
import time

client = musicpd.MPDClient()
client.connect()

reader = SimpleMFRC522()
try:
        id, text = reader.read()
        print(id)
        print(text)
finally:
        GPIO.cleanup()

print(text)
pattern = re.compile("Chop Suey")
if pattern.match(text):
    print("wahr")
    text = "Chop Suey"


client.clear()
#song = client.find("title", "Chop Suey")
song = client.find("title", text)
file = song[0]["file"]
print(file)
client.add(file)
client.play(0)
time.sleep(25)
client.stop()
