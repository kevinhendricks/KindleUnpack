#!/usr/bin/env python
# -*- coding: utf-8 -*-

DEBUG_TAGLIST = True
import mobi_taglist as taglist

import sys, os, re
#import xml.dom
#import xml.dom.minidom
#from path import pathof

class Metadata(object):
    """Class for metadata section.

    Data structure is the following:
    [0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
    """
    METADATA_START = 'start'
    METADATA_DC = 'dc'
    METADATA_META = 'meta'
    METADATA_LINK = 'link'
    METADATA_OTHER = 'other'
    METADATA_COMMENT = 'comment'
    METADATA_END = 'end'
    def __init__(self):
        self.data = []
        self.refineids = set()
        self.cover_id = None

        metadata_type = dict([ \
            [self.METADATA_START, 0], \
            [self.METADATA_DC, 1], \
            [self.METADATA_META, 2], \
            [self.METADATA_LINK, 3], \
            [self.METADATA_OTHER, 4], \
            [self.METADATA_COMMENT, -2], \
            [self.METADATA_END, -1]])
        metadata_type_inv = dict(zip(metadata_type.values(), metadata_type.keys()))
        self.metadata_type = metadata_type
        self.metadata_type_inv = metadata_type_inv

        self.tag_types = [self.METADATA_DC,
                          self.METADATA_META,
                          self.METADATA_LINK]

        self.re_metadata = re.compile(r'(<metadata[^>]*>)(.*?)(</metadata>)', re.I|re.S)
        self.re_attrib = re.compile(r'\s*(?P<attrib>\S+)\s*=\s*"(?P<value>[^"]*)"', re.I)
        self.re_element = re.compile(r'''
                (?P<comment><!--.*?-->)
            |
                (?P<start_tag><(?P<tag>[^\s/>]+)(.*?>|.*?(?P<empty>/>)))
                (?(empty)|(?P<content>.*?)(?P<end_tag></(?P=tag)>))
            ''', re.X|re.I|re.S)


    def process(self, src):
        """Import metadata from src.

        """
        re_metadata = self.re_metadata
        re_element = self.re_element
        re_attrib = self.re_attrib

        mo_meta = re_metadata.search(src)
        if mo_meta != None:
            data = []
            #[0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
            data.append([mo_meta.group(1), self.getTypeId(self.METADATA_START),
                         None, {}, None, None, None, None])

            elements = mo_meta.group(2)
            pos = 0
            mo_element = re_element.search(elements, pos)
            while mo_element != None:
                if mo_element.group('comment') != None:
                    comment = mo_element.group()
                    data.append([mo_element.group(), self.getTypeId(self.METADATA_COMMENT),
                                 None, {}, None, None, None, None])

                elif mo_element.group('start_tag') != None:
                    start_tag = mo_element.group('start_tag')
                    tag_prefix = mo_element.group('tag').split(':')[0]
                    for tag in self.tag_types:
                        if tag_prefix == tag:
                            type_id = self.getTypeId(tag)
                            break
                    else:
                        type_id = self.getTypeId(self.METADATA_OTHER)
                    tag_name = mo_element.group('tag')
                    content = mo_element.group('content')
                    end_tag = mo_element.group('end_tag')
                    attribs = dict(re_attrib.findall(start_tag))
                    isEmpty = mo_element.group('empty') != None

                    id_ = attribs.get('refines', ' ')
                    if id_[0] == '#':
                        self.refineids.add(id_[1:])

                    typeid_meta = self.getTypeId(self.METADATA_META)
                    if type_id == typeid_meta:
                        name = attribs.get('name')
                        content = attribs.get('content')
                        if name != None and name.lower() == 'cover':
                            self.cover_id = content

                    #[0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
                    data.append([mo_element.group(), type_id,
                                 tag_name, attribs, isEmpty,
                                 start_tag, content, end_tag])
                pos = mo_element.end()
                mo_element = re_element.search(elements, pos)

            data.append([mo_meta.group(3), self.getTypeId(self.METADATA_END),
                         None, {}, None, None, None, None])
            self.data = data


    def toxml(self, outall=False):
        metadata_ = []
        if outall:
            for [element, typeid, tag, attribs, isEmpty, start, content, end] in self.data[1:-1]:
                metadata_.append(element + '\n')
            return metadata_
        for [element, typeid, tag, attribs, isEmpty, start, content, end] in self.data[1:-1]:
            if 'refines' in attribs:
                continue
            metadata_.append(element + '\n')
        return metadata_

    def getRefineMetadata(self, refineids):
        metadata_ = []
        for [element, typeid, tag, attribs, isEmpty, start, content, end] in self.data[1:-1]:
            if attribs.get('refines') in refineids:
                metadata_.append(element + '\n')
        return metadata_

    def getRefineIds(self):
        return self.refineids

    def getCoverId(self):
        return self.cover_id


    def getTypeId(self, type_):
        return self.metadata_type.get(type_)

    def getType(self, type_id):
        return self.metadata_type_inv.get(type_id)

    def getNumberOfElements(self):
        return len(self.data)

    def getElement(self, index):
        """Return a sturctured metadata.

        data structure is:
        [0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
        """
        return self.data[index]

    def getElements(self, indices=None):
        """Return sturctured metadatas.

        data structure is:
        [0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
        """
        if indices == None:
            return self.data
        else: #elif isinstance(indices, list):
            return [self.data[i] for i in indices]



class Spine(object):
    """Class for spine section.

    Data structure is the following:
    [0:tag, 1:itemid, 2:attribs, 3:skelid, 4:partno, 5:filename, 6:status]
    """
    IDX_TAG = 0
    IDX_ITEMID = 1
    IDX_ATTRIBS = 2
    IDX_SKEL = 3
    IDX_PARTNO = 4
    IDX_FILENAME = 5
    IDX_STATUS = 6
    def __init__(self, k8proc):
        self.k8proc = k8proc
        self.data = []
        self.skelid_to_index = {}
        self.filename_to_index = {}
        self.partno_to_index = {}

    def process(self, src):
        """Import spine from src.

        """
        mo_spine = re.search(r'(<spine[^>]*>)(.*?)(</spine>)', src, re.I|re.S)
        if mo_spine != None:
            data = []
            data.append([mo_spine.group(1), '', '', None, -1, None, ''])

            # process itemrefs
            data_ = re.sub(r'<!--.*?-->', '', mo_spine.group(2), 0, re.S)
            itemrefs = re.findall(r'<[^>]*>', data_)
            re_idref = re.compile(r'(.*?)\s*idref="([^"]*)"(.*)', re.I)
            re_skelid = re.compile(r'(.*?)\s*skelid="([^"]*)"(.*)', re.I)
            re_itemref = re.compile(r'<itemref(.*?)/>', re.I)

            noskel_id = -1
            for itemref in itemrefs:
                mo_itemref = re_itemref.search(itemref)
                if mo_itemref == None:
                    continue
                tag = '<itemref/>'
                attribs = mo_itemref.group(1)

                mo_idref = re_idref.search(attribs)
                if mo_idref != None:
                    attribs = mo_idref.group(1) + mo_idref.group(3)
                    itemid = mo_idref.group(2)
                else:
                    print 'Warning: no itemid in <itemref /> in the spine of RESC.'
                    break
                mo_skelid = re_skelid.search(attribs)
                if mo_skelid != None:
                    attribs = mo_skelid.group(1) + mo_skelid.group(3)
                    if mo_skelid.group(2).isdigit():
                        skelid = int(mo_skelid.group(2))
                    else:
                        skelid = noskel_id
                        noskel_id -= 1
                else:
                    skelid = noskel_id
                    noskel_id -= 1
                data.append([tag, itemid, attribs, skelid, -1, None, ''])
            else:
                data.append(['</spine>', '', '', None, -1, None, ''])
                self.data = data
                self.createSkelidDict()
                self.createPartnoDict()

        if not self.hasData():
            # Make a spine if not able to retrieve from a RESC section.
            n =  self.k8proc.getNumberOfParts()
            self.create('skel', n)

        # XXX:
        # Get correspondences between itemes in a spine in RECS and ones in a skelton.
        n =  self.k8proc.getNumberOfParts()
        for i in range(n):
            # Link to K8RescProcessor.
            [skelnum, dir, filename, beg, end, aidtext] = self.k8proc.getPartInfo(i)
            index = self.getIndexBySkelid(skelnum)
            if index != None and index > 0 and index < len(self.data) - 1:
                self.data[index][self.IDX_PARTNO] = i
                #self.data[index][self.IDX_FILENAME] = filename
        return


    def create(self, itemidbase, num):
        """Create a dummy spine.

        """
        data = [['<spine toc="ncx">', '', '', None, -1, None, '']]
        for i in range(num):
            data.append(['<itemref/>', 'skel{:d}'.format(i), '', i, -1, None, ''])
        data.append(['</spine>', '', '', None, -1, None, ''])
        self.data = data
        self.createSkelidDict()
        self.createPartnoDict()


    def insert(self, i, itemid, attribs='', skelid=-1, filename=None):
        """Insert a spine.

        """
        mo = re.search(r'^\s*?(\S.*)', attribs)
        if mo != None:
            attribs = ' ' + mo.group(1)
        else:
            attribs = ''
        newdata = self.data[:i] \
            + [['<itemref/>', itemid, attribs, skelid, -1, filename, '']] \
            + self.data[i:]
        self.data = newdata
        self.createSkelidDict()
        self.createPartnoDict()


    def hasData(self):
        return len(self.data) > 0

    def getItemidList(self):
        # Get itemids.
        itemidlist = zip(*self.data)[self.IDX_ITEMID][1:-1]
        return itemidlist

    def toxml(self, dumpall=False):
        # Return itemref taglist.
        data = self.data
        spine_ = []
        for [tag, itemid, attribs, skelid, partno, filename, status] in data[1:-1]:
            if dumpall or status == 'used':
                elm = '<itemref idref="{:s}"{:s}/>'.format(itemid, attribs)
                spine_.append(elm + '\n')
        return spine_

    def getEPUBVersion(self):
        # Find epub version from itemref tags.
        epubver = '2'
        for attribs in zip(*self.data)[self.IDX_ATTRIBS][1:-1]:
            if 'properties' in attribs.lower():
                epubver = '3'
                break
        return epubver


    def getStartIndex(self):
        return 1

    def getEndIndex(self):
        return len(self.data) - 1


    def getIndexBySkelid(self, skelid):
        return self.skelid_to_index.get(skelid)

    def getIndexByPartno(self, partno):
        return self.partno_to_index.get(partno)

    def getIndexByFilename(self, filename):
        filename_to_index = self.filename_to_index
        if filename == None:
            return None
        else:
            return filename_to_index.get(filename, None)


    #XXX:
    def getFilename(self, i):
        filename = self.data[i][self.IDX_FILENAME]
        if filename != None:
            return filename
        partno = self.data[i][self.IDX_PARTNO]
        if partno >= 0 and partno < self.k8proc.getNumberOfParts():
            [skelnum, dir, filename, beg, end, aidtext] = self.k8proc.getPartInfo(partno)
            return filename
        return None

    def getIdref(self, i):
        return self.data[i][self.IDX_ITEMID]

    def getAttribs(self, i):
        return self.data[i][self.IDX_ATTRIBS]


    def isLinkToPart(self, index):
        partno = self.getPartno(index)
        n = self.k8proc.getNumberOfParts()
        return partno >= 0 and partno < n


    def getPartno(self, i):
        return self.data[i][self.IDX_PARTNO]

    def getSkelid(self, i):
        return self.data[i][self.IDX_SKEL]

    #XXX:
    def setFilename(self, i, filename):
        self.data[i][self.IDX_FILENAME] = filename

    def setIdref(self, i, ref):
        self.data[i][self.IDX_ITEMID] = ref
        self.data[i][self.IDX_STATUS] = True

    def setSkelid(self, i, skelid):
        self.data[i][self.IDX_SKEL] = skelid

    def setStatus(self, i, status):
        self.data[i][self.IDX_STATUS] = status

    def setAttribute(self, i, name, content):
        attribs = self.data[i][self.IDX_ATTRIBS]
        pa_attrib = r'(?P<head>.*?)(?P<name>{:s})\s*=\s*"(?P<content>.*?)"(?P<tail>.*)'.format(name)
        mo_attrib = re.search(pa_attrib, attribs)
        if mo_attrib != None:
            new = mo_attrib.group('head') \
                + '{:s}="{:s}"'.format(name, content) \
                + mo_attrib.group('tail')
        else:
            new =  attribs + ' {:s}="{:s}"'.format(name, content)
        self.data[i][self.IDX_ATTRIBS] = new


    def createSkelidDict(self):
        indices = range(len(self.data))
        skelids = zip(*self.data)[self.IDX_SKEL]
        self.skelid_to_index = dict(zip(skelids, indices)[1:-1])

    def createPartnoDict(self):
        indices = range(len(self.data))
        partnos = zip(*self.data)[self.IDX_PARTNO]
        self.partno_to_index = dict(zip(partnos, indices)[1:-1])

    def createFilenameDict(self):
        indices = range(1, len(self.data) - 1)
        #filenames = zip(*self.data)[self.IDX_FILENAME][1:-1]
        filenames = [self.getFilename(i) for i in indices]
        self.filename_to_index = dict(zip(filenames, indices))



class K8RESCProcessor(object):
    """RESC section processor, retrieve a spine and a metadata from RESC section.

    """
    def __init__(self, resc, k8proc):
        self.xml_header = None
        self.metadata = Metadata()
        self.spine = Spine(k8proc)
        self.k8proc = k8proc

        if resc == None or len(resc) != 3:
            self.version = -1
            self.type = -1
            self.data = ''
        else:
            [version, type_, data] = resc
            self.version = version
            self.type = type_
            self.data = data

            mo_xml = re.search(r'<\?xml[^>]*>', data, re.I)
            if mo_xml != None:
                self.xml_header = mo_xml.group()

        self.metadata.process(self.data)
        self.spine.process(self.data)


    #def metadata_toxml(self, dumpall=False):
    #    return self.metadata.toxml(dumpall)

    #def getRefineMetadata(self, refineids):
    #    return self.metadata.getRefineMetadata(refineids)

    #def getRefineIds(self):
    #    return self.metadata.getRefineIds()

    #def getCoverId(self):
    #    return self.metadata.getCoverId()

    #def spine_toxml(self, dumpall=False):
    #    return self.spine.toxml(dumpall)

    def getEPUBVersion(self):
        return self.spine.getEPUBVersion()

    def hasSpine(self):
        return self.spine.hasData()

    #def createSpine(self, itemidbase, num):
    #    self.spine.create(itemidbase, num)

    #def insertCoverPageToSine(self, cover):
    #    # Insert a cover page if not exist.
    #    return self.spine.insertCoverPage(cover)


    #def getSpineItemidList(self):
    #    return self.spine.getItemidList()

    #def getSpineStartIndex(self):
    #    return self.spine.getStartIndex()

    #def getSpineEndIndex(self):
    #    return self.spine.getEndIndex()

    #def getSpineIndexBySkelid(self, skelid):
    #    return self.spine.getIndexBySkelid(skelid)

    #def getSpineIndexByFilename(self, filename):
    #    return self.spine.getIndexByFilename(filename)

    #def getFilenameFromSpine(self, i):
    #    return self.spine.getFilename(i)

    #def setFilenameToSpine(self, i, filename):
    #    return self.spine.setFilename(i, filename)

    #def getSpineSkelid(self, i):
    #    return self.spine.getSkelid(i)

    #def setSpineSkelid(self, i, skelid):
    #    self.spine.setSkelid(i, skelid)

    #def getSpineIdref(self, i):
    #    return self.spine.getIdref(i)

    #def setSpineIdref(self, i, ref):
    #    self.spine.setIdref(i, ref)

    #def setSpineStatus(self, i, valid):
    #    self.spine.setStatus(i, valid)

    #def setSpineAttribute(self, i, name, content):
    #    self.spine.setAttribute(i, name, content)

    #def insertSpine(self, i, itemid, skelid=-1, filename=None):
    #    self.spine.insert(i, itemid, skelid, filename)

    #def createSkelidToSpineIndexDict(self):
    #    self.spine.createSkelidDict()

    #def createFilenameToSpineIndexDict(self):
    #    self.spine.createFilenameDict()
