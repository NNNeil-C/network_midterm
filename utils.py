import socket
import time
import struct
import math
import os
import sys



class Logger:
    def __init__(self, prefix, fileLength):
        self.total = fileLength
        self.lastWidth = 0
        self.prefix = prefix
        self.lastInfo = ''

    def log(self, info):
        sys.stdout.write(' ' * self.lastWidth + '\r')
        sys.stdout.flush()
        print(info)
        sys.stdout.write(self.lastInfo)
        sys.stdout.flush()

    def progress(self, num):
        sys.stdout.write(' ' * self.lastWidth + '\r')
        sys.stdout.flush()
        self.lastInfo = self.prefix + (":-------------%.2f%%\r" % (num / self.total))
        self.lastWidth = sys.stdout.write(self.lastInfo)
        sys.stdout.flush()
