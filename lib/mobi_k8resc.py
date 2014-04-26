#!/usr/bin/env python
# -*- coding: utf-8 -*-

# XXX Currently dom modules are not stable enough.
#PROC_K8RESC_USE_DOM = False
#""" Process K8 RESC section by dom modules. """

import sys, os, re
import xml.dom
import xml.dom.minidom
from path import pathof

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
        self.data = None
        #self.cover_id = None
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

        self.re_metadata = re.compile(r'(<metadata[^>]*>)(.*?)(</metadata>)', re.I)
        self.re_attrib = re.compile(r'\s*(?P<attrib>\S+)\s*=\s*"(?P<value>[^"]*)"', re.I)
        self.re_element = re.compile(r'''
                (?P<comment><!--.*?-->)
            |
                (?P<start_tag><(?P<tag>\S+).*?((?P<empty>/>)|>))
                (?(empty)|(?P<content>[^<]*)(?P<end_tag></(?P=tag)>))
            ''', re.X+re.I)

        re_pattern = ''
        tag_types = self.tag_types
        for tag_type in tag_types[:-1]:
            re_pattern += '(?P<{}><{})|'.format(tag_type, tag_type)
        else:
            re_pattern += '(?P<{}><{})'.format(tag_types[-1], tag_types[-1])
        self.re_tag_type = re.compile(re_pattern, re.I)


    def process(self, src):
        """Import metadata from src.

        """
        re_metadata = self.re_metadata
        re_element = self.re_element
        re_attrib = self.re_attrib
        re_tag_type = self.re_tag_type

        mo_meta = re_metadata.search(src)
        if mo_meta != None:
            data = []
            #[0:element, 1:type_id, 2:tag, 3:attribs, 4:isEmpty, 5:start_tag, 6:content, 7:end_tag]
            data.append([mo_meta.group(1), self.getTypeId(self.METADATA_START),
                         None, None, None, None, None, None])

            elements = mo_meta.group(2)
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

            data.append([mo_meta.group(3), self.getTypeId(self.METADATA_END),
                         None, None, None, None, None, None])
            self.data = data
            #FIxME self.searchCoverId()

    def metadata_toxml(self):
        metadata_ = []
        num = self.getNumberOfElements()
        for [element, typeid, tag, attribs, isEmpty, start, content, end] \
                in self.getElements(range(1, num-1)):
            #if typeid == self.getTypeId(resc_metadata.METADATA_COMMENT):
            #    continue
            if typeid >= 1:
                if 'refines' in attribs:
                    continue
                metadata_.append(element + '\n')
        return metadata_

    def getTypeId(self, type_):
        return self.metadata_type.get(type_)

    def getType(self, type_id):
        return self.metadata_type_inv.get(type_id)

    def getNumberOfElements(self):
        if self.data == None:
            return 0
        else:
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

class K8RESCProcessor:
    """RESC section processor, using re module.

    """
    def __init__(self, resc):
        self.cover_id = None
        self.xml_header = None
        self.metadata = Metadata()
        self.meta_types = None
        self.spine = None #[itemref, skelid, itemid, isvalid, filename]
        self.spine_skelid_dict = None
        self.spine_filename_dict = None

        if resc == None or len(resc) != 3:
            return
        [version, type_, data] = resc
        self.version = version
        self.type = type_
        self.data = data

        mo_xml = re.search(r'<\?xml[^>]*>', data, re.I)
        if mo_xml != None:
            self.xml_header = mo_xml.group()

        self.metadata.process(data)
        
        # Find cover in metadata
        metadata = self.metadata
        typeid_meta = metadata.getTypeId(metadata.METADATA_META)
        num = metadata.getNumberOfElements()
        for [element, typeid, tag, attribs, isEmpty, start, content, end] \
                in metadata.getElements(range(1, num-1)):
            if typeid == typeid_meta:
                name = attribs.get('name')
                content = attribs.get('content')
                if name != None and name.lower() == 'cover':
                    self.cover_id = content
                    break

        mo_spine = re.search(r'(<spine[^>]*>)(.*?)(</spine>)', data, re.I)
        if mo_spine != None:
            spine = []
            spine.append([mo_spine.group(1), None, None, True, None])

            # process itemrefs
            data_ = mo_spine.group(2)
            itemrefs = re.findall(r'<[^>]*>', data_)
            re_idref = re.compile(r'(.*?)\s*idref="([^"]*)"(.*)', re.I)
            re_skelid = re.compile(r'(.*?)\s*skelid="([^"]*)"(.*)', re.I)
            for itemref in itemrefs:
                mo_idref = re_idref.search(itemref)
                if mo_idref != None:
                    striped_itemref = mo_idref.group(1) + mo_idref.group(3)
                    itemid = mo_idref.group(2)
                else:
                    striped_itemref = itemref
                    print 'Warning: no itemid in <itemref /> in the spine of RESC.'
                    break
                
                mo_skelid = re_skelid.search(striped_itemref)
                if mo_skelid != None:
                    striped_itemref = mo_skelid.group(1) + mo_skelid.group(3)
                    if mo_skelid.group(2).isdigit():
                        skelid = int(mo_skelid.group(2))
                    else:
                        skelid = -1
                else:
                    skelid = -1
                
                spine.append([striped_itemref, skelid, itemid, False, None])
            else:
                spine.append(['</spine>', None, None, True, None])
                #pairs = [[spine[i][1], i] for i in range(1, len(spine)-1)]
                #spine_skelid_dict = dict(pairs)
                self.spine = spine
                self.createSkelidToSpineIndexDict()
        return


    def metadata_toxml(self):
        return self.metadata.metadata_toxml()

    def spine_toxml(self):
        spine = self.spine
        spine_ = []
        if spine != None:
            re_itemref = re.compile(r'<itemref(.*?)/>', re.I)
            for [itemref, skelid, itemid, isvalid, filename] in spine[1:-1]:
                mo_itemref = re_itemref.search(itemref)
                if isvalid and mo_itemref != None:
                    elm = '<itemref idref="{:s}"{:s}/>'.format(itemid, mo_itemref.group(1))
                    spine_.append(elm + '\n')
        return spine_

    def hasSpine(self):
        return self.spine != None

    def getSpineStartIndex(self):
        return 1

    def getSpineEndIndex(self):
        return len(self.spine) - 1

    def getSpineIndexBySkelid(self, skelid):
        """Return corresponding itemref index to skelnum.

        """
        if self.spine_skelid_dict != None:
            #[itemref, skelid, itemid, isvalid, filename]
            index = self.spine_skelid_dict.get(skelid)
        else:
            index = None
        return index

    def getSpineIndexByFilename(self, filename):
        spine_filename_dict = self.spine_filename_dict
        if filename == None:
            return None
        elif spine_filename_dict == None:
            return None
        else:
            return spine_filename_dict.get(filename)


    def getFilenameFromSpine(self, i):
        if i != None:
            #[itemref, skelid, itemid, isvalid, filename]
            return self.spine[i][4]
        else:
            return None

    def setFilenameToSpine(self, i, filename):
        if i != None:
            #[itemref, skelid, itemid, isvalid, filename]
            self.spine[i][4] = filename

    def getSpineSkelid(self, i):
        #[itemref, skelid, itemid, isvalid, filename]
        return self.spine[i][1]

    def setSpineSkelid(self, i, skelid):
        #[itemref, skelid, itemid, isvalid, filename]
        self.spine[i][1] = skelid

    def getSpineIdref(self, i):
        #[itemref, skelid, itemid, isvalid, filename]
        return self.spine[i][2]

    def setSpineIdref(self, i, ref):
        #[itemref, skelid, itemid, isvalid, filename]
        self.spine[i][2] = ref
        self.spine[i][3] = True
        
    def setSpineAttribute(self, i, name, content):
        itemref = self.spine[i][0]
        pa_attrib = r'''(?P<tag><itemref)(?:
            ((?P<head>.*?)(?P<name>{:s})\s*=\s*"(?P<content>.*?)"(?P<tail>.*))
            |(?P<nomatch>.*?/>))'''.format(name)
        mo_attrib = re.search(pa_attrib, itemref, re.I + re.X)
        if mo_attrib != None:
            if mo_attrib.group('content') != None:
                new = mo_attrib.group('tag') + mo_attrib.group('head') \
                    + '{:s}="{:s}"'.format(name, content) \
                    + mo_attrib.group('tail')
            else:
                new = mo_attrib.group('tag') \
                    + ' {:s}="{:s}"'.format(name, content) \
                    + mo_attrib.group('nomatch')
            self.spine[i][0] = new


    def insertSpine(self, i, itemid, skelid=-1, filename=None):
        newspine = self.spine[:i] \
            + [['<itemref/>', skelid, itemid, False, filename]] \
            + self.spine[i:]
        self.spine = newspine

    def createSkelidToSpineIndexDict(self):
        spine = self.spine
        if spine != None:
            pairs = [[spine[i][1], i] for i in range(1, len(spine)-1)]
            spine_skelid_dict = dict(pairs)
            self.spine_skelid_dict = spine_skelid_dict

    def createFilenameToSpineIndexDict(self):
        spine = self.spine
        if spine != None:
            pairs = [[spine[i][4], i] for i in range(1, len(spine)-1)]
            spine_filename_dict = dict(pairs)
            self.spine_filename_dict = spine_filename_dict


# XXX Currently dom modules are not stable enough.
# insertSpine() function is not implemented.
class K8RESCProcessorDom:
    """RESC section processer using dom modules.

    """
    def __init__(self, resc):
        self.cover_id = None
        self.dom_metadata = None
        self.dom_spine = None
        self.metadata_array = None
        self.spine_array = None
        self.spine_skelid_dict = None
        self.spine_filename_dict = None

        if resc == None or len(resc) != 3:
            return
        [version, type_, data] = resc
        self.version = version
        self.type = type_
        self.data = data

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

            self.dom_spine = dom_spine
            self.spine_array = spine_array
            self.createSkelidToSpineIndexDict()


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

    def hasSpine(self):
        return self.dom_spine != None

    def getSpineStartIndex(self):
        return 0

    def getSpineEndIndex(self):
        return len(self.spine_array)

    def getSpineIndexBySkelid(self, skelid):
        """Return corresponding spine item index to skelid.

        """
        if self.spine_skelid_dict != None:
            return self.spine_skelid_dict.get(skelid)
        else:
            return None

    def getSpineIndexByFilename(self, filename):
        spine_filename_dict = self.spine_filename_dict
        if filename == None:
            return None
        elif spine_filename_dict == None:
            return None
        else:
            return spine_filename_dict.get(filename)

    def getFilenameFromSpine(self, i):
        if i != None:
            return self.spine_array[i][2]
        else:
            return None

    def setFilenameToSpine(self, i, filename):
        if i != None:
            self.spine_array[i][2] = filename

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

    def getSpineSkelid(self, i):
        skelid = None
        item = self.getSpineIitem(i)
        if item != None and item.nodeType != xml.dom.Node.COMMENT_NODE:
            if item.hasAttribute('skelid'):
                skelid = item.getAttribute('skelid').encode('utf-8')
        return int(skelid)

    def setSpineSkelid(self, i, skelid):
        item = self.getSpineIitem(i)
        if item != None and item.nodeType != xml.dom.Node.COMMENT_NODE:
            if item.hasAttribute('skelid'):
                item.removeAttribute('skelid')
            item.setAttribute('skelid', str(skelid).decode('utf-8'))

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

    def setSpineAttribute(self, i, name, content):
        item = self.getSpineIitem(i)
        if item != None and item.nodeType != xml.dom.Node.COMMENT_NODE:
            if item.hasAttribute(name):
                item.removeAttribute(name)
            item.setAttribute(name, content.decode('utf-8'))


    def createSkelidToSpineIndexDict(self):
            spine_array = self.spine_array
            pairs = [[spine_array[i][1], i] for i in range(len(spine_array))]
            spine_skelid_dict = dict(pairs)
            self.spine_skelid_dict = spine_skelid_dict

    def createFilenameToSpineIndexDict(self):
        spine_array = self.spine_array
        if spine_array != None:
            pairs = [[spine_array[i][2], i] for i in range(len(spine_array))]
            spine_filename_dict = dict(pairs)
            self.spine_filename_dict = spine_filename_dict


# XXX experimental
class CoverProcessor:
    """Create a cover page.

    """
    def __init__(self, files, metadata, imgnames):
        self.files = files
        self.metadata = metadata
        self.imgnames = imgnames

        self.cover_page = 'cover_page.xhtml'
        self.cover_image = None
        self.title = 'Untitled'
        self.lang = 'en'
        
        if 'CoverOffset' in metadata.keys():
            imageNumber = int(metadata['CoverOffset'][0])
            cover_image = self.imgnames[imageNumber]
            if cover_image != None:
                self.cover_image = cover_image
        title = metadata.get('Title')[0]
        if title != None:
            self.title = title
        lang = metadata.get('Language')[0]
        if lang != None:
            self.lang = lang
        return
        
    def getImageName(self):
        return self.cover_image

    def getXHTMLName(self):
        return self.cover_page

    def writeXHTML(self):
        files = self.files
        cover_page = self.cover_page
        cover_image = self.cover_image
        title = self.title
        lang = self.lang

        image_dir = os.path.relpath(files.k8images, files.k8text).replace('\\', '/')

        data = ''
        data += '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        data += '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'
        data += ' xml:lang="{:s}">\n'.format(lang)
        data += '<head>\n<title>{:s}</title>\n'.format(title)
        data += '<style type="text/css">\n'
        data += 'body {\n\tmargin: 0;\n\tpadding: 0;\n\ttext-align: center;\n}\n'
        data += 'div {\n\theight: 100%;\n\twidth: 100%;\n\ttext-align: center;\n\tpage-break-inside: avoid;\n}\n'
        data += 'img {\n\tdisplay: inline-block;\n\theight: 100%;\n\tmargin: 0 auto;\n}\n'
        data += '</style>\n</head>\n'
        data += '<body><div>\n'
        data += '\t<img src="{:s}/{:s}" alt=""/>\n'.format(image_dir, cover_image)
        data += '</div></body>\n</html>'

        outfile = os.path.join(files.k8text, self.cover_page)
        if os.path.exists(pathof(outfile)):
            print 'Warning: {:s} already exists.'.format(cover_page)
            #return
            os.remove(pathof(outfile))
        open(pathof(outfile), 'w').write(data)
        return
        
    def guide_toxml(self):
        files = self.files
        text_dir = os.path.relpath(files.k8text, files.k8oebps)
        data = '<reference type="cover" title="Cover" href="{:s}/{:s}" />\n'.format(\
                text_dir, self.cover_page)
        return data
