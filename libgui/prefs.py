#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function

from lib.compatibility_utils import PY2, PY3, unicode_str
from lib import unipath
from lib.unipath import pathof

import os
import json
if PY2:
    import codecs


def getprefs(configfile, tkobj, PERSIST):
    # To keep things simple for possible future preference additions/deletions:
    # Try to stick to - TK Widget name = prefs dictionary key.
    # EX: tkobj.outpath = prefs['outpath']
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
        try:
            if PY3:
                with open(configfile, 'r', encoding='utf-8') as f:
                    tmpprefs = json.load(f)
            else:
                with codecs.open(configfile, 'r', encoding='utf-8') as f:
                    tmpprefs = json.load(f)
        except:
            return prefs

        if 'mobipath' in tmpprefs.keys():
            prefs['mobipath'] = unicode_str(tmpprefs['mobipath'], 'utf-8')
        if 'outpath' in tmpprefs.keys():
            prefs['outpath'] = unicode_str(tmpprefs['outpath'], 'utf-8')
        if 'apnxpath' in tmpprefs.keys():
            prefs['apnxpath'] = unicode_str(tmpprefs['apnxpath'], 'utf-8')
        if 'splitvar' in tmpprefs.keys():
            prefs['splitvar'] = tmpprefs['splitvar']
        if 'rawvar' in tmpprefs.keys():
            prefs['rawvar'] = tmpprefs['rawvar']
        if 'dbgvar'in tmpprefs.keys():
            prefs['dbgvar'] = tmpprefs['dbgvar']
        if 'hdvar' in tmpprefs.keys():
            prefs['hdvar'] = tmpprefs['hdvar']
        if 'epubver' in tmpprefs.keys():
            prefs['epubver'] = tmpprefs['epubver']
        if 'windowgeometry' in tmpprefs.keys():
            prefs['windowgeometry'] = tmpprefs['windowgeometry']

    return prefs


def saveprefs(configfile, prefs, tkobj):
    # tkobj name = prefs dictionary key

    # mobipath
    apath = pathof(tkobj.mobipath.get())
    if apath is not None and unipath.isfile(apath):
        prefs['mobipath'] = os.path.dirname(apath)

    # outpath
    apath = pathof(tkobj.outpath.get())
    if apath is not None and unipath.isdir(apath):
        prefs['outpath'] = apath

    # apnxpath
    apath = pathof(tkobj.apnxpath.get())
    if apath is not None and unipath.isfile(apath):
        prefs['apnxpath'] = os.path.dirname(apath)

    prefs['splitvar'] = tkobj.splitvar.get()
    prefs['rawvar'] = tkobj.rawvar.get()
    prefs['dbgvar'] = tkobj.dbgvar.get()
    prefs['hdvar'] = tkobj.hdvar.get()
    prefs['epubver'] = tkobj.epubver.current()
    prefs['windowgeometry'] = tkobj.root.geometry()
    try:
        if PY3:
            with open(configfile, 'w', encoding='utf-8') as f:
                json.dump(prefs, f, ensure_ascii=False, indent=4)
        else:
            with codecs.open(configfile, 'w', encoding='utf-8') as f:
                json.dump(prefs, f, ensure_ascii=False, indent=4)
        return 1
    except:
        pass
        return 0
