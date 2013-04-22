#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Because Windows (and Mac OS X) allows full unicode filenames and paths
# any paths in pure bytestring python 2.X code must be utf-8 encoded as they will need to
# be converted on the fly to unicode for Windows platforms.  Any other 8-bit str 
# encoding would lose characters that can not be represented in that encoding

# these are simple support routines to allow use of utf-8 encoded bytestrings as paths in main program
# to be converted on the fly to full unicode as temporary un-named values to prevent
# the potential mixing of unicode and bytestring string values in the main program 


import sys, os
import locale
import codecs
from utf8_utils import utf8_str

iswindows = sys.platform.startswith('win')

# convert utf-8 encoded path string to proper type
# on windows that is full unicode
# on macosx and linux this is utf-8

def pathof(s):
    if isinstance(s, unicode):
        print "Warning: pathof expects utf-8 encoded byestring: ", s
        if iswindows:
            return s
        return s.encode('utf-8')
    if iswindows:
        return s.decode('utf-8')
    return s

def exists(s):
    return os.path.exists(pathof(s))

def isfile(s):
    return os.path.isfile(pathof(s))

def isdir(s):
    return os.path.isdir(pathof(s))

def mkdir(s):
    return os.mkdir(pathof(s))

def listdir(s):
    rv = []
    for file in os.listdir(pathof(s)):
        rv.append(utf8_str(file, enc=sys.getfilesystemencoding()))
    return rv

