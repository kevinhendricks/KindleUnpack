#!/usr/bin/env python
# -*- coding: utf-8 -*-

# FIXME Remove if dom version works well.
PROC_K8RESC_USE_RE = False
""" Process K8 RESC section by re modules. """

import sys, struct, re
import xml.dom
import xml.dom.minidom

from mobi_index import MobiIndex
from mobi_utils import fromBase32
from path import pathof

_guide_types = ['cover','title-page','toc','index','glossary','acknowledgements',
                'bibliography','colophon','copyright-page','dedication',
                'epigraph','foreward','loi','lot','notes','preface','text']

# locate beginning and ending positions of tag with specific aid attribute
def locate_beg_end_of_tag(ml, aid):
    pattern = r'''<[^>]*\said\s*=\s*['"]%s['"][^>]*>''' % aid
    aid_pattern = re.compile(pattern,re.IGNORECASE)
    for m in re.finditer(aid_pattern, ml):
        plt = m.start()
        pgt = ml.find('>',plt+1)
        return plt, pgt
    return 0, 0


# iterate over all tags in block in reverse order, i.e. last ta to first tag
def reverse_tag_iter(block):
    end = len(block)
    while True:
        pgt = block.rfind(b'>', 0, end)
        if pgt == -1: break
        plt = block.rfind(b'<', 0, pgt)
        if plt == -1: break
        yield block[plt:pgt+1]
        end = plt


# FIXME Remove if dom version works well.
class Metadata:
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

        self.re_metadata_start = re.compile(r'<metadata[^>]*>', re.I)
        self.re_metadata_end = re.compile(r'</metadata>', re.I)
        self.re_attrib = re.compile(r'\s*(?P<attrib>\S+)\s*=\s*"(?P<value>[^"]*)"', re.I)
        re_pattern = ''
        tag_types = self.tag_types
        for tag_type in tag_types[:-1]:
            re_pattern += '(?P<{}><{})|'.format(tag_type, tag_type)
        else:
            re_pattern += '(?P<{}><{})'.format(tag_types[-1], tag_types[-1])
        self.re_tag_type = re.compile(re_pattern, re.I)

        self.data = None
        self.cover_id = None


    def process(self, src):
        """Import metadata from src.

        """

        self.re_element = re.compile(r'''
                (?P<comment><!--.*?-->)
            |
                (?P<start_tag><(?P<tag>\S+).*?((?P<empty>/>)|>))
                (?(empty)|(?P<content>[^<]*)(?P<end_tag></(?P=tag)>))
            ''', re.X)

        re_metadata_start = self.re_metadata_start
        re_metadata_end = self.re_metadata_end
        re_element = self.re_element
        re_attrib = self.re_attrib
        re_tag_type = self.re_tag_type

        mo_meta = re_metadata_start.search(src)
        if mo_meta != None:
            mo_meta_end = re_metadata_end.search(src[mo_meta.end():])
            if mo_meta_end == None:
                print 'Cannot find corresponded </metadata>'
                return
            data = []
            #[0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
            data.append([mo_meta.group(), self.getTypeId(self.METADATA_START),
                         None, None, None, None, None, None])

            elements = src[mo_meta.end():mo_meta.end()+mo_meta_end.start()]

            pos = 0
            mo_element = re_element.search(elements, pos)
            while mo_element != None:
                if mo_element.group('comment') != None:
                    comment = mo_element.group()
                    data.append([mo_element.group(), self.getTypeId(self.METADATA_COMMENT),
                                 None, None, None, None, None, None])

                elif mo_element.group('start_tag') != None:
                    start_tag = mo_element.group('start_tag')
                    mo_type = re_tag_type.match(start_tag)
                    if mo_type == None:
                        type_id = self.getTypeId(self.METADATA_OTHER)
                    else:
                        for tag in self.tag_types:
                            if mo_type.group(tag) != None:
                                type_id = self.getTypeId(tag)
                                break
                            else:
                                type_id = self.getTypeId(self.METADATA_OTHER)

                    tag_name = mo_element.group('tag')
                    content = mo_element.group('content')
                    end_tag = mo_element.group('end_tag')
                    attribs = dict(re_attrib.findall(start_tag))
                    isEmpty = mo_element.group('empty') != None

                    #[0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
                    data.append([mo_element.group(), type_id,
                                 tag_name, attribs, isEmpty,
                                 start_tag, content, end_tag])
                pos = mo_element.end()
                mo_element = re_element.search(elements, pos)

            data.append([mo_meta_end.group(), self.getTypeId(self.METADATA_END),
                         None, None, None, None, None, None])
            self.data = data
            self.searchCoverId()


    def searchCoverId(self):
        num = self.getNumberOfElements()
        for elm in self.getElements(range(1, num-1)):
            #[0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
            if elm[1] >= 1:
                attribs = elm[3]
                name = attribs.get('name')
                content = attribs.get('content')
                if name != None and name.lower() == 'cover':
                    self.cover_id = content
                    break


    def metadata_toxml(self):
        metadata_ = []
        num = self.getNumberOfElements()
        for elm in self.getElements(range(1, num-1)):
            #[0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
            #if elm[1] == self.getTypeId(resc_metadata.METADATA_COMMENT):
            #    continue
            if elm[1] >= 1:
                attribs = elm[3]
                if 'refines' in attribs:
                    continue
                name = attribs.get('name')
                content = attribs.get('content')
                if name != None and name.lower() == 'cover':
                    self.cover_id = content

                metadata_.append(elm[0] + '\n')
        return metadata_


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

# FIXME Remove if dom version works well.
class K8RescRe:
    """Information in the RESC section of K8 format, processing by re module.

    """
    def __init__(self, resc):
        if len(resc) != 3:
            return
        [version, type_, data] = resc
        self.version = version
        self.type = type_
        self.data = data

        self.cover_id = None
        self.metadata = Metadata()
        self.meta_types = None
        self.spine = None
        self.spine_dict = None
        self.spine_filename_dict = None

        #mo_xml = re.search(r'<\?xml[^>]*>', data, re.I)
        #if mo_xml != None:
        #    self.xml = mo_xml.group()

        self.metadata.process(data)
        if self.metadata.cover_id != None:
            self.cover_id = self.metadata.cover_id

        mo_spine = re.search(r'<spine[^>]*>', data, re.I)
        if mo_spine != None:
            mo_spine_end = re.search(r'</spine>', data[mo_spine.end():], re.I)
            if mo_spine_end == None:
                print 'Warning:Cannot find corresponded end tag in a spine element.'
                return

            spine = []
            spine.append([mo_spine.group(), None, None, True, None])

            # process itemrefs
            data_ = data[mo_spine.end():mo_spine.end()+mo_spine_end.start()]
            itemrefs = re.findall(r'<[^>]*>', data_)

            idref_tag_pattern = re.compile(r'\s*idref="([^"]*)"', re.I)
            skelid_tag_pattern = re.compile(r'\s*skelid="(\d*)"', re.I)
            for itemref in itemrefs:
                mo_idref = idref_tag_pattern.search(itemref)
                if mo_idref != None:
                    itemid = mo_idref.group(1)
                else:
                    break
                mo_skelid = skelid_tag_pattern.search(itemref)
                if mo_skelid != None:
                    skelid = int(mo_skelid.group(1))
                else:
                    skelid = -1

                itemref = idref_tag_pattern.sub('', itemref)
                itemref = skelid_tag_pattern.sub('', itemref)
                spine.append([itemref, skelid, itemid, False, None])
            else:
                spine.append(['</spine>', None, None, True, None])
                spine_dict = dict([[spine[i][1], i] for i in range(1, len(spine)-1)])

                self.spine = spine
                self.spine_dict = spine_dict
        return


    def metadata_toxml(self):
        return self.metadata.metadata_toxml()


    def spine_toxml(self):
        spine = self.spine
        spine_ = []
        if spine != None:
            itemref_pattern = re.compile('<itemref')
            for [itemref, skelid, itemid, isvalid, filename] in spine[1:-1]:
                if isvalid:
                    elm = itemref_pattern.sub('<itemref idref="' + itemid +'"', itemref)
                    spine_.append(elm + '\n')
        return spine_


    def getSpineIndexBySkelid(self, skelid):
        """Return corresponding itemref index to skelnum.

        """
        if self.spine != None:
            #[itemref, skelid, itemid, bool, filename]
            index = self.spine_dict.get(skelid)
        else:
            index = None
        return index


    def setFilenameToSpine(self, skelid, filename):
        index = self.getSpineIndexBySkelid(skelid)
        if index != None:
            #[itemref, skelid, itemid, bool, filename]
            self.spine[index][4] = filename

    def createFilenameToSpineIndexDict(self):
        spine = self.spine
        if spine != None:
            pairs = [[spine[i][4], i] for i in range(len(spine))]
            spine_filename_dict = dict(pairs)
            self.spine_filename_dict = spine_filename_dict


    def getSpineIndexByFilename(self, filename):
        spine_filename_dict = self.spine_filename_dict
        if filename == None:
            return None
        elif spine_filename_dict == None:
            return None
        else:
            return spine_filename_dict.get(filename)

    def getSpineIdref(self, i):
        #[itemref, skelid, itemid, bool, filename]
        return self.spine[i][2]

    def setSpineIdref(self, i, ref):
        #[itemref, skelid, itemid, bool, filename]
        self.spine[i][2] = ref
        self.spine[i][3] = True


class K8Resc:
    """Information in the RESC section of K8 format, processing by dom modules.

    """
    def __init__(self, resc):
        if len(resc) != 3:
            return
        [version, type_, data] = resc
        self.version = version
        self.type = type_
        self.data = data

        self.cover_id = None
        self.dom_metadata = None
        self.dom_spine = None
        self.metadata_array = None
        self.spine_array = None
        self.spine_skelid_dict = None
        self.spine_filename_dict = None

        # It seems to be able to handle utf-8 with a minidom module when
        # modifying a xml string in the RESC section as below.
        # However, it is not sure that the usage of minidom is proper.
        resc_xml = ''
        mo_xml = re.search(r'<\?xml[^>]*>', data, re.I)
        if mo_xml != None:
            resc_xml += mo_xml.group()
        else:
            resc_xml += '<?xml version="1.0" encoding="utf-8"?>'
        mo_package = re.search(r'(<package[^>]*>).*?(</package>)', data, re.I)
        if mo_package != None:
            resc_xml += mo_package.group(1)
        else:
            resc_xml += '<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid">'
        #resc_xml += '<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid">'

        mo_metadata = re.search(r'(<metadata[^>]*>).*?(</metadata>)', data, re.I)
        if mo_metadata != None:
            resc_xml += mo_metadata.group()
        mo_spine = re.search(r'(<spine[^>]*>).*?(</spine>)', data, re.I)
        if mo_spine != None:
            resc_xml += mo_spine.group()
        resc_xml += '</package>'

        dom = xml.dom.minidom.parseString(resc_xml)
        dom_metadata = dom.getElementsByTagName('metadata')
        if len(dom_metadata) > 0 and dom_metadata.item(0).hasChildNodes():
            metadata_array = []
            nodeList = dom_metadata.item(0).childNodes
            for i in range(nodeList.length):
                isvalid = True
                item = nodeList.item(i)
                if item.nodeType == xml.dom.Node.COMMENT_NODE:
                    isvalid = False
                elif item.hasAttributes():
                    if item.hasAttribute('refines'):
                        isvalid = False
                    elif item.hasAttribute('name'):
                        name = item.getAttribute('name')
                        content = item.getAttribute('content').encode('utf-8')
                        if name.lower() == 'cover':
                            if len(content) > 0:
                                self.cover_id = content
                metadata_array.append([isvalid])

            self.dom_metadata = dom_metadata
            self.metadata_array = metadata_array

        dom_spine = dom.getElementsByTagName('spine')
        if len(dom_spine) > 0 and dom_spine.item(0).hasChildNodes():
            nodeList = dom_spine.item(0).childNodes
            spine_array = []
            for i in range(nodeList.length):
                item = nodeList.item(i)
                if item.nodeType == xml.dom.Node.COMMENT_NODE:
                    continue
                elif item.hasAttributes():
                    if item.hasAttribute('skelid'):
                        skelid = int(item.getAttribute('skelid'))
                        item.removeAttribute('skelid')
                    else:
                        skelid = -1
                    spine_array.append([False, skelid, None])

            pairs = [[spine_array[i][1], i] for i in range(len(spine_array))]
            spine_skelid_dict = dict(pairs)
            self.dom_spine = dom_spine
            self.spine_array = spine_array
            self.spine_skelid_dict = spine_skelid_dict


    def metadata_toxml(self):
        metadata_ = []
        dom_metadata = self.dom_metadata
        metadata_array = self.metadata_array
        if dom_metadata != None and len(dom_metadata) > 0 \
        and dom_metadata.item(0).hasChildNodes():
            nodeList = dom_metadata.item(0).childNodes
            for i in range(nodeList.length):
                if not metadata_array[i][0]:
                    continue
                item = nodeList.item(i)
                metadata_.append(item.toxml('utf-8') + '\n')
        return metadata_

    def spine_toxml(self):
        spine_ = []
        dom_spine = self.dom_spine
        spine_array = self.spine_array
        if dom_spine != None and len(dom_spine) > 0 \
        and dom_spine.item(0).hasChildNodes():
            nodeList = dom_spine.item(0).childNodes
            for i in range(nodeList.length):
                if not spine_array[i][0]:
                    continue
                item = nodeList.item(i)
                spine_.append(item.toxml('utf-8') + '\n')
        return spine_


    def getSpineIndexBySkelid(self, skelid):
        """Return corresponding spine item index to skelid.

        """
        if self.spine_skelid_dict != None:
            return self.spine_skelid_dict.get(skelid)
        else:
            return None

    def setFilenameToSpine(self, skelid, filename):
        index = self.getSpineIndexBySkelid(skelid)
        if index != None:
            self.spine_array[index][2] = filename

    def createFilenameToSpineIndexDict(self):
        spine_array = self.spine_array
        if spine_array != None:
            pairs = [[spine_array[i][2], i] for i in range(len(spine_array))]
            spine_filename_dict = dict(pairs)
            self.spine_filename_dict = spine_filename_dict

    def getSpineIndexByFilename(self, filename):
        spine_filename_dict = self.spine_filename_dict
        if filename == None:
            return None
        elif spine_filename_dict == None:
            return None
        else:
            return spine_filename_dict.get(filename)

    def getSpineIitem(self, i):
        dom_spine = self.dom_spine
        if dom_spine == None:
            return None
        if len(dom_spine) > 0 and dom_spine.item(0).hasChildNodes():
            nodeList = dom_spine.item(0).childNodes
            if i >= 0 and i < nodeList.length:
                return nodeList.item(i)
            else:
                return None

    def getSpineIdref(self, i):
        idref = None
        item = self.getSpineIitem(i)
        if item != None and item.nodeType != xml.dom.Node.COMMENT_NODE:
            if item.hasAttribute('idref'):
                idref = item.getAttribute('idref').encode('utf-8')
        return idref

    def setSpineIdref(self, i, ref):
        item = self.getSpineIitem(i)
        if item != None and item.nodeType != xml.dom.Node.COMMENT_NODE:
            if item.hasAttribute('idref'):
                item.removeAttribute('idref')
            item.setAttribute('idref', ref.decode('utf-8'))
            self.spine_array[i][0] = True


class K8Processor:
    def __init__(self, mh, sect, debug=False):
        self.sect = sect
        self.mi = MobiIndex(sect)
        self.mh = mh
        self.skelidx = mh.skelidx
        self.dividx = mh.dividx
        self.othidx = mh.othidx
        self.fdst = mh.fdst
        self.flowmap = {}
        self.flows = None
        self.flowinfo = []
        self.parts = None
        self.partinfo = []
        self.fdsttbl = [0,0xffffffff]
        self.resc = None
        self.DEBUG = debug

        # read in and parse the FDST info which is very similar in format to the Palm DB section
        # parsing except it provides offsets into rawML file and not the Palm DB file
        # this is needed to split up the final css, svg, etc flow section
        # that can exist at the end of the rawML file
        if self.fdst != 0xffffffff:
            header = self.sect.loadSection(self.fdst)
            if header[0:4] == "FDST":
                num_sections, = struct.unpack_from('>L', header, 0x08)
                self.fdsttbl = struct.unpack_from('>%dL' % (num_sections*2), header, 12)[::2] + (mh.rawSize, )
                sect.setsectiondescription(self.fdst,"KF8 FDST INDX")
                if self.DEBUG:
                    print "\nFDST Section Map:  %d sections" % num_sections
                    for j in xrange(num_sections):
                         print "Section %d: 0x%08X - 0x%08X" % (j, self.fdsttbl[j],self.fdsttbl[j+1])
            else:
                print "\nError: K8 Mobi with Missing FDST info"


        # read/process skeleton index info to create the skeleton table
        skeltbl = []
        if self.skelidx != 0xffffffff:
            # for i in xrange(2):
            #     fname = 'skel%04d.dat' % i
            #     data = self.sect.loadSection(self.skelidx + i)
            #     open(pathof(fname), 'wb').write(data)
            outtbl, ctoc_text = self.mi.getIndexData(self.skelidx, "KF8 Skeleton")
            fileptr = 0
            for [text, tagMap] in outtbl:
                # file number, skeleton name, divtbl record count, start position, length
                skeltbl.append([fileptr, text, tagMap[1][0], tagMap[6][0], tagMap[6][1]])
                fileptr += 1
        self.skeltbl = skeltbl
        if self.DEBUG:
            print "\nSkel Table:  %d entries" % len(self.skeltbl)
            print "table: filenum, skeleton name, div tbl record count, start position, length"
            for j in xrange(len(self.skeltbl)):
                print self.skeltbl[j]

        # read/process the div index to create to <div> (and <p>) table
        divtbl = []
        if self.dividx != 0xffffffff:
            # for i in xrange(3):
            #     fname = 'div%04d.dat' % i
            #     data = self.sect.loadSection(self.dividx + i)
            #     open(pathof(fname), 'wb').write(data)
            outtbl, ctoc_text = self.mi.getIndexData(self.dividx, "KF8 Division/Fragment")
            for [text, tagMap] in outtbl:
                # insert position, ctoc offset (aidtext), file number, sequence number, start position, length
                ctocoffset = tagMap[2][0]
                ctocdata = ctoc_text[ctocoffset]
                divtbl.append([int(text), ctocdata, tagMap[3][0], tagMap[4][0], tagMap[6][0], tagMap[6][1]])
        self.divtbl = divtbl
        if self.DEBUG:
            print "\nDiv (Fragment) Table: %d entries" % len(self.divtbl)
            print "table: file position, link id text, file num, sequence number, start position, length"
            for j in xrange(len(self.divtbl)):
                print self.divtbl[j]

        # read / process other index <guide> element of opf
        othtbl = []
        if self.othidx != 0xffffffff:
            # for i in xrange(3):
            #     fname = 'oth%04d.dat' % i
            #     data = self.sect.loadSection(self.othidx + i)
            #     open(pathof(fname), 'wb').write(data)
            outtbl, ctoc_text = self.mi.getIndexData(self.othidx, "KF8 Other (<guide> elements)")
            for [text, tagMap] in outtbl:
                # ref_type, ref_title, div/frag number
                ctocoffset = tagMap[1][0]
                ref_title = ctoc_text[ctocoffset]
                ref_type = text
                fileno = None
                if 3 in tagMap.keys():
                    fileno  = tagMap[3][0]
                if 6 in tagMap.keys():
                    fileno = tagMap[6][0]
                othtbl.append([ref_type, ref_title, fileno])
        self.othtbl = othtbl
        if self.DEBUG:
            print "\nOther (Guide) Table: %d entries" % len(self.othtbl)
            print "table: ref_type, ref_title, divtbl entry number"
            for j in xrange(len(self.othtbl)):
                print self.othtbl[j]

    def setResc(self, resc=None):
        """Set K8 RESC section information.

        """
        # FIXME Remove if dom version works well.
        if PROC_K8RESC_USE_RE:
            if resc != None:
                self.resc = K8RescRe(resc)
            return

        if resc != None:
            self.resc = K8Resc(resc)

    def buildParts(self, rawML):
        # now split the rawML into its flow pieces
        resc = self.resc

        self.flows = []
        for j in xrange(0, len(self.fdsttbl)-1):
            start = self.fdsttbl[j]
            end = self.fdsttbl[j+1]
            self.flows.append(rawML[start:end])

        # the first piece represents the xhtml text
        text = self.flows[0]
        self.flows[0] = ''

        # walk the <skeleton> and <div> tables to build original source xhtml files
        # *without* destroying any file position information needed for later href processing
        # and create final list of file separation start: stop points and etc in partinfo
        if self.DEBUG:
            print "\nRebuilding flow piece 0: the main body of the ebook"
        self.parts = []
        self.partinfo = []
        divptr = 0
        baseptr = 0
        cnt = 0
        for [skelnum, skelname, divcnt, skelpos, skellen] in self.skeltbl:
            baseptr = skelpos + skellen
            skeleton = text[skelpos: baseptr]
            for i in range(divcnt):
                [insertpos, idtext, filenum, seqnum, startpos, length] = self.divtbl[divptr]
                aidtext = idtext[12:-2]
                if i == 0:
                    filename = 'part%04d.xhtml' % filenum
                slice = text[baseptr: baseptr + length]
                insertpos = insertpos - skelpos
                head = skeleton[:insertpos]
                tail = skeleton[insertpos:]
                actual_inspos = insertpos
                if (tail.find(b'>') < tail.find(b'<') or head.rfind(b'>') < head.rfind(b'<')):
                    # There is an incomplete tag in either the head or tail.
                    # This can happen for some badly formed KF8 files
                    print 'The div table for %s has incorrect insert position. Calculating manually.' % skelname
                    bp, ep = locate_beg_end_of_tag(skeleton, aidtext)
                    if bp != ep:
                        actual_inspos = ep + 1 + startpos
                if insertpos != actual_inspos:
                    print "fixed corrupt div/frag table insert position", insertpos+skelpos, actual_inspos+skelpos
                    insertpos = actual_inspos
                    self.divtbl[divptr][0] = actual_inspos + skelpos
                skeleton = skeleton[0:insertpos] + slice + skeleton[insertpos:]
                baseptr = baseptr + length
                divptr += 1
            cnt += 1
            self.parts.append(skeleton)
            self.partinfo.append([skelnum, 'Text', filename, skelpos, baseptr, aidtext])

            if resc != None:
                resc.setFilenameToSpine(skelnum, filename)
        if resc != None:
            resc.createFilenameToSpineIndexDict()

        # assembled_text = "".join(self.parts)
        # open(pathof('assembled_text.dat'),'wb').write(assembled_text)

        # The primary css style sheet is typically stored next followed by any
        # snippets of code that were previously inlined in the
        # original xhtml but have been stripped out and placed here.
        # This can include local CDATA snippets and and svg sections.

        # The problem is that for most browsers and ereaders, you can not
        # use <img src="imageXXXX.svg" /> to import any svg image that itself
        # properly uses an <image/> tag to import some raster image - it
        # should work according to the spec but does not for almost all browsers
        # and ereaders and causes epub validation issues because those  raster
        # images are in manifest but not in xhtml text - since they only
        # referenced from an svg image

        # So we need to check the remaining flow pieces to see if they are css
        # or svg images.  if svg images, we must check if they have an <image />
        # and if so inline them into the xhtml text pieces.

        # there may be other sorts of pieces stored here but until we see one
        # in the wild to reverse engineer we won't be able to tell
        self.flowinfo.append([None, None, None, None])
        svg_tag_pattern = re.compile(r'''(<svg[^>]*>)''', re.IGNORECASE)
        image_tag_pattern = re.compile(r'''(<image[^>]*>)''', re.IGNORECASE)
        for j in xrange(1,len(self.flows)):
            flowpart = self.flows[j]
            nstr = '%04d' % j
            m = re.search(svg_tag_pattern, flowpart)
            if m != None:
                # svg
                type = 'svg'
                start = m.start()
                m2 = re.search(image_tag_pattern, flowpart)
                if m2 != None:
                    format = 'inline'
                    dir = None
                    fname = None
                    # strip off anything before <svg if inlining
                    flowpart = flowpart[start:]
                else:
                    format = 'file'
                    dir = "Images"
                    fname = 'svgimg' + nstr + '.svg'
            else:
                # search for CDATA and if exists inline it
                if flowpart.find('[CDATA[') >= 0:
                    type = 'css'
                    flowpart = '<style type="text/css">\n' + flowpart + '\n</style>\n'
                    format = 'inline'
                    dir = None
                    fname = None
                else:
                    # css - assume as standalone css file
                    type = 'css'
                    format = 'file'
                    dir = "Styles"
                    fname = 'style' + nstr + '.css'

            self.flows[j] = flowpart
            self.flowinfo.append([type, format, dir, fname])


        if self.DEBUG:
            print "\nFlow Map:  %d entries" % len(self.flowinfo)
            for fi in self.flowinfo:
                print fi
            print "\n"

            print "\nXHTML File Part Position Information: %d entries" % len(self.partinfo)
            for pi in self.partinfo:
                print pi

        if False: #self.Debug:
            # dump all of the locations of the aid tags used in TEXT
            # find id links only inside of tags
            #    inside any < > pair find all "aid=' and return whatever is inside the quotes
            #    [^>]* means match any amount of chars except for  '>' char
            #    [^'"] match any amount of chars except for the quote character
            #    \s* means match any amount of whitespace
            print "\npositions of all aid= pieces"
            id_pattern = re.compile(r'''<[^>]*\said\s*=\s*['"]([^'"]*)['"][^>]*>''',re.IGNORECASE)
            for m in re.finditer(id_pattern, rawML):
                [filename, partnum, start, end] = self.getFileInfo(m.start())
                [seqnum, idtext] = self.getDivTblInfo(m.start())
                value = fromBase32(m.group(1))
                print "  aid: %s value: %d at: %d -> part: %d, start: %d, end: %d" % (m.group(1), value, m.start(), partnum, start, end)
                print "       %s  divtbl entry %d" % (idtext, seqnum)

        return


    # get information div table entry by pos
    def getDivTblInfo(self, pos):
        baseptr = 0
        for j in xrange(len(self.divtbl)):
            [insertpos, idtext, filenum, seqnum, startpos, length] = self.divtbl[j]
            if pos >= insertpos and pos < (insertpos + length):
                return seqnum, 'in: ' + idtext
            if pos < insertpos:
                return seqnum, 'before: ' + idtext
        return None, None


    # get information about the part (file) that exists at pos in original rawML
    def getFileInfo(self, pos):
        for [partnum, dir, filename, start, end, aidtext] in self.partinfo:
            if pos >= start and pos < end:
                return filename, partnum, start, end
        return None, None, None, None


    # accessor functions to properly protect the internal structure
    def getNumberOfParts(self):
        return len(self.parts)

    def getPart(self,i):
        if i >= 0 and i < len(self.parts):
            return self.parts[i]
        return None

    def getPartInfo(self, i):
        if i >= 0 and i < len(self.partinfo):
            return self.partinfo[i]
        return None

    def getNumberOfFlows(self):
        return len(self.flows)

    def getFlow(self,i):
        # note flows[0] is empty - it was all of the original text
        if i > 0 and i < len(self.flows):
            return self.flows[i]
        return None

    def getFlowInfo(self,i):
        # note flowinfo[0] is empty - it was all of the original text
        if i > 0 and i < len(self.flowinfo):
            return self.flowinfo[i]
        return None


    def getIDTagByPosFid(self, posfid, offset):
        # first convert kindle:pos:fid and offset info to position in file
        row = fromBase32(posfid)
        off = fromBase32(offset)
        [insertpos, idtext, filenum, seqnm, startpos, length] = self.divtbl[row]
        pos = insertpos + off
        fname, pn, skelpos, skelend = self.getFileInfo(pos)
        if fname is None:
            # pos does not exist
            # default to skeleton pos instead
            print "Link To Position", pos, "does not exist, retargeting to top of target"
            pos = self.skeltbl[filenum][3]
            fname, pn, skelpos, skelend = self.getFileInfo(pos)
        # an existing "id=" or "name=" attribute must exist in original xhtml otherwise it would not have worked for linking.
        # Amazon seems to have added its own additional "aid=" inside tags whose contents seem to represent
        # some position information encoded into Base32 name.
        # so find the closest "id=" before position the file  by actually searching in that file
        idtext = self.getIDTag(pos)
        return fname, idtext

    def getIDTag(self, pos):
        # find the first tag with a named anchor (name or id attribute) before pos
        fname, pn, skelpos, skelend = self.getFileInfo(pos)
        if pn is None and skelpos is None:
            print "Error: getIDTag - no file contains ", pos
        textblock = self.parts[pn]
        idtbl = []
        npos = pos - skelpos
        # if npos inside a tag then search all text before the its end of tag marker
        pgt = textblock.find('>',npos)
        plt = textblock.find('<',npos)
        if plt == npos or pgt < plt:
            npos = pgt + 1
        # find id and name attributes only inside of tags
        # use a reverse tag search since that is faster
        #    inside any < > pair find "id=" and "name=" attributes return it
        #    [^>]* means match any amount of chars except for  '>' char
        #    [^'"] match any amount of chars except for the quote character
        #    \s* means match any amount of whitespace
        textblock = textblock[0:npos]
        id_pattern = re.compile(r'''<[^>]*\sid\s*=\s*['"]([^'"]*)['"]''',re.IGNORECASE)
        name_pattern = re.compile(r'''<[^>]*\sname\s*=\s*['"]([^'"]*)['"]''',re.IGNORECASE)
        for tag in reverse_tag_iter(textblock):
            m = id_pattern.match(tag) or name_pattern.match(tag)
            if m is not None:
                return m.group(1)
        if self.DEBUG:
            print "Found no id in the textblock, link must be to top of file"
        return ''


    # do we need to do deep copying
    def setParts(self, parts):
        assert(len(parts) == len(self.parts))
        for i in range(len(parts)):
            self.parts[i] = parts[i]

    # do we need to do deep copying
    def setFlows(self, flows):
        assert(len(flows) == len(self.flows))
        for i in xrange(len(flows)):
            self.flows[i] = flows[i]


    # get information about the part (file) that exists at pos in original rawML
    def getSkelInfo(self, pos):
        for [partnum, dir, filename, start, end, aidtext] in self.partinfo:
            if pos >= start and pos < end:
                return [partnum, dir, filename, start, end, aidtext]
        return [None, None, None, None, None, None]

    # fileno is actually a reference into divtbl (a fragment)
    def getGuideText(self):
        guidetext = ''
        for [ref_type, ref_title, fileno] in self.othtbl:
            if ref_type == 'thumbimagestandard':
                continue
            if ref_type not in _guide_types and not ref_type.startswith('other.'):
                if ref_type == 'start':
                    ref_type = 'text'
                else:
                    ref_type = 'other.' + ref_type
            [pos, idtext, filenum, seqnm, startpos, length] = self.divtbl[fileno]
            [pn, dir, filename, skelpos, skelend, aidtext] = self.getSkelInfo(pos)
            idtext = self.getIDTag(pos)
            linktgt = filename
            if idtext != '':
                linktgt += '#' + idtext
            guidetext += '<reference type="%s" title="%s" href="%s/%s" />\n' % (ref_type, ref_title, dir, linktgt)
        # opf is encoded utf-8 so must convert any titles properly
        guidetext = unicode(guidetext, self.mh.codec).encode("utf-8")
        return guidetext
