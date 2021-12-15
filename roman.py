#!/usr/bin/env python3
# coding: utf-8

def into_roman(number):
    #num = [1, 4, 5, 9, 10, 40, 50, 90,
        #100, 400, 500, 900, 1000]
    num = [1, 5, 10, 50, 100, 500, 1000]
    #sym = ["I", "IV", "V", "IX", "X", "XL",
        #"L", "XC", "C", "CD", "D", "CM", "M"]
    sym = ["I", "V", "X", "L", "C", "D", "M"]
    i = 6

    while number:
        div = number // num[i]
        number %= num[i]

        while div:
            print(sym[i], end = "")
            div -= 1
        i -= 1
    print()

into_roman(1)
into_roman(4)
into_roman(5)
into_roman(5)
into_roman(6)
into_roman(9)
into_roman(10)
into_roman(13)
into_roman(14)
into_roman(16)
into_roman(19)
into_roman(22)
into_roman(1023)
