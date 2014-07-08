#!/usr/bin/env python
# -*- coding: utf-8 -*-

EPUB3_WITH_NCX = True # Do not set to False except for debug.
""" Set to True to create a toc.ncx when converting to epub3. """

EPUB3_WITH_GUIDE = True # Do not set to False except for debug.
""" Set to True to create a guide element in an opf when converting to epub3. """

DEBUG = False
if DEBUG:
    EPUB3_WITH_NCX = False
    EPUB3_WITH_GUIDE = False


OPF_NAME = 'content.opf'
""" The name for the OPF of EPUB. """

TOC_NCX = 'toc.ncx'
""" The name for the TOC of EPUB2. """

NAVIGATION_DOCUMENT = 'nav.xhtml'
""" The name for the navigation document of EPUB3. """

BEGIN_INFO_ONLY = '<!-- BEGIN INFORMATION ONLY '
""" The comment to indicate the beginning of metadata which will be ignored by kindlegen. """

END_INFO_ONLY = 'END INFORMATION ONLY -->'
""" The comment to indicate the end of metadata which will be ignored by kindlegen. """

PPD_KEY = 'page-progression-direction'
""" The meta name for page-progression-direction. """

PWM_KEY = 'primary-writing-mode'
""" The meta name for primary-writing-mode. """


import sys, os, re, uuid
from path import pathof
from xml.sax.saxutils import escape as xmlescape
from HTMLParser import HTMLParser
EXTRA_ENTITIES = {'"':'&quot;', "'":"&apos;"}
import mobi_taglist as taglist

class OPFProcessor(object):
    def __init__(self, files, metadata, fileinfo, imgnames, isNCX, mh, usedmap, pagemapxml='', guidetext=False, k8resc=None):
        self.files = files
        self.metadata = metadata
        self.fileinfo = fileinfo
        self.imgnames = imgnames
        self.isNCX = isNCX
        self.codec = mh.codec
        self.isK8 = mh.isK8()
        self.printReplica = mh.isPrintReplica()
        self.guidetext = guidetext
        self.used = usedmap
        self.k8resc = k8resc
        self.covername = None
        self.cover_id = None
        self.resc_metadata = []
        self.h = HTMLParser()
        # Create a unique urn uuid
        self.BookId = str(uuid.uuid4())
        self.starting_offset = None
        self.page_progression_direction = None
        self.pagemap = pagemapxml
        self.ncxname = None
        self.navname = None
        self.title_ids = []
        self.creator_ids = []
        self.publisher_ids = []


    def escapeit(self, sval, EXTRAS=None):
        # note, xmlescape and unescape do not work with utf-8 bytestrings
        # so pre-convert to full unicode and then convert back since opf is utf-8 encoded
        uval = sval.decode('utf-8')
        if EXTRAS:
            ures = xmlescape(self.h.unescape(uval), EXTRAS)
        else:
            ures = xmlescape(self.h.unescape(uval))
        return ures.encode('utf-8')


    # Call this function prior to call buildOPFMetadata().
    def getRESCExtraMetaData(self):
        if self.k8resc is not None:
            cover_id = self.k8resc.cover_name
            if cover_id is not None:
                self.cover_id = cover_id
            new_metadata = '' 
            for taginfo in self.k8resc.extrameta:
                new_metadata += self.k8resc.taginfo_toxml(taginfo)
            self.resc_metadata = new_metadata


    def buildOPFMetadata(self, start_tag, has_obfuscated_fonts=False):
        # Build metadata.
        metadata = self.metadata
        #k8resc = self.k8resc
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
        data.append(start_tag + '\n')
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
        if self.k8resc is not None:
            self.page_progression_direction = self.k8resc.spine_ppd
        pwm_value = metadata.pop(PWM_KEY, [None])[0]
        if pwm_value is not None:
            data.append('<meta name="'+PWM_KEY+'" content="'+self.escapeit(pwm_value, EXTRA_ENTITIES)+'" />\n')
            if 'rl' in pwm_value:
                self.page_progression_direction = 'rtl'

        # Append metadata in RESC section.
        self.getRESCExtraMetaData()
        if len(self.resc_metadata) > 0:
            data.append('<!-- Extra MetaData from RESC\n')
            data += self.resc_metadata
            data.append('-->\n')

        if 'CoverOffset' in metadata.keys():
            imageNumber = int(metadata['CoverOffset'][0])
            self.covername = self.imgnames[imageNumber]
            if self.covername is None:
                print "Error: Cover image %s was not recognized as a valid image" % imageNumber
            else:
                if self.cover_id is None:
                    self.cover_id = 'cover_img'
                    data.append('<meta name="cover" content="' + self.cover_id + '" />\n')
                self.used[self.covername] = 'used'
            del metadata['CoverOffset']
        i = taglist.find(data, 'meta', 'name', 'output encoding')
        if i is not None:
            data[i] = ''
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
        data.append(BEGIN_INFO_ONLY + '\n')
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
                # print "in opf processing ", metaName
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
        data.append(END_INFO_ONLY + '\n')
        data.append('</metadata>\n')
        return data

    # XXX: In this version, building manifest functions are splited into
    # for mobi7/azw4, for epub2 and for epub3 in order to undurstand easier
    # and to make safer for further extentions.
    # However; buildEPUB3OPFManifest() should work for all versions.
    # So it is possible to use one common function.
    # Note, this is not final.
    def buildOPFManifest(self, ncxname):
        # Build manifest for mobi7 and azw4.
        cover_id = self.cover_id
        self.ncxname = ncxname

        data = []
        data.append('<manifest>\n')
        media_map = {
                '.jpg'  : 'image/jpeg',
                '.jpeg' : 'image/jpeg',
                '.png'  : 'image/png',
                '.gif'  : 'image/gif',
                '.svg'  : 'image/svg+xml',
                '.xhtml': 'application/xhtml+xml',
                '.html' : 'text/x-oeb1-document',
                '.pdf'  : 'application/pdf'
                #'.ttf'  : 'application/x-font-ttf',
                #'.otf'  : 'application/x-font-opentype',
                #'.css'  : 'text/css'
                }
        spinerefs = []
        # Create an id set to prevent id confliction.
        idcnt = 0
        for [key,dir,fname] in self.fileinfo:
            name, ext = os.path.splitext(fname)
            ext = ext.lower()
            media = media_map.get(ext)
            ref = "item%d" % idcnt
            if dir != '':
                data.append('<item id="' + ref + '" media-type="' + media + '" href="' + dir + '/' + fname +'" />\n')
            else:
                data.append('<item id="' + ref + '" media-type="' + media + '" href="' + fname +'" />\n')
            if ext in ['.xhtml', '.html']:
                spinerefs.append(ref)
            idcnt += 1

        for fname in self.imgnames:
            if fname is not None:
                if self.used.get(fname,'not used') == 'not used':
                    continue
                name, ext = os.path.splitext(fname)
                ext = ext.lower()
                media = media_map.get(ext,ext[1:])
                if fname == self.covername:
                    ref = cover_id
                else:
                    ref = "item%d" % idcnt
                    # ref = self.createItemid('item{:d}'.format(idcnt), itemidset)
                # fonts only exist in K8 ebooks
                #if ext == '.ttf' or ext == '.otf':
                #    data.append('<item id="' + ref + '" media-type="' + media + '" href="Fonts/' + fname +'" />\n')
                #else:
                #    data.append('<item id="' + ref + '" media-type="' + media + '" href="Images/' + fname +'" />\n')
                data.append('<item id="' + ref + '" media-type="' + media + '" href="Images/' + fname +'" />\n')
                idcnt += 1

        if ncxname is not None:
            data.append('<item id="ncx" media-type="application/x-dtbncx+xml" href="' + ncxname +'"></item>\n')
        if self.pagemap != '':
            data.append('<item id="map" media-type="application/oebs-page-map+xml" href="page-map.xml"></item>\n')
        data.append('</manifest>\n')
        return [data, spinerefs]


    # This function is almost same to building manifest in writeOPF() of v0.72a,
    # manifest in output opf will be identical to v0.72a for mobi7, azw4 and mobi8.
    def buildEPUB2OPFManifest(self, ncxname):
        # for EPUB2 manifest.
        k8resc = self.k8resc
        cover_id = self.cover_id
        hasK8RescSpine = k8resc is not None and k8resc.hasSpine
        self.ncxname = ncxname

        data = []
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

        idcnt = 0
        for [key,dir,fname] in self.fileinfo:
            name, ext = os.path.splitext(fname)
            ext = ext.lower()
            media = media_map.get(ext)
            ref = "item%d" % idcnt
            if hasK8RescSpine:
                if key is not None and key in k8resc.spine_idrefs.keys():
                    ref = k8resc.spine_idrefs[key]
            if dir != '':
                data.append('<item id="' + ref + '" media-type="' + media + '" href="' + dir + '/' + fname +'" />\n')
            else:
                data.append('<item id="' + ref + '" media-type="' + media + '" href="' + fname +'" />\n')
            if ext in ['.xhtml', '.html']:
                spinerefs.append(ref)
            idcnt += 1

        for fname in self.imgnames:
            if fname is not None:
                if self.used.get(fname,'not used') == 'not used':
                    continue
                name, ext = os.path.splitext(fname)
                ext = ext.lower()
                media = media_map.get(ext,ext[1:])
                if fname == self.covername:
                    ref = cover_id
                else:
                    ref = "item%d" % idcnt
                if ext == '.ttf' or ext == '.otf':
                    data.append('<item id="' + ref + '" media-type="' + media + '" href="Fonts/' + fname +'" />\n')
                else:
                    data.append('<item id="' + ref + '" media-type="' + media + '" href="Images/' + fname +'" />\n')
                idcnt += 1
        data.append('<item id="ncx" media-type="application/x-dtbncx+xml" href="' + ncxname +'"></item>\n')
        if self.pagemap != '':
            data.append('<item id="map" media-type="application/oebs-page-map+xml" href="page-map.xml"></item>\n')
        data.append('</manifest>\n')
        return [data, spinerefs]


    # This function should work not only for epub3 but also for mobi7, azw4 and epub2.
    def buildEPUB3OPFManifest(self, ncxname, navname=None):
        # Build manifest for epub3.
        files = self.files
        k8resc = self.k8resc
        cover_id = self.cover_id
        hasK8RescSpine = k8resc is not None and k8resc.hasSpine
        isEpub3 = False
        if navname is not None:
            isEpub3 = True
        self.ncxname = ncxname
        self.navname = navname

        data = []
        # build manifest
        data.append('<manifest>\n')
        media_map = {
                '.jpg'  : 'image/jpeg',
                '.jpeg' : 'image/jpeg',
                '.png'  : 'image/png',
                '.gif'  : 'image/gif',
                '.svg'  : 'image/svg+xml',
                '.xhtml': 'application/xhtml+xml',
                '.html' : 'text/x-oeb1-document', # obsoleted?
                '.pdf'  : 'application/pdf', # for azw4(print replica textbook)
                '.ttf'  : 'application/x-font-ttf',
                '.otf'  : 'application/x-font-opentype', # replaced?
                #'.otf' : 'application/vnd.ms-opentype', # [OpenType] OpenType fonts
                #'.woff' : 'application/font-woff', # [WOFF] WOFF fonts
                #'.smil' : 'application/smil+xml', # [MediaOverlays301] EPUB Media Overlay documents
                #'.pls' : 'application/pls+xml', # [PLS] Text-to-Speech (TTS) Pronunciation lexicons
                #'.mp3'  : 'audio/mpeg',
                #'.mp4'  : 'audio/mp4',
                #'.js'   : 'text/javascript', # not supported in K8
                '.css'  : 'text/css'
                }
        spinerefs = []

        idcnt = 0
        for [key,dir,fname] in self.fileinfo:
            name, ext = os.path.splitext(fname)
            ext = ext.lower()
            media = media_map.get(ext)
            ref = "item%d" % idcnt
            if hasK8RescSpine:
                if key is not None and key in k8resc.spine_idrefs.keys():
                    ref = k8resc.spine_idrefs[key]
            properties = ''
            if dir != '':
                fpath = dir + '/' + fname
            else:
                fpath = fname
            data.append('<item id="{0:}" media-type="{1:}" href="{2:}" {3:}/>\n'.format(ref, media, fpath, properties))

            if ext in ['.xhtml', '.html']:
                spinerefs.append(ref)
            idcnt += 1

        for fname in self.imgnames:
            if fname is not None:
                if self.used.get(fname,'not used') == 'not used':
                    continue
                name, ext = os.path.splitext(fname)
                ext = ext.lower()
                media = media_map.get(ext,ext[1:])
                properties = ''
                if fname == self.covername:
                    ref = cover_id
                    if isEpub3:
                        properties = 'properties="cover-image"'
                else:
                    ref = "item%d" % idcnt
                if ext == '.ttf' or ext == '.otf':
                    fpath = 'Fonts/' + fname
                else:
                    fpath = 'Images/' + fname
                data.append('<item id="{0:}" media-type="{1:}" href="{2:}" {3:}/>\n'.format(ref, media, fpath, properties))
                idcnt += 1

        if navname is not None:
            media = 'application/xhtml+xml'
            ref = "nav"
            properties = 'properties="nav"'
            fpath = 'Text/' + navname
            data.append('<item id="{0:}" media-type="{1:}" href="{2:}" {3:}/>\n'.format(ref, media, fpath, properties))
        if ncxname is not None:
            data.append('<item id="ncx" media-type="application/x-dtbncx+xml" href="' + ncxname +'"></item>\n')
        if self.pagemap != '':
            data.append('<item id="map" media-type="application/oebs-page-map+xml" href="page-map.xml"></item>\n')
        data.append('</manifest>\n')
        return [data, spinerefs]


    def buildOPFSpine(self, spinerefs, isNCX):
        # build spine for mobi8
        k8resc = self.k8resc
        hasK8RescSpine = k8resc is not None and k8resc.hasSpine
        data = []
        ppd = ''
        if self.isK8 and self.page_progression_direction is not None:
            ppd = ' page-progression-direction="{:s}"'.format(self.page_progression_direction)
        ncx = ''
        if isNCX:
            ncx = ' toc="ncx"'
        map=''
        if self.pagemap != '':
            map = ' page-map="map"'
        spine_start_tag = '<spine{:s}{:s}{:s}>\n'.format(ppd, map, ncx)
        data.append(spine_start_tag)
        if hasK8RescSpine:
            for key in k8resc.spine_order:
                pp = k8resc.spine_pageprops[key]
                if pp is not None:
                    data.append('<itemref idref="%s" properties="%s" />\n' % (k8resc.spine_idrefs[key], pp))
                else:
                    data.append('<itemref idref="%s"/>\n' % k8resc.spine_idrefs[key])
        else:
            for entry in spinerefs:
                data.append('<itemref idref="' + entry + '"/>\n')
        data.append('</spine>\n')
        return data


    def buildOPF(self):
        # Build an OPF for mobi7 and azw4.
        print "Building an opf for mobi7/azw4."
        data = []
        data.append('<?xml version="1.0" encoding="utf-8"?>\n')
        data.append('<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid">\n')
        metadata_tag = '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
        opf_metadata = self.buildOPFMetadata(metadata_tag)
        data += opf_metadata
        if self.isNCX:
            ncxname = self.files.getInputFileBasename() + '.ncx'
        else:
            ncxname = None
        [opf_manifest, spinerefs] = self.buildOPFManifest(ncxname)
        data += opf_manifest
        opf_spine = self.buildOPFSpine(spinerefs, self.isNCX)
        data += opf_spine
        data.append('<tours>\n</tours>\n')
        if not self.printReplica:
            metaguidetext = ''
            # get guide items from metadata (note starting offset previsouly processed)
            if self.starting_offset is not None:
                so = self.starting_offset
                metaguidetext += '<reference type="text" href="'+self.fileinfo[0][2]+'#filepos'+so+'" />\n'
            guide ='<guide>\n' + metaguidetext + self.guidetext + '</guide>\n'
            data.append(guide)
        data.append('</package>\n')
        return ''.join(data)


    def buildEPUB2OPF(self, has_obfuscated_fonts=False):
        # Build an OPF for EPUB2.
        print "Building an opf for epub2"
        self.epubver = '2'
        data = []
        data.append('<?xml version="1.0" encoding="utf-8"?>\n')
        data.append('<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid">\n')
        metadata_tag = '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
        opf_metadata = self.buildOPFMetadata(metadata_tag, has_obfuscated_fonts)
        data += opf_metadata
        [opf_manifest, spinerefs] = self.buildEPUB2OPFManifest(TOC_NCX)
        data += opf_manifest
        opf_spine = self.buildOPFSpine(spinerefs, True)
        data += opf_spine
        data.append('<tours>\n</tours>\n')
        guide ='<guide>\n' + self.guidetext + '</guide>\n'
        data.append(guide)
        data.append('</package>\n')
        return ''.join(data)


    def buildEPUB3OPF(self, has_obfuscated_fonts=False):
        # Build an OPF for EPUB3.
        print "Building an opf for epub3"
        self.epubver = '3'
        has_ncx = EPUB3_WITH_NCX
        has_guide = EPUB3_WITH_GUIDE
        self.sovleRefineID()
        data = []
        data.append('<?xml version="1.0" encoding="utf-8"?>\n')
        data.append('<package version="3.0" xmlns="http://www.idpf.org/2007/opf" prefix="rendition: http://www.idpf.org/vocab/rendition/#" unique-identifier="uid">\n')
        #metadata_tag = '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">') # XXX: kobo cannot process.
        metadata_tag = '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
        opf_metadata = self.buildOPFMetadata(metadata_tag, has_obfuscated_fonts)
        newmetadata = self.convertAmazonMetadataToEPUB3(opf_metadata)
        opf_metadata = newmetadata
        data += opf_metadata
        [opf_manifest, spinerefs] = self.buildEPUB3OPFManifest(TOC_NCX, NAVIGATION_DOCUMENT)
        data += opf_manifest

        opf_spine = self.buildOPFSpine(spinerefs, has_ncx)
        data += opf_spine
        #data.append('<tours>\n</tours>\n')
        if has_guide:
            guide ='<guide>\n' + self.guidetext + '</guide>\n'
            data.append(guide)
        data.append('</package>\n')
        return ''.join(data)


    def buildK8OPF(self, has_obfuscated_fonts=False, epubver='2'):
        # Build an OPF for mobi8.
        # epubver: specify epub version: 2, 3 or A for automatic
        if epubver.upper() == 'A':
            epubver = self.sovleEPUBVersion()
        if epubver == '2':
            return self.buildEPUB2OPF(has_obfuscated_fonts)
        elif epubver == '3':
            return self.buildEPUB3OPF(has_obfuscated_fonts)
        else:
            return self.buildEPUB2OPF(has_obfuscated_fonts)


    def writeOPF(self, has_obfuscated_fonts=False, epubver='2'):
        # write out the metadata as an OEB 1.0 OPF file
        #print "Write opf"
        if self.isK8:
            return self.writeK8OPF(has_obfuscated_fonts, epubver)
        else:
            data = self.buildOPF()
            outopf = os.path.join(self.files.mobi7dir, self.files.getInputFileBasename() + '.opf')
            open(pathof(outopf), 'wb').write(data)


    def writeK8OPF(self, has_obfuscated_fonts=False, epubver='2'):
        # Write opf for mobi8
        data = self.buildK8OPF(has_obfuscated_fonts, epubver)
        outopf = os.path.join(self.files.k8oebps, OPF_NAME)
        open(pathof(outopf), 'wb').write(data)
        return self.BookId


    def getBookId(self):
        return self.BookId

    def getNCXName(self):
        return self.ncxname

    def getNAVName(self):
        return self.navname

    def getEPUBVersion(self):
        return self.epubver

    def hasNCX(self):
        return self.ncxname is not None

    def hasNAV(self):
        return self.navname is not None


    def sovleEPUBVersion(self):
        # Determine EPUB version from metadata and spine.
        metadata = self.metadata
        k8resc = self.k8resc
        self.epubver = '2'
        if 'true' == metadata.get('fixed-layout', [''])[0].lower():
            self.epubver = '3'
        elif 'rtl' in metadata.get(PPD_KEY, [''])[0].lower():
            self.epubver = '3'
        elif 'rl' in metadata.get(PWM_KEY, [''])[0].lower():
            self.epubver = '3'
        elif k8resc is not None and k8resc.hasSpine():
            self.epubver = k8resc.getEPUBVersion()
        return self.epubver


    def convertAmazonMetadataToEPUB3(self, metadata):
        # Convert Amazon definded meta to epub3 meta.
        overwrite_rendition_properties = True

        insert_pos = taglist.find(metadata, BEGIN_INFO_ONLY)
        if insert_pos is None:
            insert_pos = taglist.find(metadata, '<!-- The following meta tags are just for information and will be ignored by mobigen/kindlegen.')
        if insert_pos is None:
            insert_pos = len(metadata) - 1
        opf_metadata = metadata[:insert_pos]
        opf_metadata_tail = metadata[insert_pos:]

        isrc = taglist.find(opf_metadata, 'meta', 'name', 'fixed-layout')
        if isrc is not None:
            fixedlayout = taglist.get_attrib(opf_metadata, isrc, 'content')
            content = {'true' : 'pre-paginated'}.get(fixedlayout.lower(), 'reflowable')
            idst = taglist.find(opf_metadata, 'meta', 'property', 'rendition:layout')
            if idst is None:
                newdata = '<meta property="rendition:layout">' + content + '</meta>\n'
                opf_metadata.append(newdata)
            elif overwrite_rendition_properties:
                newdata = taglist.set_content(opf_metadata, idst, content)
                opf_metadata[idst] = newdata

        isrc = taglist.find(opf_metadata, 'meta', 'name', 'orientation-lock')
        if isrc is not None:
            orientation = taglist.get_attrib(opf_metadata, isrc, 'content')
            content = {'none' : 'auto'}.get(orientation.lower(), orientation)
            idst = taglist.find(opf_metadata, 'meta', 'property', 'rendition:orientation')
            if idst is None:
                newdata = '<meta property="rendition:orientation">' + content + '</meta>\n'
                opf_metadata.append(newdata)
            elif overwrite_rendition_properties:
                newdata = taglist.set_content(opf_metadata, idst, content)
                opf_metadata[idst] = newdata

        # Not certain whether corresponded or not.
        isrc = taglist.find(opf_metadata, 'meta', 'name', 'original-resolution')
        #if isrc is not None:
        if False:
            resolution = taglist.get_attrib(opf_metadata, isrc, 'content')
            re_resolution = re.compile(r'(?P<width>\d+)\D+(?P<height>\d+)', re.I)
            mo_resolution = re_resolution.search(resolution)
            if mo_resolution is not None:
                width = mo_resolution.group('width')
                height = mo_resolution.group('height')
                if int(width) > 0 and int(height) > 0:
                    viewport = 'width={}, height={}'.format(width, height)
            idst = taglist.find(opf_metadata, 'meta', 'property', 'rendition:viewport')
            if idst is None:
                newdata = '<meta property="rendition:viewport">' + viewport + '</meta>\n'
                opf_metadata.append(newdata)
            elif overwrite_rendition_properties:
                newdata = taglist.set_content(opf_metadata, idst, viewport)
                opf_metadata[idst] = newdata

        opf_metadata += opf_metadata_tail
        return opf_metadata


    # XXX: Under construction.
    def sovleRefineID(self):
        metadata = self.metadata
        dc_title = metadata.get('Title', [])
        dc_creator = metadata.get('Creator', [])
        dc_publisher = metadata.get('Publisher', [])
        fileas_title = metadata.get('Title file-as', [])
        fileas_creator = metadata.get('Creator file-as', [])
        fileas_publisher = metadata.get('Publisher file-as', [])

        title_ids = []
        creator_ids = []
        publisher_ids = []

        k8resc = self.k8resc
        if k8resc is not None:
            refineids = k8resc.metadata.getRefineIds()
            for id_ in refineids:
                if 'title' in id_.lower():
                    title_ids.append(id_)
            for id_ in refineids:
                if 'creator' in id_.lower():
                    creator_ids.append(id_)
            for id_ in refineids:
                if 'publisher' in id_.lower():
                    publisher_ids.append(id_)

        if len(dc_title) == 1:
            if len(title_ids) == 1 and len(fileas_title) <= 1:
                pass
            elif len(title_ids) == 0 and len(fileas_title) == 1:
                title_ids.append('title')
            else:
                title_ids = []
        else:
            title_ids = []

        if len(dc_publisher) == 1:
            if len(publisher_ids) == 1and len(fileas_publisher) <= 1:
                pass
            elif len(publisher_ids) == 0 and len(fileas_publisher) == 1:
                publisher_ids.append('publisher')
            else:
                publisher_ids = []
        else:
            publisher_ids = []

        if len(dc_creator) == 1:
            if len(creator_ids) == 1 and len(fileas_creator) <= 1:
                pass
            elif len(creator_ids) == 0 and len(fileas_creator) == 1:
                creator_ids.append('creator')
            else:
                creator_ids = []
        else:
            creator_ids = []

        self.title_ids = title_ids
        self.creator_ids = creator_ids
        self.publisher_ids = publisher_ids
        return
