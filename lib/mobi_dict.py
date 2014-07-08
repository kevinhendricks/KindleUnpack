#!/usr/bin/env python
# -*- coding: utf-8 -*-

DEBUG_DICT = False

import sys
import array, struct, os, re, imghdr

from mobi_index import getVariableWidthValue, readTagSection, countSetBits, getTagMap
from mobi_utils import toHex, toBin, getLanguage

class dictSupport:
    def __init__(self, mh, sect):
        self.mh = mh
        self.header = mh.header
        self.sect = sect
        self.metaOrthIndex = mh.metaOrthIndex
        self.metaInflIndex = mh.metaInflIndex

    def getPositionMap (self):
        header = self.header
        sect = self.sect

        positionMap = {}

        metaOrthIndex = self.metaOrthIndex
        metaInflIndex = self.metaInflIndex

        decodeInflection = True
        if metaOrthIndex != 0xFFFFFFFF:
            print "Info: Document contains orthographic index, handle as dictionary"
            if metaInflIndex == 0xFFFFFFFF:
                decodeInflection = False
            else:
                metaInflIndexData = sect.loadSection(metaInflIndex)
                metaIndexCount, = struct.unpack_from('>L', metaInflIndexData, 0x18)
                if metaIndexCount != 1:
                    print "Error: Dictionary contains multiple inflection index sections, which is not yet supported"
                    decodeInflection = False
                inflIndexData = sect.loadSection(metaInflIndex + 1)
                inflNameData = sect.loadSection(metaInflIndex + 1 + metaIndexCount)
                tagSectionStart, = struct.unpack_from('>L', metaInflIndexData, 0x04)
                inflectionControlByteCount, inflectionTagTable = readTagSection(tagSectionStart, metaInflIndexData)
                if DEBUG_DICT:
                    print "inflectionTagTable: %s" % inflectionTagTable
                if self.hasTag(inflectionTagTable, 0x07):
                    print "Error: Dictionary uses obsolete inflection rule scheme which is not yet supported"
                    decodeInflection = False

            data = sect.loadSection(metaOrthIndex)
            tagSectionStart, = struct.unpack_from('>L', data, 0x04)
            controlByteCount, tagTable = readTagSection(tagSectionStart, data)
            orthIndexCount, = struct.unpack_from('>L', data, 0x18)
            print "orthIndexCount is", orthIndexCount
            if DEBUG_DICT:
                print "orthTagTable: %s" % tagTable
            hasEntryLength = self.hasTag(tagTable, 0x02)
            if not hasEntryLength:
                print "Info: Index doesn't contain entry length tags"

            print "Read dictionary index data"
            for i in range(metaOrthIndex + 1, metaOrthIndex + 1 + orthIndexCount):
                data = sect.loadSection(i)
                idxtPos, = struct.unpack_from('>L', data, 0x14)
                entryCount, = struct.unpack_from('>L', data, 0x18)
                idxPositions = []
                for j in range(entryCount):
                    pos, = struct.unpack_from('>H', data, idxtPos + 4 + (2 * j))
                    idxPositions.append(pos)
                # The last entry ends before the IDXT tag (but there might be zero fill bytes we need to ignore!)
                idxPositions.append(idxtPos)

                for j in range(entryCount):
                    startPos = idxPositions[j]
                    endPos = idxPositions[j+1]
                    textLength = ord(data[startPos])
                    text = data[startPos+1:startPos+1+textLength]
                    tagMap = getTagMap(controlByteCount, tagTable, data, startPos+1+textLength, endPos)
                    if 0x01 in tagMap:
                        if decodeInflection and 0x2a in tagMap:
                            inflectionGroups = self.getInflectionGroups(text, inflectionControlByteCount, inflectionTagTable, inflIndexData, inflNameData, tagMap[0x2a])
                        else:
                            inflectionGroups = ""
                        assert len(tagMap[0x01]) == 1
                        entryStartPosition = tagMap[0x01][0]
                        if hasEntryLength:
                            # The idx:entry attribute "scriptable" must be present to create entry length tags.
                            ml = '<idx:entry scriptable="yes"><idx:orth value="%s">%s</idx:orth>' % (text, inflectionGroups)
                            if entryStartPosition in positionMap:
                                positionMap[entryStartPosition] = positionMap[entryStartPosition] + ml
                            else:
                                positionMap[entryStartPosition] = ml
                            assert len(tagMap[0x02]) == 1
                            entryEndPosition = entryStartPosition + tagMap[0x02][0]
                            if entryEndPosition in positionMap:
                                positionMap[entryEndPosition] = "</idx:entry>" + positionMap[entryEndPosition]
                            else:
                                positionMap[entryEndPosition] = "</idx:entry>"

                        else:
                            indexTags = '<idx:entry>\n<idx:orth value="%s">\n%s</idx:entry>\n' % (text, inflectionGroups)
                            if entryStartPosition in positionMap:
                                positionMap[entryStartPosition] = positionMap[entryStartPosition] + indexTags
                            else:
                                positionMap[entryStartPosition] = indexTags
        return positionMap

    def hasTag(self, tagTable, tag):
        '''
        Test if tag table contains given tag.

        @param tagTable: The tag table.
        @param tag: The tag to search.
        @return: True if tag table contains given tag; False otherwise.
        '''
        for currentTag, _, _, _ in tagTable:
            if currentTag == tag:
                return True
        return False

    def getInflectionGroups(self, mainEntry, controlByteCount, tagTable, data, inflectionNames, groupList):
        '''
        Create string which contains the inflection groups with inflection rules as mobipocket tags.

        @param mainEntry: The word to inflect.
        @param controlByteCount: The number of control bytes.
        @param tagTable: The tag table.
        @param data: The inflection index data.
        @param inflectionNames: The inflection rule name data.
        @param groupList: The list of inflection groups to process.
        @return: String with inflection groups and rules or empty string if required tags are not available.
        '''
        result = ""
        idxtPos, = struct.unpack_from('>L', data, 0x14)
        entryCount, = struct.unpack_from('>L', data, 0x18)
        for value in groupList:
            offset, = struct.unpack_from('>H', data, idxtPos + 4 + (2 * value))
            if value + 1 < entryCount:
                nextOffset, = struct.unpack_from('>H', data, idxtPos + 4 + (2 * (value + 1)))
            else:
                nextOffset = None

            # First byte seems to be always 0x00 and must be skipped.
            assert ord(data[offset]) == 0x00
            tagMap = getTagMap(controlByteCount, tagTable, data, offset + 1, nextOffset)

            # Make sure that the required tags are available.
            if 0x05 not in tagMap:
                print "Error: Required tag 0x05 not found in tagMap"
                return ""
            if 0x1a not in tagMap:
                print "Error: Required tag 0x1a not found in tagMap"
                return ""

            result += "<idx:infl>"

            for i in range(len(tagMap[0x05])):
                # Get name of inflection rule.
                value = tagMap[0x05][i]
                consumed, textLength = getVariableWidthValue(inflectionNames, value)
                inflectionName = inflectionNames[value+consumed:value+consumed+textLength]

                # Get and apply inflection rule.
                value = tagMap[0x1a][i]
                offset, = struct.unpack_from('>H', data, idxtPos + 4 + (2 * value))
                textLength = ord(data[offset])
                inflection = self.applyInflectionRule(mainEntry, data, offset+1, offset+1+textLength)
                if inflection is not None:
                    result += '  <idx:iform name="%s" value="%s"/>' % (inflectionName, inflection)

            result += "</idx:infl>"
        return result


    def applyInflectionRule(self, mainEntry, inflectionRuleData, start, end):
        '''
        Apply inflection rule.

        @param mainEntry: The word to inflect.
        @param inflectionRuleData: The inflection rules.
        @param start: The start position of the inflection rule to use.
        @param end: The end position of the inflection rule to use.
        @return: The string with the inflected word or None if an error occurs.
        '''
        mode = -1
        byteArray = array.array("c", mainEntry)
        position = len(byteArray)
        for charOffset in range(start, end):
            char = inflectionRuleData[charOffset]
            byte = ord(char)
            if byte >= 0x0a and byte <= 0x13:
                # Move cursor backwards
                offset = byte - 0x0a
                if mode not in [0x02, 0x03]:
                    mode = 0x02
                    position = len(byteArray)
                position -= offset
            elif byte > 0x13:
                if mode == -1:
                    print "Error: Unexpected first byte %i of inflection rule" % byte
                    return None
                elif position == -1:
                    print "Error: Unexpected first byte %i of inflection rule" % byte
                    return None
                else:
                    if mode == 0x01:
                        # Insert at word start
                        byteArray.insert(position, char)
                        position += 1
                    elif mode == 0x02:
                        # Insert at word end
                        byteArray.insert(position, char)
                    elif mode == 0x03:
                        # Delete at word end
                        position -= 1
                        deleted = byteArray.pop(position)
                        if deleted != char:
                            if DEBUG_DICT:
                                print "0x03: %s %s %s %s" % (mainEntry, toHex(inflectionRuleData[start:end]), char, deleted)
                            print "Error: Delete operation of inflection rule failed"
                            return None
                    elif mode == 0x04:
                        # Delete at word start
                        deleted = byteArray.pop(position)
                        if deleted != char:
                            if DEBUG_DICT:
                                print "0x03: %s %s %s %s" % (mainEntry, toHex(inflectionRuleData[start:end]), char, deleted)
                            print "Error: Delete operation of inflection rule failed"
                            return None
                    else:
                        print "Error: Inflection rule mode %x is not implemented" % mode
                        return None
            elif byte == 0x01:
                # Insert at word start
                if mode not in [0x01, 0x04]:
                    position = 0
                mode = byte
            elif byte == 0x02:
                # Insert at word end
                if mode not in [0x02, 0x03]:
                    position = len(byteArray)
                mode = byte
            elif byte == 0x03:
                # Delete at word end
                if mode not in [0x02, 0x03]:
                    position = len(byteArray)
                mode = byte
            elif byte == 0x04:
                # Delete at word start
                if mode not in [0x01, 0x04]:
                    position = 0
                mode = byte
            else:
                print "Error: Inflection rule mode %x is not implemented" % byte
                return None
        return byteArray.tostring()

