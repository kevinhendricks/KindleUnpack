#!/usr/bin/python

# Changelog
#  0.11 - Version by adamselene
#  0.11pd - Tweaked version by pdurrant
#  0.12 - extracts pictures too, and all into a folder.
#  0.13 - added bak in optional output dir for those who don't want ti based on infile
#  0.14 - auto flush stdout and wrapped in main, added proper return codes

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

import struct, os, imghdr

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

def unpackBook(infile, outdir):
	outhtml = os.path.join(outdir, os.path.splitext(os.path.split(infile)[1])[0]) + '.html'
	
	sect = Sectionizer(infile, 'rb')
	if sect.ident != 'BOOKMOBI' and sect.ident != 'TEXtREAd':
		raise ValueError('invalid file format')

	header = sect.loadSection(0)
	firstimg, = struct.unpack_from('>L', header, 0x6C)

	crypto_type, = struct.unpack_from('>H', header, 0xC)
	if crypto_type != 0:
		raise ValueError('file is encrypted')

	records, = struct.unpack_from('>H', header, 0x8)

	multibyte = 0
	trailers = 0
	if sect.ident == 'BOOKMOBI':
		mobi_length, = struct.unpack_from('>L', header, 0x14)
		mobi_version, = struct.unpack_from('>L', header, 0x68)
		if (mobi_length >= 0xE8) and (mobi_version > 5):
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

	f = file(outhtml, 'wb')
	for i in xrange(records):
		data = sect.loadSection(1+i)
		data = trimTrailingDataEntries(data)
		data = unpack(data)
		f.write(data)
	f.close()
	
	for i in xrange(firstimg, sect.num_sections):
		data = sect.loadSection(i)
		imgtype = imghdr.what("dummy",data)
		if imgtype in ['gif','jpeg','bmp']:
			outimg = os.path.join(os.path.join(outdir,'images'),("Image-%05d" % (1+i-firstimg)) + '.' + imgtype)
			f = file(outimg, 'wb')
			f.write(data)
			f.close()
			

def main(argv=sys.argv):
	print "MobiUnpack 0.14"
	print "  Copyright (c) 2009 Charles M. Hannum <root@ihack.net>"
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
			if not os.path.exists(outdir):
				os.mkdir(outdir)

			infileext = os.path.splitext(infile)[1].upper()
			if infileext not in ['.MOBI', '.PRC', '.AZW']:
				print "Error: first parameter must be a mobipocket file."
				return 1	
		try:
			unpackBook(infile, outdir)
		except ValueError, e:
			print "Error: %s" % e
			return 1
		return 0

if __name__ == "__main__":
	sys.exit(main())
