#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Changelog
#  0.11 - Version by adamselene
#  0.11pd - Tweaked version by pdurrant
#  0.12 - extracts pictures too, and all into a folder.
#  0.13 - added back in optional output dir for those who don't want it based on infile
#  0.14 - auto flush stdout and wrapped in main, added proper return codes
#  0.15 - added support for metadata
#  0.16 - metadata now starting to be output as an opf file (PD)
#  0.17 - Also created tweaked text as source for Mobipocket Creator
#  0.18 - removed raw mobi file completely but kept _meta.html file for ease of conversion
#  0.19 - added in metadata for ASIN, Updated Title and Rights to the opf
#  0.20 - remove _meta.html since no longer needed
#  0.21 - Fixed some typos in the opf output, and also updated handling
#         of test for trailing data/multibyte characters
#  0.22 - Fixed problem with > 9 images
#  0.23 - Now output Start guide item
#  0.24 - Set firstaddl value for 'TEXtREAd'
#  0.25 - Now added character set metadata to html file for utf-8 files.
#  0.26 - Dictionary support added. Image handling speed improved.
#         For huge files create temp files to speed up decoding.
#         Language decoding fixed. Metadata is now converted to utf-8 when written to opf file.
#  0.27 - Add idx:entry attribute "scriptable" if dictionary contains entry length tags.
#         Don't save non-image sections as images. Extract and save source zip file
#         included by kindlegen as kindlegensrc.zip.
#  0.28 - Added back correct image file name extensions, created FastConcat class to simplify and clean up
#  0.29 - Metadata handling reworked, multiple entries of the same type are now supported.
#         Several missing types added.
#         FastConcat class has been removed as in-memory handling with lists is faster, even for huge files.
#  0.30 - Add support for outputting **all** metadata values - encode content with hex if of unknown type
#  0.31 - Now supports Print Replica ebooks, outputting PDF and mysterious data sections
#  0.32 - Now supports NCX file extraction/building.
#                 Overhauled the structure of mobiunpack to be more class oriented.
#  0.33 - Split Classes ito separate files and added prelim support for KF8 format eBooks
#  0.34 - Improved KF8 support, guide support, bug fixes
#  0.35 - Added splitting combo mobi7/mobi8 into standalone mobi7 and mobi8 files
#         Also handle mobi8-only file properly
#  0.36 - very minor changes to support KF8 mobis with no flow items, no ncx, etc
#  0.37 - separate output, add command line switches to control, interface to Mobi_Unpack.pyw
#  0.38 - improve split function by resetting flags properly, fix bug in Thumbnail Images
#  0.39 - improve split function so that ToC info is not lost for standalone mobi8s
#  0.40 - make mobi7 split match official versions, add support for graphic novel metadata,
#         improve debug for KF8
#  0.41 - fix when StartOffset set to 0xffffffff, fix to work with older mobi versions,
#         fix other minor metadata issues
#  0.42 - add new class interface to allow it to integrate more easily with internal calibre routines
#  0.43 - bug fixes for new class interface
#  0.44 - more bug fixes and fix for potnetial bug caused by not properly closing created zip archive
#  0.45 - sync to version in the new Mobi_Unpack plugin
#  0.46 - fixes for: obfuscated fonts, improper toc links and ncx, add support for opentype fonts
#  0.47 - minor opf improvements
#  0.48 - ncx link fixes
#  0.49 - use azw3 when splitting mobis
#  0.50 - unknown change
#  0.51 - fix for converting filepos links to hrefs, Added GPL3 notice, made KF8 extension just '.azw3'
#  0.52 - fix for cover metadata (no support for Mobipocket Creator)
#  0.53 - fix for proper identification of embedded fonts, added new metadata items
#  0.54 - Added error-handling so wonky embedded fonts don't bomb the whole unpack process,
#         entity escape KF8 metadata to ensure valid OPF.
#  0.55  Strip extra StartOffset EXTH from the mobi8 header when splitting, keeping only the relevant one
#         For mobi8 files, don't generate duplicate guide entries from the metadata if we could extract one
#         from the OTH table.
#  0.56 - Added further entity escaping of OPF text.
#         Allow unicode string file paths to be passed as arguments to the unpackBook method without blowing up later
#         when the attempt to "re"-unicode a portion of that filename occurs in the process_all_mobi_headers method.
#  0.57 - Fixed eror when splitting Preview files downloaded from KDP website
#  0.58 - Output original kindlegen build log ('CMET' record) if included in the package.
#  0.58 - Include and extend functionality of DumpMobiHeader, replacing DEBUG with DUMP
#  0.59 - Much added DUMP functionality, including full dumping and descriptions of sections
#  0.60 - Encoding chapter names in UTF-8. This fixes NCX and OPF files from being encoded in non UTF-8 encodings. By Nicholas LeBlanc.

DUMP = False
""" Set to True to dump all possible information. """

WRITE_RAW_DATA = False
""" Set to True to create additional files with raw data for debugging/reverse engineering. """

SPLIT_COMBO_MOBIS = False
""" Set to True to split combination mobis into mobi7 and mobi8 pieces. """

EOF_RECORD = chr(0xe9) + chr(0x8e) + "\r\n"
""" The EOF record content. """

KINDLEGENSRC_FILENAME = "kindlegensrc.zip"
""" The name for the kindlegen source archive. """

KINDLEGENLOG_FILENAME = "kindlegenbuild.log"
""" The name for the kindlegen build log. """

K8_BOUNDARY = "BOUNDARY"
""" The section data that divides K8 mobi ebooks. """

class Unbuffered:
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
    def __getattr__(self, attr):
        return getattr(self.stream, attr)
import sys
sys.stdout=Unbuffered(sys.stdout)


import array, struct, os, re, imghdr, zlib, zipfile, datetime
import getopt, binascii

# import the mobiunpack support libraries
from mobi_utils import getLanguage, toHex, fromBase32, toBase32, mangle_fonts
from mobi_uncompress import HuffcdicReader, PalmdocReader, UncompressedReader
from mobi_opf import OPFProcessor
from mobi_html import HTMLProcessor, XHTMLK8Processor
from mobi_ncx import ncxExtract
from mobi_dict import dictSupport
from mobi_k8proc import K8Processor
from mobi_split import mobi_split

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
        if not os.path.exists(outdir):
            os.mkdir(outdir)
        self.mobi7dir = os.path.join(outdir,'mobi7')
        if not os.path.exists(self.mobi7dir):
            os.mkdir(self.mobi7dir)

        self.imgdir = os.path.join(self.mobi7dir, 'Images')
        if not os.path.exists(self.imgdir):
            os.mkdir(self.imgdir)
        self.outbase = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0])

    def getInputFileBasename(self):
        return os.path.splitext(os.path.basename(self.infile))[0]

    def makeK8Struct(self):
        outdir = self.outdir
        self.k8dir = os.path.join(self.outdir,'mobi8')
        if not os.path.exists(self.k8dir):
            os.mkdir(self.k8dir)
        self.k8metainf = os.path.join(self.k8dir,'META-INF')
        if not os.path.exists(self.k8metainf):
            os.mkdir(self.k8metainf)
        self.k8oebps = os.path.join(self.k8dir,'OEBPS')
        if not os.path.exists(self.k8oebps):
            os.mkdir(self.k8oebps)
        self.k8images = os.path.join(self.k8oebps,'Images')
        if not os.path.exists(self.k8images):
            os.mkdir(self.k8images)
        self.k8fonts = os.path.join(self.k8oebps,'Fonts')
        if not os.path.exists(self.k8fonts):
            os.mkdir(self.k8fonts)
        self.k8styles = os.path.join(self.k8oebps,'Styles')
        if not os.path.exists(self.k8styles):
            os.mkdir(self.k8styles)
        self.k8text = os.path.join(self.k8oebps,'Text')
        if not os.path.exists(self.k8text):
            os.mkdir(self.k8text)

    # recursive zip creation support routine
    def zipUpDir(self, myzip, tdir, localname):
        currentdir = tdir
        if localname != "":
            currentdir = os.path.join(currentdir,localname)
        list = os.listdir(currentdir)
        for file in list:
            afilename = file
            localfilePath = os.path.join(localname, afilename)
            realfilePath = os.path.join(currentdir,file)
            if os.path.isfile(realfilePath):
                myzip.write(realfilePath, localfilePath, zipfile.ZIP_DEFLATED)
            elif os.path.isdir(realfilePath):
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
        imgnames = os.listdir(self.imgdir)
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
                data = file(filein,'rb').read()
                if obfuscate_data:
                    if name in obfuscate_data:
                        data = mangle_fonts(key, data)
                file(fileout,'wb').write(data)
                if name.endswith(".ttf") or name.endswith(".otf"):
                    os.remove(filein)

        # opf file name hard coded to "content.opf"
        container = '<?xml version="1.0" encoding="UTF-8"?>\n'
        container += '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        container += '    <rootfiles>\n'
        container += '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        container += '    </rootfiles>\n</container>\n'
        fileout = os.path.join(self.k8metainf,'container.xml')
        file(fileout,'wb').write(container)

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
            file(fileout,'wb').write(encryption)

        # ready to build epub
        self.outzip = zipfile.ZipFile(bname, 'w')

        # add the mimetype file uncompressed
        mimetype = 'application/epub+zip'
        fileout = os.path.join(self.k8dir,'mimetype')
        file(fileout,'wb').write(mimetype)
        nzinfo = ZipInfo('mimetype', compress_type=zipfile.ZIP_STORED)
        self.outzip.writestr(nzinfo, mimetype)

        self.zipUpDir(self.outzip,self.k8dir,'META-INF')

        self.zipUpDir(self.outzip,self.k8dir,'OEBPS')
        self.outzip.close()

def datetimefrompalmtime(palmtime):
    if palmtime > 0x7FFFFFFF:
        pythondatetime = datetime.datetime(year=1904,month=1,day=1)+datetime.timedelta(seconds=palmtime)
    else:
        pythondatetime = datetime.datetime(year=1970,month=1,day=1)+datetime.timedelta(seconds=palmtime)
    return pythondatetime


class Sectionizer:
    def __init__(self, filename):
        self.data = open(filename, 'rb').read()
        self.palmheader = self.data[:78]
        self.palmname = self.data[:32]
        self.ident = self.palmheader[0x3C:0x3C+8]
        self.num_sections, = struct.unpack_from('>H', self.palmheader, 76)
        self.filelength = len(self.data)
        sectionsdata = struct.unpack_from('>%dL' % (self.num_sections*2), self.data, 78) + (self.filelength, 0)
        self.sectionoffsets = sectionsdata[::2]
        self.sectionattributes = sectionsdata[1::2]
        self.sectiondescriptions = ["" for x in range(self.num_sections+1)]
        self.sectiondescriptions[-1] = "File Length Only"
        return

    def dumpsectionsinfo(self):
        print "Section     Offset  Length      UID Attribs Description"
        for i in xrange(self.num_sections):
            print "%3d %3X  0x%07X 0x%05X % 8d % 7d %s" % (i,i, self.sectionoffsets[i], self.sectionoffsets[i+1] - self.sectionoffsets[i], self.sectionattributes[i]&0xFFFFFF, (self.sectionattributes[i]>>24)&0xFF, self.sectiondescriptions[i])
        print "%3d %3X  0x%07X                          %s" % (self.num_sections,self.num_sections, self.sectionoffsets[self.num_sections], self.sectiondescriptions[self.num_sections])

    def setsectiondescription(self, section, description):
        if section < len(self.sectiondescriptions):
            self.sectiondescriptions[section] = description
        else:
            print "Section out of range: %d, description %s" % (section,description)

    def dumppalmheader(self):
        print "Palm Database Header"
        print "Database name: " + repr(self.palmheader[:32])
        dbattributes, = struct.unpack_from('>H', self.palmheader, 32)
        print "Bitfield attributes: 0x%0X" % dbattributes,
        if dbattributes != 0:
            print " ( ",
            if (dbattributes & 2):
                print "Read-only; ",
            if (dbattributes & 4):
                print "Dirty AppInfoArea; ",
            if (dbattributes & 8):
                print "Needs to be backed up; ",
            if (dbattributes & 16):
                print "OK to install over newer; ",
            if (dbattributes & 32):
                print "Reset after installation; ",
            if (dbattributes & 64):
                print "No copying by PalmPilot beaming; ",
            print ")"
        else:
            print ""
        print "File version: %d" % struct.unpack_from('>H', self.palmheader, 34)[0]
        dbcreation, = struct.unpack_from('>L', self.palmheader, 36)
        print "Creation Date: " + str(datetimefrompalmtime(dbcreation))+ (" (0x%0X)" % dbcreation)
        dbmodification, = struct.unpack_from('>L', self.palmheader, 40)
        print "Modification Date: " + str(datetimefrompalmtime(dbmodification))+ (" (0x%0X)" % dbmodification)
        dbbackup, = struct.unpack_from('>L', self.palmheader, 44)
        if dbbackup != 0:
            print "Backup Date: " + str(datetimefrompalmtime(dbbackup))+ (" (0x%0X)" % dbbackup)
        print "Modification No.: %d" % struct.unpack_from('>L', self.palmheader, 48)[0]
        print "App Info offset: 0x%0X" % struct.unpack_from('>L', self.palmheader, 52)[0]
        print "Sort Info offset: 0x%0X" % struct.unpack_from('>L', self.palmheader, 56)[0]
        print "Type/Creator: %s/%s" % (repr(self.palmheader[60:64]), repr(self.palmheader[64:68]))
        print "Unique seed: 0x%0X" % struct.unpack_from('>L', self.palmheader, 68)[0]
        expectedzero, = struct.unpack_from('>L', self.palmheader, 72)
        if expectedzero != 0:
            print "Should be zero but isn't: %d" % struct.unpack_from('>L', self.palmheader, 72)[0]
        print "Number of sections: %d" % struct.unpack_from('>H', self.palmheader, 76)[0]
        return


    def loadSection(self, section):
        before, after = self.sectionoffsets[section:section+2]
        return self.data[before:after]

def sortedHeaderKeys(mheader):
    hdrkeys = sorted(mheader.keys(), key=lambda akey: mheader[akey][0])
    return hdrkeys


class MobiHeader:
    # all values are packed in big endian format
    palmdoc_header = {
            'compression_type'  : (0x00, '>H', 2),
            'fill0'             : (0x02, '>H', 2),
            'text_length'       : (0x04, '>L', 4),
            'text_records'      : (0x08, '>H', 2),
            'max_section_size'  : (0x0a, '>H', 2),
            'read_pos   '       : (0x0c, '>L', 4),
    }

    mobi6_header = {
            'compression_type'  : (0x00, '>H', 2),
            'fill0'             : (0x02, '>H', 2),
            'text_length'       : (0x04, '>L', 4),
            'text_records'      : (0x08, '>H', 2),
            'max_section_size'  : (0x0a, '>H', 2),
            'crypto_type'       : (0x0c, '>H', 2),
            'fill1'             : (0x0e, '>H', 2),
            'magic'             : (0x10, '4s', 4),
            'header_length (from MOBI)'     : (0x14, '>L', 4),
            'type'              : (0x18, '>L', 4),
            'codepage'          : (0x1c, '>L', 4),
            'unique_id'         : (0x20, '>L', 4),
            'version'           : (0x24, '>L', 4),
            'metaorthindex'     : (0x28, '>L', 4),
            'metainflindex'     : (0x2c, '>L', 4),
            'index_names'       : (0x30, '>L', 4),
            'index_keys'        : (0x34, '>L', 4),
            'extra_index0'      : (0x38, '>L', 4),
            'extra_index1'      : (0x3c, '>L', 4),
            'extra_index2'      : (0x40, '>L', 4),
            'extra_index3'      : (0x44, '>L', 4),
            'extra_index4'      : (0x48, '>L', 4),
            'extra_index5'      : (0x4c, '>L', 4),
            'first_nontext'     : (0x50, '>L', 4),
            'title_offset'      : (0x54, '>L', 4),
            'title_length'      : (0x58, '>L', 4),
            'language_code'     : (0x5c, '>L', 4),
            'dict_in_lang'      : (0x60, '>L', 4),
            'dict_out_lang'     : (0x64, '>L', 4),
            'min_version'       : (0x68, '>L', 4),
            'first_resc_offset' : (0x6c, '>L', 4),
            'huff_offset'       : (0x70, '>L', 4),
            'huff_num'          : (0x74, '>L', 4),
            'huff_tbl_offset'   : (0x78, '>L', 4),
            'huff_tbl_len'      : (0x7c, '>L', 4),
            'exth_flags'        : (0x80, '>L', 4),
            'fill3_a'           : (0x84, '>L', 4),
            'fill3_b'           : (0x88, '>L', 4),
            'fill3_c'           : (0x8c, '>L', 4),
            'fill3_d'           : (0x90, '>L', 4),
            'fill3_e'           : (0x94, '>L', 4),
            'fill3_f'           : (0x98, '>L', 4),
            'fill3_g'           : (0x9c, '>L', 4),
            'fill3_h'           : (0xa0, '>L', 4),
            'unknown0'          : (0xa4, '>L', 4),
            'drm_offset'        : (0xa8, '>L', 4),
            'drm_count'         : (0xac, '>L', 4),
            'drm_size'          : (0xb0, '>L', 4),
            'drm_flags'         : (0xb4, '>L', 4),
            'fill4_a'           : (0xb8, '>L', 4),
            'fill4_b'           : (0xbc, '>L', 4),
            'first_content'     : (0xc0, '>H', 2),
            'last_content'      : (0xc2, '>H', 2),
            'unknown0'          : (0xc4, '>L', 4),
            'fcis_offset'       : (0xc8, '>L', 4),
            'fcis_count'        : (0xcc, '>L', 4),
            'flis_offset'       : (0xd0, '>L', 4),
            'flis_count'        : (0xd4, '>L', 4),
            'unknown1'          : (0xd8, '>L', 4),
            'unknown2'          : (0xdc, '>L', 4),
            'srcs_offset'       : (0xe0, '>L', 4),
            'srcs_count'        : (0xe4, '>L', 4),
            'unknown3'          : (0xe8, '>L', 4),
            'unknown4'          : (0xec, '>L', 4),
            'fill5'             : (0xf0, '>H', 2),
            'traildata_flags'   : (0xf2, '>H', 2),
            'ncx_index'         : (0xf4, '>L', 4),
            'unknown5'          : (0xf8, '>L', 4),
            'unknown6'          : (0xfc, '>L', 4),
            'datp_offset'       : (0x100, '>L', 4),
            'unknown7'          : (0x104, '>L', 4),
            'Unknown    '       : (0x108, '>L', 4),
            'Unknown    '       : (0x10C, '>L', 4),
            'Unknown    '       : (0x110, '>L', 4),
            'Unknown    '       : (0x114, '>L', 4),
            'Unknown    '       : (0x118, '>L', 4),
            'Unknown    '       : (0x11C, '>L', 4),
            'Unknown    '       : (0x120, '>L', 4),
            'Unknown    '       : (0x124, '>L', 4),
            'Unknown    '       : (0x128, '>L', 4),
            'Unknown    '       : (0x12C, '>L', 4),
            'Unknown    '       : (0x130, '>L', 4),
            'Unknown    '       : (0x134, '>L', 4),
            'Unknown    '       : (0x138, '>L', 4),
            'Unknown    '       : (0x11C, '>L', 4),
            }

    mobi8_header = {
            'compression_type'  : (0x00, '>H', 2),
            'fill0'             : (0x02, '>H', 2),
            'text_length'       : (0x04, '>L', 4),
            'text_records'      : (0x08, '>H', 2),
            'max_section_size'  : (0x0a, '>H', 2),
            'crypto_type'       : (0x0c, '>H', 2),
            'fill1'             : (0x0e, '>H', 2),
            'magic'             : (0x10, '4s', 4),
            'header_length (from MOBI)'     : (0x14, '>L', 4),
            'type'              : (0x18, '>L', 4),
            'codepage'          : (0x1c, '>L', 4),
            'unique_id'         : (0x20, '>L', 4),
            'version'           : (0x24, '>L', 4),
            'metaorthindex'     : (0x28, '>L', 4),
            'metainflindex'     : (0x2c, '>L', 4),
            'index_names'       : (0x30, '>L', 4),
            'index_keys'        : (0x34, '>L', 4),
            'extra_index0'      : (0x38, '>L', 4),
            'extra_index1'      : (0x3c, '>L', 4),
            'extra_index2'      : (0x40, '>L', 4),
            'extra_index3'      : (0x44, '>L', 4),
            'extra_index4'      : (0x48, '>L', 4),
            'extra_index5'      : (0x4c, '>L', 4),
            'first_nontext'     : (0x50, '>L', 4),
            'title_offset'      : (0x54, '>L', 4),
            'title_length'      : (0x58, '>L', 4),
            'language_code'     : (0x5c, '>L', 4),
            'dict_in_lang'      : (0x60, '>L', 4),
            'dict_out_lang'     : (0x64, '>L', 4),
            'min_version'       : (0x68, '>L', 4),
            'first_resc_offset' : (0x6c, '>L', 4),
            'huff_offset'       : (0x70, '>L', 4),
            'huff_num'          : (0x74, '>L', 4),
            'huff_tbl_offset'   : (0x78, '>L', 4),
            'huff_tbl_len'      : (0x7c, '>L', 4),
            'exth_flags'        : (0x80, '>L', 4),
            'fill3_a'           : (0x84, '>L', 4),
            'fill3_b'           : (0x88, '>L', 4),
            'fill3_c'           : (0x8c, '>L', 4),
            'fill3_d'           : (0x90, '>L', 4),
            'fill3_e'           : (0x94, '>L', 4),
            'fill3_f'           : (0x98, '>L', 4),
            'fill3_g'           : (0x9c, '>L', 4),
            'fill3_h'           : (0xa0, '>L', 4),
            'unknown0'          : (0xa4, '>L', 4),
            'drm_offset'        : (0xa8, '>L', 4),
            'drm_count'         : (0xac, '>L', 4),
            'drm_size'          : (0xb0, '>L', 4),
            'drm_flags'         : (0xb4, '>L', 4),
            'fill4_a'           : (0xb8, '>L', 4),
            'fill4_b'           : (0xbc, '>L', 4),
            'fdst_offset'       : (0xc0, '>L', 4),
            'fdst_flow_count'   : (0xc4, '>L', 4),
            'fcis_offset'       : (0xc8, '>L', 4),
            'fcis_count'        : (0xcc, '>L', 4),
            'flis_offset'       : (0xd0, '>L', 4),
            'flis_count'        : (0xd4, '>L', 4),
            'unknown1'          : (0xd8, '>L', 4),
            'unknown2'          : (0xdc, '>L', 4),
            'srcs_offset'       : (0xe0, '>L', 4),
            'srcs_count'        : (0xe4, '>L', 4),
            'unknown3'          : (0xe8, '>L', 4),
            'unknown4'          : (0xec, '>L', 4),
            'fill5'             : (0xf0, '>H', 2),
            'traildata_flags'   : (0xf2, '>H', 2),
            'ncx_index'         : (0xf4, '>L', 4),
            'fragment_index'    : (0xf8, '>L', 4),
            'skeleton_index'    : (0xfc, '>L', 4),
            'datp_offset'       : (0x100, '>L', 4),
            'guide_index'       : (0x104, '>L', 4),
            'Unknown    '       : (0x108, '>L', 4),
            'Unknown    '       : (0x10C, '>L', 4),
            'Unknown    '       : (0x110, '>L', 4),
            'Unknown    '       : (0x114, '>L', 4),
            'Unknown    '       : (0x118, '>L', 4),
            'Unknown    '       : (0x11C, '>L', 4),
            'Unknown    '       : (0x120, '>L', 4),
            'Unknown    '       : (0x124, '>L', 4),
            'Unknown    '       : (0x128, '>L', 4),
            'Unknown    '       : (0x12C, '>L', 4),
            'Unknown    '       : (0x130, '>L', 4),
            'Unknown    '       : (0x134, '>L', 4),
            'Unknown    '       : (0x138, '>L', 4),
            'Unknown    '       : (0x11C, '>L', 4),
            }

    palmdoc_header_sorted_keys = sortedHeaderKeys(palmdoc_header)
    mobi6_header_sorted_keys = sortedHeaderKeys(mobi6_header)
    mobi8_header_sorted_keys = sortedHeaderKeys(mobi8_header)

    id_map_strings = {
        1 : 'Drm Server Id',
        2 : 'Drm Commerce Id',
        3 : 'Drm Ebookbase Book Id',
        100 : 'Creator',
        101 : 'Publisher',
        102 : 'Imprint',
        103 : 'Description',
        104 : 'ISBN',
        105 : 'Subject',
        106 : 'Published',
        107 : 'Review',
        108 : 'Contributor',
        109 : 'Rights',
        110 : 'SubjectCode',
        111 : 'Type',
        112 : 'Source',
        113 : 'ASIN',
        114 : 'versionNumber',
        117 : 'Adult',
        118 : 'Price',
        119 : 'Currency',
        122 : 'fixed-layout',
        123 : 'book-type',
        124 : 'orientation-lock',
        126 : 'original-resolution',
        127 : 'zero-gutter',
        128 : 'zero-margin',
        129 : 'K8(129)_Masthead/Cover_Image',
        132 : 'RegionMagnification',
        200 : 'DictShortName',
        208 : 'Watermark',
        501 : 'Document Type',
        502 : 'last_update_time',
        503 : 'Updated_Title',
        504 : 'ASIN_(504)',
        524 : 'Language_(524)',
        525 : 'TextDirection',
        528 : 'Unknown_Logical_Value_(528)',
        535 : 'Kindlegen_BuildRev_Number',

    }
    id_map_values = {
        115 : 'sample',
        116 : 'StartOffset',
        121 : 'K8(121)_Boundary_Section',
        125 : 'K8(125)_Count_of_Resources_Fonts_Images',
        131 : 'K8(131)_Unidentified_Count',
        201 : 'CoverOffset',
        202 : 'ThumbOffset',
        203 : 'Has Fake Cover',
        204 : 'Creator Software',
        205 : 'Creator Major Version',
        206 : 'Creator Minor Version',
        207 : 'Creator Build Number',
        401 : 'Clipping Limit',
        402 : 'Publisher Limit',
        404 : 'Text to Speech Disabled',
    }
    id_map_hexstrings = {
        209 : 'Tamper Proof Keys (hex)',
        300 : 'Font Signature (hex)',
        403 : 'Unknown',
        405 : 'Unknown',
        406 : 'Unknown',
        403 : 'Unknown',
        450 : 'Unknown',
        451 : 'Unknown',
        452 : 'Unknown',
        453 : 'Unknown',

    }

    def __init__(self, sect, sectNumber):
        self.sect = sect
        self.start = sectNumber
        self.header = self.sect.loadSection(self.start)
        if len(self.header)>20 and self.header[16:20] == 'MOBI':
            self.sect.sectiondescriptions[0] = "Mobipocket Header"
            self.palm = False
        elif self.sect.ident == 'TEXtREAd':
            self.sect.sectiondescriptions[0] = "PalmDOC Header"
            self.palm = True
        else:
            raise unpackException('Unknown File Format')

        self.records, = struct.unpack_from('>H', self.header, 0x8)

        # set defaults in case this is a PalmDOC
        self.title = self.sect.palmname
        self.length = len(self.header)-16
        self.type = 3
        self.codepage = 1252
        self.codec = 'windows-1252'
        self.unique_id = 0
        self.version = 0
        self.hasExth = False
        self.exth = ''
        self.exth_offset = self.length + 16
        self.exth_length = 0
        self.crypto_type = 0
        self.firstnontext = self.start+self.records + 1
        self.firstresource = self.start+self.records + 1
        self.ncxidx = 0xffffffff
        self.metaOrthIndex = 0xffffffff
        self.metaInflIndex = 0xffffffff
        self.skelidx = 0xffffffff
        self.dividx = 0xffffffff
        self.othidx = 0xfffffff
        self.fdst = 0xffffffff
        self.mlstart = self.sect.loadSection(self.start+1)[:4]


        # set up for decompression/unpacking
        self.compression, = struct.unpack_from('>H', self.header, 0x0)
        if self.compression == 0x4448:
            reader = HuffcdicReader()
            huffoff, huffnum = struct.unpack_from('>LL', self.header, 0x70)
            huffoff = huffoff + self.start
            self.sect.setsectiondescription(huffoff,"Huffman Compression Seed")
            reader.loadHuff(self.sect.loadSection(huffoff))
            for i in xrange(1, huffnum):
                self.sect.setsectiondescription(huffoff+i,"Huffman CDIC Compression Seed %d" % i)
                reader.loadCdic(self.sect.loadSection(huffoff+i))
            self.unpack = reader.unpack
        elif self.compression == 2:
            self.unpack = PalmdocReader().unpack
        elif self.compression == 1:
            self.unpack = UncompressedReader().unpack
        else:
            raise unpackException('invalid compression type: 0x%4x' % self.compression)

        if self.palm:
            return

        self.length, self.type, self.codepage, self.unique_id, self.version = struct.unpack('>LLLLL', self.header[20:40])
        codec_map = {
            1252 : 'windows-1252',
            65001: 'utf-8',
        }
        if self.codepage in codec_map.keys():
            self.codec = codec_map[self.codepage]


        # title
        toff, tlen = struct.unpack('>II', self.header[0x54:0x5c])
        tend = toff + tlen
        self.title=self.header[toff:tend]



        exth_flag, = struct.unpack('>L', self.header[0x80:0x84])
        self.hasExth = exth_flag & 0x40
        self.exth = ''
        self.exth_offset = self.length + 16
        self.exth_length = 0
        if self.hasExth:
            self.exth_length, = struct.unpack_from('>L', self.header, self.exth_offset+4)
            self.exth_length = ((self.exth_length + 3)>>2)<<2 # round to next 4 byte boundary
            self.exth = self.header[self.exth_offset:self.exth_offset+self.exth_length]

        self.mlstart = self.sect.loadSection(self.start+1)
        self.mlstart = self.mlstart[0:4]
        self.crypto_type, = struct.unpack_from('>H', self.header, 0xC)

        # Start sector for additional files such as images, fonts, resources, etc
        self.firstresource, = struct.unpack_from('>L', self.header, 0x6C)
        self.firstnontext, = struct.unpack_from('>L', self.header, 0x50)
        if self.firstresource != 0xffffffff:
            self.firstresource += self.start
        if self.firstnontext != 0xffffffff:
            self.firstnontext += self.start

        if self.isPrintReplica():
            return

        if self.version < 8:
            # Dictionary metaOrthIndex
            self.metaOrthIndex, = struct.unpack_from('>L', self.header, 0x28)
            if self.metaOrthIndex != 0xffffffff:
                self.metaOrthIndex += self.start

            # Dictionary metaInflIndex
            self.metaInflIndex, = struct.unpack_from('>L', self.header, 0x2C)
            if self.metaInflIndex != 0xffffffff:
                self.metaInflIndex += self.start

        # handle older headers without any ncxindex info and later
        # specifically 0xe4 headers
        if self.length + 16 < 0xf8:
            return

        # NCX Index
        self.ncxidx, = struct.unpack('>L', self.header[0xf4:0xf8])
        if self.ncxidx != 0xffffffff:
            self.ncxidx += self.start

        # K8 specific Indexes
        if self.start != 0 or self.version == 8:
            # Index into <xml> file skeletons in RawML
            self.skelidx, = struct.unpack_from('>L', self.header, 0xfc)
            if self.skelidx != 0xffffffff:
                self.skelidx += self.start

            # Index into <div> sections in RawML
            self.dividx, = struct.unpack_from('>L', self.header, 0xf8)
            if self.dividx != 0xffffffff:
                self.dividx += self.start

            # Index into Other files
            self.othidx, = struct.unpack_from('>L', self.header, 0x104)
            if self.othidx != 0xffffffff:
                self.othidx += self.start

            # dictionaries do not seem to use the same approach in K8's
            # so disable them
            self.metaOrthIndex = 0xffffffff
            self.metaInflIndex = 0xffffffff

            # need to use the FDST record to find out how to properly unpack
            # the rawML into pieces
            # it is simply a table of start and end locations for each flow piece
            self.fdst, = struct.unpack_from('>L', self.header, 0xc0)
            self.fdstcnt, = struct.unpack_from('>L', self.header, 0xc4)
            # if cnt is 1 or less, fdst section mumber can be garbage
            if self.fdstcnt <= 1:
                self.fdst = 0xffffffff
            if self.fdst != 0xffffffff:
                self.fdst += self.start
                for i in xrange(self.fdstcnt):
                    self.sect.setsectiondescription(self.fdst+i,"FDST Index %d" % i)

    def dump_exth(self):
        # determine text encoding
        codec=self.codec
        if (not self.hasExth) or (self.exth_length) == 0 or (self.exth == ''):
            return
        num_items, = struct.unpack('>L', self.exth[8:12])
        pos = 12
        print "Key Size Decription                     Value"
        for _ in range(num_items):
            id, size = struct.unpack('>LL', self.exth[pos:pos+8])
            contentsize = size-8
            content = self.exth[pos + 8: pos + size]
            if id in MobiHeader.id_map_strings.keys():
                exth_name = MobiHeader.id_map_strings[id]
                print '{0: >3d} {1: >4d} {2: <30s} {3:s}'.format(id, contentsize, exth_name, unicode(content, codec).encode("utf-8"))
            elif id in MobiHeader.id_map_values.keys():
                exth_name = MobiHeader.id_map_values[id]
                if size == 9:
                    value, = struct.unpack('B',content)
                    print '{0:3d} byte {1:<30s} {2:d}'.format(id, exth_name, value)
                elif size == 10:
                    value, = struct.unpack('>H',content)
                    print '{0:3d} word {1:<30s} 0x{2:0>4X} ({2:d})'.format(id, exth_name, value)
                elif size == 12:
                    value, = struct.unpack('>L',content)
                    print '{0:3d} long {1:<30s} 0x{2:0>8X} ({2:d})'.format(id, exth_name, value)
                else:
                    print '{:3d} {:4d} {:<30s} {:s})'.format(id, contentsize, "Bad size for "+exth_name, content.encode('hex'))
            elif id in MobiHeader.id_map_hexstrings.keys():
                exth_name = MobiHeader.id_map_hexstrings[id]
                print '{0:3d} {1:4d} {2:<30s} 0x{3:s}'.format(id, contentsize, exth_name, content.encode('hex'))
            else:
                exth_name = "Unknown EXTH ID {0:d}".format(id)
                print "{0: >3d} {1: >4d} {2: <30s} 0x{3:s}".format(id, contentsize, exth_name, content.encode('hex'))
            pos += size
        return

    def dumpheader(self):
        # first 16 bytes are not part of the official mobiheader
        # but we will treat it as such
        # so section 0 is 16 (decimal) + self.length in total == at least 0x108 bytes for Mobi 8 headers
        print "Dumping section %d, Mobipocket Header version: %d, total length %d" % (self.start,self.version, self.length+16)
        self.hdr = {}
        # set it up for the proper header version
        if self.version == 0:
            self.mobi_header = MobiHeader.palmdoc_header
            self.mobi_header_sorted_keys = MobiHeader.palmdoc_header_sorted_keys
        elif self.version < 8:
            self.mobi_header = MobiHeader.mobi6_header
            self.mobi_header_sorted_keys = MobiHeader.mobi6_header_sorted_keys
        else:
            self.mobi_header = MobiHeader.mobi8_header
            self.mobi_header_sorted_keys = MobiHeader.mobi8_header_sorted_keys

        # parse the header information
        for key in self.mobi_header_sorted_keys:
            (pos, format, tot_len) = self.mobi_header[key]
            if pos < (self.length + 16):
                val, = struct.unpack_from(format, self.header, pos)
                self.hdr[key] = val

        if 'title_offset' in self.hdr:
            title_offset = self.hdr['title_offset']
            title_length = self.hdr['title_length']
        else:
            title_offset = 0
            title_length = 0
        if title_offset == 0:
            title_offset = len(self.header)
            title_length = 0
            self.title = self.sect.palmname
        else:
            self.title = self.header[title_offset:title_offset+title_length]
            # title record always padded with two nul bytes and then padded with nuls to next 4 byte boundary
            title_length = ((title_length+2+3)>>2)<<2

        self.extra1 = self.header[self.exth_offset+self.exth_length:title_offset]
        self.extra2 = self.header[title_offset+title_length:]


        print "Mobipocket header from section %d" % self.start
        print "     Offset  Value Hex Dec        Description"
        for key in self.mobi_header_sorted_keys:
            (pos, format, tot_len) = self.mobi_header[key]
            if pos < (self.length + 16):
                if key != 'magic':
                    fmt_string = "0x{0:0>3X} ({0:3d}){1: >" + str(9-2*tot_len) +"s}0x{2:0>" + str(2*tot_len) + "X} {2:10d} {3:s}"
                else:
                    fmt_string = "0x{0:0>3X} ({0:3d}){2:>11s}            {3:s}"
                print fmt_string.format(pos, " ",self.hdr[key], key)
        print ""

        if self.exth_length > 0:
            print "EXTH metadata, offset %d, padded length %d" % (self.exth_offset,self.exth_length)
            self.dump_exth()
            print ""

        if len(self.extra1) > 0:
            print "Extra data between EXTH and Title, length %d" % len(self.extra1)
            print self.extra1.encode('hex')
            print ""

        if title_length > 0:
            print "Title in header at offset %d, padded length %d: '%s'" %(title_offset,title_length,self.title)
            print ""

        if len(self.extra2) > 0:
            print "Extra data between Title and end of header, length %d" % len(self.extra2)
            print  self.extra2.encode('hex')
            print ""


    def isPrintReplica(self):
        return self.mlstart[0:4] == "%MOP"

    def isK8(self):
        return self.start != 0 or self.version == 8

    def isEncrypted(self):
        return self.crypto_type != 0

    def hasNCX(self):
        return self.ncxidx != 0xffffffff

    def isDictionary(self):
        return self.metaOrthIndex != 0xffffffff

    def getncxIndex(self):
        return self.ncxidx

    def decompress(self, data):
        return self.unpack(data)

    def Language(self):
        langcode = struct.unpack('!L', self.header[0x5c:0x60])[0]
        langid = langcode & 0xFF
        sublangid = (langcode >> 10) & 0xFF
        return [getLanguage(langid, sublangid)]

    def DictInLanguage(self):
        if self.isDictionary():
            langcode = struct.unpack('!L', self.header[0x60:0x64])[0]
            langid = langcode & 0xFF
            sublangid = (langcode >> 10) & 0xFF
            if langid != 0:
                return [getLanguage(langid, sublangid)]
        return False

    def DictOutLanguage(self):
        if self.isDictionary():
            langcode = struct.unpack('!L', self.header[0x64:0x68])[0]
            langid = langcode & 0xFF
            sublangid = (langcode >> 10) & 0xFF
            if langid != 0:
                return [getLanguage(langid, sublangid)]
        return False

    def getRawML(self):
        def getSizeOfTrailingDataEntry(data):
            num = 0
            for v in data[-4:]:
                if ord(v) & 0x80:
                    num = 0
                num = (num << 7) | (ord(v) & 0x7f)
            return num
        def trimTrailingDataEntries(data):
            for _ in xrange(trailers):
                num = getSizeOfTrailingDataEntry(data)
                data = data[:-num]
            if multibyte:
                num = (ord(data[-1]) & 3) + 1
                data = data[:-num]
            return data
        multibyte = 0
        trailers = 0
        if self.sect.ident == 'BOOKMOBI':
            mobi_length, = struct.unpack_from('>L', self.header, 0x14)
            mobi_version, = struct.unpack_from('>L', self.header, 0x68)
            if (mobi_length >= 0xE4) and (mobi_version >= 5):
                flags, = struct.unpack_from('>H', self.header, 0xF2)
                multibyte = flags & 1
                while flags > 1:
                    if flags & 2:
                        trailers += 1
                    flags = flags >> 1
        # get raw mobi markup languge
        print "Unpacking raw markup language"
        dataList = []
        # offset = 0
        for i in xrange(1, self.records+1):
            data = trimTrailingDataEntries(self.sect.loadSection(self.start + i))
            dataList.append(self.unpack(data))
            if self.isK8():
                self.sect.setsectiondescription(self.start + i,"KF8 Text Section {0:d}".format(i))
            elif self.version == 0:
                self.sect.setsectiondescription(self.start + i,"PalmDOC Text Section {0:d}".format(i))
            else:
                self.sect.setsectiondescription(self.start + i,"Mobipocket Text Section {0:d}".format(i))
        return "".join(dataList)

    def getMetaData(self):

        def addValue(name, value):
            if name not in self.metadata:
                self.metadata[name] = [value]
            else:
                self.metadata[name].append(value)

        self.metadata = {}
        codec=self.codec
        if self.hasExth:
            extheader=self.exth
            _length, num_items = struct.unpack('>LL', extheader[4:12])
            extheader = extheader[12:]
            pos = 0
            for _ in range(num_items):
                id, size = struct.unpack('>LL', extheader[pos:pos+8])
                content = extheader[pos + 8: pos + size]
                if id in MobiHeader.id_map_strings.keys():
                    name = MobiHeader.id_map_strings[id]
                    addValue(name, unicode(content, codec).encode("utf-8"))
                elif id in MobiHeader.id_map_values.keys():
                    name = MobiHeader.id_map_values[id]
                    if size == 9:
                        value, = struct.unpack('B',content)
                        addValue(name, str(value))
                    elif size == 10:
                        value, = struct.unpack('>H',content)
                        addValue(name, str(value))
                    elif size == 12:
                        value, = struct.unpack('>L',content)
                        addValue(name, str(value))
                    else:
                        addValue(name, content.encode('hex'))
                elif id in MobiHeader.id_map_hexstrings.keys():
                    name = MobiHeader.id_map_hexstrings[id]
                    addValue(name, content.encode('hex'))
                else:
                    name = str(id) + ' (hex)'
                    addValue(name, content.encode('hex'))
                pos += size
        return self.metadata

    def processPrintReplica(self, files):
        # read in number of tables, and so calculate the start of the indicies into the data
        rawML = self.getRawML()
        numTables, = struct.unpack_from('>L', rawML, 0x04)
        tableIndexOffset = 8 + 4*numTables
        # for each table, read in count of sections, assume first section is a PDF
        # and output other sections as binary files
        paths = []
        for i in xrange(numTables):
            sectionCount, = struct.unpack_from('>L', rawML, 0x08 + 4*i)
            for j in xrange(sectionCount):
                sectionOffset, sectionLength, = struct.unpack_from('>LL', rawML, tableIndexOffset)
                tableIndexOffset += 8
                if j == 0:
                    entryName = os.path.join(files.outdir, files.getInputFileBasename() + ('.%03d.pdf' % (i+1)))
                else:
                    entryName = os.path.join(files.outdir, files.getInputFileBasename() + ('.%03d.%03d.data' % ((i+1),j)))
                file(entryName, 'wb').write(rawML[sectionOffset:(sectionOffset+sectionLength)])


def process_all_mobi_headers(files, sect, mhlst, K8Boundary, k8only=False):
    imgnames = []
    for mh in mhlst:
        if mh.isK8():
            sect.sectiondescriptions[mh.start]="KF8 Header"
            mhname = os.path.join(files.outdir,"header_K8.dat")
            print "Processing K8 section of book..."
        elif mh.isPrintReplica():
            sect.sectiondescriptions[mh.start]="Print Replica Header"
            mhname = os.path.join(files.outdir,"header_PR.dat")
            print "Processing PrintReplica section of book..."
        else:
            if mh.version == 0:
                sect.sectiondescriptions[mh.start]="PalmDoc Header".format(mh.version)
            else:
                sect.sectiondescriptions[mh.start]="Mobipocket {0:d} Header".format(mh.version)
            mhname = os.path.join(files.outdir,"header.dat")
            print "Processing Mobipocket {0:d} section of book...".format(mh.version)

        if DUMP:
            # write out raw mobi header data
            file(mhname, 'wb').write(mh.header)

        # process each mobi header
        if mh.isEncrypted():
            raise unpackException('Book is encrypted')

        # build up the metadata
        metadata = mh.getMetaData()
        metadata['Language'] = mh.Language()
        metadata['Title'] = [unicode(mh.title, mh.codec).encode("utf-8")]
        metadata['Codec'] = [mh.codec]
        metadata['UniqueID'] = [str(mh.unique_id)]

        if not DUMP:
            print "Mobi Version:", mh.version
            print "Codec:", mh.codec
            print "Title:", mh.title
            if 'Updated_Title'  in mh.metadata:
                print "EXTH Title:", str(mh.metadata['Updated_Title'][0])
            if mh.compression == 0x4448:
                print "Huffdic compression"
            elif mh.compression == 2:
                print "Palmdoc compression"
            elif mh.compression == 1:
                print "No compression"
        else:
            mh.dumpheader()

        # save the raw markup language
        rawML = mh.getRawML()
        mh.rawSize = len(rawML)
        if DUMP or WRITE_RAW_DATA:
            ext = '.rawml'
            if mh.isK8():
                outraw = os.path.join(files.k8dir,files.getInputFileBasename() + ext)
            else:
                if mh.isPrintReplica():
                    ext = '.rawpr'
                    outraw = os.path.join(files.outdir,files.getInputFileBasename() + ext)
                else:
                    outraw = os.path.join(files.mobi7dir,files.getInputFileBasename() + ext)
            file(outraw,'wb').write(rawML)


        # process additional sections that represent images, resources, fonts, and etc
        # build up a list of image names to use to postprocess the rawml
        print "Unpacking images, resources, fonts, etc"
        beg = mh.firstresource
        end = sect.num_sections
        if beg < K8Boundary:
            # then we're processing the first part of a combination file
            end = K8Boundary
        obfuscate_data = []
        for i in xrange(beg, end):
            data = sect.loadSection(i)
            type = data[0:4]
            if type in ["FLIS", "FCIS", "FDST", "DATP"]:
                #print "FLIS, etc."
                if DUMP:
                    fname = "%05d" % i
                    fname = type + fname
                    if mh.isK8():
                        fname += "_K8"
                    fname += '.dat'
                    outname= os.path.join(files.outdir, fname)
                    file(outname, 'wb').write(data)
                    print "Dumping section {0:d} type {1:s} to file {2:s} ".format(i,type,outname)
                sect.setsectiondescription(i,"Type {0:s}".format(type))
                imgnames.append(None)
                continue
            elif type == "SRCS":
                #print "SRCS"
                # The mobi file was created by kindlegen and contains a zip archive with all source files.
                # Extract the archive and save it.
                print "File contains kindlegen source archive, extracting as %s" % KINDLEGENSRC_FILENAME
                srcname = os.path.join(files.outdir, KINDLEGENSRC_FILENAME)
                file(srcname, 'wb').write(data[16:])
                imgnames.append(None)
                sect.setsectiondescription(i,"Zipped Source Files")
                continue
            elif type == "CMET":
                #print "CMET"
                # The mobi file was created by kindlegen v2.7 or greater and contains the original build log.
                # Extract the log and save it.
                print "File contains kindlegen build log, extracting as %s" % KINDLEGENLOG_FILENAME
                srcname = os.path.join(files.outdir, KINDLEGENLOG_FILENAME)
                file(srcname, 'wb').write(data[10:])
                imgnames.append(None)
                sect.setsectiondescription(i,"Kindlegen log")
                continue
            elif type == "FONT":
                #print "FONT"
                # fonts only exist in K8 ebooks
                # Format:
                # bytes  0 -  3:  'FONT'
                # bytes  4 -  7:  uncompressed size
                # bytes  8 - 11:  flags
                #                     bit 0x0001 - zlib compression
                #                     bit 0x0002 - obfuscated with xor string
                # bytes 12 - 15:  offset to start of compressed font data
                # bytes 16 - 19:  length of xor string stored before the start of the comnpress font data
                # bytes 19 - 23:  start of xor string
                fontname = "font%05d" % i
                ext = '.dat'
                font_error = False
                font_data = data # Raw section data preserved if an error occurs
                try:
                    usize, fflags, dstart, xor_len, xor_start = struct.unpack_from('>LLLLL',data,4)
                except:
                    print "Failed to extract font: {0:s} from section {1:d}".format(fontname,i)
                    font_error = True
                    ext = '.failed'
                    pass
                if not font_error:
                    print "Extracting font:", fontname
                    font_data = data[dstart:]
                    extent = len(font_data)
                    extent = min(extent, 1040)
                    if fflags & 0x0002:
                        # obfuscated so need to de-obfuscate the first 1040 bytes
                        key = bytearray(data[xor_start: xor_start+ xor_len])
                        buf = bytearray(font_data)
                        for n in xrange(extent):
                            buf[n] ^=  key[n%xor_len]
                        font_data = bytes(buf)
                    if fflags & 0x0001:
                        # ZLIB compressed data
                        font_data = zlib.decompress(font_data)
                    hdr = font_data[0:4]
                    if hdr == '\0\1\0\0' or hdr == 'true' or hdr == 'ttcf':
                        ext = '.ttf'
                    elif hdr == 'OTTO':
                        ext = '.otf'
                    else:
                        print "Warning: unknown font header %s" % hdr.encode('hex')
                    if (ext == '.ttf' or ext == '.otf') and (fflags & 0x0002):
                        obfuscate_data.append(fontname + ext)
                fontname += ext
                outfnt = os.path.join(files.imgdir, fontname)
                file(outfnt, 'wb').write(font_data)
                imgnames.append(fontname)
                sect.setsectiondescription(i,"Font {0:s}".format(fontname))
                continue

            elif type == "RESC":
                #print "RESC"
                # resources only exist in K8 ebooks
                # not sure what they are, looks like
                # a piece of the top of the original content.opf
                # file, so only write them out
                # if DUMP is True
                if DUMP:
                    data = data[4:]
                    rescname = "resc%05d.dat" % i
                    print "    extracting resource: ", rescname
                    outrsc = os.path.join(files.imgdir, rescname)
                    file(outrsc, 'wb').write(data)
                imgnames.append(None)
                sect.setsectiondescription(i,"Mysterious RESC data")
                continue

            if data == EOF_RECORD:
                #print "EOF"
                imgnames.append(None)
                sect.setsectiondescription(i,"End Of File")
                continue

            # if reach here should be an image but double check to make sure
            # Get the proper file extension
            imgtype = imghdr.what(None, data)
            if imgtype is None:
                print "Warning: Section %s does not contain a recognised resource" % i
                imgnames.append(None)
                sect.setsectiondescription(i,"Mysterious Section, first four bytes '{0:s}' ({1:s})".format(data[0:4],toHex(data[0:4])))
                if DUMP:
                    fname = "unknown%05d.dat" % i
                    outname= os.path.join(files.outdir, fname)
                    file(outname, 'wb').write(data)
                    sect.setsectiondescription(i,"Mysterious Section, first four bytes '{0:s}' ({1:s}), extracting as {2:s}".format(data[0:4],toHex(data[0:4]),fname))
            else:
                imgname = "image%05d.%s" % (i, imgtype)
                print "Extracting image: {0:s} from section {1:d}".format(imgname,i)
                outimg = os.path.join(files.imgdir, imgname)
                file(outimg, 'wb').write(data)
                imgnames.append(imgname)
                sect.setsectiondescription(i,"Image {0:s}".format(imgname))


        # FIXME all of this PrintReplica code is untested!
        # Process print replica book.
        if mh.isPrintReplica() and not k8only:
            filenames = []
            print "Print Replica ebook detected"
            try:
                mh.processPrintReplica(files)
            except Exception, e:
                print 'Error processing Print Replica: ' + str(e)
            filenames.append(['', files.getInputFileBasename() + '.pdf'])
            usedmap = {}
            for name in imgnames:
                if name != None:
                    usedmap[name] = 'used'
            opf = OPFProcessor(files, metadata, filenames, imgnames, False, mh, usedmap)
            opf.writeOPF()
            continue

        if mh.isK8():
            # K8 mobi
            # require other indexes which contain parsing information and the FDST info
            # to process the rawml back into the xhtml files, css files, svg image files, etc
            k8proc = K8Processor(mh, sect, DUMP)
            k8proc.buildParts(rawML)

            # collect information for the guide first
            guidetext = k8proc.getGuideText()
            # if the guide was empty, add in any guide info from metadata, such as StartOffset
            if not guidetext and 'StartOffset' in metadata.keys():
                # Apparently, KG 2.5 carries over the StartOffset from the mobi7 part...
                # This seems to break on some devices that only honors the first StartOffset (FW 3.4), because it effectively points at garbage in the mobi8 part.
                # Taking that into account, we only care about the *last* StartOffset, which should always be the correct one in these cases (the one actually pointing to the right place in the mobi8 part).
                starts = metadata['StartOffset']
                last_start = starts[-1]
                last_start = int(last_start)
                if last_start == 0xffffffff:
                    last_start = 0
                # Argh!!  Some metadata StartOffsets are the row number of the divtbl
                # while others are a position in the file - Not sure how to deal with this issue
                # Safer to assume it is a position
                seq, idtext = k8proc.getDivTblInfo(last_start)
                filename, idtext = k8proc.getIDTagByPosFid(toBase32(seq), '0000000000')
                linktgt = filename
                if idtext != '':
                    linktgt += '#' + idtext
                guidetext += '<reference type="text" href="Text/%s" />\n' % linktgt

            # process the toc ncx
            # ncx map keys: name, pos, len, noffs, text, hlvl, kind, pos_fid, parent, child1, childn, num
            ncx = ncxExtract(mh, files)
            ncx_data = ncx.parseNCX()

            # extend the ncx data with
            # info about filenames and proper internal idtags
            for i in range(len(ncx_data)):
                ncxmap = ncx_data[i]
                [junk1, junk2, junk3, fid, junk4, off] = ncxmap['pos_fid'].split(':')
                filename, idtag = k8proc.getIDTagByPosFid(fid, off)
                ncxmap['filename'] = filename
                ncxmap['idtag'] = idtag
                ncx_data[i] = ncxmap

            # write out the toc.ncx
            ncx.writeK8NCX(ncx_data, metadata)

            # convert the rawML to a set of xhtml files
            htmlproc = XHTMLK8Processor(imgnames, k8proc)
            usedmap = htmlproc.buildXHTML()

            # write out the files
            filenames = []
            n =  k8proc.getNumberOfParts()
            for i in range(n):
                part = k8proc.getPart(i)
                [skelnum, dir, filename, beg, end, aidtext] = k8proc.getPartInfo(i)
                filenames.append([dir, filename])
                fname = os.path.join(files.k8oebps,dir,filename)
                file(fname,'wb').write(part)
            n = k8proc.getNumberOfFlows()
            for i in range(1, n):
                [type, format, dir, filename] = k8proc.getFlowInfo(i)
                flowpart = k8proc.getFlow(i)
                if format == 'file':
                    filenames.append([dir, filename])
                    fname = os.path.join(files.k8oebps,dir,filename)
                    file(fname,'wb').write(flowpart)

            opf = OPFProcessor(files, metadata, filenames, imgnames, ncx.isNCX, mh, usedmap, guidetext)

            if obfuscate_data:
                uuid = opf.writeOPF(True)
            else:
                uuid = opf.writeOPF()

            # make an epub of it all
            files.makeEPUB(usedmap, obfuscate_data, uuid)

        elif not k8only:
            # An original Mobi
            # process the toc ncx
            # ncx map keys: name, pos, len, noffs, text, hlvl, kind, pos_fid, parent, child1, childn, num
            ncx = ncxExtract(mh, files)
            ncx_data = ncx.parseNCX()
            ncx.writeNCX(metadata)

            positionMap = {}
            # If Dictionary build up the positionMap
            if mh.isDictionary():
                if mh.DictInLanguage():
                    metadata['DictInLanguage'] = mh.DictInLanguage()
                if mh.DictOutLanguage():
                    metadata['DictOutLanguage'] = mh.DictOutLanguage()
                positionMap = dictSupport(mh, sect).getPositionMap()

            # convert the rawml back to Mobi ml
            proc = HTMLProcessor(files, metadata, imgnames)
            srctext = proc.findAnchors(rawML, ncx_data, positionMap)
            srctext, usedmap = proc.insertHREFS()
            filenames=[]

            # write the proper mobi html
            fname = files.getInputFileBasename() + '.html'
            filenames.append(['', fname])
            outhtml = os.path.join(files.mobi7dir, fname)
            file(outhtml, 'wb').write(srctext)

            # create an OPF
            # extract guidetext from srctext
            guidetext =''
            guidematch = re.search(r'''<guide>(.*)</guide>''',srctext,re.IGNORECASE+re.DOTALL)
            if guidematch:
                replacetext = r'''href="'''+filenames[0][1]+r'''#filepos\1"'''
                guidetext = re.sub(r'''filepos=['"]{0,1}0*(\d+)['"]{0,1}''', replacetext, guidematch.group(1))
                guidetext += '\n'
                if isinstance(guidetext, unicode):
                    guidetext = guidetext.decode(mh.codec).encode("utf-8")
                else:
                    guidetext = unicode(guidetext, mh.codec).encode("utf-8")
            opf = OPFProcessor(files, metadata, filenames, imgnames, ncx.isNCX, mh, usedmap, guidetext)
            opf.writeOPF()

        # process unknown sections between end of text and resources
        if DUMP:
            print "Unpacking any remaining unknown records"
        beg = mh.start
        end = sect.num_sections
        if beg < K8Boundary:
            # then we're processing the first part of a combination file
            end = K8Boundary
        for i in xrange(beg, end):
            if sect.sectiondescriptions[i] == "":
                data = sect.loadSection(i)
                type = data[0:4]
                if type == "INDX":
                    fname = "Unknown%05d(INDX).dat" % i
                    description = "Unknown INDX section"
                else:
                    fname = "unknown%05d.dat" % i
                    description = "Mysterious Section, first four bytes '{0}' ({1})".format(data[0:4],toHex(data[0:4]))
                if DUMP:
                    outname= os.path.join(files.outdir, fname)
                    file(outname, 'wb').write(data)
                    print "Extracting {0}: {1} from section {2:d}".format(description,fname,i)
                    description = description + ", extracting as {0}".format(fname)
                sect.setsectiondescription(i,description)

    return


def unpackBook(infile, outdir):
    files = fileNames(infile, outdir)

    # process the PalmDoc database header and verify it is a mobi
    sect = Sectionizer(infile)
    if sect.ident != 'BOOKMOBI' and sect.ident != 'TEXtREAd':
        raise unpackException('Invalid file format')
    if DUMP:
        sect.dumppalmheader()
    else:
        print "Palm DB type: {0:s}, {1:d} sections.".format(sect.ident,sect.num_sections)

    # scan sections to see if this is a compound mobi file (K8 format)
    # and build a list of all mobi headers to process.
    mhlst = []
    mh = MobiHeader(sect,0)
    # if this is a mobi8-only file hasK8 here will be true
    mhlst.append(mh)
    K8Boundary = -1

    if mh.isK8():
        print "Unpacking a KF8 book..."
        hasK8 = True
    else:
        # This is either a Mobipocket 7 or earlier, or a combi M7/KF8
        # Find out which
        hasK8 = False
        for i in xrange(len(sect.sectionoffsets)-1):
            before, after = sect.sectionoffsets[i:i+2]
            if (after - before) == 8:
                data = sect.loadSection(i)
                if data == K8_BOUNDARY:
                    sect.setsectiondescription(i,"Mobi/KF8 Boundary Section")
                    mh = MobiHeader(sect,i+1)
                    hasK8 = True
                    mhlst.append(mh)
                    K8Boundary = i
                    break
        if hasK8:
            print "Unpacking a Combination M{0:d}/KF8 book...".format(mh.version)
            if SPLIT_COMBO_MOBIS:
                # if this is a combination mobi7-mobi8 file split them up
                mobisplit = mobi_split(infile)
                if mobisplit.combo:
                    outmobi7 = os.path.join(files.outdir, 'mobi7-'+files.getInputFileBasename() + '.mobi')
                    outmobi8 = os.path.join(files.outdir, 'mobi8-'+files.getInputFileBasename() + '.azw3')
                    file(outmobi7, 'wb').write(mobisplit.getResult7())
                    file(outmobi8, 'wb').write(mobisplit.getResult8())
        else:
            print "Unpacking a Mobipocket {0:d} book...".format(mh.version)

    if hasK8:
        files.makeK8Struct()
    process_all_mobi_headers(files, sect, mhlst, K8Boundary, False)
    if DUMP:
        sect.dumpsectionsinfo()
    return


def usage(progname):
    print ""
    print "Description:"
    print "  Unpacks an unencrypted Kindle/MobiPocket ebook to html and images"
    print "  or an unencrypted Kindle/Print Replica ebook to PDF and images"
    print "  into the specified output folder."
    print "Usage:"
    print "  %s -r -s -d -h infile [outdir]" % progname
    print "Options:"
    print "    -r           write raw data to the output folder"
    print "    -s           split combination mobis into mobi7 and mobi8 ebooks"
    print "    -d           dump headers and other info to output and extra files"
    print "    -h           print this help message"


def main(argv=sys.argv):
    global DUMP
    global WRITE_RAW_DATA
    global SPLIT_COMBO_MOBIS
    print "MobiUnpack 0.59"
    print "   Based on initial version Copyright © 2009 Charles M. Hannum <root@ihack.net>"
    print "   Extensions / Improvements Copyright © 2009-2012 P. Durrant, K. Hendricks, S. Siebert, fandrieu, DiapDealer, nickredding."
    print "   This program is free software: you can redistribute it and/or modify"
    print "   it under the terms of the GNU General Public License as published by"
    print "   the Free Software Foundation, version 3."

    progname = os.path.basename(argv[0])
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hdrs")
    except getopt.GetoptError, err:
        print str(err)
        usage(progname)
        sys.exit(2)

    if len(args)<1:
        usage(progname)
        sys.exit(2)

    for o, a in opts:
        if o == "-d":
            DUMP = True
        if o == "-r":
            WRITE_RAW_DATA = True
        if o == "-s":
            SPLIT_COMBO_MOBIS = True
        if o == "-h":
            usage(progname)
            sys.exit(0)

    if len(args) > 1:
        infile, outdir = args
    else:
        infile = args[0]
        outdir = os.path.splitext(infile)[0]

    infileext = os.path.splitext(infile)[1].upper()
    if infileext not in ['.MOBI', '.PRC', '.AZW', '.AZW3', '.AZW4']:
        print "Error: first parameter must be a Kindle/Mobipocket ebook or a Kindle/Print Replica ebook."
        return 1

    try:
        print 'Unpacking Book...'
        unpackBook(infile, outdir)
        print 'Completed'

    except ValueError, e:
        print "Error: %s" % e
        return 1

    return 0


if __name__ == '__main__':
    sys.stdout=Unbuffered(sys.stdout)
    sys.exit(main())
