#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function

import sys

from lib.compatibility_utils import PY2, text_type, unicode_str
from lib.compatibility_utils import unicode_argv, add_cp65001_codec

import lib.unipath as unipath
from lib.unipath import pathof

import os
import traceback

import codecs
add_cp65001_codec()

try:
    from queue import Full
    from queue import Empty
except ImportError:
    from Queue import Full
    from Queue import Empty

if PY2 and sys.platform.startswith("win"):
    from libgui.askfolder_ed import AskFolder

from multiprocessing import Process, Queue

if PY2:
    import Tkinter as tkinter
    import Tkconstants as tkinter_constants
    import tkFileDialog as tkinter_filedialog
    import ttk as tkinter_ttk
else:
    import tkinter
    import tkinter.constants as tkinter_constants
    import tkinter.filedialog as tkinter_filedialog
    import tkinter.ttk as tkinter_ttk

from libgui.scrolltextwidget import ScrolledText

import lib.kindleunpack as kindleunpack

# Set to false to NOT save prefences to an ini file.
# Starting directories for file dialogs will still persist
# for the current KindleUnpack session.
#
# Need to delete the ini file after setting to false, of course.
PERSISTENT_PREFS = True

from inspect import getfile, currentframe
from libgui.prefs import getprefs, saveprefs

# Probably overkill, but to ensure cross-platform success no matter how the script is called/run...
SCRIPT_NAME = unicode_str(getfile(currentframe()))
SCRIPT_DIR = unicode_str(os.path.dirname(unipath.abspath(getfile(currentframe()))))
PROGNAME = unicode_str(os.path.splitext(SCRIPT_NAME)[0])

# Include platform in the ini file name. That way, settings can still persist
# in the event that different OSs access the same script via a network share/flash-drive.
CONFIGFILE = unicode_str(os.path.join(SCRIPT_DIR, '{0}_{1}.json'.format(PROGNAME, sys.platform[:3])))

# Wrap a stream so that output gets appended to shared queue
# using utf-8 encoding
class QueuedStream:
    def __init__(self, stream, q):
        self.stream = stream
        self.encoding = stream.encoding
        self.q = q
        if self.encoding == None:
            self.encoding = 'utf-8'
    def write(self, data):
        if isinstance(data,text_type):
            data = data.encode('utf-8')
        elif self.encoding not in ['utf-8','UTF-8','cp65001','CP65001']:
            udata = data.decode(self.encoding)
            data = udata.encode('utf-8')
        self.q.put(data)
    def __getattr__(self, attr):
        if attr == 'mode':
            return 'wb'
        if attr == 'encoding':
            return 'utf-8'
        return getattr(self.stream, attr)


class MainDialog(tkinter.Frame):

    def __init__(self, root):
        tkinter.Frame.__init__(self, root, border=5)
        self.root = root
        self.interval = 50
        self.p2 = None
        self.q = Queue()
        # To keep things simple for possible future preference additions/deletions:
        # Try to stick to - TK Widget name = prefs dictionary key = ini.get|set name.
        # EX: mobipath = prefs['mobipath'] = config.get('Defaults', mobipath).
        self.prefs = getprefs(CONFIGFILE, self.root, PERSISTENT_PREFS)

        self.status = tkinter.StringVar()
        tkinter.Label(self, textvariable=self.status, justify='center').grid(row=0, columnspan=3, sticky=tkinter_constants.N)
        self.status.set('Upack a non-DRM Kindle eBook')
        sticky = tkinter_constants.E + tkinter_constants.W
        ALL = tkinter_constants.E+tkinter_constants.W+tkinter_constants.N+tkinter_constants.S
        # Set to the column the textentry boxes are in.
        self.grid_columnconfigure(1, weight=1)
        # Set to the row the debug log widget is in.
        self.grid_rowconfigure(10, weight=1)

        tkinter.Label(self, text='').grid(row=1, sticky=tkinter_constants.E)
        tkinter.Label(self, text='Unencrypted Kindle eBook input file', wraplength=200).grid(row=2, sticky=tkinter_constants.E)
        self.mobipath = tkinter.Entry(self, width=50)
        self.mobipath.grid(row=2, column=1, sticky=sticky)
        self.mobipath.insert(0, '')
        button = tkinter.Button(self, text="Browse...", command=self.get_mobipath)
        button.grid(row=2, column=2, sticky=sticky)

        tkinter.Label(self, text='Output Directory', wraplength=200).grid(row=3, sticky=tkinter_constants.E)
        self.outpath = tkinter.Entry(self, width=50)
        self.outpath.grid(row=3, column=1, sticky=sticky)
        if self.prefs['outpath'] and PERSISTENT_PREFS and unipath.exists(CONFIGFILE):
            outpath = pathof(os.path.normpath(self.prefs['outpath']))
            self.outpath.insert(0, outpath)
        else:
            self.outpath.insert(0, '')
        button = tkinter.Button(self, text="Browse...", command=self.get_outpath)
        button.grid(row=3, column=2, sticky=sticky)

        tkinter.Label(self, text='OPTIONAL: APNX file Associated with AZW3', wraplength=200).grid(row=4, sticky=tkinter_constants.E)
        self.apnxpath = tkinter.Entry(self, width=50)
        self.apnxpath.grid(row=4, column=1, sticky=sticky)
        self.apnxpath.insert(0, '')
        button = tkinter.Button(self, text="Browse...", command=self.get_apnxpath)
        button.grid(row=4, column=2, sticky=sticky)

        self.splitvar = tkinter.IntVar()
        checkbox = tkinter.Checkbutton(self, text="Split Combination Kindlegen eBooks", variable=self.splitvar)
        if self.prefs['splitvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=5, column=1, columnspan=2, sticky=tkinter_constants.W)

        self.rawvar = tkinter.IntVar()
        checkbox = tkinter.Checkbutton(self, text="Write Raw Data", variable=self.rawvar)
        if self.prefs['rawvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=6, column=1, columnspan=2, sticky=tkinter_constants.W)

        self.dbgvar = tkinter.IntVar()
        checkbox = tkinter.Checkbutton(self, text="Dump Mode", variable=self.dbgvar)
        if self.prefs['dbgvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=7, column=1, columnspan=2, sticky=tkinter_constants.W)

        self.hdvar = tkinter.IntVar()
        checkbox = tkinter.Checkbutton(self, text="Use HD Images If Present", variable=self.hdvar)
        if self.prefs['hdvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=8, column=1, columnspan=2, sticky=tkinter_constants.W)

        tkinter.Label(self, text='ePub Output Type:').grid(row=9, sticky=tkinter_constants.E)
        self.epubver_val = tkinter.StringVar()
        self.epubver = tkinter_ttk.Combobox(self, textvariable=self.epubver_val, state='readonly')
        self.epubver['values'] = ('ePub 2', 'ePub 3', 'Auto-detect', 'Force ePub 2')
        self.epubver.current(0)
        if self.prefs['epubver'] and PERSISTENT_PREFS:
            self.epubver.current(self.prefs['epubver'])
        self.epubver.grid(row=9, column=1, columnspan=2, pady=(3,5), sticky=tkinter_constants.W)

        msg1 = 'Conversion Log \n\n'
        self.stext = ScrolledText(self, bd=5, relief=tkinter_constants.RIDGE, wrap=tkinter_constants.WORD)
        self.stext.grid(row=10, column=0, columnspan=3, sticky=ALL)
        self.stext.insert(tkinter_constants.END,msg1)

        self.sbotton = tkinter.Button(
            self, text="Start", width=10, command=self.convertit)
        self.sbotton.grid(row=11, column=1, sticky=tkinter_constants.S+tkinter_constants.E)
        self.qbutton = tkinter.Button(
            self, text="Quit", width=10, command=self.quitting)
        self.qbutton.grid(row=11, column=2, sticky=tkinter_constants.S+tkinter_constants.W)
        if self.prefs['windowgeometry'] and PERSISTENT_PREFS:
            self.root.geometry(self.prefs['windowgeometry'])
        else:
            self.root.update_idletasks()
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            rootsize = (605, 575)
            x = w//2 - rootsize[0]//2
            y = h//2 - rootsize[1]//2
            self.root.geometry('%dx%d+%d+%d' % (rootsize + (x, y)))
        self.root.protocol('WM_DELETE_WINDOW', self.quitting)

    # read queue shared between this main process and spawned child processes
    def readQueueUntilEmpty(self):
        done = False
        text = ''
        while not done:
            try:
                data = self.q.get_nowait()
                text += unicode_str(data, 'utf-8')
            except Empty:
                done = True
                pass
        return text

    # read from subprocess pipe without blocking
    # invoked every interval via the widget "after"
    # option being used, so need to reset it for the next time
    def processQueue(self):
        poll = self.p2.exitcode
        if poll != None:
            text = self.readQueueUntilEmpty()
            msg = text + '\n\n' + 'eBook successfully unpacked\n'
            if poll != 0:
                msg = text + '\n\n' + 'Error: Unpacking Failed\n'
            self.p2.join()
            self.showCmdOutput(msg)
            self.p2 = None
            self.sbotton.configure(state='normal')
            return
        text = self.readQueueUntilEmpty()
        self.showCmdOutput(text)
        # make sure we get invoked again by event loop after interval
        self.stext.after(self.interval,self.processQueue)
        return

    # post output from subprocess in scrolled text widget
    def showCmdOutput(self, msg):
        if msg and msg !='':
            if sys.platform.startswith('win'):
                msg = msg.replace('\r\n','\n')
            self.stext.insert(tkinter_constants.END,msg)
            self.stext.yview_pickplace(tkinter_constants.END)
        return

    def get_mobipath(self):
        cwd = unipath.getcwd()
        mobipath = tkinter_filedialog.askopenfilename(
            parent=None, title='Select Unencrypted Kindle eBook File',
            initialdir=self.prefs['mobipath'] or cwd,
            initialfile=None,
            defaultextension=('.mobi', '.prc', '.azw', '.azw4', '.azw3'),
            filetypes=[('All Kindle formats', ('.mobi', '.prc', '.azw', '.azw4', '.azw3')),
                       ('Kindle Mobi eBook File', '.mobi'), ('Kindle PRC eBook File', '.prc'),
                       ('Kindle AZW eBook File', '.azw'), ('Kindle AZW4 Print Replica', '.azw4'),
                       ('Kindle Version 8', '.azw3'),('All Files', '.*')])
        if mobipath:
            self.prefs['mobipath'] = pathof(os.path.dirname(mobipath))
            mobipath = pathof(os.path.normpath(mobipath))
            self.mobipath.delete(0, tkinter_constants.END)
            self.mobipath.insert(0, mobipath)
        return

    def get_apnxpath(self):
        cwd = unipath.getcwd()
        apnxpath = tkinter_filedialog.askopenfilename(
            parent=None, title='Optional APNX file associated with AZW3',
            initialdir=self.prefs['apnxpath'] or cwd,
            initialfile=None,
            defaultextension='.apnx', filetypes=[('Kindle APNX Page Information File', '.apnx'), ('All Files', '.*')])
        if apnxpath:
            self.prefs['apnxpath'] = pathof(os.path.dirname(apnxpath))
            apnxpath = pathof(os.path.normpath(apnxpath))
            self.apnxpath.delete(0, tkinter_constants.END)
            self.apnxpath.insert(0, apnxpath)
        return

    def get_outpath(self):
        cwd = unipath.getcwd()
        if sys.platform.startswith("win") and PY2:
            # tk_chooseDirectory is horribly broken for unicode paths
            # on windows - bug has been reported but not fixed for years
            # workaround by using our own unicode aware version
            outpath = AskFolder(message="Folder to Store Output into",
                defaultLocation=self.prefs['outpath'] or unipath.getcwd())
        else:
            outpath = tkinter_filedialog.askdirectory(
                parent=None, title='Folder to Store Output into',
                initialdir=self.prefs['outpath'] or cwd, initialfile=None)
        if outpath:
            self.prefs['outpath'] = outpath
            outpath = pathof(os.path.normpath(outpath))
            self.outpath.delete(0, tkinter_constants.END)
            self.outpath.insert(0, outpath)
        return

    def quitting(self):
        # kill any still running subprocess
        if self.p2 != None:
            if (self.p2.exitcode == None):
                self.p2.terminate()
        if PERSISTENT_PREFS:
            if not saveprefs(CONFIGFILE, self.prefs, self):
                print("Couldn't save INI file.")
        self.root.destroy()
        self.quit()

    # run in a child process and collect its output
    def convertit(self):
        # now disable the button to prevent multiple launches
        self.sbotton.configure(state='disabled')
        mobipath = unicode_str(self.mobipath.get())
        apnxpath = unicode_str(self.apnxpath.get())
        outdir = unicode_str(self.outpath.get())
        if not mobipath or not unipath.exists(mobipath):
            self.status.set('Specified eBook file does not exist')
            self.sbotton.configure(state='normal')
            return
        apnxfile = None
        if apnxpath != "" and unipath.exists(apnxpath):
            apnxfile = apnxpath
        if not outdir:
            self.status.set('No output directory specified')
            self.sbotton.configure(state='normal')
            return
        q = self.q
        log = 'Input Path = "'+ mobipath + '"\n'
        log += 'Output Path = "' + outdir + '"\n'
        if apnxfile != None:
            log += 'APNX Path = "' + apnxfile + '"\n'
        dump = False
        writeraw = False
        splitcombos = False
        use_hd = False
        if self.dbgvar.get() == 1:
            dump = True
            log += 'Debug = True\n'
        if self.rawvar.get() == 1:
            writeraw = True
            log += 'WriteRawML = True\n'
        if self.splitvar.get() == 1:
            splitcombos = True
            log += 'Split Combo KF8 Kindle eBooks = True\n'
        if self.epubver.current() == 0:
            epubversion = '2'
        elif self.epubver.current() == 1:
            epubversion = '3'
        elif self.epubver.current() == 2:
            epubversion = 'A'
        else:
            epubversion = 'F'
        log += 'Epub Output Type Set To: {0}\n'.format(self.epubver_val.get())
        if self.hdvar.get():
            use_hd = True
            # stub for processing the Use HD Images setting
            log += 'Use HD Images If Present = True\n'
        log += '\n\n'
        log += 'Please Wait ...\n\n'
        self.stext.insert(tkinter_constants.END,log)
        self.p2 = Process(target=unpackEbook, args=(q, mobipath, outdir, apnxfile, epubversion, use_hd, dump, writeraw, splitcombos))
        self.p2.start()

        # python does not seem to allow you to create
        # your own eventloop which every other gui does - strange
        # so need to use the widget "after" command to force
        # event loop to run non-gui events every interval
        self.stext.after(self.interval,self.processQueue)
        return


# child process / multiprocessing thread starts here
def unpackEbook(q, infile, outdir, apnxfile, epubversion, use_hd, dump, writeraw, splitcombos):
    sys.stdout = QueuedStream(sys.stdout, q)
    sys.stderr = QueuedStream(sys.stderr, q)
    rv = 0
    try:
        kindleunpack.unpackBook(infile, outdir, apnxfile, epubversion, use_hd, dodump=dump, dowriteraw=writeraw, dosplitcombos=splitcombos)
    except Exception as e:
        print("Error: %s" % e)
        print(traceback.format_exc())
        rv = 1
    sys.exit(rv)


def main(argv=unicode_argv()):
    root = tkinter.Tk()
    root.title('Kindle eBook Unpack Tool')
    root.minsize(440, 350)
    root.resizable(True, True)
    MainDialog(root).pack(fill=tkinter_constants.BOTH, expand=tkinter_constants.YES)
    root.mainloop()
    return 0

if __name__ == "__main__":
    sys.exit(main())
