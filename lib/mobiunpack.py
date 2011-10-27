#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

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
#  0.24 - Set firstimg value for 'TEXtREAd'
#  0.25 - Now added character set metadata to html file for utf-8 files.
#  0.26 - Dictionary support added. Image handling speed improved. For huge files create temp files to speed up decoding.
#         Language decoding fixed. Metadata is now converted to utf-8 when written to opf file.
#  0.27 - Add idx:entry attribute "scriptable" if dictionary contains entry length tags. Don't save non-image sections
#         as images. Extract and save source zip file included by kindlegen as kindlegensrc.zip.
#  0.28 - Added back correct image file name extensions, created FastConcat class to simplify and clean up
#  0.29 - Metadata handling reworked, multiple entries of the same type are now supported. Serveral missing types added.
#         FastConcat class has been removed as in-memory handling with lists is faster, even for huge files.
#  0.30 - Add support for outputting **all** metadata values - encode content with hex if of unknown type 
#  0.31 - Now supports Print Replica ebooks, outputting PDF and mysterious data sections
#  0.32 - Now supports NCX file extraction/building.
#		  Overhauled the structure of mobiunpack to be more class oriented.

DEBUG = False
DEBUG_NCX = False
""" Set to True to print debug information. """

WRITE_RAW_DATA = False
""" Set to True to create additional files with raw data for debugging/reverse engineering. """

EOF_RECORD = chr(0xe9) + chr(0x8e) + "\r\n"
""" The EOF record content. """

KINDLEGENSRC_FILENAME = "kindlegensrc.zip"
""" The name for the kindlegen source archive. """

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

import array, struct, os, re, imghdr

class unpackException(Exception):
	pass

class fileNames:
	def __init__(self, infile, outdir):
		self.infile = infile
		self.outdir = outdir
		if not os.path.exists(outdir):
			os.mkdir(outdir)
		self.outsrc = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.html'
		self.outopf = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.opf'
		self.outncx = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.ncx'
		self.imgdir = os.path.join(outdir, 'images')
		if not os.path.exists(self.imgdir):
			os.mkdir(self.imgdir)
		self.outsrcbasename = os.path.basename(self.outsrc)
		self.outhtmlbasename = unicode(os.path.basename(self.outsrc), sys.getfilesystemencoding()).encode("utf-8")
		
	def getOutRaw(self, ext):
		return os.path.join(self.outdir, os.path.splitext(os.path.split(self.infile)[1])[0]) + ext

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
			raise unpackException('invalid huff header')
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
			raise unpackException('invalid cdic header')
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

class mobiUnpack:
	def __init__(self, files):
		self.infile = files.infile
		self.outdir = files.outdir
		self.sect = Sectionizer(self.infile, 'rb')
		if self.sect.ident != 'BOOKMOBI' and sect.ident != 'TEXtREAd':
			raise unpackException('invalid file format')

		self.header = self.sect.loadSection(0)
		self.records, = struct.unpack_from('>H', self.header, 0x8)
		self.length, self.type, self.codepage, self.unique_id, self.version = struct.unpack('>LLLLL', self.header[20:40])
		self.crypto_type, = struct.unpack_from('>H', self.header, 0xC)
		self.rawText = self.__getRawtext()
		
	def processPrintReplica(self):
		# read in number of tables, and so calculate the start of the indicies into the data
		numTables, = struct.unpack_from('>L', self.rawText, 0x04)
		tableIndexOffset = 8 + 4*numTables
		# for each table, read in count of sections, assume first section is a PDF
		# and output other sections as binary files
		paths = []
		for i in xrange(numTables):
			sectionCount, = struct.unpack_from('>L', self.rawText, 0x08 + 4*i)
			for j in xrange(sectionCount):
				sectionOffset, sectionLength, = struct.unpack_from('>LL', self.rawText, tableIndexOffset)
				tableIndexOffset += 8
				if j == 0:
					entryName = os.path.join(self.outdir, os.path.splitext(os.path.split(self.infile)[1])[0]) + ('.%03d.pdf' % (i+1))
					paths.append(entryName)
				else:
					entryName = os.path.join(self.outdir, os.path.splitext(os.path.split(self.infile)[1])[0]) + ('.%03d.%03d.data' % ((i+1),j))
				f = open(entryName, 'wb')
				f.write(self.rawText[sectionOffset:(sectionOffset+sectionLength)])
				f.close()
		self.printReplicaPaths = paths
				
	def __getSizeOfTrailingDataEntry(self, data):
		num = 0
		for v in data[-4:]:
			if ord(v) & 0x80:
				num = 0
			num = (num << 7) | (ord(v) & 0x7f)
		return num	
	
	def Language(self):
		langcode = struct.unpack('!L', self.header[0x5c:0x60])[0]
		langid = langcode & 0xFF
		sublangid = (langcode >> 10) & 0xFF
		return [getLanguage(langid, sublangid)]
		
	def DictInLanguage(self):
		langcode = struct.unpack('!L', self.header[0x60:0x64])[0]
		langid = langcode & 0xFF
		sublangid = (langcode >> 10) & 0xFF
		if langid != 0:
			return [getLanguage(langid, sublangid)]
		return False
	
	def DictOutLanguage(self):
		langcode = struct.unpack('!L', self.header[0x64:0x68])[0]
		langid = langcode & 0xFF
		sublangid = (langcode >> 10) & 0xFF
		if langid != 0:
			return [getLanguage(langid, sublangid)]
		return False
		
	def getMetaData(self):
		codec=self.codec
		extheader=self.header[16 + self.length:]
		
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
			117 : 'Adult',
			118 : 'Price',
			119 : 'Currency',
			200 : 'DictShortName',
			208 : 'Watermark',
			501 : 'CDE Type',
			503 : 'Updated Title',
		}
		id_map_values = { 
			116 : 'StartOffset',
			201 : 'CoverOffset',
			202 : 'ThumbOffset',
			203 : 'Fake Cover',
			204 : 'Creator Software',
			205 : 'Creator Major Version',
			206 : 'Creator Minor Version',
			207 : 'Creator Build Number',
			401 : 'Clipping Limit',
			402 : 'Publisher Limit',
			404 : 'Text to Speech Disabled',
		}
		id_map_hexstrings = { 
			209 : 'Tamper Proof Keys (hex)',
			300 : 'Font Signature (hex)',
		}
	
		metadata = {}
	
		def addValue(name, value):
			if name not in metadata:
				metadata[name] = [value]
			else:
				metadata[name].append(value)
				if DEBUG:
					print "multiple values: metadata[%s]=%s" % (name, metadata[name])
	
		_length, num_items = struct.unpack('>LL', extheader[4:12])
		extheader = extheader[12:]
		pos = 0
		for _ in range(num_items):
			id, size = struct.unpack('>LL', extheader[pos:pos+8])
			content = extheader[pos + 8: pos + size]
			if id in id_map_strings.keys():
				name = id_map_strings[id]
				addValue(name, unicode(content, codec).encode("utf-8"))
			elif id in id_map_values.keys():
				name = id_map_values[id]
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
					print "Error: Value for %s has unexpected size of %s" % (name, size)
			elif id in id_map_hexstrings.keys():
				name = id_map_hexstrings[id]
				addValue(name, content.encode('hex'))
			else:
				print "Warning: Unknown metadata with id %s found" % id
				name = str(id) + ' (hex)'
				addValue(name, content.encode('hex'))
			pos += size
		return metadata

	def __getRawtext(self):
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
	
		compression, = struct.unpack_from('>H', self.header, 0x0)
		if compression == 0x4448:
			print "Huffdic compression"
			reader = HuffcdicReader()
			huffoff, huffnum = struct.unpack_from('>LL', self.header, 0x70)
			reader.loadHuff(self.sect.loadSection(huffoff))
			for i in xrange(1, huffnum):
				reader.loadCdic(self.sect.loadSection(huffoff+i))
			unpack = reader.unpack
		elif compression == 2:
			print "Palmdoc compression"
			unpack = PalmdocReader().unpack
		elif compression == 1:
			print "No compression"
			unpack = UncompressedReader().unpack
		else:
			raise unpackException('invalid compression type: 0x%4x' % compression)
			
		def trimTrailingDataEntries(data):
			for _ in xrange(trailers):
				num = self.__getSizeOfTrailingDataEntry(data)
				data = data[:-num]
			if multibyte:
				num = (ord(data[-1]) & 3) + 1
				data = data[:-num]
			return data
		
		# get raw mobi html-like markup languge
		print "Unpack raw html"
		dataList = []
		for i in xrange(self.records):
			data = trimTrailingDataEntries(self.sect.loadSection(1+i))
			dataList.append(unpack(data))
		return "".join(dataList)
		
	@property
	def isPrintReplica(self):
		return (self.rawText[0:4] == "%MOP")
		
	@property
	def isEncrypted(self):
		if self.crypto_type != 0:
			return True
		return False
		
	@property
	def codec_map(self):
		return {
			1252 : 'windows-1252',
			65001: 'utf-8',
		}
		
	@property
	def firstidx(self):
		if self.sect.ident != 'TEXtREAd':
			idx, = struct.unpack_from('>L', self.header, 0x50)
		else:
			idx = 0xFFFFFFFF
		return idx
	
	@property
	def firstimg(self):
		if self.sect.ident != 'TEXtREAd':
			img, = struct.unpack_from('>L', self.header, 0x6C)
		else:
			img = self.records + 1
		return img
	
	@property
	def codec(self):
		if self.codepage in self.codec_map.keys():
			return self.codec_map[self.codepage]
		else:
			return 'windows-1252'
		
	@property
	def title(self):
		toff, tlen = struct.unpack('>II', self.header[0x54:0x5c])
		tend = toff + tlen
		return self.header[toff:tend]
	
	@property
	def hasExth(self):
		exth_flag, = struct.unpack('>L', self.header[0x80:0x84])
		return exth_flag & 0x40
	
class ncxExtract:
	def __init__(self, header, sect, records, files):
		self.header = header
		self.sect = sect
		self.records = records
		self.isNCX = False
		self.files = files
		
	def parseINDX(self):
		files = self.files
		indx_data = False
		indx_text = False
		indx_num = 1
		idnx_codec = '' #not used..
		
		#  get first INDX section
		indx_first, = struct.unpack('>L', self.header[0xf4:0xf8])
		if indx_first == 0xffffffff:
			print "No ncx"
			return False
	
		# sanity check of indx_first
		if indx_first > (self.sect.num_sections - 2) or indx_first<=self.records:
			print "Warning: incorrect index section number:",\
				self.records, '<', indx_first, '<', self.sect.num_sections
			return False

		# read INDX0
		data = self.sect.loadSection(indx_first)
		if DEBUG_NCX:
			outraw = os.path.join(files.outdir, 'indx0.dat')
			f = open(outraw, 'wb')
			f.write(data)
			f.close()
		indxHeader = self.parseINDXHeader(data)
		if not indxHeader:
			return False
		
		#must be of type 0
		if not indxHeader['type'] == 0:
			print "Warning: INDX0 not type 0"
			return False
	
		#NOTE: the number of "DATA" indx is stored in here...
		indx_num = indxHeader['count']
		
		#TODO: use indxHeader "code" to set encoding...
		indx_codec = indxHeader['code']
		
		#NOTE: used to figure out the INDX structure
		tagx = readTagSection(indxHeader['len'], data)	
		if DEBUG_NCX:
			print "INDX0: ", indx_num, "INDX sections"
			print "TAGX: ", tagx

		# read CTOC
		if DEBUG_NCX:
			print "CTOC"
		data = self.sect.loadSection(indx_first + indx_num + 1)
		if data[:4] == 'INDX':
			print "Warning: CTOC is an INDX"
			return False
		indx_text = self.readCTOC(data)

		# read all INDXx
		indx_data = []
		for n in range(indx_num):
			indx_id = n + 1
			if DEBUG_NCX:
				print "INDX%d" % indx_id
			data = self.sect.loadSection(indx_first + indx_id)
			
			if DEBUG_NCX:
				#dump the whole section, not just the navdata part as before
				outraw = os.path.join(files.outdir,'indx%d.dat' % indx_id)
				f = open(outraw, 'wb')
				f.write(data)
				f.close()
			
			#parse header
			indxHeader = self.parseINDXHeader(data)
			if not indxHeader:
				return False
			#must be of type 1
			if not indxHeader['type'] == 1:
				print "Warning: INDX%d not type 1" % indx_id
				
			#parse IDXT (starts @ 'start')
			#NOTE: IDXT contains the offset to each entry
			idxt = self.parseIDXT(data[indxHeader['start']:])
			if DEBUG_NCX:
				print 'IDXT', idxt
	
			# now process the indx
			#(actually starts @ 'len' but we use the IDXT offset data to navigate)
			#print "INDX1"
			tmp = self.parseINDX1(data, idxt, indx_text, tagx)
			if not tmp:
				print "Warning: error parsing NCX data in INDX%d" % indx_id
				return False
			indx_data = indx_data + tmp
		
		if len(indx_data) < indxHeader['count']:
			print "Warning: missing INDX entries %d/%d" %\
				(len(indx_data), indxHeader['count'])
		self.indx_data = indx_data
		return indx_data
	
	def parseINDXHeader(self, data):
		"read INDX header"
		#must be INDX
		if not data[:4] == 'INDX':
			print "Warning: index section is not INDX"
			return False

		words = (
			'len', 'nul1', 'type', 'gen', 'start', 'count', 'code',
			'lng', 'total', 'ordt', 'ligt', 'nligt', 'nctoc'
		)

		num = len(words)	
		values = struct.unpack('>%dL' % num, data[4:4*(num+1)])

		header = {}
		for n in range(num):
			header[words[n]] = values[n]
	
		if DEBUG_NCX:
			print "parsed INDX header:"
			for n in words:
				print n, "%X" % header[n],
			print
		return header
	
	def readCTOC(self, txtdata):
		files = self.files
		# read all blocks from CTOC
		if DEBUG_NCX:
			outraw = os.path.join(files.outdir,'ctoc.dat')
			f = open(outraw, 'wb')
			f.write(txtdata)
			f.close()
	
		ctoc_data = {}
		offset = 0
		while offset<len(txtdata):
			#stop if first byte is 0
			if txtdata[offset] == '\0':
				break
			idx_offs = offset
			#first n bytes: name len as vwi
			pos, ilen = getVariableWidthValue(txtdata, offset)
			offset += pos
			#<len> next bytes: name
			name = txtdata[offset:offset+ilen]
			offset += ilen
			# print idx_offs, name
			ctoc_data[idx_offs] = name
		return ctoc_data
	
	def parseIDXT(self, data, pos_offset=0):
		if not data[:4] == 'IDXT':
			print "Warning: not IDXT"
			return False
		pos = []
		offset = 4
		while offset<len(data):
			value, = struct.unpack_from('>H', data, offset)
			offset += 2
			#note: some files have a trailing 00 00
			if value:
				pos.append(value)
		return pos
	
	def parseINDX1(self, data, idxt, indx_txt, tagx):
		#read all blocks from INDX1
		tag_fieldname_map = {
			1: 'pos',
			2: 'len',
			3: 'noffs',
			4: 'hlvl',
			5: 'koffs',
			21: 'parent',
			22: 'child1',
			23: 'childn'
		}
	
		indx_data = []
		num = 0
		offset = 0
		max_offset = len(data) - 1
		taglst_cnt, taglst = tagx
		if taglst_cnt > 1:
			print "Error: multiple tagx taglist entries not handled"
		
		for offset in idxt:
			if offset > max_offset:
				print 'Warning: wrong IDXT entries, offset out of range', offset
				break
			if data[offset] == '\0':
				print 'Warning: missing ncx entry @ %X' % offset
				break

			tmp = {
				'name': None,
				'type': 0,
				'pos':  -1,
				'len':  0,
				'noffs': -1,
				'text' : "Unknown Text",
				'hlvl' : -1,
				'kind' : "Unknown Kind",
				'parent' : -1,
				'child1' : -1,
				'childn' : -1,
				'num'  : num
			}
	
			#first byte: name len
			ilen, = struct.unpack('B', data[offset])
			offset += 1
			#<len> next bytes: name
			name = data[offset:offset+ilen]
			offset += ilen
			tmp['name'] = name
			
			#next byte: type:
			type, = struct.unpack('B', data[offset])
			offset += 1
			tmp['type'] = type
		
			# The tagx info and the type byte is used to decipher which fields
			# should be read in
			for (tag, nvars, mask, stop) in taglst:
				if stop:
					break
				if tag in tag_fieldname_map.keys():
					fieldname = tag_fieldname_map[tag]
					if type & mask == mask:
						assert(nvars == 1)
						pos, fieldvalue = getVariableWidthValue(data, offset)
						offset += pos
						tmp[fieldname] = fieldvalue
						if tag == 3:
							tmp['text'] = indx_txt.get(fieldvalue, 'Unknown Text')
						if tag == 5:
							tmp['kind'] = indx_txt.get(fieldvalue, 'Unknown Kind')
				else : 	
					# unknown tag so skip proper number of values if needed and continue
					print 'reading indx1 - unknown tag: ', tag, ' skipping it'
					# NOTE: skipping should not be needed anymore with IDXT...
					if type & mask == mask:
						for i in range(nvars):
							pos, temp = getVariableWidthValue(data, offset)
							offset += pos
	
			indx_data.append(tmp)
			if DEBUG_NCX:
				if True:
					print "record number is ", num
					print "name is ", tmp['name'], "type is %x " % tmp['type']
					print "position is ", tmp['pos']," and length is ", tmp['len']
					print "name offset is ", tmp['noffs']," which is text ", tmp['text']
					print "kind is ", tmp['kind']," and heading level is ", tmp['hlvl']
					print "parent is ", tmp['parent']
					print "first child is ",tmp['child1']," and last child is ", tmp['childn']
					print "\n\n"
				else:
					fld_dbg = ('type', 'hlvl', 'parent', 'child1', 'childn')
					print "\t".join(['%X'%tmp[f] for f in fld_dbg])
			num += 1
		return indx_data
	
	def buildNCX(self, htmlfile, title, ident):
		indx_data = self.indx_data
		
		ncx_header = \
'''<?xml version='1.0' encoding='utf-8'?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="en">
  <head>
    <meta content="%s" name="dtb:uid"/>
    <meta content="%d" name="dtb:depth"/>
    <meta content="mobiunpack.py" name="dtb:generator"/>
    <meta content="0" name="dtb:totalPageCount"/>
    <meta content="0" name="dtb:maxPageNumber"/>
  </head>
  <docTitle>
    <text>%s</text>
  </docTitle>
  <navMap>
'''

		ncx_footer = \
'''  </navMap>
</ncx>
'''

		ncx_entry = \
'''<navPoint id="%s" playOrder="%d">
  <navLabel>
    <text>%s</text>
  </navLabel>
  <content src="%s"/>'''

		#recursive part
		def recursINDX(max_lvl=0, num=0, lvl=0, start=-1, end=-1):
			if start>len(indx_data) or end>len(indx_data):
				print "Warning: missing INDX child entries", start, end, len(indx_data)
				return ''
			if DEBUG_NCX:
				print "recursINDX lvl %d from %d to %d" % (lvl, start, end)
			xml = ''
			if start <= 0:
				start = 0
			if end <= 0:
				end = len(indx_data)
			if lvl > max_lvl:
				 max_lvl = lvl
			indent = '  ' * (2 + lvl)
			
			for i in range(start, end):
				e = indx_data[i]
				if not e['hlvl'] == lvl:
					continue
				#open entry
				num += 1
				link = '%s#filepos%d' % (htmlfile, e['pos'])
				tagid = 'np_%d' % num
				entry = ncx_entry % (tagid, num, e['text'], link)
				entry = re.sub(re.compile('^', re.M), indent, entry, 0)
				xml += entry + '\n'
				#recurs
				if e['child1']>=0:
					xmlrec, max_lvl, num = recursINDX(max_lvl, num, lvl + 1,\
						e['child1'], e['childn'] + 1)
					xml += xmlrec
				#close entry
				xml += indent + '</navPoint>\n'
			return xml, max_lvl, num
	
		body, max_lvl, num = recursINDX()
		header = ncx_header % (ident, max_lvl + 1, title)
		ncx =  header + body + ncx_footer
		if not len(indx_data) == num:
			print "Warning: different number of entries in NCX", len(indx_data), num
		return ncx
	
	def writeNCX(self, files, metadata):
		# build the xml
		self.isNCX = True
		print "Write ncx"
		xml = self.buildNCX(files.outsrcbasename, metadata['Title'][0], metadata['UniqueID'][0])		
		
		#write the ncx file ("outncx" is then used when building the opf)
		f = open(files.outncx, 'wb')
		f.write(xml)
		f.close
	
class dictSupport:
	def __init__(self, header, sect):
		self.header = header
		self.sect = sect
		
	def getPositionMap (self):
		header = self.header
		sect = self.sect
		
		positionMap = {}
		
		metaOrthIndex, = struct.unpack_from('>L', header, 0x28)
		metaInflIndex, = struct.unpack_from('>L', header, 0x2C)
		
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
				if DEBUG:
					print "inflectionTagTable: %s" % inflectionTagTable
				if self.hasTag(inflectionTagTable, 0x07):
					print "Error: Dictionary uses obsolete inflection rule scheme which is not yet supported"
					decodeInflection = False
	
			data = sect.loadSection(metaOrthIndex)
			tagSectionStart, = struct.unpack_from('>L', data, 0x04)
			controlByteCount, tagTable = readTagSection(tagSectionStart, data)
			orthIndexCount, = struct.unpack_from('>L', data, 0x18)
			if DEBUG:
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
					tagMap = self.getTagMap(controlByteCount, tagTable, data, startPos+1+textLength, endPos)
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
			tagMap = self.getTagMap(controlByteCount, tagTable, data, offset + 1, nextOffset)
	
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
				if inflection != None:
					result += '  <idx:iform name="%s" value="%s"/>' % (inflectionName, inflection)
	
			result += "</idx:infl>"
		return result
	
	def getTagMap(self, controlByteCount, tagTable, entryData, startPos, endPos):
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
					if self.countSetBits(mask) > 1:
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
		
	def countSetBits(self, value, bits = 8):
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
	
class processHTML:
	def __init__(self, files, metadata):
		self.files = files
		self.metadata = metadata

	def processImages(self, firstimg, sect):
		outdir = self.files.outdir
		imgdir = self.files.imgdir
		# write out the images to the folder of images
		print "Decode images"
		imgnames = []
		for i in xrange(firstimg, sect.num_sections):
			# We might write sections which doesn't contain an image (usually the last sections), but they won't be
			# referenced as images from the html code, so there is no need to filter them.
			data = sect.loadSection(i)
			type = data[0:4]
			if type in ["FLIS", "FCIS", "FDST", "DATP"]: # FIXME FDST and DATP aren't mentioned in MOBI wiki entry.
				# Ignore FLIS, FCIS, FDST and DATP sections.
				if DEBUG:
					print "Skip section %i as it doesn't contain an image but a %s record." % (i, type)
				imgnames.append(None)
				continue
			elif type == "SRCS":
				# The mobi file was created by kindlegen and contains a zip archive with all source files.
				# Extract the archive and save it.
				print "Info: File contains kindlegen source archive, extracting as %s" % KINDLEGENSRC_FILENAME
				f = open(os.path.join(outdir, KINDLEGENSRC_FILENAME), "wb")
				f.write(data[16:])
				f.close()
				imgnames.append(None)
				continue
			if data == EOF_RECORD:
				if DEBUG:
					print "Skip section %i as it doesn't contain an image but the EOF record." % i
				# The EOF section should be the last section.
				if i + 1 != sect.num_sections:
					print "Warning: EOF section is not the last section"
				imgnames.append(None)
				continue
			# Get the proper file extension 
			imgtype = imghdr.what(None, data)
			if imgtype is None:
				print "Warning: Section %s contains no image or an unknown image format" % i
				imgnames.append(None)
				if DEBUG:
					print 'First 4 bytes: %s' % toHex(data[0:4])
					imgname = "image%05d.raw" % (1+i-firstimg)
					outimg = os.path.join(imgdir, imgname)
					f = open(outimg, 'wb')
					f.write(data)
					f.close()
			else:
				imgname = "image%05d.%s" % (1+i-firstimg, imgtype)
				imgnames.append(imgname)
				outimg = os.path.join(imgdir, imgname)
				f = open(outimg, 'wb')
				f.write(data)
				f.close()
		self.imgnames = imgnames
		return self.imgnames
	
	def findAnchors(self, rawtext, indx_data, positionMap):
		# process the raw text
		# find anchors...
		print "Find link anchors"
		link_pattern = re.compile(r'''<[^<>]+filepos=['"]{0,1}(\d+)[^<>]*>''', re.IGNORECASE)
		# TEST NCX: merge in filepos from indx
		pos_links = [int(m.group(1)) for m in link_pattern.finditer(rawtext)]
		if indx_data:
			pos_indx = [e['pos'] for e in indx_data if e['pos']>0]
			pos_links = list(set(pos_links + pos_indx))

		for position in pos_links:
			if position in positionMap:
				positionMap[position] = positionMap[position] + '<a id="filepos%d" />' % position
			else:
				positionMap[position] = '<a id="filepos%d" />' % position
	
		# apply dictionary metadata and anchors
		print "Insert data into html"
		pos = 0
		lastPos = len(rawtext)
		dataList = []
		for end in sorted(positionMap.keys()):
			if end == 0 or end > lastPos:
				continue # something's up - can't put a tag in outside <html>...</html>
			dataList.append(rawtext[pos:end])
			dataList.append(positionMap[end])
			pos = end
		dataList.append(rawtext[pos:])
		srctext = "".join(dataList)
		rawtext = None
		datalist = None
		self.srctext = srctext
		self.indx_data = indx_data
		return srctext
	
	def insertHREFS(self):
		srctext = self.srctext
		imgnames = self.imgnames
		files = self.files
		metadata = self.metadata
		
		# put in the hrefs
		print "Insert hrefs into html"
		# Two different regex search and replace routines.
		# Best results are with the second so far IMO (DiapDealer).
		
		#link_pattern = re.compile(r'''<a filepos=['"]{0,1}0*(\d+)['"]{0,1} *>''', re.IGNORECASE)
		link_pattern = re.compile(r'''<a\s+filepos=['"]{0,1}0*(\d+)['"]{0,1}(.*?)>''', re.IGNORECASE)
		#srctext = link_pattern.sub(r'''<a href="#filepos\1">''', srctext)
		srctext = link_pattern.sub(r'''<a href="#filepos\1"\2>''', srctext)
	
		# remove empty anchors
		print "Remove empty anchors from html"
		srctext = re.sub(r"<a/>",r"", srctext)
	
		# convert image references
		print "Insert image references into html"
		# split string into image tag pieces and other pieces
		image_pattern = re.compile(r'''(<img.*?>)''', re.IGNORECASE)
		image_index_pattern = re.compile(r'''recindex=['"]{0,1}([0-9]+)['"]{0,1}''', re.IGNORECASE)
		srcpieces = re.split(image_pattern, srctext)
		srctext = self.srctext = None

		# all odd pieces are image tags (nulls string on even pieces if no space between them in srctext)
		for i in range(1, len(srcpieces), 2):
			tag = srcpieces[i]
			for m in re.finditer(image_index_pattern, tag):
				imageNumber = int(m.group(1))
				imageName = imgnames[imageNumber-1]
				if imageName is None:
					print "Error: Referenced image %s was not recognized as a valid image" % imageNumber
				else:
					replacement = 'src="images/' + imageName + '"'
					tag = re.sub(image_index_pattern, replacement, tag, 1)
			srcpieces[i] = tag
		srctext = "".join(srcpieces)
		
		# add in character set meta into the html header if needed
		if 'Codec' in metadata:
			srctext = srctext[0:12]+'<meta http-equiv="content-type" content="text/html; charset='+metadata.get('Codec')[0]+'" />'+srctext[12:]
		# write out source text
		print "Write html"
		f = open(files.outsrc, 'wb')
		f.write(srctext)
		f.close
		return srctext

	def processOPF(self, printReplica, isNCX, codec, srctext = False):
		files = self.files
		metadata = self.metadata
		imgnames = self.imgnames
		
		# write out the metadata as an OEB 1.0 OPF file
		print "Write opf"
		f = file(files.outopf, 'wb')
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
			if key in metadata:
				for value in metadata[key]:
					# Strip all tag attributes for the closing tag.
					closingTag = tag.split(" ")[0]
					data.append('<%s>%s</%s>\n' % (tag, value, closingTag))
				del metadata[key]
				
		data = []
		data.append('<?xml version="1.0" encoding="utf-8"?>\n')
		data.append('<package unique-identifier="uid">\n')
		data.append('<metadata>\n')
		data.append('<dc-metadata xmlns:dc="http://purl.org/metadata/dublin_core"')
		data.append(' xmlns:oebpackage="http://openebook.org/namespaces/oeb-package/1.0/">\n')
		# Handle standard metadata
		if 'Title' in metadata:
			handleTag(data, metadata, 'Title', 'dc:Title')
		else:
			data.append('<dc:Title>Untitled</dc:Title>\n')
		handleTag(data, metadata, 'Language', 'dc:Language')
		if 'UniqueID' in metadata:
			handleTag(data, metadata, 'UniqueID', 'dc:Identifier id="uid"')
		else:
			data.append('<dc:Identifier id="uid">0</dc:Identifier>\n')
		handleTag(data, metadata, 'Creator', 'dc:Creator')
		handleTag(data, metadata, 'Contributor', 'dc:Contributor')
		handleTag(data, metadata, 'Publisher', 'dc:Publisher')
		handleTag(data, metadata, 'Source', 'dc:Source')
		handleTag(data, metadata, 'Type', 'dc:Type')
		handleTag(data, metadata, 'ISBN', 'dc:Identifier scheme="ISBN"')
		if 'Subject' in metadata:
			if 'SubjectCode' in metadata:
				codeList = metadata['SubjectCode']
				del metadata['SubjectCode']
			else:
				codeList = None
			for i in range(len(metadata['Subject'])):
				if codeList and i < len(codeList):
					data.append('<dc:Subject BASICCode="'+codeList[i]+'">')
				else:
					data.append('<dc:Subject>')
				data.append(metadata['Subject'][i]+'</dc:Subject>\n')
			del metadata['Subject']
		handleTag(data, metadata, 'Description', 'dc:Description')
		handleTag(data, metadata, 'Published', 'dc:Date')
		handleTag(data, metadata, 'Rights', 'dc:Rights')
		data.append('</dc-metadata>\n<x-metadata>\n')
		handleTag(data, metadata, 'DictInLanguage', 'DictionaryInLanguage')
		handleTag(data, metadata, 'DictOutLanguage', 'DictionaryOutLanguage')
		if 'Codec' in metadata:
			for value in metadata['Codec']:
				data.append('<output encoding="'+value+'" />\n')
			del metadata['Codec']
		if 'CoverOffset' in metadata:
			imageNumber = int(metadata['CoverOffset'][0])
			imageName = imgnames[imageNumber]
			if imageName is None:
				print "Error: Cover image %s was not recognized as a valid image" % imageNumber
			else:
				data.append('<EmbeddedCover>images/'+imageName+'</EmbeddedCover>\n')
			del metadata['CoverOffset']
		handleTag(data, metadata, 'Review', 'Review')
		handleTag(data, metadata, 'Imprint', 'Imprint')
		handleTag(data, metadata, 'Adult', 'Adult')
		handleTag(data, metadata, 'DictShortName', 'DictionaryVeryShortName')
		if 'Price' in metadata and 'Currency' in metadata:
			priceList = metadata['Price']
			currencyList = metadata['Currency']
			if len(priceList) != len(currencyList):
				print "Error: found %s price entries, but %s currency entries."
			else:
				for i in range(len(priceList)):
					data.append('<SRP Currency="'+currencyList[i]+'">'+priceList[i]+'</SRP>\n')
			del metadata['Price']
			del metadata['Currency']
		data += '</x-metadata>\n'
		data.append("<!-- The following meta tags are just for information and will be ignored by mobigen/kindlegen. -->\n")
		if 'ThumbOffset' in metadata:
			imageNumber = int(metadata['ThumbOffset'][0])
			imageName = imgnames[imageNumber]
			if imageName is None:
				print "Error: Cover Thumbnail image %s was not recognized as a valid image" % imageNumber
			else:
				data.append('<meta name="Cover ThumbNail Image" content="'+'images/'+imageName+'" />\n')
			del metadata['ThumbOffset']
			for metaName in META_TAGS:
				if metaName in metadata:
					for value in metadata[metaName]:
						data.append('<meta name="'+metaName+'" content="'+value+'" />\n')
					del metadata[metaName]
		for key in metadata.keys():
			if key != 'StartOffset':
				for value in metadata[key]:
					data.append('<meta name="'+key+'" content="'+value+'" />\n')
				del metadata[key]
		data.append('</metadata>\n<manifest>\n')
		data.append('<item id="item1" media-type="text/x-oeb1-document" href="'+files.outhtmlbasename+'" />\n')
		if isNCX:
			outncxbasename = os.path.basename(files.outncx)
			data += '<item id="ncx" media-type="application/x-dtbncx+xml" href="'+outncxbasename+'"></item>\n'
			data.append('</manifest>\n<spine toc="ncx">\n<itemref idref="item1"/>\n</spine>\n<tours>\n</tours>\n')
		else:
			data.append('</manifest>\n<spine>\n<itemref idref="item1"/>\n</spine>\n<tours>\n</tours>\n')
		
		# get guide items from metadata
		metaguidetext = ''
		if 'StartOffset' in metadata:
			metaguidetext += '<reference type="text" href="'+files.outhtmlbasename+'#filepos'+metadata.get('StartOffset')[0]+'" />\n'
			del metadata['StartOffset']
	
		guidetext =''
		if not printReplica:
			# get guide items from text
			guidematch = re.search(r'''<guide>(.*)</guide>''',srctext,re.IGNORECASE+re.DOTALL)
			if guidematch:
				replacetext = r'''href="'''+files.outhtmlbasename+r'''#filepos\1"'''
				guidetext = re.sub(r'''filepos=['"]{0,1}0*(\d+)['"]{0,1}''', replacetext, guidematch.group(1))
				guidetext += '\n'
				guidetext = unicode(guidetext, codec).encode("utf-8")
		data.append('<guide>\n' + metaguidetext + guidetext + '</guide>\n')
		data.append('</package>')
		
		f.write("".join(data))
		f.close()
	
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
		29 : {0 : 'sv' , 1 : 'sv' , 8 : 'sv-fi'}, # Swedish,  Swedish (Finland)
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



def unpackBook(infile, outdir):
	files = fileNames(infile, outdir)
	
	# Instantiate the mobiUnpack class	
	mu = mobiUnpack(files)
	if mu.isEncrypted:
			raise unpackException('file is encrypted')
	header = mu.header
	sect = mu.sect
	records = mu.records
	
	if WRITE_RAW_DATA:
		#write out raw header
		f = open(files.getOutRaw('.rawhdr'), 'wb')
		f.write(header)
		f.close()
	
	# if exth region exists then parse it for the metadata
	metadata = {}
	if mu.hasExth:
		metadata = mu.getMetaData()
	metadata['Language'] = mu.Language()
	if mu.DictInLanguage():
		metadata['DictInLanguage'] = mu.DictInLanguage()
	if mu.DictOutLanguage():
		metadata['DictOutLanguage'] = mu.DictOutLanguage()
	metadata['Title'] = [unicode(mu.title, mu.codec).encode("utf-8")]
	metadata['Codec'] = [mu.codec]
	metadata['UniqueID'] = [str(mu.unique_id)]
	
	# Extract raw text
	rawtext = mu.rawText
	
	# Instantiate printReplica class
	printReplica = mu.isPrintReplica
	if printReplica:
		print "Print Replica ebook detected"

	# Instantiate nxcExtract class and parse the INDX.
	ncx = ncxExtract(header, sect, records, files)
	indx_data = ncx.parseINDX()
	
	# Build the ncx file if ncx data exists.
	if indx_data:
		ncx.writeNCX(files, metadata)

	# write out raw text
	if WRITE_RAW_DATA:
		if printReplica:
			outraw = files.getOutRaw('.rawpr')
		else:
			outraw = files.getOutRaw('.rawml')
		f = open(outraw, 'wb')
		f.write(rawtext)
		f.close()

	#write out raw index sections
	if WRITE_RAW_DATA:
		if mu.firstidx != 0xffffffff:
			for i in xrange(mu.firstidx, mu.firstimg):
				data = sect.loadSection(i)
				outraw = files.getOutRaw( ('.%03x.rawidx' % i))
				f = open(outraw, 'wb')
				f.write(data)
				f.close()
	
	# Get the position map from the dictSupport class.
	positionMap = dictSupport(header, sect).getPositionMap()

	# Process images.
	proc = processHTML(files, metadata)
	imgnames = proc.processImages(mu.firstimg, sect)
	
	# Process print replica book.
	if printReplica:
		try:
			mu.processPrintReplica()
		except Exception, e:
			print 'Error processing Print Replica: ' + str(e)
			
	else:
		# Find anchors and insert hrefs in links.
		srctext = proc.findAnchors(rawtext, indx_data, positionMap)
		srctext = proc.insertHREFS()

	# Create the opf file.
	if printReplica:
		proc.processOPF(printReplica, ncx.isNCX, mu.codec)
	else:
		proc.processOPF(printReplica, ncx.isNCX, mu.codec, srctext)

def main(argv=sys.argv):
	print "MobiUnpack 0.32"
	print "  Copyright (c) 2009 Charles M. Hannum <root@ihack.net>"
	print "  With Additions by P. Durrant, K. Hendricks, S. Siebert, fandrieu and DiapDealer."
	if len(argv) < 2:
		print ""
		print "Description:"
		print "  Unpacks an unencrypted Kindle/MobiPocket ebook to html and images"
		print "  or an unencrypted Kindle/Print Replica ebook to PDF and images"
		print "  in a folder of the same name as the original ebook."
		print "Usage:"
		print "  mobiunpack.py infile [outdir]"
		return 1
	else:  
		if len(argv) >= 3:
			infile, outdir = argv[1:]
		else:
			infile = argv[1]
			outdir = os.path.splitext(infile)[0]
		infileext = os.path.splitext(infile)[1].upper()
		if infileext not in ['.MOBI', '.PRC', '.AZW', '.AZW4']:
			print "Error: first parameter must be a Kindle/Mobipocket ebook or a Kindle/Print Replica ebook."
			return 1
	
		try:
			print 'Unpacking Book...'
			unpackBook(infile, outdir)
			print 'Completed'
			
		except ValueError, e:
			print "Error: %s" % e
			return 1
		return 0

if __name__ == "__main__":
	sys.exit(main())

# For execution runtime tests start mobiunpack as follows:
# python -m timeit -r 3 -n 1 -v "import mobiunpack; mobiunpack.main([None, '<filename.mobi>'])"
