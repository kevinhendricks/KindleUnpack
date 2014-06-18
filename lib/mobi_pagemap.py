#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

import sys, struct, re

_TABLE = [('m', 1000), ('cm', 900), ('d', 500), ('cd', 400), ('c', 100), ('xc', 90), ('l', 50), ('xl', 40), ('x', 10), ('ix', 9), ('v', 5), ('iv', 4), ('i', 1)]

def int_to_roman(i):
    parts = []
    num = i
    for letter, value in _TABLE:
        while value <= num:
            num -= value
            parts.append(letter)
    return ''.join(parts)

def roman_to_int(s):
    result = 0
    rnstr = s
    for letter, value in _TABLE:
        while rnstr.startswith(letter):
            result += value
            rnstr = rnstr[len(letter):]
    return result

_pattern = r'''\(([^\)]*)\)'''
_tup_pattern = re.compile(_pattern,re.IGNORECASE)


def _parseNames(numpages, data):
    pagenames = []
    for i in range(numpages):
        pagenames.append(None)
    for m in re.finditer(_tup_pattern, data):
        tup = m.group(1)
        spos, nametype, svalue = tup.split(",")
        # print spos, nametype, svalue
        if nametype == 'a' or  nametype == 'r':
            svalue = int(svalue)
        spos = int(spos)
        for i in range(spos - 1, numpages):
            if nametype == 'r':
                pname = int_to_roman(svalue)
                svalue += 1
            elif nametype == 'a':
                pname = "%s" % svalue
                svalue += 1
            elif nametype == 'c':
                sp = svalue.find('|')
                if sp == -1:
                    pname = svalue
                else:
                    pname = svalue[0:sp]
                    svalue = svalue[sp+1:]
            else:
                print "Error: unknown page numbering type", nametype
            pagenames[i] = pname
    return pagenames



class PageMapProcessor:
    def __init__(self, mh, data):
        self.mh = mh
        self.data = data
        self.pagenames = []
        self.pageoffsets = []
        print "Extracting Page Map Information"
        rev_len, = struct.unpack_from('>L', self.data, 0x10)
        # skip over header, revision string length data, and revision string
        ptr = 0x14 + rev_len 
        pm_1, pm_len, pm_nn, pm_bits  = struct.unpack_from('>4H', self.data, ptr)
        # print pm_1, pm_len, pm_nn, pm_bits
        pmstr = self.data[ptr+8:ptr+8+pm_len]
        pmoff = self.data[ptr+8+pm_len:]
        offsize = ">L"
        offwidth = 4
        if pm_bits == 16:
            offsize = ">H"
            offwidth = 2
        ptr = 0
        for i in range(pm_nn):
            od, = struct.unpack_from(offsize, pmoff, ptr)
            ptr += offwidth
            self.pageoffsets.append(od)
        self.pagenames = _parseNames(pm_nn, pmstr)

    
    def getNames(self):
        return self.pagenames

    def getOffsets(self):
        return self.pageoffsets


    def generateKF8PageMapXML(self, k8proc):
        pagemapxml = '<page-map xmlns="http://www.idpf.org/2007/opf">\n'
        for i in xrange(len(self.pagenames)):
            pos = self.pageoffsets[i]
            name = self.pagenames[i]
            if name != None and name != "":
                [pn, dir, filename, skelpos, skelend, aidtext] = k8proc.getSkelInfo(pos)
                idtext = k8proc.getPageIDTag(pos)
                linktgt = filename
                if idtext != '':
                    linktgt += '#' + idtext
                pagemapxml += '<page name="%s" href="%s/%s" />\n' % (name, dir, linktgt)
        # page-map.xml is encoded utf-8 so must convert any text properly
        pagemapxml += "</page-map>\n"
        pagemapxml = unicode(pagemapxml, self.mh.codec).encode("utf-8")
        return pagemapxml
