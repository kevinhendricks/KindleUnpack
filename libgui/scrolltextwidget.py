#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals, division, absolute_import, print_function
from lib.compatibility_utils import PY2

if PY2:
    import Tkinter as tkinter
    import Tkconstants as tkinter_constants
else:
    import tkinter
    import tkinter.constants as tkinter_constants

# basic scrolled text widget
class ScrolledText(tkinter.Text):

    def __init__(self, master=None, **kw):
        self.frame = tkinter.Frame(master)
        self.vbar = tkinter.Scrollbar(self.frame)
        self.vbar.pack(side=tkinter_constants.RIGHT, fill=tkinter_constants.Y)
        kw.update({'yscrollcommand': self.vbar.set})
        tkinter.Text.__init__(self, self.frame, **kw)
        self.pack(side=tkinter_constants.LEFT, fill=tkinter_constants.BOTH, expand=True)
        self.vbar['command'] = self.yview
        # Copy geometry methods of self.frame without overriding Text
        # methods = hack!
        text_meths = vars(tkinter.Text).keys()
        methods = list(vars(tkinter.Pack).keys()) + list(vars(tkinter.Grid).keys()) + list(vars(tkinter.Place).keys())
        methods = set(methods).difference(text_meths)
        for m in methods:
            if m[0] != '_' and m != 'config' and m != 'configure':
                setattr(self, m, getattr(self.frame, m))

    def __str__(self):
        return str(self.frame)
