#!/usr/bin/env python

import sys
import struct
import binascii

# important  pdb header offsets
unique_id_seed = 68
number_of_pdb_records = 76

# important palmdoc header offsets
book_length = 4
book_record_count = 8
first_pdb_record = 78

# important rec0 offsets
length_of_book = 4
mobi_header_base = 16
mobi_header_length = 20
mobi_type = 24
mobi_version = 36
first_non_text = 80
title_offset = 84
first_image_record = 108
first_content_index = 192
last_content_index = 194
kf8_last_content_index = 192 # for KF8 mobi headers
fcis_index = 200
flis_index = 208
srcs_index = 224
srcs_count = 228
primary_index = 244
datp_index = 256

def getint(datain,ofs,sz='L'):
        i, = struct.unpack_from('>'+sz,datain,ofs)
        return i

def writeint(datain,ofs,n,len='L'):
        if len=='L':
                return datain[:ofs]+struct.pack('>L',n)+datain[ofs+4:]
        else:
                return datain[:ofs]+struct.pack('>H',n)+datain[ofs+2:]

def getsecaddr(datain,secno):
        nsec = getint(datain,number_of_pdb_records,'H')
        assert secno>=0 & secno<nsec,'secno %d out of range (nsec=%d)'%(secno,nsec)
        secstart = getint(datain,first_pdb_record+secno*8)
        if secno == nsec-1:
                secend = len(datain)
        else:
                secend = getint(datain,first_pdb_record+(secno+1)*8)
        return secstart,secend

def readsection(datain,secno):
        secstart, secend = getsecaddr(datain,secno)
        return datain[secstart:secend]

def writesection(datain,secno,secdata): # overwrite, accounting for different length
        secstart, secend = getsecaddr(datain,secno)
        dataout = datain[:secstart]+secdata+datain[secend:]
        dif = len(secdata) - (secend-secstart)
        if dif == 0:
                return dataout
        nsec = getint(datain,number_of_pdb_records,'H')
        if secno == nsec-1:
                return dataout
        for i in range(secno+1,nsec):
                ofs, = struct.unpack_from('>L',dataout,first_pdb_record+i*8)
                ofs = ofs+dif
                dataout = dataout[:first_pdb_record+i*8]+struct.pack('>L',ofs)+dataout[first_pdb_record+i*8+4:]
        return dataout

def nullsection(datain,secno): # make it zero-length without deleting it
        secstart, secend = getsecaddr(datain,secno)
        dataout = datain[:secstart]+datain[secend:]
        dif =  secend-secstart
        if dif == 0:
                return dataout
        nsec = getint(datain,number_of_pdb_records,'H')
        if secno == nsec-1:
                return dataout
        for i in range(secno+1,nsec):
                ofs, = struct.unpack_from('>L',dataout,first_pdb_record+i*8)
                ofs = ofs-dif
                dataout = dataout[:first_pdb_record+i*8]+struct.pack('>L',ofs)+dataout[first_pdb_record+i*8+4:]
        return dataout

def deletesectionrange(datain,firstsec,lastsec): # delete a range of sections
        firstsecstart,firstsecend = getsecaddr(datain,firstsec)
        lastsecstart,lastsecend = getsecaddr(datain,lastsec)
        dif = lastsecend - firstsecstart + 8*(lastsec-firstsec+1)
        dataout = datain[:firstsecstart]+datain[lastsecend:]
        nsec = getint(datain,number_of_pdb_records,'H')
        dataout = writeint(dataout,number_of_pdb_records,nsec-(lastsec-firstsec+1),'H')
        for i in range(0,firstsec):
                ofs, = struct.unpack_from('>L',dataout,first_pdb_record+i*8)
                ofs = ofs-8*(lastsec-firstsec+1)
                dataout = dataout[:first_pdb_record+i*8]+struct.pack('>L',ofs)+dataout[first_pdb_record+i*8+4:] 
        for i in range(lastsec+1,nsec):
                ofs, = struct.unpack_from('>L',dataout,first_pdb_record+i*8)
                ofs = ofs - dif
                it = 2*(i-(lastsec-firstsec+1))
                dataout = dataout[:first_pdb_record+i*8]+\
                          struct.pack('>L',ofs)+struct.pack('>L',it)+\
                          dataout[first_pdb_record+i*8+8:]
        dataout = dataout[:first_pdb_record+firstsec*8]+dataout[first_pdb_record+(lastsec+1)*8:]
        dataout = writeint(dataout,number_of_pdb_records,nsec-(lastsec-firstsec+1),'H')
        dataout = writeint(dataout,unique_id_seed,2*(nsec-(lastsec-firstsec+1))+1)
        return dataout

def insertsection(datain,secno,secdata): # insert a new section
        nsec = getint(datain,number_of_pdb_records,'H')
        if secno == nsec:
                newsecstart = len(datain)
        else:
                insert_secstart, insert_secend = getsecaddr(datain,secno)
                newsecstart = insert_secstart
        dataout = datain[:unique_id_seed]+struct.pack('>L',2*(nsec+1)+1)+datain[unique_id_seed+4:first_pdb_record-2]+struct.pack('>H',nsec+1)
        
        for i in range(0,secno):
                ofs = getint(datain,first_pdb_record+i*8)+8
                dataout += struct.pack('>L',ofs)+struct.pack('>L',2*i)
        dataout += struct.pack('>L',newsecstart+8)+struct.pack('>L',2*secno)
        for i in range(secno,nsec):
                ofs = getint(datain,first_pdb_record+i*8)+len(secdata)+8
                dataout += struct.pack('>L',ofs)+struct.pack('>L',2*i)
        r0start,r0end=getsecaddr(dataout,0)
        dataout += '\0' * (r0start-(first_pdb_record+8*(nsec+1)))
        dataout += datain[r0start-8:newsecstart]+secdata+datain[newsecstart:]
        dataout = writeint(dataout,number_of_pdb_records,nsec+1,'H')
        dataout = writeint(dataout,unique_id_seed,2*(nsec+1)+1)       
        return dataout

def insertsectionrange(sectionsource,firstsec,lastsec,sectiontarget,targetsec): # insert a range of sections
        dataout = sectiontarget
        for idx in range(lastsec,firstsec-1,-1):
                dataout = insertsection(dataout,targetsec,readsection(sectionsource,idx))
        return dataout
        
def get_exth_params(rec0):
        ebase = mobi_header_base + getint(rec0,mobi_header_length)
        elen = getint(rec0,ebase+4)
        enum = getint(rec0,ebase+8)
        return ebase,elen,enum

def add_exth(rec0,exth_num,exth_bytes):
        ebase,elen,enum = get_exth_params(rec0)
        newrecsize = 8+len(exth_bytes)
        newrec0 = rec0[0:ebase+4]+struct.pack('>L',elen+newrecsize)+struct.pack('>L',enum+1)+\
                  struct.pack('>L',exth_num)+struct.pack('>L',newrecsize)+exth_bytes+rec0[ebase+12:]
        newrec0 = writeint(newrec0,title_offset,getint(newrec0,title_offset)+newrecsize)
        return newrec0
        
def read_exth(rec0,exth_num):
        ebase,elen,enum = get_exth_params(rec0)
        ebase = ebase+12
        while enum>0:
                exth_id = getint(rec0,ebase)
                if exth_id == exth_num:
                        return rec0[ebase+8:ebase+getint(rec0,ebase+4)]
                enum = enum-1
                ebase = ebase+getint(rec0,ebase+4)
        return ''

def write_exth(rec0,exth_num,exth_bytes):
        ebase,elen,enum = get_exth_params(rec0)
        ebase_idx = ebase+12
        enum_idx = enum
        while enum_idx>0:
                exth_id = getint(rec0,ebase_idx)
                if exth_id == exth_num:
                        dif = len(exth_bytes)+8-getint(rec0,ebase_idx+4)
                        newrec0 = rec0
                        if dif != 0:
                                newrec0 = writeint(newrec0,title_offset,getint(newrec0,title_offset)+dif)
                        return newrec0[:ebase+4]+struct.pack('>L',elen+len(exth_bytes)+8-getint(rec0,ebase_idx+4))+\
                                                          struct.pack('>L',enum)+rec0[ebase+12:ebase_idx+4]+\
                                                          struct.pack('>L',len(exth_bytes)+8)+exth_bytes+\
                                                          rec0[ebase_idx+getint(rec0,ebase_idx+4):]
                enum_idx = enum_idx-1
                ebase_idx = ebase_idx+getint(rec0,ebase_idx+4)
        return rec0

def del_exth(rec0,exth_num):
        ebase,elen,enum = get_exth_params(rec0)
        ebase_idx = ebase+12
        enum_idx = enum
        while enum_idx>0:
                exth_id = getint(rec0,ebase_idx)
                if exth_id == exth_num:
                        dif = getint(rec0,ebase_idx+4)
                        newrec0 = rec0
                        newrec0 = writeint(newrec0,title_offset,getint(newrec0,title_offset)-dif)
                        newrec0 = newrec0[:ebase_idx]+newrec0[ebase_idx+dif:]
                        newrec0 = newrec0[0:ebase+4]+struct.pack('>L',elen-dif)+struct.pack('>L',enum-1)+newrec0[ebase+12:]             
                        return newrec0
                enum_idx = enum_idx-1
                ebase_idx = ebase_idx+getint(rec0,ebase_idx+4)
        return rec0
        
                
class mobi_split:

        def __init__(self, infile):
                datain = file(infile, 'rb').read()
                datain_rec0 = readsection(datain,0)
                ver = getint(datain_rec0,mobi_version)
                self.combo = (ver!=8)
                if not self.combo:
                        return
                exth121 = read_exth(datain_rec0,121)
                if len(exth121) == 0:
                        self.combo = False
                        return
                datain_kf8, = struct.unpack_from('>L',exth121,0)
                datain_kfrec0 =readsection(datain,datain_kf8)

                # create the standalone mobi7
                num_sec = getint(datain,number_of_pdb_records,'H')
                # remove BOUNDARY up to but not including EOF record
                self.result_file7 = deletesectionrange(datain,datain_kf8-1,num_sec-2)
                # check if there are SRCS records and delete them
                srcs = getint(datain_rec0,srcs_index)
                num_srcs = getint(datain_rec0,srcs_count)
                if srcs > 0:
                        self.result_file7 = deletesectionrange(self.result_file7,srcs,srcs+num_srcs-1)
                        datain_rec0 = writeint(datain_rec0,srcs_index,0xffffffff)
                        datain_rec0 = writeint(datain_rec0,srcs_count,0)
                # remove the EXTH 121 KF8 Boundary meta data
                datain_rec0 = del_exth(datain_rec0,121)
                self.result_file7 = writesection(self.result_file7,0,datain_rec0)
                # null out FONT and RES, but leave the (empty) PDB record so image refs remain valid
                firstimage = getint(datain_rec0,first_image_record)
                lastimage = getint(datain_rec0,last_content_index,'H')
                for i in range(firstimage,lastimage):
                        imgsec = readsection(self.result_file7,i)
                        if imgsec[0:4] in ['RESC','FONT']:
                                self.result_file7 = nullsection(self.result_file7,i)
                # mobi7 finished

                # create standalone mobi8
                self.result_file8 = deletesectionrange(datain,0,datain_kf8-1)
                target = getint(datain_kfrec0,first_image_record)
                self.result_file8 = insertsectionrange(datain,firstimage,lastimage,self.result_file8,target)
                datain_kfrec0 =readsection(self.result_file8,0)
                ofs_list = [(kf8_last_content_index,'L'),(fcis_index,'L'),(flis_index,'L'),(datp_index,'L')]
                for ofs,sz in ofs_list:
                        n = getint(datain_kfrec0,ofs,sz)
                        if n>0:
                                datain_kfrec0 = writeint(datain_kfrec0,ofs,n+lastimage-firstimage+1,sz)
                self.result_file8 = writesection(self.result_file8,0,datain_kfrec0)
                # mobi8 finished
                
        def getResult8(self):
                return self.result_file8

        def getResult7(self):
                return self.result_file7

