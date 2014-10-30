#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function

from compatibility_utils import PY2, PY3, utf8_str, unicode_str
import unipath
from unipath import pathof

import os

try:
    from configparser import RawConfigParser
except ImportError:
    from ConfigParser import RawConfigParser

def native_str(apath, encoding='utf-8'):
    apath = unicode_str(apath, encoding)
    if PY3:
        return apath
    return apath.encode(encoding)

def getprefs(configfile, tkobj, PERSIST):
    # To keep things simple for possible future preference additions/deletions:
    # Try to stick to - TK Widget name = prefs dictionary key = ini.get|set name.
    # EX: mobipath = prefs['mobipath'] = config.get('Defaults', mobipath).
    prefs = {}

    # Sane defaults
    prefs['mobipath'] = unipath.getcwd()
    prefs['outpath'] = unipath.getcwd()
    prefs['apnxpath'] = unipath.getcwd()
    prefs['splitvar'] = 0
    prefs['rawvar'] = 0
    prefs['dbgvar'] = 0
    prefs['hdvar'] = 0
    prefs['epubver'] = 0
    tkobj.update_idletasks()
    w = tkobj.winfo_screenwidth()
    h = tkobj.winfo_screenheight()
    rootsize = (605, 575)
    x = w//2 - rootsize[0]//2
    y = h//2 - rootsize[1]//2
    prefs['windowgeometry'] = ('%dx%d+%d+%d' % (rootsize + (x, y)))

    if unipath.exists(configfile) and PERSIST:
        config = RawConfigParser()
        try:
            if PY3:
                config.read(configfile)
            else:
                with open(configfile, 'rb') as f:
                    config.readfp(f)
        except:
            return prefs

        # Python 2.x's ConfigParser module will not save unicode strings to an ini file (at least on Windows)
        # no matter how hard you try to smack it around and scare it into doing so.
        # The workaround is to encode the file path using the utf-8 encoding
        if config.has_option('Defaults', 'mobipath'):
            prefs['mobipath'] = unicode_str(config.get('Defaults', 'mobipath'),'utf-8')
        if config.has_option('Defaults', 'outpath'):
            prefs['outpath'] = unicode_str(config.get('Defaults', 'outpath'), 'utf-8')
        if config.has_option('Defaults', 'apnxpath'):
            prefs['apnxpath'] = unicode_str(config.get('Defaults', 'apnxpath'), 'utf-8')
        if config.has_option('Defaults', 'splitvar'):
            prefs['splitvar'] = config.getint('Defaults', 'splitvar')
        if config.has_option('Defaults', 'rawvar'):
            prefs['rawvar'] = config.getint('Defaults', 'rawvar')
        if config.has_option('Defaults', 'dbgvar'):
            prefs['dbgvar'] = config.getint('Defaults', 'dbgvar')
        if config.has_option('Defaults', 'hdvar'):
            prefs['hdvar'] = config.getint('Defaults', 'hdvar')
        if config.has_option('Defaults', 'epubver'):
            prefs['epubver'] = config.getint('Defaults', 'epubver')
        if config.has_option('Geometry', 'windowgeometry'):
            prefs['windowgeometry'] = config.get('Geometry', 'windowgeometry')

    return prefs


def saveprefs(configfile, prefs, tkobj):
    # tkobj name = prefs dictionary key = ini.get|set name
    config = RawConfigParser()
    config.add_section('Defaults')

    # mobipath
    apath = pathof(tkobj.mobipath.get())
    if apath is not None and unipath.isfile(apath):
            config.set('Defaults', 'mobipath', native_str(os.path.dirname(apath)))
    else:
        config.set('Defaults', 'mobipath', native_str(prefs['mobipath']))

    # outpath
    apath = pathof(tkobj.outpath.get())
    if apath is not None and unipath.isdir(apath):
            config.set('Defaults', 'outpath', native_str(apath))
    else:
        config.set('Defaults', 'outpath', native_str(prefs['outpath']))

    # apnxpath
    apath = pathof(tkobj.apnxpath.get())
    if apath is not None and unipath.isfile(apath):
            config.set('Defaults', 'apnxpath', native_str(os.path.dirname(apath)))
    else:
        config.set('Defaults', 'apnxpath', native_str(prefs['apnxpath']))

    config.set('Defaults', 'splitvar', tkobj.splitvar.get())
    config.set('Defaults', 'rawvar', tkobj.rawvar.get())
    config.set('Defaults', 'dbgvar', tkobj.dbgvar.get())
    config.set('Defaults', 'hdvar', tkobj.hdvar.get())
    config.set('Defaults', 'epubver', tkobj.epubver.current())
    config.add_section('Geometry')
    config.set('Geometry', 'windowgeometry', tkobj.root.geometry())
    try:
        if PY3:
            with open(configfile, 'w') as f:
                config.write(f)
        else:
            with open(configfile, 'wb') as f:
                config.write(f)
        return 1
    except:
        pass
        return 0
