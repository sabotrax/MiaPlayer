#!/usr/bin/env python3
# coding: utf-8

def into_roman(number):
    #num = [1, 4, 5, 9, 10, 40, 50, 90,
        #100, 400, 500, 900, 1000]
    # non-subtraction notation
    num = [1, 5, 10, 50, 100, 500, 1000]
    #sym = ["I", "IV", "V", "IX", "X", "XL",
        #"L", "XC", "C", "CD", "D", "CM", "M"]
    sym = ["I", "V", "X", "L", "C", "D", "M"]
    i = 6

    roman_number = ""
    while number:
        div = number // num[i]
        number %= num[i]

        while div:
            #print(sym[i], end = "")
            roman_number = roman_number + sym[i]
            div -= 1
        i -= 1
    #print()
    return roman_number

for i in range(1, 50):
    rn = into_roman(i)
    print(rn + " " + str(len(rn)))
