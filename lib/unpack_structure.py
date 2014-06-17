#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

DUMP = False
""" Set to True to dump all possible information. """

import sys
import os

import struct, zlib, zipfile
import re, binascii
import path
from path import pathof

class unpackException(Exception):
    pass

class ZipInfo(zipfile.ZipInfo):
    def __init__(self, *args, **kwargs):
        if 'compress_type' in kwargs:
            compress_type = kwargs.pop('compress_type')
        super(ZipInfo, self).__init__(*args, **kwargs)
        self.compress_type = compress_type

class fileNames:
    def __init__(self, infile, outdir):
        self.infile = infile
        self.outdir = outdir
        if not path.exists(outdir):
            path.mkdir(outdir)
        self.mobi7dir = os.path.join(outdir,'mobi7')
        if not path.exists(self.mobi7dir):
            path.mkdir(self.mobi7dir)
        self.imgdir = os.path.join(self.mobi7dir, 'Images')
        if not path.exists(self.imgdir):
            path.mkdir(self.imgdir)
        self.hdimgdir = os.path.join(outdir,'HDImages')
        if not path.exists(self.hdimgdir):
            path.mkdir(self.hdimgdir)
        self.outbase = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0])

    def getInputFileBasename(self):
        return os.path.splitext(os.path.basename(self.infile))[0]

    def makeK8Struct(self):
        outdir = self.outdir
        self.k8dir = os.path.join(self.outdir,'mobi8')
        if not path.exists(self.k8dir):
            path.mkdir(self.k8dir)
        self.k8metainf = os.path.join(self.k8dir,'META-INF')
        if not path.exists(self.k8metainf):
            path.mkdir(self.k8metainf)
        self.k8oebps = os.path.join(self.k8dir,'OEBPS')
        if not path.exists(self.k8oebps):
            path.mkdir(self.k8oebps)
        self.k8images = os.path.join(self.k8oebps,'Images')
        if not path.exists(self.k8images):
            path.mkdir(self.k8images)
        self.k8fonts = os.path.join(self.k8oebps,'Fonts')
        if not path.exists(self.k8fonts):
            path.mkdir(self.k8fonts)
        self.k8styles = os.path.join(self.k8oebps,'Styles')
        if not path.exists(self.k8styles):
            path.mkdir(self.k8styles)
        self.k8text = os.path.join(self.k8oebps,'Text')
        if not path.exists(self.k8text):
            path.mkdir(self.k8text)

    # recursive zip creation support routine
    def zipUpDir(self, myzip, tdir, localname):
        currentdir = tdir
        if localname != "":
            currentdir = os.path.join(currentdir,localname)
        list = path.listdir(currentdir)
        for file in list:
            afilename = file
            localfilePath = os.path.join(localname, afilename)
            realfilePath = os.path.join(currentdir,file)
            if path.isfile(realfilePath):
                myzip.write(pathof(realfilePath), pathof(localfilePath), zipfile.ZIP_DEFLATED)
            elif path.isdir(realfilePath):
                self.zipUpDir(myzip, tdir, localfilePath)

    def makeEPUB(self, usedmap, obfuscate_data, uid):
        bname = os.path.join(self.k8dir, self.getInputFileBasename() + '.epub')
        # Create an encryption key for Adobe font obfuscation
        # based on the epub's uid
        if obfuscate_data:
            key = re.sub(r'[^a-fA-F0-9]', '', uid)
            key = binascii.unhexlify((key + key)[:32])

        # copy over all images and fonts that are actually used in the ebook
        # and remove all font files from mobi7 since not supported
        imgnames = path.listdir(self.imgdir)
        for name in imgnames:
            if usedmap.get(name,'not used') == 'used':
                filein = os.path.join(self.imgdir,name)
                if name.endswith(".ttf"):
                    fileout = os.path.join(self.k8fonts,name)
                elif name.endswith(".otf"):
                    fileout = os.path.join(self.k8fonts,name)
                elif name.endswith(".failed"):
                    fileout = os.path.join(self.k8fonts,name)
                else:
                    fileout = os.path.join(self.k8images,name)
                data = open(pathof(filein),'rb').read()
                if obfuscate_data:
                    if name in obfuscate_data:
                        data = mangle_fonts(key, data)
                open(pathof(fileout),'wb').write(data)
                if name.endswith(".ttf") or name.endswith(".otf"):
                    os.remove(pathof(filein))

        # opf file name hard coded to "content.opf"
        container = '<?xml version="1.0" encoding="UTF-8"?>\n'
        container += '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        container += '    <rootfiles>\n'
        container += '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        container += '    </rootfiles>\n</container>\n'
        fileout = os.path.join(self.k8metainf,'container.xml')
        open(pathof(fileout),'wb').write(container)

        if obfuscate_data:
            encryption = '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" \
xmlns:enc="http://www.w3.org/2001/04/xmlenc#" xmlns:deenc="http://ns.adobe.com/digitaleditions/enc">\n'
            for font in obfuscate_data:
                encryption += '  <enc:EncryptedData>\n'
                encryption += '    <enc:EncryptionMethod Algorithm="http://ns.adobe.com/pdf/enc#RC"/>\n'
                encryption += '    <enc:CipherData>\n'
                encryption += '      <enc:CipherReference URI="OEBPS/Fonts/' + font + '"/>\n'
                encryption += '    </enc:CipherData>\n'
                encryption += '  </enc:EncryptedData>\n'
            encryption += '</encryption>\n'
            fileout = os.path.join(self.k8metainf,'encryption.xml')
            open(pathof(fileout),'wb').write(encryption)

        # ready to build epub
        self.outzip = zipfile.ZipFile(pathof(bname), 'w')

        # add the mimetype file uncompressed
        mimetype = 'application/epub+zip'
        fileout = os.path.join(self.k8dir,'mimetype')
        open(pathof(fileout),'wb').write(mimetype)
        nzinfo = ZipInfo('mimetype', compress_type=zipfile.ZIP_STORED)
        self.outzip.writestr(nzinfo, mimetype)

        self.zipUpDir(self.outzip,self.k8dir,'META-INF')

        self.zipUpDir(self.outzip,self.k8dir,'OEBPS')
        self.outzip.close()
