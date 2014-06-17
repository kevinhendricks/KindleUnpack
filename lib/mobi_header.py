#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


import sys
import os

import codecs
import struct, re


# import the mobiunpack support libraries
from mobi_utils import getLanguage 
from mobi_uncompress import HuffcdicReader, PalmdocReader, UncompressedReader

class unpackException(Exception):
    pass


def sortedHeaderKeys(mheader):
    hdrkeys = sorted(mheader.keys(), key=lambda akey: mheader[akey][0])
    return hdrkeys


# HD Containers have their own headers and their own EXTH
# this is just guesswork so far, making big assumption that 
# metavalue key numbers remain the same in the CONT EXTH

# Note:  The layout of the CONT Header is still unknown
# so just deal with their EXTH sections for now

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
        508 : 'Title file-as',
        517 : 'Creator file-as',
        522 : 'Publisher file-as',
        524 : 'Language_(524)',
        525 : 'primary-writing-mode',
        527 : 'page-progression-direction',
        528 : 'Unknown_Logical_Value_(528)',
        529 : 'Original_Source_Description_(529)',
        534 : 'Unknown_(534)',
        535 : 'Kindlegen_BuildRev_Number',
        534 : 'Unknown_(536)',

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
        406 : 'Rental_Indicator',
    }
    id_map_hexstrings = {
        209 : 'Tamper Proof Keys (hex)',
        300 : 'Font Signature (hex)',
        403 : 'Unknown_(403) (hex)',
        405 : 'Unknown_(405) (hex)',
        407 : 'Unknown_(407) (hex)',
        450 : 'Unknown_(450) (hex)',
        451 : 'Unknown_(451) (hex)',
        452 : 'Unknown_(452) (hex)',
        453 : 'Unknown_(453) (hex)',

    }

    def __init__(self, sect, sectNumber):
        self.sect = sect
        self.start = sectNumber
        self.header = self.sect.loadSection(self.start)
        if len(self.header)>20 and self.header[16:20] == 'MOBI':
            self.sect.setsectiondescription(0,"Mobipocket Header")
            self.palm = False
        elif self.sect.ident == 'TEXtREAd':
            self.sect.setsectiondescription(0, "PalmDOC Header")
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
        self.othidx = 0xffffffff
        self.fdst = 0xffffffff
        self.mlstart = self.sect.loadSection(self.start+1)[:4]
        self.rawSize = 0
        self.metadata = {}

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
        self.exth_offset = self.length + 16
        self.exth_length = 0
        if self.hasExth:
            self.exth_length, = struct.unpack_from('>L', self.header, self.exth_offset+4)
            self.exth_length = ((self.exth_length + 3)>>2)<<2 # round to next 4 byte boundary
            self.exth = self.header[self.exth_offset:self.exth_offset+self.exth_length]

        # self.mlstart = self.sect.loadSection(self.start+1)
        # self.mlstart = self.mlstart[0:4]
        self.crypto_type, = struct.unpack_from('>H', self.header, 0xC)

        # Start sector for additional files such as images, fonts, resources, etc
        # Can be missing so fall back to default set previously
        ofst, = struct.unpack_from('>L', self.header, 0x6C)
        if ofst != 0xffffffff:
            self.firstresource = ofst + self.start
        ofst, = struct.unpack_from('>L', self.header, 0x50)
        if ofst != 0xffffffff:
            self.firstnontext = ofst + self.start

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
                # setting of fdst section description properly handled in mobi_kf8proc

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
                elif size == 16:
                    hival, = struct.unpack('>L',content[0:4])
                    loval, = struct.unpack('>L',content[0:4])
                    value = hival*0x100000000 + loval
                    print '{0:3d}   LL {1:<30s} 0x{2:0>16X} ({2:d})'.format(id, exth_name, value)
                else:
                    print '{0: >3d} {1: >4d} {2: <30s} (0x{3:s})'.format(id, contentsize, "Bad size for "+exth_name, content.encode('hex'))
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
        rawML = "".join(dataList)
        self.rawSize = len(rawML)
        return rawML


    def getMetaData(self):
        def addValue(name, value):
            if name not in self.metadata:
                self.metadata[name] = [value]
            else:
                self.metadata[name].append(value)

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
                    addValue(name, unicode(content, codec).encode('utf-8'))
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

        # add the basics to the metadata
        self.metadata['Language'] = self.Language()
        self.metadata['Title'] = [unicode(self.title, self.codec).encode("utf-8")]
        self.metadata['Codec'] = [self.codec]
        self.metadata['UniqueID'] = [str(self.unique_id)]

        return self.metadata


    def describeHeader(self, DUMP):
        print "Mobi Version:", self.version
        print "Codec:", self.codec
        print "Title:", self.title
        if 'Updated_Title'  in self.metadata:
            print "EXTH Title:", str(self.metadata['Updated_Title'][0])
        if self.compression == 0x4448:
            print "Huffdic compression"
        elif self.compression == 2:
            print "Palmdoc compression"
        elif self.compression == 1:
            print "No compression"
        if DUMP:
            self.dumpheader()
