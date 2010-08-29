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

import struct, os, imghdr, re

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
						for z in xrange(n):
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
		1 : {0 : 'ar' , 20 : 'ar-dz' , 60 : 'ar-bh' , 12 : 'ar-eg' , 44 : 'ar-jo' , 52 : 'ar-kw' , 48 : 'ar-lb' , 24 : 'ar-ma' , 32 : 'ar-om' , 64 : 'ar-qa' , 4 : 'ar-sa' , 40 : 'ar-sy' , 28 : 'ar-tn' , 56 : 'ar-ae' , 36 : 'ar-ye'}, # Arabic,  Arabic (Algeria),  Arabic (Bahrain),  Arabic (Egypt),  Arabic (Jordan),  Arabic (Kuwait),  Arabic (Lebanon),  Arabic (Morocco),  Arabic (Oman),  Arabic (Qatar),  Arabic (Saudi Arabia),  Arabic (Syria),  Arabic (Tunisia),  Arabic (United Arab Emirates),  Arabic (Yemen)
		43 : {0 : 'hy'}, # Armenian
		77 : {0 : 'as'}, # Assamese
		44 : {0 : 'az'}, # "Azeri (IANA: Azerbaijani)
		45 : {0 : 'eu'}, # Basque
		35 : {0 : 'be'}, # Belarusian
		69 : {0 : 'bn'}, # Bengali
		2 : {0 : 'bg'}, # Bulgarian
		3 : {0 : 'ca'}, # Catalan
		4 : {0 : 'zh' , 12 : 'zh-hk' , 8 : 'zh-cn' , 16 : 'zh-sg' , 4 : 'zh-tw'}, # Chinese,  Chinese (Hong Kong),  Chinese (PRC),  Chinese (Singapore),  Chinese (Taiwan)
		26 : {0 : 'hr'}, # Croatian
		5 : {0 : 'cs'}, # Czech
		6 : {0 : 'da'}, # Danish
		19 : {0 : 'nl' , 8 : 'nl-be'}, # Dutch / Flemish,  Dutch (Belgium)
		9 : {0 : 'en' , 12 : 'en-au' , 40 : 'en-bz' , 16 : 'en-ca' , 24 : 'en-ie' , 32 : 'en-jm' , 20 : 'en-nz' , 52 : 'en-ph' , 28 : 'en-za' , 44 : 'en-tt' , 8 : 'en-gb', 2 : 'en-gb' , 4 : 'en-us' , 48 : 'en-zw'}, # English,  English (Australia),  English (Belize),  English (Canada),  English (Ireland),  English (Jamaica),  English (New Zealand),  English (Philippines),  English (South Africa),  English (Trinidad),  English (United Kingdom),  English (United States),  English (Zimbabwe)
		37 : {0 : 'et'}, # Estonian
		56 : {0 : 'fo'}, # Faroese
		41 : {0 : 'fa'}, # Farsi / Persian
		11 : {0 : 'fi'}, # Finnish
		12 : {0 : 'fr' , 4 : 'fr' , 8 : 'fr-be' , 12 : 'fr-ca' , 20 : 'fr-lu' , 24 : 'fr-mc' , 16 : 'fr-ch'}, # French,  French (Mobipocket bug?),  French (Belgium),  French (Canada),  French (Luxembourg),  French (Monaco),  French (Switzerland)
		55 : {0 : 'ka'}, # Georgian
		7 : {0 : 'de' , 12 : 'de-at' , 20 : 'de-li' , 16 : 'de-lu' , 8 : 'de-ch'}, # German,  German (Austria),  German (Liechtenstein),  German (Luxembourg),  German (Switzerland)
		8 : {0 : 'el'}, # Greek, Modern (1453-)
		71 : {0 : 'gu'}, # Gujarati
		13 : {0 : 'he'}, # Hebrew (also code 'iw'?)
		57 : {0 : 'hi'}, # Hindi
		14 : {0 : 'hu'}, # Hungarian
		15 : {0 : 'is'}, # Icelandic
		33 : {0 : 'id'}, # Indonesian
		16 : {0 : 'it' , 4 : 'it' , 8 : 'it-ch'}, # Italian,  Italian (Mobipocket bug?),  Italian (Switzerland)
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
		22 : {0 : 'pt' , 8 : 'pt' , 4 : 'pt-br'}, # Portuguese,  Portuguese (Mobipocket bug?),  Portuguese (Brazil)
		70 : {0 : 'pa'}, # Punjabi
		23 : {0 : 'rm'}, # "Rhaeto-Romanic" (IANA: Romansh)
		24 : {0 : 'ro'}, # Romanian
		25 : {0 : 'ru'}, # Russian
		59 : {0 : 'sz'}, # "Sami (Lappish)" (not an IANA language code)
								  # IANA code for "Northern Sami" is 'se'
								  # 'SZ' is the IANA region code for Swaziland
		79 : {0 : 'sa'}, # Sanskrit
		26 : {12 : 'sr'}, # Serbian -- Mobipocket Cyrillic/Latin distinction broken
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
		67 : {0 : 'uz' , 8 : 'uz'}, # Uzbek,  Uzbek (Mobipocket bug?)
		42 : {0 : 'vi'}, # Vietnamese
		52 : {0 : 'xh'}, # Xhosa
		53 : {0 : 'zu'}, # Zulu
	}

	return mobilangdict.get(int(langID), {0 : 'en'}).get(int(sublangID), 'en')

def getMetaData(extheader):
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
	length, num_items = struct.unpack('>LL', extheader[4:12])
	extheader = extheader[12:]
	pos = 0
	left = num_items
	while left > 0:
		left -= 1
		id, size = struct.unpack('>LL', extheader[pos:pos+8])
		content = extheader[pos + 8: pos + size]
		if id in id_map_strings.keys():
			name = id_map_strings[id]
			metadata[name] = content
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


def unpackBook(infile, outdir):
	codec_map = {
		1252 : 'Windows-1252',
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

	firstimg, = struct.unpack_from('>L', header, 0x6C)

	crypto_type, = struct.unpack_from('>H', header, 0xC)
	if crypto_type != 0:
		raise ValueError('file is encrypted')

	# get length of this header
	length, type, codepage, unique_id, version = struct.unpack('>LLLLL', header[20:40])

	# convert the codepage to codec string
	codec = 'cp-1252'
	if codepage in codec_map.keys() :
		codec = codec_map[codepage]

	# get book title
	toff, tlen = struct.unpack('>II', header[0x54:0x5c])
	tend = toff + tlen
	title = header[toff:tend]

	# get the language code
	langcode = struct.unpack('!L', header[0x5c:0x60])[0]
	langid = langcode & 0xFF
	sublangid = (langcode >> 10) & 0xFF

	# if exth region exists then parse it for the metadata
	exth_flag, = struct.unpack('>L', header[0x80:0x84])
	metadata = {}
	if exth_flag & 0x40:
		metadata = getMetaData(header[16 + length:])

	# add in what we have collected here
	metadata['Title'] = title
	metadata['Codec'] = codec
	metadata['Language']  = getLanguage(metadata.get('LangID',0),metadata.get('SubLangID',0))
	metadata['UniqueID'] = str(unique_id)

	records, = struct.unpack_from('>H', header, 0x8)

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
		reader = HuffcdicReader()
		huffoff, huffnum = struct.unpack_from('>LL', header, 0x70)
		reader.loadHuff(sect.loadSection(huffoff))
		for i in xrange(1, huffnum):
			reader.loadCdic(sect.loadSection(huffoff+i))
		unpack = reader.unpack
	elif compression == 2:
		unpack = PalmdocReader().unpack
	elif compression == 1:
		unpack = UncompressedReader().unpack
	else:
		raise ValueError('invalid compression type: 0x%4x' % compression)

	def getSizeOfTrailingDataEntry(data):
		num = 0
		for v in data[-4:]:
			if ord(v) & 0x80:
				num = 0
			num = (num << 7) | (ord(v) & 0x7f)
		return num

	def trimTrailingDataEntries(data):
		for x in xrange(trailers):
			num = getSizeOfTrailingDataEntry(data)
			data = data[:-num]
		if multibyte:
			num = (ord(data[-1]) & 3) + 1
			data = data[:-num]
		return data

	# get raw mobi html-like markup languge
	rawtext = ''
	for i in xrange(records):
		data = sect.loadSection(1+i)
		data = trimTrailingDataEntries(data)
		data = unpack(data)
		rawtext += data
		
	#write out raw text
	#outraw = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.rawml'
	#f = open(outraw, 'wb')
	#f.write(rawtext)
	#f.close
	
	# write out the images to the folder of images, and make a note of the names
	# we really only need the names to get the image type right.
	imgnames = []
	for i in xrange(firstimg, sect.num_sections):
		data = sect.loadSection(i)
		imgtype = imghdr.what("dummy",data)
		if imgtype is None:
			imgnames.append("Not_an_Image")
		else:
			imgname = ("Image-%05d." % (1+i-firstimg))+imgtype
			imgnames.append(imgname)
			outimg = os.path.join(imgdir,imgnames[i-firstimg])
			f = open(outimg, 'wb')
			f.write(data)
			f.close()

	# process the raw text
	# Adding anchors...
	positions = set([])
	link_pattern = re.compile(r'''<[^<>]+filepos=['"]{0,1}(\d+)[^<>]*>''',
		re.IGNORECASE)
	for match in link_pattern.finditer(rawtext):
		positions.add(int(match.group(1)))
	pos = 0
	srctext = ''
	anchor = '<a id="filepos%d" />'
	for end in sorted(positions):
		if end == 0:
			continue # something's up - can't put a link in before <html>
		srctext += rawtext[pos:end] + (anchor % end)
		pos = end
	srctext += rawtext[pos:]

	# and now put in the hrefs
	link_pattern = re.compile(r'''<a filepos=['"]{0,1}0*(\d+)['"]{0,1} *>''',
		re.IGNORECASE)
	srctext = link_pattern.sub(r'''<a href="#filepos\1">''', srctext)

	# remove empty anchors
	srctext = re.sub(r"<a/>",r"", srctext)

	#write out rare text
	#outrare = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.rareml'
	#f = open(outrare, 'wb')
	#f.write(srctext)
	#f.close

	# convert image references
	for i in xrange(sect.num_sections-firstimg):
		if imgnames[i] is not "Not_an_Image":
			searchtext = '''<img([^>]*)recindex=['"]{0,1}%05d['"]{0,1}''' % (i+1)
			replacetext = r'''<img\1src="'''+ '''images/''' + imgnames[i] +'''"'''
			srctext = re.sub(searchtext, replacetext, srctext)

	#write out source text
	f = open(outsrc, 'wb')
	f.write(srctext)
	f.close

	# write out the metadata as an OEB 1.0 OPF file
	outhtmlbasename = os.path.basename(outsrc)
	f = file(outopf, 'wb')
	data = '<?xml version="1.0" encoding="utf-8"?>\n'
	data += '<package unique-identifier="uid">\n'
	data += '<metadata>\n'
	data += '<dc-metadata xmlns:dc="http://purl.org/metadata/dublin_core"'
	data += ' xmlns:oebpackage="http://openebook.org/namespaces/oeb-package/1.0/">\n'
	# Handle standard metadata
	data += '<dc:Title>' + metadata.get('Title','Untitled') + '</dc:Title>\n'
	data += '<dc:Language>' + getLanguage(metadata.get('LangID',0),metadata.get('SubLangID',0)) + '</dc:Language>\n'
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
	if 'Codec' in metadata:
		data += '<output encoding="'+metadata.get('Codec')+'">\n</output>\n'
	if 'CoverOffset' in metadata:
		data += '<EmbeddedCover>images/'+imgnames[int(metadata.get('CoverOffset'))]+'</EmbeddedCover>\n'
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
	print "MobiUnpack 0.22"
	print "  Copyright (c) 2009 Charles M. Hannum <root@ihack.net>"
	print "  With Images Support and Other Additions by P. Durrant and K. Hendricks"
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
			print 'Unpacking Book ... '
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
