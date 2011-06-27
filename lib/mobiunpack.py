#!/usr/bin/python

# Changelog
#  0.11 - Version by adamselene
#  0.11pd - Tweaked version by pdurrant
#  0.12 - extracts pictures too, and all into a folder.
#  0.13 - added back in optional output dir for those who don't want it based on infile
#  0.14 - auto flush stdout and wrapped in main, added proper return codes
#  0.15 - added support for metadata
#  0.16 - metadata now starting to be output as an opf file (PD)
#  0.17 - Also created tweaked text as source for Mobipocket Creator
#  0.18 - removed raw mobi file completely but kept _meta.html file for ease of conversion
#  0.19 - added in metadata for ASIN, Updated Title and Rights to the opf
#  0.20 - remove _meta.html since no longer needed
#  0.21 - Fixed some typos in the opf output, and also updated handling
#         of test for trailing data/multibyte characters
#  0.22 - Fixed problem with > 9 images
#  0.23 - Now output Start guide item
#  0.24 - set firstimg value for 'TEXtREAd'
#  0.25 - Now added character set metadata to html file for utf-8 files.
#  0.26 - Dictionary support added. Image handling speed improved. For huge files create temp files to speed up decoding.
#         Language decoding fixed. Metadata is now converted to utf-8 when written to opf file.

DEBUG = False
""" Set to True to print debug information. """

WRITE_RAW_DATA = False
""" Set to True to create additional files with raw data for debugging/reverse engineering. """

HUGE_FILE_SIZE = 5 * 1024 * 1024
""" If the size of the uncompressed raw html exceeds this limit, use temporary files to speed up processing. """

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

import array, struct, os, re

class UncompressedReader:
	def unpack(self, data):
		return data

class PalmdocReader:
	def unpack(self, i):
		o, p = '', 0
		while p < len(i):
			c = ord(i[p])
			p += 1
			if (c >= 1 and c <= 8):
				o += i[p:p+c]
				p += c
			elif (c < 128):
				o += chr(c);
			elif (c >= 192):
				o += ' ' + chr(c ^ 128);
			else:
				if p < len(i):
					c = (c << 8) | ord(i[p])
					p += 1
					m = (c >> 3) & 0x07ff
					n = (c & 7) + 3
					if (m > n):
						o += o[-m:n-m]
					else:
						for _ in xrange(n):
							o += o[-m]
		return o

class HuffcdicReader:
	q = struct.Struct('>Q').unpack_from

	def loadHuff(self, huff):
		if huff[0:8] != 'HUFF\x00\x00\x00\x18':
			raise ValueError('invalid huff header')
		off1, off2 = struct.unpack_from('>LL', huff, 8)

		def dict1_unpack(v):
			codelen, term, maxcode = v&0x1f, v&0x80, v>>8
			assert codelen != 0
			if codelen <= 8:
				assert term
			maxcode = ((maxcode + 1) << (32 - codelen)) - 1
			return (codelen, term, maxcode)
		self.dict1 = map(dict1_unpack, struct.unpack_from('>256L', huff, off1))

		dict2 = struct.unpack_from('>64L', huff, off2)
		self.mincode, self.maxcode = (), ()
		for codelen, mincode in enumerate((0,) + dict2[0::2]):
			self.mincode += (mincode << (32 - codelen), )
		for codelen, maxcode in enumerate((0,) + dict2[1::2]):
			self.maxcode += (((maxcode + 1) << (32 - codelen)) - 1, )

		self.dictionary = []

	def loadCdic(self, cdic):
		if cdic[0:8] != 'CDIC\x00\x00\x00\x10':
			raise ValueError('invalid cdic header')
		phrases, bits = struct.unpack_from('>LL', cdic, 8)
		n = min(1<<bits, phrases-len(self.dictionary))
		h = struct.Struct('>H').unpack_from
		def getslice(off):
			blen, = h(cdic, 16+off)
			slice = cdic[18+off:18+off+(blen&0x7fff)]
			return (slice, blen&0x8000)
		self.dictionary += map(getslice, struct.unpack_from('>%dH' % n, cdic, 16))

	def unpack(self, data):
		q = HuffcdicReader.q

		bitsleft = len(data) * 8
		data += "\x00\x00\x00\x00\x00\x00\x00\x00"
		pos = 0
		x, = q(data, pos)
		n = 32

		s = ''
		while True:
			if n <= 0:
				pos += 4
				x, = q(data, pos)
				n += 32
			code = (x >> n) & ((1 << 32) - 1)

			codelen, term, maxcode = self.dict1[code >> 24]
			if not term:
				while code < self.mincode[codelen]:
					codelen += 1
				maxcode = self.maxcode[codelen]

			n -= codelen
			bitsleft -= codelen
			if bitsleft < 0:
				break

			r = (maxcode - code) >> (32 - codelen)
			slice, flag = self.dictionary[r]
			if not flag:
				self.dictionary[r] = None
				slice = self.unpack(slice)
				self.dictionary[r] = (slice, 1)
			s += slice
		return s

class Sectionizer:
	def __init__(self, filename, perm):
		self.f = file(filename, perm)
		header = self.f.read(78)
		self.ident = header[0x3C:0x3C+8]
		self.num_sections, = struct.unpack_from('>H', header, 76)
		sections = self.f.read(self.num_sections*8)
		self.sections = struct.unpack_from('>%dL' % (self.num_sections*2), sections, 0)[::2] + (0xfffffff, )

	def loadSection(self, section):
		before, after = self.sections[section:section+2]
		self.f.seek(before)
		return self.f.read(after - before)

def getLanguage(langID, sublangID):
	mobilangdict = {
		54 : {0 : 'af'}, # Afrikaans
		28 : {0 : 'sq'}, # Albanian
		 1 : {0 : 'ar' , 5 : 'ar-dz' , 15 : 'ar-bh' , 3 : 'ar-eg' , 2 : 'ar-iq',  11 : 'ar-jo' , 13 : 'ar-kw' , 12 : 'ar-lb' , 4: 'ar-ly', 6 : 'ar-ma' , 8 : 'ar-om' , 16 : 'ar-qa' , 1 : 'ar-sa' , 10 : 'ar-sy' , 7 : 'ar-tn' , 14 : 'ar-ae' , 9 : 'ar-ye'}, # Arabic,  Arabic (Algeria),  Arabic (Bahrain),  Arabic (Egypt),  Arabic (Iraq), Arabic (Jordan),  Arabic (Kuwait),  Arabic (Lebanon),  Arabic (Libya), Arabic (Morocco),  Arabic (Oman),  Arabic (Qatar),  Arabic (Saudi Arabia),  Arabic (Syria),  Arabic (Tunisia),  Arabic (United Arab Emirates),  Arabic (Yemen)
		43 : {0 : 'hy'}, # Armenian
		77 : {0 : 'as'}, # Assamese
		44 : {0 : 'az'}, # "Azeri (IANA: Azerbaijani)
		45 : {0 : 'eu'}, # Basque
		35 : {0 : 'be'}, # Belarusian
		69 : {0 : 'bn'}, # Bengali
		 2 : {0 : 'bg'}, # Bulgarian
		 3 : {0 : 'ca'}, # Catalan
		 4 : {0 : 'zh' , 3 : 'zh-hk' , 2 : 'zh-cn' , 4 : 'zh-sg' , 1 : 'zh-tw'}, # Chinese,  Chinese (Hong Kong),  Chinese (PRC),  Chinese (Singapore),  Chinese (Taiwan)
		26 : {0 : 'hr'}, # Croatian
		 5 : {0 : 'cs'}, # Czech
		 6 : {0 : 'da'}, # Danish
		19 : {1 : 'nl' , 2 : 'nl-be'}, # Dutch / Flemish,  Dutch (Belgium)
 		 9 : {1 : 'en' , 3 : 'en-au' , 40 : 'en-bz' , 4 : 'en-ca' , 6 : 'en-ie' , 8 : 'en-jm' , 5 : 'en-nz' , 13 : 'en-ph' , 7 : 'en-za' , 11 : 'en-tt' , 2 : 'en-gb', 1 : 'en-us' , 12 : 'en-zw'}, # English,  English (Australia),  English (Belize),  English (Canada),  English (Ireland),  English (Jamaica),  English (New Zealand),  English (Philippines),  English (South Africa),  English (Trinidad),  English (United Kingdom),  English (United States),  English (Zimbabwe)
		37 : {0 : 'et'}, # Estonian
		56 : {0 : 'fo'}, # Faroese
		41 : {0 : 'fa'}, # Farsi / Persian
		11 : {0 : 'fi'}, # Finnish
		12 : {1 : 'fr' , 2 : 'fr-be' , 3 : 'fr-ca' , 5 : 'fr-lu' , 6 : 'fr-mc' , 4 : 'fr-ch'}, # French,  French (Belgium),  French (Canada),  French (Luxembourg),  French (Monaco),  French (Switzerland)
		55 : {0 : 'ka'}, # Georgian
		 7 : {1 : 'de' , 3 : 'de-at' , 5 : 'de-li' , 4 : 'de-lu' , 2 : 'de-ch'}, # German,  German (Austria),  German (Liechtenstein),  German (Luxembourg),  German (Switzerland)
		 8 : {0 : 'el'}, # Greek, Modern (1453-)
		71 : {0 : 'gu'}, # Gujarati
		13 : {0 : 'he'}, # Hebrew (also code 'iw'?)
		57 : {0 : 'hi'}, # Hindi
		14 : {0 : 'hu'}, # Hungarian
		15 : {0 : 'is'}, # Icelandic
		33 : {0 : 'id'}, # Indonesian
		16 : {1 : 'it' , 2 : 'it-ch'}, # Italian,  Italian (Switzerland)
		17 : {0 : 'ja'}, # Japanese
		75 : {0 : 'kn'}, # Kannada
		63 : {0 : 'kk'}, # Kazakh
		87 : {0 : 'x-kok'}, # Konkani (real language code is 'kok'?)
		18 : {0 : 'ko'}, # Korean
		38 : {0 : 'lv'}, # Latvian
		39 : {0 : 'lt'}, # Lithuanian
		47 : {0 : 'mk'}, # Macedonian
		62 : {0 : 'ms'}, # Malay
		76 : {0 : 'ml'}, # Malayalam
		58 : {0 : 'mt'}, # Maltese
		78 : {0 : 'mr'}, # Marathi
		97 : {0 : 'ne'}, # Nepali
		20 : {0 : 'no'}, # Norwegian
		72 : {0 : 'or'}, # Oriya
		21 : {0 : 'pl'}, # Polish
		22 : {2 : 'pt' , 1 : 'pt-br'}, # Portuguese,  Portuguese (Brazil)
		70 : {0 : 'pa'}, # Punjabi
		23 : {0 : 'rm'}, # "Rhaeto-Romanic" (IANA: Romansh)
		24 : {0 : 'ro'}, # Romanian
		25 : {0 : 'ru'}, # Russian
		59 : {0 : 'sz'}, # "Sami (Lappish)" (not an IANA language code)
								  # IANA code for "Northern Sami" is 'se'
								  # 'SZ' is the IANA region code for Swaziland
		79 : {0 : 'sa'}, # Sanskrit
		26 : {3 : 'sr'}, # Serbian
		27 : {0 : 'sk'}, # Slovak
		36 : {0 : 'sl'}, # Slovenian
		46 : {0 : 'sb'}, # "Sorbian" (not an IANA language code)
								  # 'SB' is IANA region code for 'Solomon Islands'
								  # Lower Sorbian = 'dsb'
								  # Upper Sorbian = 'hsb'
								  # Sorbian Languages = 'wen'
		10 : {0 : 'es' , 4 : 'es' , 44 : 'es-ar' , 64 : 'es-bo' , 52 : 'es-cl' , 36 : 'es-co' , 20 : 'es-cr' , 28 : 'es-do' , 48 : 'es-ec' , 68 : 'es-sv' , 16 : 'es-gt' , 72 : 'es-hn' , 8 : 'es-mx' , 76 : 'es-ni' , 24 : 'es-pa' , 60 : 'es-py' , 40 : 'es-pe' , 80 : 'es-pr' , 56 : 'es-uy' , 32 : 'es-ve'}, # Spanish,  Spanish (Mobipocket bug?),  Spanish (Argentina),  Spanish (Bolivia),  Spanish (Chile),  Spanish (Colombia),  Spanish (Costa Rica),  Spanish (Dominican Republic),  Spanish (Ecuador),  Spanish (El Salvador),  Spanish (Guatemala),  Spanish (Honduras),  Spanish (Mexico),  Spanish (Nicaragua),  Spanish (Panama),  Spanish (Paraguay),  Spanish (Peru),  Spanish (Puerto Rico),  Spanish (Uruguay),  Spanish (Venezuela)
		48 : {0 : 'sx'}, # "Sutu" (not an IANA language code)
								  # "Sutu" is another name for "Southern Sotho"?
								  # IANA code for "Southern Sotho" is 'st'
		65 : {0 : 'sw'}, # Swahili
		29 : {0 : 'sv' , 8 : 'sv-fi'}, # Swedish,  Swedish (Finland)
		73 : {0 : 'ta'}, # Tamil
		68 : {0 : 'tt'}, # Tatar
		74 : {0 : 'te'}, # Telugu
		30 : {0 : 'th'}, # Thai
		49 : {0 : 'ts'}, # Tsonga
		50 : {0 : 'tn'}, # Tswana
		31 : {0 : 'tr'}, # Turkish
		34 : {0 : 'uk'}, # Ukrainian
		32 : {0 : 'ur'}, # Urdu
		67 : {2 : 'uz'}, # Uzbek
		42 : {0 : 'vi'}, # Vietnamese
		52 : {0 : 'xh'}, # Xhosa
		53 : {0 : 'zu'}, # Zulu
	}

	return mobilangdict.get(int(langID), {0 : 'en'}).get(int(sublangID), 'en')

def getMetaData(codec, extheader):
	id_map_strings = { 
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
		118 : 'Price',
		119 : 'Currency',
		503 : 'Updated Title',
	}
	id_map_values = { 
		116 : 'StartOffset',
		201 : "CoverOffset",
	}
	metadata = {}
	_length, num_items = struct.unpack('>LL', extheader[4:12])
	extheader = extheader[12:]
	pos = 0
	left = num_items
	while left > 0:
		left -= 1
		id, size = struct.unpack('>LL', extheader[pos:pos+8])
		content = extheader[pos + 8: pos + size]
		if id in id_map_strings.keys():
			name = id_map_strings[id]
			metadata[name] = unicode(content, codec).encode("utf-8")
		elif id in id_map_values.keys():
			name = id_map_values[id]
			if size == 9:
				value, = struct.unpack('B',content)
				metadata[name] = str(value)
			elif size == 10:
				value, = struct.unpack('>H',content)
				metadata[name] = str(value)
			elif size == 12:
				value, = struct.unpack('>L',content)
				metadata[name] = str(value)
		pos += size
	return metadata

def getSizeOfTrailingDataEntry(data):
	num = 0
	for v in data[-4:]:
		if ord(v) & 0x80:
			num = 0
		num = (num << 7) | (ord(v) & 0x7f)
	return num

def getVariableWidthValue(data, offset):
	'''
	Decode variable width value from given bytes.
	
	@param data: The bytes to decode.
	@param offset: The start offset into data.
	@return: Tuple of consumed bytes count and decoded value.
	'''
	value = 0
	consumed = 0
	finished = False
	while not finished:
		v = data[offset + consumed]
		consumed += 1
		if ord(v) & 0x80:
			finished = True
		value = (value << 7) | (ord(v) & 0x7f)
	return consumed, value

def toHex(byteList):
	'''
	Convert list of characters into a string of hex values.
	
	@param byteList: List of characters.
	@return: String with the character hex values separated by spaces.
	'''
	return " ".join([hex(ord(c))[2:].zfill(2) for c in byteList])

def toBin(value, bits = 8):
	'''
	Convert integer value to binary string representation.
	
	@param value: The integer value.
	@param bits: The number of bits for the binary string (defaults to 8).
	@return: String with the binary representation.
	'''
	return "".join(map(lambda y:str((value>>y)&1), range(bits-1, -1, -1)))

def countSetBits(value, bits = 8):
	'''
	Count the set bits in the given value.
	
	@param value: Integer value.
	@param bits: The number of bits of the input value (defaults to 8).
	@return: Number of set bits.
	'''
	count = 0
	for _ in range(bits):
		if value & 0x01 == 0x01:
			count += 1
		value = value >> 1
	return count

def readTagSection(start, data):
	'''
	Read tag section from given data.
	
	@param start: The start position in the data.
	@param data: The data to process.
	@return: Tuple of control byte count and list of tag tuples.
	'''
	tags = []
	assert data[start:start+4] == "TAGX"
	firstEntryOffset, = struct.unpack_from('>L', data, start + 0x04)
	controlByteCount, = struct.unpack_from('>L', data, start + 0x08)

	# Skip the first 12 bytes already read above.
	for i in range(12, firstEntryOffset, 4):
		pos = start + i
		tags.append((ord(data[pos]), ord(data[pos+1]), ord(data[pos+2]), ord(data[pos+3])))
	return controlByteCount, tags

def getInflectionGroups(mainEntry, controlByteCount, tagTable, data, inflectionNames, groupList):
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
			print "Required tag 0x05 not found in tagMap"
			return ""
		if 0x1a not in tagMap:
			print "Required tag 0x1a not found in tagMap"
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
			inflection = applyInflectionRule(mainEntry, data, offset+1, offset+1+textLength)
			if inflection != None:
				result += '  <idx:iform name="%s" value="%s"/>' % (inflectionName, inflection)

		result += "</idx:infl>"
	return result

def hasTag(tagTable, tag):
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

def getTagMap(controlByteCount, tagTable, entryData, startPos, endPos):
	'''
	Create a map of tags and values from the given byte section.
	
	@param controlByteCount: The number of control bytes.
	@param tagTable: The tag table.
	@param entryData: The data to process.
	@param startPos: The starting position in entryData.
	@param endPos: The end position in entryData or None if it is unknown.
	@return: Hashmap of tag and list of values.
	'''
	tags = []
	tagHashMap = {}
	controlByteIndex = 0
	dataStart = startPos + controlByteCount

	for tag, valuesPerEntry, mask, endFlag in tagTable:
		if endFlag == 0x01:
			controlByteIndex += 1
			continue

		value = ord(entryData[startPos + controlByteIndex]) & mask

		if value != 0:
			if value == mask:
				if countSetBits(mask) > 1:
					# If all bits of masked value are set and the mask has more than one bit, a variable width value
					# will follow after the control bytes which defines the length of bytes (NOT the value count!)
					# which will contain the corresponding variable width values.
					consumed, value = getVariableWidthValue(entryData, dataStart)
					dataStart += consumed
					tags.append((tag, None, value, valuesPerEntry))
				else:
					tags.append((tag, 1, None, valuesPerEntry))
			else:
				# Shift bits to get the masked value.
				while mask & 0x01 == 0:
					mask = mask >> 1
					value = value >> 1
				tags.append((tag, value, None, valuesPerEntry))

	for tag, valueCount, valueBytes, valuesPerEntry in tags:
		values = []
		if valueCount != None:
			# Read valueCount * valuesPerEntry variable width values.
			for _ in range(valueCount):
				for _ in range(valuesPerEntry):
					consumed, data = getVariableWidthValue(entryData, dataStart)
					dataStart += consumed
					values.append(data)
		else:
			# Convert valueBytes to variable width values.
			totalConsumed = 0
			while totalConsumed < valueBytes:
				# Does this work for valuesPerEntry != 1?
				consumed, data = getVariableWidthValue(entryData, dataStart)
				dataStart += consumed
				totalConsumed += consumed
				values.append(data)
			if totalConsumed != valueBytes:
				print "Error: Should consume %s bytes, but consumed %s" % (valueBytes, totalConsumed)
		tagHashMap[tag] = values
		
	# Test that all bytes have been processed if endPos is given.
	if endPos is not None and dataStart != endPos:
		# The last entry might have some zero padding bytes, so complain only if non zero bytes are left.
		for char in entryData[dataStart:endPos]:
			if char != chr(0x00):
				print "Warning: There are unprocessed index bytes left: %s" % toHex(entryData[dataStart:endPos])
				if DEBUG:
					print "controlByteCount: %s" % controlByteCount
					print "tagTable: %s" % tagTable
					print "data: %s" % toHex(entryData[startPos:endPos])
					print "tagHashMap: %s" % tagHashMap
				break

	return tagHashMap

def applyInflectionRule(mainEntry, inflectionRuleData, start, end):
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
						if DEBUG:
							print "0x03: %s %s %s %s" % (mainEntry, toHex(inflectionRuleData[start:end]), char, deleted)
						print "Error: Delete operation of inflection rule failed"
						return None
				elif mode == 0x04:
					# Delete at word start
					deleted = byteArray.pop(position)
					if deleted != char:
						if DEBUG:
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

def unpackBook(infile, outdir):
	codec_map = {
		1252 : 'windows-1252',
		65001: 'utf-8',
	}
	if not os.path.exists(outdir):
		os.mkdir(outdir)
	outsrc = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.html'
	outopf = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.opf'
	imgdir = os.path.join(outdir, 'images')
	if not os.path.exists(imgdir):
		os.mkdir(imgdir)

	sect = Sectionizer(infile, 'rb')
	if sect.ident != 'BOOKMOBI' and sect.ident != 'TEXtREAd':
		raise ValueError('invalid file format')

	header = sect.loadSection(0)

	#write out raw header
	if WRITE_RAW_DATA:
		outraw = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.rawhdr'
		f = open(outraw, 'wb')
		f.write(header)
		f.close()

	if sect.ident != 'TEXtREAd':
		firstidx, = struct.unpack_from('>L', header, 0x50)
		firstimg, = struct.unpack_from('>L', header, 0x6C)
	else:
		records, = struct.unpack_from('>H', header, 0x8)
		firstidx = 0xFFFFFFFF
		firstimg = records + 1

	crypto_type, = struct.unpack_from('>H', header, 0xC)
	if crypto_type != 0:
		raise ValueError('file is encrypted')

	# get length of this header
	length, type, codepage, unique_id, version = struct.unpack('>LLLLL', header[20:40])
	print "Mobipocket version %s" % version

	# convert the codepage to codec string
	codec = 'windows-1252'
	if codepage in codec_map.keys() :
		codec = codec_map[codepage]

	# get book title
	toff, tlen = struct.unpack('>II', header[0x54:0x5c])
	tend = toff + tlen
	title = header[toff:tend]

	# if exth region exists then parse it for the metadata
	exth_flag, = struct.unpack('>L', header[0x80:0x84])
	metadata = {}
	if exth_flag & 0x40:
		metadata = getMetaData(codec, header[16 + length:])

	# get the language code
	langcode = struct.unpack('!L', header[0x5c:0x60])[0]
	langid = langcode & 0xFF
	sublangid = (langcode >> 10) & 0xFF
	metadata['Language']  = getLanguage(langid, sublangid)

	langcode = struct.unpack('!L', header[0x60:0x64])[0]
	langid = langcode & 0xFF
	sublangid = (langcode >> 10) & 0xFF
	if langid != 0:
		metadata['DictInLanguage'] = getLanguage(langid, sublangid)

	langcode = struct.unpack('!L', header[0x64:0x68])[0]
	langid = langcode & 0xFF
	sublangid = (langcode >> 10) & 0xFF
	if langid != 0:
		metadata['DictOutLanguage'] = getLanguage(langid, sublangid)

	metadata['Title'] = unicode(title, codec).encode("utf-8")
	metadata['Codec'] = codec
	metadata['UniqueID'] = str(unique_id)

	rawSize, = struct.unpack_from('>L', header, 0x4)
	records, = struct.unpack_from('>H', header, 0x8)

	hugeFile = True if rawSize > HUGE_FILE_SIZE else False
		
	multibyte = 0
	trailers = 0
	if sect.ident == 'BOOKMOBI':
		mobi_length, = struct.unpack_from('>L', header, 0x14)
		mobi_version, = struct.unpack_from('>L', header, 0x68)
		if (mobi_length >= 0xE4) and (mobi_version >= 5):
			flags, = struct.unpack_from('>H', header, 0xF2)
			multibyte = flags & 1
			while flags > 1:
				if flags & 2:
					trailers += 1
				flags = flags >> 1

	compression, = struct.unpack_from('>H', header, 0x0)
	if compression == 0x4448:
		print "Huffdic compression"
		reader = HuffcdicReader()
		huffoff, huffnum = struct.unpack_from('>LL', header, 0x70)
		reader.loadHuff(sect.loadSection(huffoff))
		for i in xrange(1, huffnum):
			reader.loadCdic(sect.loadSection(huffoff+i))
		unpack = reader.unpack
	elif compression == 2:
		print "Palmdoc compression"
		unpack = PalmdocReader().unpack
	elif compression == 1:
		print "No compression"
		unpack = UncompressedReader().unpack
	else:
		raise ValueError('invalid compression type: 0x%4x' % compression)

	def trimTrailingDataEntries(data):
		for _ in xrange(trailers):
			num = getSizeOfTrailingDataEntry(data)
			data = data[:-num]
		if multibyte:
			num = (ord(data[-1]) & 3) + 1
			data = data[:-num]
		return data

	#get raw mobi html-like markup languge
	print "Unpack raw html"
	rawtext = ''
	if hugeFile:
		outraw = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.rawml'
		f = open(outraw, 'wb')
	for i in xrange(records):
		data = sect.loadSection(1+i)
		data = trimTrailingDataEntries(data)
		data = unpack(data)
		if hugeFile:
			f.write(data)
		else:
			rawtext += data

	if hugeFile:
		f.close()
		f = open(outraw, 'rb')
		rawtext = f.read()
		f.close()
		if not WRITE_RAW_DATA:
			os.unlink(outraw)
			
	#write out raw text
	if WRITE_RAW_DATA and not hugeFile:
		outraw = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.rawml'
		f = open(outraw, 'wb')
		f.write(rawtext)
		f.close()

	#write out raw index sections
	if WRITE_RAW_DATA:
		if firstidx != 0xffffffff:
			for i in xrange(firstidx, firstimg):
				data = sect.loadSection(i)
				outraw = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + ('.%03x.rawidx' % i)
				f = open(outraw, 'wb')
				f.write(data)
				f.close()

	positionMap = {}

	metaOrthIndex, = struct.unpack_from('>L', header, 0x28)
	metaInflIndex, = struct.unpack_from('>L', header, 0x2C)

	decodeInflection = True
	if metaOrthIndex != 0xFFFFFFFF:
		print "Document contains orthographic index, handle as dictionary"
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
			if DEBUG:
				print "inflectionTagTable: %s" % inflectionTagTable
			if hasTag(inflectionTagTable, 0x07):
				print "Error: Dictionary uses obsolete inflection rule scheme which is not yet supported"
				decodeInflection = False

		data = sect.loadSection(metaOrthIndex)
		tagSectionStart, = struct.unpack_from('>L', data, 0x04)
		controlByteCount, tagTable = readTagSection(tagSectionStart, data)
		orthIndexCount, = struct.unpack_from('>L', data, 0x18)
		if DEBUG:
			print "orthTagTable: %s" % tagTable
		hasEntryLength = hasTag(tagTable, 0x02)
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
						inflectionGroups = getInflectionGroups(text, inflectionControlByteCount, inflectionTagTable, inflIndexData, inflNameData, tagMap[0x2a])
					else:
						inflectionGroups = ""
					assert len(tagMap[0x01]) == 1
					entryStartPosition = tagMap[0x01][0]
					if hasEntryLength:
						if entryStartPosition in positionMap:
							positionMap[entryStartPosition] = positionMap[entryStartPosition] + '<idx:entry><idx:orth value="%s">%s</idx:orth>' % (text, inflectionGroups)
						else:
							positionMap[entryStartPosition] = '<idx:entry><idx:orth value="%s">%s</idx:orth>' % (text, inflectionGroups)
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

	# write out the images to the folder of images
	print "Decode images"
	for i in xrange(firstimg, sect.num_sections):
		# We might write sections which doesn't contain an image (usually the last sections), but they won't be
		# referenced as images from the html code, so there is no need to filter them.
		data = sect.loadSection(i)
		# The file extension doesn't need not match the actual file content, it must be just a supported one.
		imgname = ("%05d.jpg" % (1+i-firstimg))
		outimg = os.path.join(imgdir, imgname)
		f = open(outimg, 'wb')
		f.write(data)
		f.close()

	# process the raw text
	# find anchors...
	print "Find link anchors"
	link_pattern = re.compile(r'''<[^<>]+filepos=['"]{0,1}(\d+)[^<>]*>''',
		re.IGNORECASE)
	for match in link_pattern.finditer(rawtext):
		position = int(match.group(1))
		if position in positionMap:
			positionMap[position] = positionMap[position] + '<a id="filepos%d" />' % position
		else:
			positionMap[position] = '<a id="filepos%d" />' % position

	# apply dictionary metadata and anchors
	print "Insert data into html"
	if hugeFile:
		outtmp = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.tmp'
		f = open(outtmp, "wb")

	pos = 0
	srctext = ''
	lastPos = len(rawtext)
	for end in sorted(positionMap.keys()):
		if end == 0 or end > lastPos:
			continue # something's up - can't put a tag in outside <html>...</html>
		if hugeFile:
			f.write(rawtext[pos:end])
			f.write(positionMap[end])
		else:
			srctext += rawtext[pos:end] + positionMap[end]
		pos = end

	if hugeFile:
		f.write(rawtext[pos:])
		f.close()
	
	# free rawtext resources
	rawtext = None

	if hugeFile:
		f = open(outtmp, "rb")
		srctext = f.read()
		f.close()
		os.unlink(outtmp)
		
	# put in the hrefs
	print "Insert hrefs into html"
	link_pattern = re.compile(r'''<a filepos=['"]{0,1}0*(\d+)['"]{0,1} *>''', re.IGNORECASE)
	srctext = link_pattern.sub(r'''<a href="#filepos\1">''', srctext)

	# remove empty anchors
	print "Remove empty anchors from html"
	srctext = re.sub(r"<a/>",r"", srctext)

	# convert image references
	print "Insert image references into html"
	# First pattern ensures that replacements are only done within the image tag.
	image_pattern = re.compile(r'''(<img.*?>)''', re.IGNORECASE)
	# Second pattern replaces recindex/hirecindex/lorecindex name and value.
	image_index_pattern = re.compile(r'''recindex=['"]{0,1}([0-9]+)['"]{0,1}''', re.IGNORECASE)

	subImageIndex = lambda match: image_index_pattern.sub(r'''src="images/\1.jpg"''', match.group(0))
	srctext = image_pattern.sub(subImageIndex, srctext)
	
	# add in character set meta into the html header if needed
	srctext = srctext[0:12]+'<meta http-equiv="content-type" content="text/html; charset='+metadata.get('Codec')+'" />'+srctext[12:]
	
	# write out source text
	print "Write html"
	f = open(outsrc, 'wb')
	f.write(srctext)
	f.close

	# write out the metadata as an OEB 1.0 OPF file
	print "Write opf"
	outhtmlbasename = os.path.basename(outsrc)
	f = file(outopf, 'wb')
	data = '<?xml version="1.0" encoding="utf-8"?>\n'
	data += '<package unique-identifier="uid">\n'
	data += '<metadata>\n'
	data += '<dc-metadata xmlns:dc="http://purl.org/metadata/dublin_core"'
	data += ' xmlns:oebpackage="http://openebook.org/namespaces/oeb-package/1.0/">\n'
	# Handle standard metadata
	data += '<dc:Title>' + metadata.get('Title','Untitled') + '</dc:Title>\n'
	data += '<dc:Language>' + metadata.get('Language') + '</dc:Language>\n'
	data += '<dc:Identifier id="uid">' + metadata.get('UniqueID',0) + '</dc:Identifier>\n'
	if 'Creator' in metadata:
		data += '<dc:Creator>'+metadata.get('Creator')+'</dc:Creator>\n'
	if 'Publisher' in metadata:
		data += '<dc:Publisher>'+metadata.get('Publisher')+'</dc:Publisher>\n'
	if 'ISBN' in metadata:
		data += '<dc:Identifier scheme="ISBN">'+metadata.get('ISBN')+'</dc:Identifier>\n'
	if 'Subject' in metadata:
		if 'SubjectCode' in metadata:
			data += '<dc:Subject BASICCode="'+metadata.get('SubjectCode')+'">'
		else:
			data += '<dc:Subject>'
		data += metadata.get('Subject')+'</dc:Subject>\n'
	if 'Description' in metadata:
		data += '<dc:Description>'+metadata.get('Description')+'</dc:Description>\n'
	if 'Published' in metadata:
		data += '<dc:Date>'+metadata.get('Published')+'</dc:Date>\n'
	if 'Rights' in metadata:
		data += '<dc:Rights>'+metadata.get('Rights')+'</dc:Rights>\n'
	data += '</dc-metadata>\n<x-metadata>\n'
	if 'DictInLanguage' in metadata:
		data += '<DictionaryInLanguage>'+metadata.get('DictInLanguage')+'</DictionaryInLanguage>\n'
	if 'DictOutLanguage' in metadata:
		data += '<DictionaryOutLanguage>'+metadata.get('DictOutLanguage')+'</DictionaryOutLanguage>\n'
	if 'Codec' in metadata:
		data += '<output encoding="'+metadata.get('Codec')+'">\n</output>\n'
	if 'CoverOffset' in metadata:
		data += '<EmbeddedCover>images/%05d.jpg</EmbeddedCover>\n' % (int(metadata.get('CoverOffset')) + 1)
	if 'Review' in metadata:
		data += '<Review>'+metadata.get('Review')+'</Review>\n'
	if ('Price' in metadata) and ('Currency' in metadata):
		data += '<SRP Currency="'+metadata.get('Currency')+'">'+metadata.get('Price')+'</SRP>\n'
	data += '</x-metadata>\n'
	if ('ASIN' in metadata):
		data += '<meta name="ASIN" content="' + metadata['ASIN'] + '" />\n'
	if ('Updated Title' in metadata):
		data += '<meta name="Updated Title" content="' + metadata['Updated Title'] + '" />\n'
	data += '</metadata>\n<manifest>\n'
	data += '<item id="item1" media-type="text/x-oeb1-document" href="'+outhtmlbasename+'"></item>\n'
	data += '</manifest>\n<spine>\n<itemref idref="item1"/>\n</spine>\n<tours>\n</tours>\n'
	
	# get guide items from metadata
	metaguidetext = ''
	if 'StartOffset' in metadata:
		metaguidetext += '<reference title="Start" type="text" href="'+outhtmlbasename+'#filepos'+metadata.get('StartOffset')+'" />'
	
	# get guide items from text
	guidetext =''
	guidematch = re.search(r'''<guide>(.*)</guide>''',srctext,re.IGNORECASE+re.DOTALL)
	if guidematch:
		replacetext = r'''href="'''+outhtmlbasename+r'''#filepos\1"'''
		guidetext = re.sub(r'''filepos=['"]{0,1}0*(\d+)['"]{0,1}''', replacetext, guidematch.group(0))
		guidetext = guidetext[7:-8]
	data += '<guide>\n'+metaguidetext+'\n'+guidetext+'\n'+'</guide>\n'
	
	data += '</package>'
	f.write(data)
	f.close()

def main(argv=sys.argv):
	print "MobiUnpack 0.26"
	print "  Copyright (c) 2009 Charles M. Hannum <root@ihack.net>"
	print "  With Images Support and Other Additions by P. Durrant and K. Hendricks"
	print "  With Dictionary Support and Other Additions by S. Siebert"
	if len(sys.argv) < 2:
		print ""
		print "Description:"
		print "  Unpacks an unencrypted MobiPocket file to html and images"
		print "  in a folder of the same name as the mobipocket file."
		print "Usage:"
		print "  mobiunpack.py infile.mobi [outdir]"
		return 1
	else:  
		if len(sys.argv) >= 3:
			infile, outdir = sys.argv[1:]
		else:
			infile = sys.argv[1]
			outdir = os.path.splitext(infile)[0]
		infileext = os.path.splitext(infile)[1].upper()
		if infileext not in ['.MOBI', '.PRC', '.AZW']:
			print "Error: first parameter must be a mobipocket file."
			return 1
	
		try:
			print 'Unpacking Book...'
			unpackBook(infile, outdir)
			print 'Completed'
			
			outname = os.path.basename(infile)
			outname = os.path.splitext(outname)[0] + '.html'
			outname = os.path.join(outdir,outname)
			print 'The Mobi HTML Markup Language File can be found at: ' + outname 
		except ValueError, e:
			print "Error: %s" % e
			return 1
		return 0

if __name__ == "__main__":
	sys.exit(main())
