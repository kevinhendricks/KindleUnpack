#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys, os, re, uuid
from path import pathof
from xml.sax.saxutils import escape as xmlescape
from HTMLParser import HTMLParser
EXTRA_ENTITIES = {'"':'&quot;', "'":"&apos;"}

class OPFProcessor:
    def __init__(self, files, metadata, filenames, imgnames, isNCX, mh, usedmap, pagemapxml='', guidetext=False, k8resc=None):
        self.files = files
        self.metadata = metadata
        self.filenames = filenames
        self.imgnames = imgnames
        self.isNCX = isNCX
        self.codec = mh.codec
        self.isK8 = mh.isK8()
        self.printReplica = mh.isPrintReplica()
        self.guidetext = guidetext
        self.used = usedmap
        self.k8resc = k8resc
        self.covername = None
        self.h = HTMLParser()
        # Create a unique urn uuid
        self.BookId = str(uuid.uuid4())
        self.starting_offset = None
        self.page_progression_direction = None
        self.pagemap = pagemapxml

    def escapeit(self, sval, EXTRAS=None):
        # note, xmlescape and unescape do not work with utf-8 bytestrings
        # so pre-convert to full unicode and then convert back since opf is utf-8 encoded
        uval = sval.decode('utf-8')
        if EXTRAS:
            ures = xmlescape(self.h.unescape(uval), EXTRAS)
        else:
            ures = xmlescape(self.h.unescape(uval))
        return ures.encode('utf-8')

    def writeOPF(self, has_obfuscated_fonts=False):
        # write out the metadata as an OEB 1.0 OPF file
        print "Write opf"
        metadata = self.metadata
        k8resc = self.k8resc

        META_TAGS = ['Drm Server Id', 'Drm Commerce Id', 'Drm Ebookbase Book Id', 'ASIN', 'ThumbOffset', 'Fake Cover',
                                                'Creator Software', 'Creator Major Version', 'Creator Minor Version', 'Creator Build Number',
                                                'Watermark', 'Clipping Limit', 'Publisher Limit', 'Text to Speech Disabled', 'CDE Type',
                                                'Updated Title', 'Font Signature (hex)', 'Tamper Proof Keys (hex)',  ]
        def handleTag(data, metadata, key, tag):
            '''
            Format metadata values.

            @param data: List of formatted metadata entries.
            @param metadata: The metadata dictionary.
            @param key: The key of the metadata value to handle.
            @param tag: The opf tag the the metadata value.
            '''
            if key in metadata.keys():
                for value in metadata[key]:
                    closingTag = tag.split(" ")[0]
                    res = '<%s>%s</%s>\n' % (tag, self.escapeit(value), closingTag)
                    data.append(res)
                del metadata[key]

        def handleMetaPairs(data, metadata, key, name):
            if key in metadata.keys():
                for value in metadata[key]:
                    res = '<meta name="%s" content="%s" />\n' % (name, self.escapeit(value, EXTRA_ENTITIES))
                    data.append(res)
                del metadata[key]

        data = []
        data.append('<?xml version="1.0" encoding="utf-8"?>\n')
        data.append('<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid">\n')
        data.append('<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n')
        # Handle standard metadata
        if 'Title' in metadata.keys():
            handleTag(data, metadata, 'Title', 'dc:title')
        else:
            data.append('<dc:title>Untitled</dc:title>\n')
        handleTag(data, metadata, 'Language', 'dc:language')
        if 'UniqueID' in metadata.keys():
            handleTag(data, metadata, 'UniqueID', 'dc:identifier id="uid"')
        else:
            # No unique ID in original, give it a generic one.
            data.append('<dc:identifier id="uid">0</dc:identifier>\n')
        if self.isK8 and has_obfuscated_fonts:
            # Use the random generated urn:uuid so obuscated fonts work.
            # It doesn't need to be _THE_ unique identifier to work as a key
            # for obfuscated fonts in Sigil, ADE and calibre. Its just has
            # to use the opf:scheme="UUID" and have the urn:uuid: prefix.
            data.append('<dc:identifier opf:scheme="UUID">urn:uuid:'+self.BookId+'</dc:identifier>\n')

        handleTag(data, metadata, 'Creator', 'dc:creator')
        handleTag(data, metadata, 'Contributor', 'dc:contributor')
        handleTag(data, metadata, 'Publisher', 'dc:publisher')
        handleTag(data, metadata, 'Source', 'dc:source')
        handleTag(data, metadata, 'Type', 'dc:type')
        handleTag(data, metadata, 'ISBN', 'dc:identifier opf:scheme="ISBN"')
        if 'Subject' in metadata.keys():
            if 'SubjectCode' in metadata.keys():
                codeList = metadata['SubjectCode']
                del metadata['SubjectCode']
            else:
                codeList = None
            for i in range(len(metadata['Subject'])):
                if codeList and i < len(codeList):
                    data.append('<dc:subject BASICCode="'+codeList[i]+'">')
                else:
                    data.append('<dc:subject>')
                data.append(self.escapeit(metadata['Subject'][i])+'</dc:subject>\n')
            del metadata['Subject']
        handleTag(data, metadata, 'Description', 'dc:description')
        handleTag(data, metadata, 'Published', 'dc:date opf:event="publication"')
        handleTag(data, metadata, 'Rights', 'dc:rights')
        handleTag(data, metadata, 'DictInLanguage', 'DictionaryInLanguage')
        handleTag(data, metadata, 'DictOutLanguage', 'DictionaryOutLanguage')

       # page-progression-direction
        ppd_key = 'page-progression-direction'
        self.page_progression_direction = metadata.pop(ppd_key, [None])[0]
        pwm_key = 'primary-writing-mode'
        pwm_value = metadata.pop(pwm_key, [None])[0]
        if pwm_value != None:
            data.append('<meta name="'+pwm_key+'" content="'+self.escapeit(pwm_value, EXTRA_ENTITIES)+'" />\n')
            if 'rl' in pwm_value:
                self.page_progression_direction = 'rtl'

        # Append metadata in RESC section.
        cover_id = None
        if k8resc != None:
            cover_id = k8resc.cover_id
            resc_metadata_ = k8resc.metadata_toxml()
            if len(resc_metadata_) > 0:
                data.append('<!-- Begin imported from RESC section -->\n')
                data += resc_metadata_
                data.append('<!-- End imported from RESC section -->\n')

        if 'CoverOffset' in metadata.keys():
            imageNumber = int(metadata['CoverOffset'][0])
            self.covername = self.imgnames[imageNumber]
            if self.covername is None:
                print "Error: Cover image %s was not recognized as a valid image" % imageNumber
            else:
                if cover_id == None:
                    cover_id = 'cover_img'
                    data.append('<meta name="cover" content="' + cover_id + '" />\n')
                self.used[self.covername] = 'used'
            del metadata['CoverOffset']
        handleMetaPairs(data, metadata, 'Codec', 'output encoding')
        # handle kindlegen specifc tags
        handleMetaPairs(data, metadata, 'RegionMagnification', 'RegionMagnification')
        handleMetaPairs(data, metadata, 'fixed-layout', 'fixed-layout')
        handleMetaPairs(data, metadata, 'original-resolution', 'original-resolution')
        handleMetaPairs(data, metadata, 'orientation-lock', 'orientation-lock')
        handleMetaPairs(data, metadata, 'book-type', 'book-type')
        handleMetaPairs(data, metadata, 'zero-gutter', 'zero-gutter')
        handleMetaPairs(data, metadata, 'zero-margin', 'zero-margin')

        handleTag(data, metadata, 'Review', 'Review')
        handleTag(data, metadata, 'Imprint', 'Imprint')
        handleTag(data, metadata, 'Adult', 'Adult')
        handleTag(data, metadata, 'DictShortName', 'DictionaryVeryShortName')
        if 'Price' in metadata.keys() and 'Currency' in metadata.keys():
            priceList = metadata['Price']
            currencyList = metadata['Currency']
            if len(priceList) != len(currencyList):
                print "Error: found %s price entries, but %s currency entries."
            else:
                for i in range(len(priceList)):
                    data.append('<SRP Currency="'+currencyList[i]+'">'+priceList[i]+'</SRP>\n')
            del metadata['Price']
            del metadata['Currency']
        data.append("<!-- The following meta tags are just for information and will be ignored by mobigen/kindlegen. -->\n")
        if 'ThumbOffset' in metadata.keys():
            imageNumber = int(metadata['ThumbOffset'][0])
            imageName = self.imgnames[imageNumber]
            if imageName is None:
                print "Error: Cover Thumbnail image %s was not recognized as a valid image" % imageNumber
            else:
                data.append('<meta name="Cover ThumbNail Image" content="'+ 'Images/'+imageName+'" />\n')
                # self.used[imageName] = 'used' # thumbnail image is always generated by Kindlegen, so don't include in manifest
                self.used[imageName] = 'not used'
            del metadata['ThumbOffset']
        for metaName in META_TAGS:
            if metaName in metadata.keys():
                for value in metadata[metaName]:
                    data.append('<meta name="'+metaName+'" content="'+self.escapeit(value, EXTRA_ENTITIES)+'" />\n')
                    del metadata[metaName]
        for key in metadata.keys():
            for value in metadata[key]:
                if key == 'StartOffset':
                    if int(value) == 0xffffffff:
                        value = '0'
                    self.starting_offset = value
                data.append('<meta name="'+key+'" content="'+self.escapeit(value, EXTRA_ENTITIES)+'" />\n')
            del metadata[key]
        data.append('</metadata>\n')

        # build manifest
        data.append('<manifest>\n')
        media_map = {
                '.jpg'  : 'image/jpeg',
                '.jpeg' : 'image/jpeg',
                '.png'  : 'image/png',
                '.gif'  : 'image/gif',
                '.svg'  : 'image/svg+xml',
                '.xhtml': 'application/xhtml+xml',
                '.html' : 'text/x-oeb1-document',
                '.pdf'  : 'application/pdf',
                '.ttf'  : 'application/x-font-ttf',
                '.otf'  : 'application/x-font-opentype',
                '.css'  : 'text/css'
                }
        spinerefs = []

        # Create an id set to prevent id confliction.
        if k8resc != None and k8resc.hasSpine():
            istart = k8resc.getSpineStartIndex()
            iend = k8resc.getSpineEndIndex()
            itemidset = set(zip(*k8resc.spine)[2][istart:iend])
        else:
            itemidset = set()
        if cover_id != None:
            itemidset.add(cover_id)

        def create_itemid(idcnt):
            idsuf = 0
            itemid = "item{0:d}".format(idcnt)
            while itemid in itemidset:
                itemid = "item{0:d}-{1:d}".format(idcnt, idsuf)
                idsuf += 1
            itemidset.add(itemid)
            return itemid

        idcnt = 0
        for [dir,fname] in self.filenames:
            name, ext = os.path.splitext(fname)
            ext = ext.lower()
            media = media_map.get(ext)
            ref = create_itemid(idcnt)
            if k8resc != None and k8resc.hasSpine():
                index = k8resc.getSpineIndexByFilename(fname)
                if index != None:
                    itemid = k8resc.getSpineIdref(index)
                    #ref += '_' + itemid
                    ref = itemid
                    k8resc.setSpineIdref(index, ref)

            if dir != '':
                data.append('<item id="' + ref + '" media-type="' + media + '" href="' + dir + '/' + fname +'" />\n')
            else:
                data.append('<item id="' + ref + '" media-type="' + media + '" href="' + fname +'" />\n')
            if ext in ['.xhtml', '.html']:
                spinerefs.append(ref)
            idcnt += 1

        for fname in self.imgnames:
            if fname != None:
                if self.used.get(fname,'not used') == 'not used':
                    continue
                name, ext = os.path.splitext(fname)
                ext = ext.lower()
                media = media_map.get(ext,ext[1:])
                if fname == self.covername:
                    ref = cover_id
                    # ref += '" properties="cover-image'
                else:
                    ref = create_itemid(idcnt)

                if ext == '.ttf' or ext == '.otf':
                    data.append('<item id="' + ref + '" media-type="' + media + '" href="Fonts/' + fname +'" />\n')
                else:
                    data.append('<item id="' + ref + '" media-type="' + media + '" href="Images/' + fname +'" />\n')
                idcnt += 1

        if self.isNCX:
            if self.isK8:
                ncxname = 'toc.ncx'
            else:
                ncxname = self.files.getInputFileBasename() + '.ncx'
            data.append('<item id="ncx" media-type="application/x-dtbncx+xml" href="' + ncxname +'"></item>\n')
        if self.pagemap != '':
            data.append('<item id="map" media-type="application/oebs-page-map+xml" href="page-map.xml"></item>\n')
        data.append('</manifest>\n')

        # build spine
        spine_start_tag = '<spine'
        if self.page_progression_direction != None:
            spine_start_tag += ' page-progression-direction="{:s}"'.format(self.page_progression_direction)
        if self.isNCX:
            spine_start_tag += ' toc="ncx"'
        spine_start_tag += '>\n'
        data.append(spine_start_tag)
        if k8resc != None and k8resc.hasSpine():
            spine_ = k8resc.spine_toxml()
            data += spine_
        else:
            for entry in spinerefs:
                data.append('<itemref idref="' + entry + '"/>\n')
        data.append('</spine>\n')

        data.append('<tours>\n</tours>\n')

        if not self.printReplica:
            metaguidetext = ''
            if not self.isK8:
                # get guide items from metadata (note starting offset previsouly processed)
                if self.starting_offset != None:
                    so = self.starting_offset
                    metaguidetext += '<reference type="text" href="'+self.filenames[0][1]+'#filepos'+so+'" />\n'
            data.append('<guide>\n' + metaguidetext + self.guidetext + '</guide>\n')
        data.append('</package>\n')
        if self.isK8:
            outopf = os.path.join(self.files.k8oebps,'content.opf')
        else:
            outopf = os.path.join(self.files.mobi7dir, self.files.getInputFileBasename() + '.opf')
        open(pathof(outopf), 'wb').write("".join(data))
        if self.isK8:
            return self.BookId
