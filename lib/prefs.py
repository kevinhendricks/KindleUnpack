#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

import os, sys, codecs
from ConfigParser import RawConfigParser

def getprefs(configfile, tkobj, PERSIST):
    # To keep things simple for possible future preference additions/deletions:
    # Try to stick to - TK Widget name = prefs dictionary key = ini.get|set name.
    # EX: mobipath = prefs['mobipath'] = config.get('Defaults', mobipath).
    prefs = {}

    # Sane defaults
    prefs['mobipath'] = os.getcwdu()
    prefs['outpath'] = os.getcwdu()
    prefs['apnxpath'] = os.getcwdu()
    prefs['splitvar'] = 0
    prefs['rawvar'] = 0
    prefs['dbgvar'] = 0
    prefs['hdvar'] = 0
    prefs['epubver'] = 0
    tkobj.update_idletasks()
    w = tkobj.winfo_screenwidth()
    h = tkobj.winfo_screenheight()
    rootsize = (605, 575)
    x = w/2 - rootsize[0]/2
    y = h/2 - rootsize[1]/2
    prefs['windowgeometry'] = (u'%dx%d+%d+%d' % (rootsize + (x, y)))

    if os.path.exists(configfile) and PERSIST:
        config = RawConfigParser()
        try:
            with codecs.open(configfile, 'r', 'utf-8') as f:
                config.readfp(f)
        except:
            return prefs
        # Python 2.x's ConfigParser module will not save unicode strings to an ini file (at least on Windows)
        # no matter how hard you try to smack it around and scare it into doing so.
        # The workaround (to support unicode path prefences) is to encode the file path using the 
        # unicode_escape 'codec' when writing, and to decode using the unicode_escape codec when reading.
        if config.has_option('Defaults', 'mobipath'):
            prefs['mobipath'] = config.get('Defaults', 'mobipath').decode('unicode_escape')
        if config.has_option('Defaults', 'outpath'):
            prefs['outpath'] = config.get('Defaults', 'outpath').decode('unicode_escape')
        if config.has_option('Defaults', 'apnxpath'):
            prefs['apnxpath'] = config.get('Defaults', 'apnxpath').decode('unicode_escape')
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
    #tkobj name = prefs dictionary key = ini.get|set name
    config = RawConfigParser()
    config.add_section('Defaults')
    if len(tkobj.mobipath.get()):
        if os.path.isfile(tkobj.mobipath.get()):
            config.set('Defaults', 'mobipath', os.path.dirname(tkobj.mobipath.get()).encode('unicode_escape'))
        else:
            config.set('Defaults', 'mobipath', prefs['mobipath'].encode('unicode_escape'))
    else:
        config.set('Defaults', 'mobipath', prefs['mobipath'].encode('unicode_escape'))
    if len(tkobj.outpath.get()):
        if os.path.isdir(tkobj.outpath.get()):
            config.set('Defaults', 'outpath', tkobj.outpath.get().encode('unicode_escape'))
        else:
            config.set('Defaults', 'outpath', prefs['outpath'].encode('unicode_escape'))
    else:
        config.set('Defaults', 'outpath', prefs['outpath'].encode('unicode_escape'))
    if len(tkobj.apnxpath.get()):
        if os.path.isfile(tkobj.apnxpath.get()):
            config.set('Defaults', 'apnxpath', os.path.dirname(tkobj.apnxpath.get()).encode('unicode_escape'))
        else:
            config.set('Defaults', 'apnxpath', prefs['apnxpath'].encode('unicode_escape'))
    else:
        config.set('Defaults', 'apnxpath', prefs['apnxpath'].encode('unicode_escape'))
    config.set('Defaults', 'splitvar', tkobj.splitvar.get())
    config.set('Defaults', 'rawvar', tkobj.rawvar.get())
    config.set('Defaults', 'dbgvar', tkobj.dbgvar.get())
    config.set('Defaults', 'hdvar', tkobj.hdvar.get())
    config.set('Defaults', 'epubver', tkobj.epubver.current())
    config.add_section('Geometry')
    config.set('Geometry', 'windowgeometry', tkobj.root.geometry())
    try:
        with codecs.open(configfile, 'w', 'utf-8') as f:
            config.write(f)
        return 1
    except:
        pass
        return 0