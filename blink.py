#!/usr/bin/env python3

import board
import neopixel
import time

# The order of the pixel colors - RGB or GRB. Some NeoPixels have red and green reversed!
# For RGBW NeoPixels, simply change the ORDER to RGBW or GRBW.
ORDER = neopixel.GRBW
pixels = neopixel.NeoPixel(board.D12, 10, brightness=0.1, auto_write=False, pixel_order=ORDER)

RED = (255, 0, 0)
YELLOW = (255, 150, 0)
GREEN = (0, 255, 0)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
PURPLE = (180, 0, 255)

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
#pixels.fill((GREEN))
#pixels.show()
