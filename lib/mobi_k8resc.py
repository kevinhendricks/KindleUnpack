#!/usr/bin/env python
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

import sys, re
from mobi_utils import fromBase32

        # rp = RESCProcessor(resc_data)
        # rp.parseData()
        # print "cover name: ", rp.cover_name
        # print "extra metadata"
        # for tname, tattr, tcontent in rp.extrameta:
        #     print "    ", tname, tattr, tcontent
        # print "spine ppd: ",rp.spine_ppd
        # for key in rp.spine_order:
        #     print key, rp.spine_idrefs[key], rp.spine_pageprops[key]

_DEBUG = False
_OPF_PARENT_TAGS = ['xml', 'package', 'metadata', 'dc-metadata', 'x-metadata', 'manifest', 'spine', 'tours', 'guide']

class K8RESCProcessor(object):

    def __init__(self, data):
        self.resc = None
        self.opos = 0
        self.extrameta = []
        self.cover_name = None
        self.cover_attributes = {}
        self.spine_idrefs = {}
        self.spine_order = []
        self.spine_pageprops = {}
        self.spine_ppd = None
        self.hasSpine = False
        m_header = re.match(r'^\w+=(\w+)\&\w+=(\d+)&\w+=(\d+)',data)
        self.resc_header = m_header.group()
        resc_size = fromBase32(m_header.group(1))
        self.resc_version = int(m_header.group(2))
        self.resc_type = int(m_header.group(3))
        resc_rawbytes = len(data) - m_header.end()
        if resc_rawbytes == resc_size:
            self.resc_length = resc_size
        else:
            # Most RESC has a nul string at its tail but some do not.
            end_pos = data.find('\x00', m_header.end())
            if end_pos < 0:
                self.resc_length = resc_rawbytes
            else:
                self.resc_length = end_pos - m_header.end()
        if self.resc_length != resc_size:
            print "Warning: RESC section length({:d}bytes) does not match its size({:d}bytes).".format(self.resc_length, resc_size)
        self.resc = data[m_header.end():m_header.end()+self.resc_length]
        self.parseData()
        self.hasSpine = len(self.spine_order) > 0

    # RESC tag iterator
    def resc_tag_iter(self):
        tcontent = last_tattr = None
        prefix = ['']
        while True:
            text, tag = self.parseresc()
            if text is None and tag is None:
                break
            if text is not None:
                tcontent = text.rstrip(" \r\n")
            else: # we have a tag
                ttype, tname, tattr = self.parsetag(tag)
                if ttype == "begin":
                    tcontent = None
                    prefix.append(tname + '.')
                    if tname in _OPF_PARENT_TAGS:
                        yield "".join(prefix), tname, tattr, tcontent
                    else:
                        last_tattr = tattr
                else: # single or end
                    if ttype == "end":
                        prefix.pop()
                        tattr = last_tattr
                        last_tattr = None
                        if tname in _OPF_PARENT_TAGS:
                            tname += '-end'
                    yield "".join(prefix), tname, tattr, tcontent
                    tcontent = None


    # now parse the RESC to extract spine and extra metadata info
    def parseData(self):
        global _DEBUG
        for prefix, tname, tattr, tcontent in self.resc_tag_iter():
            if _DEBUG:
                print "  "
                print prefix, tname
                print tattr
                print tcontent
            if tname == "spine":
                self.spine_ppd = tattr.get("page-progession-direction", None)
            if tname == "itemref":
                skelid = tattr.get("skelid", None)
                if skelid is None and len(self.spine_order) == 0:
                    # assume it was removed initial coverpage
                    skelid = "coverpage"
                    self.cover_attributes["linear"] = "no"
                self.spine_order.append(skelid)
                idref = tattr.get("idref", None)
                if idref is not None:
                    idref = 'x_' + idref
                self.spine_idrefs[skelid] = idref
                self.spine_pageprops[skelid] = tattr.get("properties", None)
            if tname == "meta" or tname.startswith("dc:"):
                if tattr.get("name","") == "cover":
                    self.cover_name = tattr.get("content",None)
                else:
                    self.extrameta.append([tname, tattr, tcontent])


    # parse and return either leading text or the next tag
    def parseresc(self):
        p = self.opos
        if p >= len(self.resc):
            return None, None
        if self.resc[p] != '<':
            res = self.resc.find('<',p)
            if res == -1 :
                res = len(self.resc)
            self.opos = res
            return self.resc[p:res], None
        # handle comment as a special case
        if self.resc[p:p+4] == '<!--':
            te = self.resc.find('-->',p+1)
            if te != -1:
                te = te+2
        else:
            te = self.resc.find('>',p+1)
            ntb = self.resc.find('<',p+1)
            if ntb != -1 and ntb < te:
                self.opos = ntb
                return self.resc[p:ntb], None
        self.opos = te + 1
        return None, self.resc[p:te+1]

    # parses tag to identify:  [tname, ttype, tattr]
    #    tname: tag name     
    #    ttype: tag type ('begin', 'end' or 'single');
    #    tattr: dictionary of tag atributes
    def parsetag(self, s):
        p = 1
        tname = None
        ttype = None
        tattr = {}
        while s[p:p+1] == ' ' : p += 1
        if s[p:p+1] == '/':
            ttype = 'end'
            p += 1
            while s[p:p+1] == ' ' : p += 1
        b = p
        while s[p:p+1] not in ('>', '/', ' ', '"', "'","\r","\n") : p += 1
        tname=s[b:p].lower()
        # some special cases
        if tname == "?xml":
            tname = "xml"
        if tname == "!--":
            ttype = 'single'
            comment = s[p:-3].strip()
            tattr['comment'] = comment
        if ttype is None:
            # parse any attributes of begin or single tags
            while s.find('=',p) != -1 :
                while s[p:p+1] == ' ' : p += 1
                b = p
                while s[p:p+1] != '=' : p += 1
                aname = s[b:p].lower()
                aname = aname.rstrip(' ')
                p += 1
                while s[p:p+1] == ' ' : p += 1
                if s[p:p+1] in ('"', "'") :
                    p = p + 1
                    b = p
                    while s[p:p+1] not in ('"', "'"): p += 1
                    val = s[b:p]
                    p += 1
                else :
                    b = p
                    while s[p:p+1] not in ('>', '/', ' ') : p += 1
                    val = s[b:p]
                tattr[aname] = val
        if tattr is not None and len(tattr)== 0: tattr = None
        if ttype is None:
            ttype = 'begin'
            if s.find('/',p) >= 0:
                ttype = 'single'
        return ttype, tname, tattr


    def taginfo_toxml(self, taginfo):
        res = []
        tname, tattr, tcontent = taginfo
        res.append('<' + tname)
        if tattr is not None:
            for key in tattr.keys():
                res.append(' "' + key + '"="'+tattr[key]+'"' )
        if tcontent is not None:
            res.append('>' + tcontent + '</' + tname + '>\n')
        else: 
            res.append('/>\n')
        return "".join(res)
