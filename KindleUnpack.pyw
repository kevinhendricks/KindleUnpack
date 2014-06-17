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

from scrolltextwidget import ScrolledText

class MainDialog(Tkinter.Frame):
    def __init__(self, root):
        Tkinter.Frame.__init__(self, root, border=5)
        self.root = root
        self.interval = 50
        self.p2 = None
        self.q = Queue()
        self.status = Tkinter.Label(self, text='Upack a non-DRM Kindle eBook')
        self.status.pack(fill=Tkconstants.X, expand=1)
        body = Tkinter.Frame(self)
        body.pack(fill=Tkconstants.X, expand=1)
        sticky = Tkconstants.E + Tkconstants.W
        body.grid_columnconfigure(1, weight=2)

        Tkinter.Label(body, text='Unencrypted Kindle eBook input file').grid(row=0, sticky=Tkconstants.E)
        self.mobipath = Tkinter.Entry(body, width=50)
        self.mobipath.grid(row=0, column=1, sticky=sticky)
        self.mobipath.insert(0, '')
        button = Tkinter.Button(body, text="Browse...", command=self.get_mobipath)
        button.grid(row=0, column=2)

        Tkinter.Label(body, text='Output Directory').grid(row=1, sticky=Tkconstants.E)
        self.outpath = Tkinter.Entry(body, width=50)
        self.outpath.grid(row=1, column=1, sticky=sticky)
        self.outpath.insert(0, '')
        button = Tkinter.Button(body, text="Browse...", command=self.get_outpath)
        button.grid(row=1, column=2)

        Tkinter.Label(body, text='OPTIONAL: APNX file Associated with AZW3').grid(row=2, sticky=Tkconstants.E)
        self.apnxpath = Tkinter.Entry(body, width=50)
        self.apnxpath.grid(row=2, column=1, sticky=sticky)
        self.apnxpath.insert(0, '')
        button = Tkinter.Button(body, text="Browse...", command=self.get_apnxpath)
        button.grid(row=2, column=2)

        Tkinter.Label(body, text='').grid(row=3, sticky=Tkconstants.E)
        self.splitvar = Tkinter.IntVar()
        checkbox = Tkinter.Checkbutton(body, text="Split Combination KF8 Kindle eBooks", variable=self.splitvar)
        checkbox.grid(row=3, column=1, sticky=Tkconstants.W)

        Tkinter.Label(body, text='').grid(row=4, sticky=Tkconstants.E)
        self.rawvar = Tkinter.IntVar()
        checkbox = Tkinter.Checkbutton(body, text="Write Raw Data", variable=self.rawvar)
        checkbox.grid(row=4, column=1, sticky=Tkconstants.W)

        Tkinter.Label(body, text='').grid(row=5, sticky=Tkconstants.E)
        self.dbgvar = Tkinter.IntVar()
        checkbox = Tkinter.Checkbutton(body, text="Dump Mode", variable=self.dbgvar)
        checkbox.grid(row=5, column=1, sticky=Tkconstants.W)

        msg1 = 'Conversion Log \n\n'
        self.stext = ScrolledText(body, bd=5, relief=Tkconstants.RIDGE, height=30, width=60, wrap=Tkconstants.WORD)
        self.stext.grid(row=6, column=0, columnspan=2,sticky=sticky)
        self.stext.insert(Tkconstants.END,msg1)

        buttons = Tkinter.Frame(self)
        buttons.pack()
        self.sbotton = Tkinter.Button(
            buttons, text="Start", width=10, command=self.convertit)
        self.sbotton.pack(side=Tkconstants.LEFT)

        Tkinter.Frame(buttons, width=10).pack(side=Tkconstants.LEFT)
        self.qbutton = Tkinter.Button(
            buttons, text="Quit", width=10, command=self.quitting)
        self.qbutton.pack(side=Tkconstants.RIGHT)

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
            initialdir=cwd,
            initialfile=None,
            defaultextension='.mobi', filetypes=[('Kindle Mobi eBook File', '.mobi'), ('Kindle PRC eBook File', '.prc'), ('Kindle AZW eBook File', '.azw'), ('Kindle AZW4 Print Replica', '.azw4'),('Kindle Version 8', '.azw3'),('All Files', '.*')])
        if mobipath:
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
            initialdir=cwd,
            initialfile=None,
            defaultextension='.apnx', filetypes=[('Kindle APNX Page Information File', '.apnx'), ('All Files', '.*')])
        if apnxpath:
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
                defaultLocation=os.getcwdu())
        else:
            outpath = tkFileDialog.askdirectory(
                parent=None, title='Folder to Store Output into',
                initialdir=cwd, initialfile=None)
        if outpath:
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
        self.root.destroy()


    # run in a child process and collect its output
    def convertit(self):
        # now disable the button to prevent multiple launches
        self.sbotton.configure(state='disabled')
        mobipath = utf8_str(self.mobipath.get())
        apnxpath = utf8_str(self.apnxpath.get())
        outdir = utf8_str(self.outpath.get())
        if not mobipath or not path.exists(mobipath):
            self.status['text'] = 'Specified eBook file does not exist'
            self.sbotton.configure(state='normal')
            return
        apnxfile = None
        if apnxpath != "" and path.exists(apnxpath):
            apnxfile = apnxpath
        if not outdir:
            self.status['text'] = 'No output directory specified'
            self.sbotton.configure(state='normal')
            return
        q = self.q
        log = 'Input Path = "'+ mobipath + '"\n'
        log += 'Output Path = "' + outdir + '"\n'
        dump = False
        writeraw = False
        splitcombos = False
        if self.dbgvar.get() == 1:
            dump = True
            log += 'Debug = True\n'
        if self.rawvar.get() == 1:
            writeraw = True
            log += 'WriteRawML = True\n'
        if self.splitvar.get() == 1:
            splitcombos = True
            log += 'Split Combo KF8 Kindle eBooks = True\n'
        log += '\n\n'
        log += 'Please Wait ...\n\n'
        self.stext.insert(Tkconstants.END,log)
        self.p2 = Process(target=unpackEbook, args=(q, mobipath, outdir, apnxfile, dump, writeraw, splitcombos))
        self.p2.start()

        # python does not seem to allow you to create
        # your own eventloop which every other gui does - strange 
        # so need to use the widget "after" command to force
        # event loop to run non-gui events every interval
        self.stext.after(self.interval,self.processQueue)
        return


# child process / multiprocessing thread starts here
def unpackEbook(q, infile, outdir, apnxfile, dump, writeraw, splitcombos):
    sys.stdout = QueuedStream(sys.stdout, q)
    sys.stderr = QueuedStream(sys.stderr, q)
    rv = 0
    try:
        kindleunpack.unpackBook(infile, outdir, apnxfile, dodump=dump, dowriteraw=writeraw, dosplitcombos=splitcombos)
    except Exception, e:
        print "Error: %s" % e
        rv = 1
    sys.exit(rv)


def main(argv=utf8_argv()):
    root = Tkinter.Tk()
    root.title('Kindle eBook Unpack Tool')
    root.resizable(True, False)
    root.minsize(300, 0)
    MainDialog(root).pack(fill=Tkconstants.X, expand=1)
    root.mainloop()
    return 0
    
if __name__ == "__main__":
    sys.exit(main())

