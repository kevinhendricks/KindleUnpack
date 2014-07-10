#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

KF8_BOUNDARY = "BOUNDARY"
""" The section data that divides KF8 mobi ebooks. """

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

import os, getopt, struct
import imghdr

def sortedHeaderKeys(mheader):
    hdrkeys = sorted(mheader.keys(), key=lambda akey: mheader[akey][0])
    return hdrkeys

class dumpHeaderException(Exception):
    pass

class PalmDB:
    # important  palmdb header offsets
    unique_id_seed = 68
    number_of_pdb_records = 76
    first_pdb_record = 78

    def __init__(self, palmdata):
        self.data = palmdata
        self.nsec, = struct.unpack_from('>H',self.data,PalmDB.number_of_pdb_records)

    def getsecaddr(self,secno):
        secstart, = struct.unpack_from('>L', self.data, PalmDB.first_pdb_record+secno*8)
        if secno == self.nsec-1:
            secend = len(self.data)
        else:
            secend, = struct.unpack_from('>L',self.data,PalmDB.first_pdb_record+(secno+1)*8)
        return secstart,secend

    def readsection(self,secno):
        if secno < self.nsec:
            secstart, secend = self.getsecaddr(secno)
            return self.data[secstart:secend]
        return ''

    def getnumsections(self):
        return self.nsec



class HdrParser:
    # all values are packed in big endian format
    mobi6_header = {
            'compression_type'  : (0x00, '>H', 2),
            'fill0'             : (0x02, '>H', 2),
            'text_length'       : (0x04, '>L', 4),
            'text_records'      : (0x08, '>H', 2),
            'max_section_size'  : (0x0a, '>H', 2),
            'crypto_type'       : (0x0c, '>H', 2),
            'fill1'             : (0x0e, '>H', 2),
            'magic'             : (0x10, '4s', 4),
            'header_length'     : (0x14, '>L', 4),
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
            'header_length'     : (0x14, '>L', 4),
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
            'skeleton_index'  : (0xfc, '>L', 4),
            'datp_offset'       : (0x100, '>L', 4),
            'guide_index'       : (0x104, '>L', 4),
            }

    mobi6_header_sorted_keys = sortedHeaderKeys(mobi6_header)
    mobi8_header_sorted_keys = sortedHeaderKeys(mobi8_header)

    def __init__(self, header, start):
        # first 16 bytes are not part of the official mobiheader
        # but we will treat it as such
        # so section 0 is 16 (decimal) + self.length in total == 0x108 bytes for Mobi 8 headers
        self.header = header
        self.start = start
        self.version, = struct.unpack_from('>L', self.header, 0x24)
        self.length, = struct.unpack_from('>L',self.header, 0x14)
        print "Header Version is: 0x%0x" % self.version
        print "Header start position is: 0x%0x" % self.start
        print "Header Length is: 0x%0x" % self.length
        # if self.length != 0xf8:
        #     print "Error: Unexpected Header Length: 0x%0x" % self.length
        self.hdr = {}
        self.extra = self.header[self.length+16:]
        # set it up for the proper header version
        if self.version < 8:
            self.mobi_header_sorted_keys = HdrParser.mobi6_header_sorted_keys
            self.mobi_header = HdrParser.mobi6_header
        else:
            self.mobi_header_sorted_keys = HdrParser.mobi8_header_sorted_keys
            self.mobi_header = HdrParser.mobi8_header

        # parse the header information
        for key in self.mobi_header_sorted_keys:
            (pos, format, tot_len) = self.mobi_header[key]
            if pos < (self.length + 16):
                val, = struct.unpack_from(format, self.header, pos)
                self.hdr[key] = val
        self.exth = ''
        if self.hdr['exth_flags'] & 0x40:
            exth_offset = self.length + 16
            self.exth = self.header[exth_offset:]
            self.extra = self.header[self.length+ 16: exth_offset]

    def dumpHeaderInfo(self):
        for key in self.mobi_header_sorted_keys:
            (pos, format, tot_len) = self.mobi_header[key]
            if pos < (self.length + 16):
                if key != 'magic':
                    fmt_string = "  Field: %20s   Offset: 0x%03x   Width:  %d   Value: 0x%0" + str(tot_len) + "x"
                else:
                    fmt_string = "  Field: %20s   Offset: 0x%03x   Width:  %d   Value: %s"
                print fmt_string % (key, pos, tot_len, self.hdr[key])
        print "Extra Region Length: 0x%0x" % len(self.extra)
        print "EXTH Region Length:  0x%0x" % len(self.exth)
        print "EXTH MetaData"
        self.dump_exth()
        return


    def dump_exth(self):
        # determine text encoding
        codepage = self.hdr['codepage']
        codec = 'windows-1252'
        codec_map = {
                1252 : 'windows-1252',
                65001: 'utf-8',
                }
        if codepage in codec_map.keys():
            codec = codec_map[codepage]
        if self.exth == '':
            return
        extheader = self.exth
        id_map_strings = {
                1 : 'Drm Server Id (1)',
                2 : 'Drm Commerce Id (2)',
                3 : 'Drm Ebookbase Book Id(3)',
                100 : 'Creator_(100)',
                101 : 'Publisher_(101)',
                102 : 'Imprint_(102)',
                103 : 'Description_(103)',
                104 : 'ISBN_(104)',
                105 : 'Subject_(105)',
                106 : 'Published_(106)',
                107 : 'Review_(107)',
                108 : 'Contributor_(108)',
                109 : 'Rights_(109)',
                110 : 'SubjectCode_(110)',
                111 : 'Type_(111)',
                112 : 'Source_(112)',
                113 : 'ASIN_(113)',
                114 : 'versionNumber_(114)',
                117 : 'Adult_(117)',
                118 : 'Price_(118)',
                119 : 'Currency_(119)',
                122 : 'fixed-layout_(122)',
                123 : 'book-type_(123)',
                124 : 'orientation-lock_(124)',
                126 : 'original-resolution_(126)',
                127 : 'zero-gutter_(127)',
                128 : 'zero-margin_(128)',
                129 : 'K8_Masthead/Cover_Image_(129)',
                132 : 'RegionMagnification_(132)',
                200 : 'DictShortName_(200)',
                208 : 'Watermark_(208)',
                501 : 'CDE_Type_(501)',
                502 : 'last_update_time_(502)',
                503 : 'Updated_Title_(503)',
                504 : 'ASIN_(504)',
                524 : 'Language_(524)',
                525 : 'TextDirection_(525)',
                528 : 'Unknown_Logical_Value_(528)',
                535 : 'Kindlegen_BuildRev_Number_(535)',
                536 : 'Unknown_(536)',
                542 : 'Unknown_(542)',
        }
        id_map_values = {
                115 : 'sample_(115)',
                116 : 'StartOffset_(116)',
                121 : 'K8(121)_Boundary_Section_(121)',
                125 : 'K8_Count_of_Resources_Fonts_Images_(125)',
                131 : 'K8_Unidentified_Count_(131)',
                201 : 'CoverOffset_(201)',
                202 : 'ThumbOffset_(202)',
                203 : 'Fake_Cover_(203)',
                204 : 'Creator_Software_(204)',
                205 : 'Creator_Major_Version_(205)',
                206 : 'Creator_Minor_Version_(206)',
                207 : 'Creator_Build_Number_(207)',
                401 : 'Clipping_Limit_(401)',
                402 : 'Publisher_Limit_(402)',
                404 : 'Text_to_Speech_Disabled_(404)',
        }
        id_map_hexstrings = {
                209 : 'Tamper_Proof_Keys_(209_in_hex)',
                300 : 'Font_Signature_(300_in_hex)',
        }
        _length, num_items = struct.unpack('>LL', extheader[4:12])
        print "MetaData Header length: 0x%0x" % 12
        print "MetaData data length  : 0x%0x" %  _length
        print "Metadata # of items   : 0x%0x" %  num_items
        extheader = extheader[12:]
        pos = 0
        for _ in range(num_items):
            id, size = struct.unpack('>LL', extheader[pos:pos+8])
            content = extheader[pos + 8: pos + size]
            if id in id_map_strings.keys():
                name = id_map_strings[id]
                print '\n    Key: "%s"\n        Value: "%s"' % (name, unicode(content, codec).encode("utf-8"))
            elif id in id_map_values.keys():
                name = id_map_values[id]
                if size == 9:
                    value, = struct.unpack('B',content)
                    print '\n    Key: "%s"\n        Value: 0x%01x' % (name, value)
                elif size == 10:
                    value, = struct.unpack('>H',content)
                    print '\n    Key: "%s"\n        Value: 0x%02x' % (name, value)
                elif size == 12:
                    value, = struct.unpack('>L',content)
                    print '\n    Key: "%s"\n        Value: 0x%04x' % (name, value)
                else:
                    print "\nError: Value for %s has unexpected size of %s" % (name, size)
            elif id in id_map_hexstrings.keys():
                name = id_map_hexstrings[id]
                print '\n    Key: "%s"\n        Value: 0x%s' % (name, content.encode('hex'))
            else:
                print "\nWarning: Unknown metadata with id %s found" % id
                name = str(id) + ' (hex)'
                print '    Key: "%s"\n        Value: 0x%s' % (name, content.encode('hex'))
            pos += size
        return



# this is just guesswork so far, making big assumption that 
# metavalue key numbers reamin the same in the CONT EXTH
def dump_contexth(cpage, extheader):
    # determine text encoding
    codec = 'windows-1252'
    codec_map = {
         1252 : 'windows-1252',
         65001: 'utf-8',
    }
    if cpage in codec_map.keys():
        codec = codec_map[cpage]
    if extheader == '':
        return
    id_map_strings = {
           1 : 'Drm Server Id (1)',
           2 : 'Drm Commerce Id (2)',
           3 : 'Drm Ebookbase Book Id(3)',
           100 : 'Creator_(100)',
           101 : 'Publisher_(101)',
           102 : 'Imprint_(102)',
           103 : 'Description_(103)',
           104 : 'ISBN_(104)',
           105 : 'Subject_(105)',
           106 : 'Published_(106)',
           107 : 'Review_(107)',
           108 : 'Contributor_(108)',
           109 : 'Rights_(109)',
           110 : 'SubjectCode_(110)',
           111 : 'Type_(111)',
           112 : 'Source_(112)',
           113 : 'ASIN_(113)',
           114 : 'versionNumber_(114)',
           117 : 'Adult_(117)',
           118 : 'Price_(118)',
           119 : 'Currency_(119)',
           122 : 'fixed-layout_(122)',
           123 : 'book-type_(123)',
           124 : 'orientation-lock_(124)',
           126 : 'original-resolution_(126)',
           127 : 'zero-gutter_(127)',
           128 : 'zero-margin_(128)',
           129 : 'K8_Masthead/Cover_Image_(129)',
           132 : 'RegionMagnification_(132)',
           200 : 'DictShortName_(200)',
           208 : 'Watermark_(208)',
           501 : 'CDE_Type_(501)',
           502 : 'last_update_time_(502)',
           503 : 'Updated_Title_(503)',
           504 : 'ASIN_(504)',
           524 : 'Language_(524)',
           525 : 'TextDirection_(525)',
           528 : 'Unknown_Logical_Value_(528)',
           535 : 'Kindlegen_BuildRev_Number_(535)',
           536 : 'Unknown_(536)',
           538 : 'Image_Size_(538)',
           539 : 'Mimetype_(539)',
           542 : 'Unknown_(542)',
           543 : 'Unknown_(543)',
    }
    id_map_values = {
           115 : 'sample_(115)',
           116 : 'StartOffset_(116)',
           121 : 'K8(121)_Boundary_Section_(121)',
           125 : 'K8_Count_of_Resources_Fonts_Images_(125)',
           131 : 'K8_Unidentified_Count_(131)',
           201 : 'CoverOffset_(201)',
           202 : 'ThumbOffset_(202)',
           203 : 'Fake_Cover_(203)',
           204 : 'Creator_Software_(204)',
           205 : 'Creator_Major_Version_(205)',
           206 : 'Creator_Minor_Version_(206)',
           207 : 'Creator_Build_Number_(207)',
           401 : 'Clipping_Limit_(401)',
           402 : 'Publisher_Limit_(402)',
           404 : 'Text_to_Speech_Disabled_(404)',
    }
    id_map_hexstrings = {
           209 : 'Tamper_Proof_Keys_(209_in_hex)',
           300 : 'Font_Signature_(300_in_hex)',
    }
    _length, num_items = struct.unpack('>LL', extheader[4:12])
    extheader = extheader[12:]
    pos = 0
    for _ in range(num_items):
        id, size = struct.unpack('>LL', extheader[pos:pos+8])
        content = extheader[pos + 8: pos + size]
        if id in id_map_strings.keys():
            name = id_map_strings[id]
            print '\n    Key: "%s"\n        Value: "%s"' % (name, unicode(content, codec).encode("utf-8"))
        elif id in id_map_values.keys():
            name = id_map_values[id]
            if size == 9:
                value, = struct.unpack('B',content)
                print '\n    Key: "%s"\n        Value: 0x%01x' % (name, value)
            elif size == 10:
                value, = struct.unpack('>H',content)
                print '\n    Key: "%s"\n        Value: 0x%02x' % (name, value)
            elif size == 12:
                value, = struct.unpack('>L',content)
                print '\n    Key: "%s"\n        Value: 0x%04x' % (name, value)
            else:
                print "\nError: Value for %s has unexpected size of %s" % (name, size)
        elif id in id_map_hexstrings.keys():
            name = id_map_hexstrings[id]
            print '\n    Key: "%s"\n        Value: 0x%s' % (name, content.encode('hex'))
        else:
            print "\nWarning: Unknown metadata with id %s found" % id
            name = str(id) + ' (hex)'
            print '    Key: "%s"\n        Value: 0x%s' % (name, content.encode('hex'))
        pos += size
    return


def usage(progname):
    print ""
    print "Description:"
    print "   Dump all mobi headers in the mobi ebook file as generated by the latest kindlegen"
    print "  "
    print "Usage:"
    print "  %s -h infile.mobi" % progname
    print "  "
    print "Options:"
    print "    -h           print this help message"


def main(argv=sys.argv):
    print "DumpMobiHeader v014"
    progname = os.path.basename(argv[0])
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h")
    except getopt.GetoptError, err:
        print str(err)
        usage(progname)
        sys.exit(2)

    if len(args) != 1:
        usage(progname)
        sys.exit(2)

    for o, a in opts:
        if o == "-h":
            usage(progname)
            sys.exit(0)

    infile = args[0]
    infileext = os.path.splitext(infile)[1].upper()
    print infile, infileext
    if infileext not in ['.MOBI', '.PRC', '.AZW', '.AZW3','.AZW4']:
        print "Error: first parameter must be a Kindle/Mobipocket ebook."
        return 1

    try:
        # make sure it is really a mobi ebook
        mobidata = file(infile, 'rb').read()
        palmheader = mobidata[0:78]
        ident = palmheader[0x3C:0x3C+8]
        if ident != 'BOOKMOBI':
            raise dumpHeaderException('invalid file format')

        headers = {}

        pp = PalmDB(mobidata)
        header = pp.readsection(0)

        print "\n\nFirst Header Dump from Section %d" % 0
        hp = HdrParser(header, 0)
        hp.dumpHeaderInfo()
        headers[0] = hp
        

        # next determine if this is a combo (dual) KF8 mobi file
        # we could examine the metadata for exth_121 in the old mobi header
        # but it is just as quick to scan the palmdb for the boundary section
        # ONLY do this for combination mobi files
        if hp.version != 8:
            n = pp.getnumsections()
            for i in xrange(n):
                before, after = pp.getsecaddr(i)
                if (after - before) == 8:
                    data = pp.readsection(i)
                    if data == KF8_BOUNDARY:
                        header = pp.readsection(i+1)
                        print "\n\nMobi Ebook uses the new dual mobi/KF8 file format"
                        print "\nSecond Header Dump from Section %d" % (i+1)
                        hp = HdrParser(header, i+1)
                        hp.dumpHeaderInfo()
                        headers[i+1] = hp
                        break

        # now dump a basic sector map of the palmdb
        n = pp.getnumsections()
        dtmap = {
            "FLIS": "FLIS",
            "FCIS": "FCIS",
            "FDST": "FDST",
            "DATP": "DATP",
            "BOUN": "BOUNDARY",
            "FONT": "FONT",
            "RESC": "RESC",
            "CRES": "CRES",
            "CONT": "CONT",
            chr(0xa0) + chr(0xa0) + chr(0xa0) + chr(0xa0): "Empty_Image/Resource_Placeholder",
            chr(0xe9) + chr(0x8e) + "\r\n" : "EOF_RECORD",
            }
        dtmapext = {
            "CONTBOUNDARY" : "CONTBOUNDARY",
        }
        dtmap2 = {
            "kindle:embed" : "KINDLE:EMBED",
        }
        indmap = {
            "INDX" : "INDX",
            "IDXT" : "IDXT"
            }
        boundary = -1
        tr = -1
        off = -1
        hp = None
        secmap = {}
        print "\nMap of Palm DB Sections"
        print "    Dec  - Hex : Description"
        print "    ---- - ----  -----------"
        for i in xrange(n):
            before, after = pp.getsecaddr(i)
            data = pp.readsection(i)
            dlen = len(data)
            dt = data[0:4]
            dtext = data[0:12]
            desc = '' 
            imgtype = imghdr.what(None, data)
            if i in headers.keys():
                hp = headers[i]
                off =  i
                version = hp.hdr['version']
                desc = "HEADER %d" % version
                # update known section map
                tr = hp.hdr['text_records']
                for j in xrange(tr):
                    secmap[j + off + 1] = "Text Record %d" % j
                ncx_index = hp.hdr.get('ncx_index', 0xffffffff)
                if ncx_index != 0xffffffff:
                    secmap[ncx_index + off] = "NCX Index 0"
                    secmap[ncx_index + off + 1] = "NCX Index 1"
                    secmap[ncx_index + off + 2] = "NCX Index CNX"
                skel_index = hp.hdr.get('skeleton_index', 0xffffffff)
                if skel_index != 0xffffffff:
                    secmap[skel_index + off] = "Skeleton Index 0"
                    secmap[skel_index + off + 1] = "Skeleton Index_Index 1"
                frag_index = hp.hdr.get('fragment_index', 0xffffffff)
                if frag_index != 0xffffffff:
                    secmap[frag_index + off] = "Fragment Index 0"
                    secmap[frag_index + off + 1] = "Fragment Index 1"
                    secmap[frag_index + off + 2] = "Fragment Index CNX"
                guide_index = hp.hdr.get('guide_index', 0xffffffff)
                if guide_index != 0xffffffff:
                    secmap[guide_index + off] = "Guide Index 0"
                    secmap[guide_index + off + 1] = "Guide Index 1"
                    secmap[guide_index + off + 2] = "Guide Index CNX"
                srcs_offset = hp.hdr.get('srcs_offset', 0xffffffff)
                if srcs_offset != 0xffffffff:
                    srcs_count = hp.hdr['srcs_count']
                    for j in xrange(srcs_count):
                        secmap[j + srcs_offset + off] = 'Source Archive %d' % j
            elif i in secmap.keys():
                desc = secmap[i]
            elif dtext in dtmapext.keys():
                desc = dtmapext[dtext]
            elif dtext in dtmap2.keys():
                desc = data
            elif dt in dtmap.keys():
                desc = dtmap[dt]
                if dt == "CONT":
                    cpage, = struct.unpack_from('>L', data, 12)
                    contexth = data[48:]
                    print "    %04d - %04x: %s [%d]" % (i, i, desc, dlen)
                    print "Container EXTH Dump"
                    dump_contexth(cpage, contexth)
            elif dt in indmap.keys():
                desc = "Index"
            elif imgtype is not None:
                desc = "Image " + imgtype
            else:
                desc = dtext.encode('hex')
                desc = desc + " " + dtext
            if desc != "CONT":
                print "    %04d - %04x: %s [%d]" % (i, i, desc, dlen)

    except Exception, e:
        print "Error: %s" % e
        return 1

    return 0


if __name__ == '__main__':
    sys.stdout=Unbuffered(sys.stdout)
    sys.exit(main())
