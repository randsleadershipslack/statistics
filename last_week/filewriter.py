#! /usr/bin/env python2.7

def filewriter(fname, content):
    """
    Now that I'm starting to write to USB media, it's reputed
    to be less reliable, so I want to confirm my write was successful
    by reopening and reading from the file
    """
    attempts = 5
    done = False
    while not done:
        f = open(fname, "w")
        f.write(content)
        f.close()
        f = open(fname, "r")
        new_content = f.read()
        f.close()
        if new_content == content:
            done = True
        else:
            m = "Difference in content writing to {}; {} attempts remaining"
            print m.format(fname, attempts)
            attempts -= 1
        if attempts <= 0:
            raise RuntimeError("Failed to write to {}".format(fname))

