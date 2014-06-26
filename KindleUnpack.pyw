#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

import sys
sys.path.append('lib')
import os, os.path, urllib
import codecs

from utf8_utils import add_cp65001_codec, utf8_argv, utf8_str
add_cp65001_codec()

import path

if sys.platform.startswith("win"):
    from askfolder_ed import AskFolder

from Queue import Full
from Queue import Empty
from multiprocessing import Process, Queue

import kindleunpack

# Set to false to NOT save prefences to an ini file.
# Starting directories for file dialogs will still persist
# for the current KindleUnpack session.
#
# Need to delete the ini file after setting to false, of course.
PERSISTENT_PREFS = True

from inspect import getfile, currentframe
from prefs import getprefs, saveprefs

# Probably overkill, but to ensure cross-platform success no matter how the script is called/run...
SCRIPT_NAME = utf8_str(getfile(currentframe()))
SCRIPT_DIR = utf8_str(os.path.dirname(os.path.abspath(getfile(currentframe()))))
PROGNAME = utf8_str(os.path.splitext(SCRIPT_NAME)[0])
# Include platform in the ini file name. That way, settings can still persist
# in the event that different OSs access the same script via a network share/flash-drive.
CONFIGFILE = utf8_str(os.path.join(SCRIPT_DIR, '{0}_{1}.ini'.format(PROGNAME, sys.platform[:3])))

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
        if isinstance(data,unicode):
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

import Tkinter
import Tkconstants
import tkFileDialog
import tkMessageBox
import tkFont
import ttk

from scrolltextwidget import ScrolledText

class MainDialog(Tkinter.Frame):
    def __init__(self, root):
        Tkinter.Frame.__init__(self, root, border=5)
        self.root = root
        self.interval = 50
        self.p2 = None
        self.q = Queue()
        # To keep things simple for possible future preference additions/deletions:
        # Try to stick to - TK Widget name = prefs dictionary key = ini.get|set name.
        # EX: mobipath = prefs['mobipath'] = config.get('Defaults', mobipath).
        self.prefs = getprefs(CONFIGFILE, self.root, PERSISTENT_PREFS)

        self.status = Tkinter.StringVar()
        Tkinter.Label(self, textvariable=self.status, justify='center').grid(row=0, columnspan=3, sticky=Tkconstants.N)
        self.status.set('Upack a non-DRM Kindle eBook')
        sticky = Tkconstants.E + Tkconstants.W
        ALL = Tkconstants.E+Tkconstants.W+Tkconstants.N+Tkconstants.S
        # Set to the column the textentry boxes are in.
        self.grid_columnconfigure(1, weight=1)
        # Set to the row the debug log widget is in.
        self.grid_rowconfigure(10, weight=1)

        Tkinter.Label(self, text='').grid(row=1, sticky=Tkconstants.E)
        Tkinter.Label(self, text='Unencrypted Kindle eBook input file', wraplength=200).grid(row=2, sticky=Tkconstants.E)
        self.mobipath = Tkinter.Entry(self, width=50)
        self.mobipath.grid(row=2, column=1, sticky=sticky)
        self.mobipath.insert(0, '')
        button = Tkinter.Button(self, text="Browse...", command=self.get_mobipath)
        button.grid(row=2, column=2, sticky=sticky)

        Tkinter.Label(self, text='Output Directory', wraplength=200).grid(row=3, sticky=Tkconstants.E)
        self.outpath = Tkinter.Entry(self, width=50)
        self.outpath.grid(row=3, column=1, sticky=sticky)
        if self.prefs['outpath'] and PERSISTENT_PREFS and os.path.exists(CONFIGFILE):
            outpath = os.path.normpath(self.prefs['outpath'])
            outpath = utf8_str(outpath)
            self.outpath.insert(0, outpath)
        else:
            self.outpath.insert(0, '')
        button = Tkinter.Button(self, text="Browse...", command=self.get_outpath)
        button.grid(row=3, column=2, sticky=sticky)

        Tkinter.Label(self, text='OPTIONAL: APNX file Associated with AZW3', wraplength=200).grid(row=4, sticky=Tkconstants.E)
        self.apnxpath = Tkinter.Entry(self, width=50)
        self.apnxpath.grid(row=4, column=1, sticky=sticky)
        self.apnxpath.insert(0, '')
        button = Tkinter.Button(self, text="Browse...", command=self.get_apnxpath)
        button.grid(row=4, column=2, sticky=sticky)

        self.splitvar = Tkinter.IntVar()
        checkbox = Tkinter.Checkbutton(self, text="Split Combination Kindlegen eBooks", variable=self.splitvar)
        if self.prefs['splitvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=5, column=1, columnspan=2, sticky=Tkconstants.W)

        self.rawvar = Tkinter.IntVar()
        checkbox = Tkinter.Checkbutton(self, text="Write Raw Data", variable=self.rawvar)
        if self.prefs['rawvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=6, column=1, columnspan=2, sticky=Tkconstants.W)

        self.dbgvar = Tkinter.IntVar()
        checkbox = Tkinter.Checkbutton(self, text="Dump Mode", variable=self.dbgvar)
        if self.prefs['dbgvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=7, column=1, columnspan=2, sticky=Tkconstants.W)

        self.hdvar = Tkinter.IntVar()
        checkbox = Tkinter.Checkbutton(self, text="Use HD Images If Present", variable=self.hdvar)
        if self.prefs['hdvar'] and PERSISTENT_PREFS:
            checkbox.select()
        checkbox.grid(row=8, column=1, columnspan=2, sticky=Tkconstants.W)

        Tkinter.Label(self, text='ePub Output Type:').grid(row=9, sticky=Tkconstants.E)
        self.epubver_val = Tkinter.StringVar()
        self.epubver = ttk.Combobox(self, textvariable=self.epubver_val, state='readonly')
        self.epubver['values'] = ('ePub 2', 'ePub 3', 'Auto-detect')
        self.epubver.current(0)
        if self.prefs['epubver'] and PERSISTENT_PREFS:
            self.epubver.current(self.prefs['epubver'])
        self.epubver.grid(row=9, column=1, columnspan=2, pady=(3,5), sticky=Tkconstants.W)

        msg1 = 'Conversion Log \n\n'
        self.stext = ScrolledText(self, bd=5, relief=Tkconstants.RIDGE, wrap=Tkconstants.WORD)
        self.stext.grid(row=10, column=0, columnspan=3, sticky=ALL)
        self.stext.insert(Tkconstants.END,msg1)

        self.sbotton = Tkinter.Button(
            self, text="Start", width=10, command=self.convertit)
        self.sbotton.grid(row=11, column=1, sticky=Tkconstants.S+Tkconstants.E)
        self.qbutton = Tkinter.Button(
            self, text="Quit", width=10, command=self.quitting)
        self.qbutton.grid(row=11, column=2, sticky=Tkconstants.S+Tkconstants.W)
        if self.prefs['windowgeometry'] and PERSISTENT_PREFS:
            self.root.geometry(self.prefs['windowgeometry'].encode('utf8'))
        else:
            self.root.update_idletasks()
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            rootsize = (605, 575)
            x = w/2 - rootsize[0]/2
            y = h/2 - rootsize[1]/2
            self.root.geometry('%dx%d+%d+%d' % (rootsize + (x, y)))
        self.root.protocol('WM_DELETE_WINDOW', self.quitting)

    # read queue shared between this main process and spawned child processes
    def readQueueUntilEmpty(self):
        done = False
        text = ''
        while not done:
            try:
                data = self.q.get_nowait()
                text += data
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
            self.stext.insert(Tkconstants.END,msg)
            self.stext.yview_pickplace(Tkconstants.END)
        return


    def get_mobipath(self):
        cwd = os.getcwdu()
        cwd = cwd.encode('utf-8')
        mobipath = tkFileDialog.askopenfilename(
            parent=None, title='Select Unencrypted Kindle eBook File',
            initialdir=self.prefs['mobipath'] or cwd,
            initialfile=None,
            defaultextension=('.mobi', '.prc', '.azw', '.azw4', '.azw3'), filetypes=[('All Kindle formats', ('.mobi', '.prc', '.azw', '.azw4', '.azw3')), ('Kindle Mobi eBook File', '.mobi'), ('Kindle PRC eBook File', '.prc'), ('Kindle AZW eBook File', '.azw'), ('Kindle AZW4 Print Replica', '.azw4'),('Kindle Version 8', '.azw3'),('All Files', '.*')])
        if mobipath:
            self.prefs['mobipath'] = os.path.dirname(mobipath)
            mobipath = os.path.normpath(mobipath)
            mobipath = utf8_str(mobipath)
            self.mobipath.delete(0, Tkconstants.END)
            self.mobipath.insert(0, mobipath)
        return


    def get_apnxpath(self):
        cwd = os.getcwdu()
        cwd = cwd.encode('utf-8')
        apnxpath = tkFileDialog.askopenfilename(
            parent=None, title='Optional APNX file associated with AZW3',
            initialdir=self.prefs['apnxpath'] or cwd,
            initialfile=None,
            defaultextension='.apnx', filetypes=[('Kindle APNX Page Information File', '.apnx'), ('All Files', '.*')])
        if apnxpath:
            self.prefs['apnxpath'] = os.path.dirname(apnxpath)
            apnxpath = os.path.normpath(apnxpath)
            apnxpath = utf8_str(apnxpath)
            self.apnxpath.delete(0, Tkconstants.END)
            self.apnxpath.insert(0, apnxpath)
        return


    def get_outpath(self):
        ucwd = os.getcwdu()
        cwd = ucwd.encode('utf-8')
        if sys.platform.startswith("win"):
            # tk_chooseDirectory is horribly broken for unicode paths
            # on windows - bug has been reported but not fixed for years
            # workaround by using our own unicode aware version
            outpath = AskFolder(message="Folder to Store Output into",
                defaultLocation=self.prefs['outpath'] or os.getcwdu())
        else:
            outpath = tkFileDialog.askdirectory(
                parent=None, title='Folder to Store Output into',
                initialdir=self.prefs['outpath'] or cwd, initialfile=None)
        if outpath:
            self.prefs['outpath'] = outpath
            outpath = os.path.normpath(outpath)
            outpath = utf8_str(outpath)
            self.outpath.delete(0, Tkconstants.END)
            self.outpath.insert(0, outpath)
        return


    def quitting(self):
        # kill any still running subprocess
        if self.p2 != None:
            if (self.p2.exitcode == None):
                self.p2.terminate()
        if PERSISTENT_PREFS:
            if not saveprefs(CONFIGFILE, self.prefs, self):
                print 'Couldn\'t save INI file.'
        self.root.destroy()
        self.quit()


    # run in a child process and collect its output
    def convertit(self):
        # now disable the button to prevent multiple launches
        self.sbotton.configure(state='disabled')
        mobipath = utf8_str(self.mobipath.get())
        apnxpath = utf8_str(self.apnxpath.get())
        outdir = utf8_str(self.outpath.get())
        if not mobipath or not path.exists(mobipath):
            self.status.set('Specified eBook file does not exist')
            self.sbotton.configure(state='normal')
            return
        apnxfile = None
        if apnxpath != "" and path.exists(apnxpath):
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
        else:
            epubversion = 'A'
        log += 'Epub Output Type Set To: {0}\n'.format(self.epubver_val.get())
        if self.hdvar.get():
            use_hd = True
            # stub for processing the Use HD Images setting
            log += 'Use HD Images If Present = True\n'
        log += '\n\n'
        log += 'Please Wait ...\n\n'
        self.stext.insert(Tkconstants.END,log)
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
    except Exception, e:
        print "Error: %s" % e
        rv = 1
    sys.exit(rv)


def main(argv=utf8_argv()):
    root = Tkinter.Tk()
    root.title('Kindle eBook Unpack Tool')
    root.minsize(440, 350)
    root.resizable(True, True)
    MainDialog(root).pack(fill=Tkconstants.BOTH, expand=Tkconstants.YES)
    root.mainloop()
    return 0
    
if __name__ == "__main__":
    sys.exit(main())

