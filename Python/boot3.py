#!/usr/bin/env python
#fileencoding: utf-8
#Modified : Keowu

import os
import sys
import struct
import binascii
import hashlib
import zlib
from stat import *
import shutil

def sha_file(sha, file):
    if file is None:
        return
    file.seek(0, 0)
    while True:
        data = file.read(65536)
        if not data:
            break
        sha.update(data)

def write_bootimg(output, kernel, ramdisk, second,
        name, cmdline, base, ramdisk_addr, second_addr,
        tags_addr, page_size, padding_size, dt_image):
    ''' make C8600-compatible bootimg.
        output: file object
        kernel, ramdisk, second: file object or string
        name, cmdline: string
        base, page_size, padding_size: integer size

        official document:
        http://android.git.kernel.org/?p=platform/system/core.git;a=blob;f=mkbootimg/bootimg.h

        Note: padding_size is not equal to page_size in HuaWei C8600
    '''

    if name is None:
        name = ''

    if cmdline is None:
        cmdline = 'mem=211M console=null androidboot.hardware=qcom'

    assert len(name) <= 16, 'Error: board name too large'
    assert len(cmdline) <= 512, 'Error: kernel commandline too large'

    if not isinstance(base, int):
        base = 0x10000000 # 0x00200000?
        sys.stderr.write('base is %s, using default base instead.\n' % type(base))

    if not isinstance(ramdisk_addr, int):
        ramdisk_addr = base + 0x01000000
        sys.stderr.write('ramdisk_addr is %s, using default ramdisk_addr instead.\n' % type(ramdisk_addr))

    if not isinstance(second_addr, int):
        second_addr = base + 0x00F00000
        sys.stderr.write('second_addr is %s, using default second_addr instead.\n' % type(second_addr))

    if not isinstance(tags_addr, int):
        tags_addr = base + 0x00000100
        sys.stderr.write('tags_addr is %s, using default tags_addr instead.\n' % type(tags_addr))

    if not isinstance(page_size, int):
        page_size = 0x800
        sys.stderr.write('page_size is %s, using default page_size instead.\n' % type(page_size))

    if not isinstance(padding_size, int):
        padding_size = 0x800 # 0x1000?
        sys.stderr.write('padding_size is %s, using default padding_size instead.\n' % type(padding_size))

    if not hasattr(output, 'write'):
        output = sys.stdout

    padding = lambda x: struct.pack('%ds' % ((~x + 1) & (padding_size - 1)), '')

    def getsize(x):
        if x is None:
            return 0
        assert hasattr(x, 'seek')
        assert hasattr(x, 'tell')
        x.seek(0, 2)
        return x.tell()

    def writecontent(output, x):
        if x is None:
            return None

        assert hasattr(x, 'read')

        x.seek(0, 0)
        output.write(x.read())
        output.write(padding(x.tell()))

        if hasattr(x, 'close'):
            x.close()

    sha = hashlib.sha1()
    sha_file(sha, kernel)
    sha.update(struct.pack('<I', getsize(kernel)))
    sha_file(sha, ramdisk)
    sha.update(struct.pack('<I', getsize(ramdisk)))
    sha_file(sha, second)
    sha.update(struct.pack('<I', getsize(second)))
    if dt_image is not None:
        sha_file(sha, dt_image)
        sha.update(struct.pack('<I', getsize(dt_image)))
    id = sha.digest()

    kernel_addr = base + 0x00008000
    output.write(struct.pack('<8s10I16s512s32s', 'ANDROID!',
        getsize(kernel), kernel_addr,
        getsize(ramdisk), ramdisk_addr,
        getsize(second), second_addr,
        tags_addr, page_size, getsize(dt_image), 0,
        name, cmdline, id))

    output.write(padding(608))
    writecontent(output, kernel)
    writecontent(output, ramdisk)
    writecontent(output, second)
    writecontent(output, dt_image)
    if hasattr('output', 'close'):
        output.close()

def parse_bootimg(bootimg):
    ''' parse C8600-compatible bootimg.
        write kernel to kernel[.gz]
        write ramdisk to ramdisk[.gz]
        write second to second[.gz]

        official document:
        http://android.git.kernel.org/?p=platform/system/core.git;a=blob;f=mkbootimg/bootimg.h

        Note: padding_size is not equal to page_size in HuaWei C8600
    '''

    bootinfo = open('bootinfo.txt', 'w')
    check_mtk_head(bootimg, bootinfo)

    (   magic,
        kernel_size, kernel_addr,
        ramdisk_size, ramdisk_addr,
        second_size, second_addr,
        tags_addr, page_size, dt_size, zero,
        name, cmdline, id4x8
    ) = struct.unpack('<8s10I16s512s32s', bootimg.read(608))
    bootimg.seek(page_size - 608, 1)

    base = kernel_addr - 0x00008000
    assert magic.decode('latin') == 'ANDROID!', 'invald bootimg'
    if not base == ramdisk_addr - 0x01000000:
        sys.stderr.write('found nonstandard ramdisk_addr\n')
    if not base == second_addr - 0x00f00000:
        sys.stderr.write('found nonstandard second_addr\n')
    if not base == tags_addr - 0x00000100:
        sys.stderr.write('found nonstandard tags_addr\n')
    if dt_size:
        sys.stderr.write('found device_tree_image\n')

    sys.stderr.write('base: 0x%x\n' % base)
    sys.stderr.write('ramdisk_addr: 0x%x\n' % ramdisk_addr)
    sys.stderr.write('second_addr: 0x%x\n' % second_addr)
    sys.stderr.write('tags_addr: 0x%x\n' % tags_addr)
    sys.stderr.write('page_size: %d\n' % page_size)
    sys.stderr.write('name: "%s"\n' % name.decode('latin').strip('\x00'))
    sys.stderr.write('cmdline: "%s"\n' % cmdline.decode('latin').strip('\x00'))

    bootinfo.write('base:0x%x\n' % base)
    bootinfo.write('ramdisk_addr:0x%x\n' % ramdisk_addr)
    bootinfo.write('second_addr:0x%x\n' % second_addr)
    bootinfo.write('tags_addr:0x%x\n' % tags_addr)
    bootinfo.write('page_size:0x%x\n' % page_size)
    bootinfo.write('name:%s\n' % name.decode('latin').strip('\x00'))
    bootinfo.write('cmdline:%s\n' % cmdline.decode('latin').strip('\x00'))

    while True:
        if bootimg.read(page_size) == struct.pack('%ds' % page_size, ''):
            continue
        bootimg.seek(-page_size, 1)
        size = bootimg.tell()
        break

    padding = lambda x: (~x + 1) & (size - 1)
    sys.stderr.write('padding_size=%d\n' % size)

    bootinfo.write('padding_size:0x%x\n' % size)
    bootinfo.close()

    gzname = lambda x: x == struct.pack('3B', 0x1f, 0x8b, 0x08) and '.gz' or ''

    kernel = bootimg.read(kernel_size)
    output = open('kernel%s' % gzname(kernel[:3]) , 'wb')
    output.write(kernel)
    output.close()
    bootimg.seek(padding(kernel_size), 1)

    ramdisk = bootimg.read(ramdisk_size)
    output = open('ramdisk%s' % gzname(ramdisk[:3]) , 'wb')
    output.write(ramdisk)
    output.close()
    bootimg.seek(padding(ramdisk_size), 1)

    if second_size:
        second = bootimg.read(second_size)
        output = open('second%s' % gzname(second[:3]) , 'wb')
        output.write(second)
        output.close()
        bootimg.seek(padding(ramdisk_size), 1)

    if dt_size:
        dt_image = bootimg.read(dt_size)
        output = open('dt_image%s' % gzname(dt_image[:3]) , 'wb')
        output.write(dt_image)
        output.close()
#        bootimg.seek(padding(second_size), 1)

    bootimg.close()

# CRC CCITT
crc_ccitt_table = []
for crc in range(0, 256):
    for x in range(0, 8):
        if crc & 0x1:
            crc = (crc >> 1) ^ 0x8408
        else:
            crc >>= 1
    crc_ccitt_table.append(crc)

def crc_ccitt(data, crc=0xffff):
    for item in data:
        crc = (crc >> 8) ^ crc_ccitt_table[crc & 0xff ^ item]
    return crc

#def write_crc(data, output):
#    crc = crc_ccitt(data) ^ 0xffff
#    # output.write(struct.pack('<H', crc))

POSITION = {0x30000000: 'boot.img',
            0x40000000: 'system.img',
            0x50000000: 'userdata.img',
            0x60000000: 'recovery.img',
            0xf2000000: 'splash.565',}
def parse_updata(updata, debug=False):
    ''' parse C8600 UPDATA binary.
        if debug is true or 1 or yes, write content to [position], else according POSITION

        UPDATA.APP Structure (only guess)
        magic                   |       0x55 0xaa 0x5a 0xa5
        header_length           |       unsigned int
        tag1                    |       0x01 0x00 0x00 0x00
        boardname               |       char[8]
        position                |       unsigned int
        content_length          |       unsigned int
        date                    |       char[16] -> YYYY.MM.DD
        time                    |       char[16] -> hh.mm.ss
        INPUT                   |       char[16] -> INPUT
        null                    |       char[16]
        unknown                 |       2 bytes, unknown
        tag2                    |       0x00 0x10 0x00 0x00
        header                  |       crc-ccitt for every 4096 of content
        content                 |
        padding                 |       padding to 4 bytes
    '''

    while True:
        data = updata.read(4)
        if not data:
            break
        if data == struct.pack('4s', ''):
            continue

        data += updata.read(94)
        assert len(data) == 98, 'invalid updata'
        (   magic,
            header_length,
            tag1,       # \x01\x00\x00\x00
            boardname,
            position,
            content_length,
            date,
            time,
            INPUT,
            null,
            unknown,    # 2 bytes
            tag2,       # \x00\x10\x00\x00
        ) = struct.unpack('<4sI4s8sII16s16s16s16s2s4s', data)

        magic, = struct.unpack('!I', magic)
        tag1, unknown, tag2 = struct.unpack('!IHI', tag1 + unknown + tag2)
        padding = (~(header_length + content_length) + 1) & 3

        assert magic == 0x55aa5aa5, 'invalid updata %x' % magic
        assert tag1 == 0x01000000, 'invalid tag1 %x' % tag1
        assert tag2 == 0x00100000, 'invalid tag2 %x' % tag2

        remain = header_length - 98
        header = list(struct.unpack('%dB' % remain, updata.read(remain)))

        sys.stderr.write('0x%x %x %d\n' % (position, unknown, content_length))

        if debug:
            output = open('0x%x' % position, 'wb')
        else:
            output = open(POSITION.get(position, os.devnull), 'wb')

        remain = content_length
        while remain > 0:
            size = remain > 4096 and 4096 or remain
            data = updata.read(size)
            if debug:
                check = list(struct.unpack('%dB' % size, data))
                check.append(header.pop(0))
                check.append(header.pop(0))
                assert crc_ccitt(check) == 0xf0b8
            output.write(data)
            remain -= size
        output.close()

        updata.seek(padding, 1)

    updata.close()

ZTE_PARTITIONS = {0x1 : 'qcsblhd_cfgdata.mbn',
                  0x2 : 'qcsbl.mbn',
                  0x3 : 'oemsbl.mbn,oemsblhd.mbn',
                  0x4 : 'amss.mbn,amsshd.mbn',
                  0x5 : 'appsboot.mbn,appsboothd.mbn',
                  0x13: 'boot.img',
                  0x15: 'recovery.img',
                  0x19: 'splash.img',
                  0x14: 'system.img',
                  0x1c: 'partition.mbn',
                  0x1d: 'partition_zte.mbn',}
def parse_zte_bin(binfile, debug=False):
    ''' parse ZTE image.bin.
        if debug is true or 1 or yes, write content to [position], else according POSITION

        image.bin Structure (only guess)
        magic1                    |  char[0x40]  'ZTE SOFTWARE UPDATE PACKAGE'
        partition_num             |  unsigned int
        partitions[partition_num] |  struct partitions
        padding...                |  padding to 0x400 bytes
        content                   |  parse according to partitions[]
        null                      |  char[0x40]
        magic2                    |  char[0x40]  'ZTE SOFTWARE UPDATE PACKAGE'

        struct partitions (only guess)
        partitionid               |  unsigned int
        partition_off             |  char *
        partition_size            |  unsigned int
        has_head                  |  unsigned int
        head_off                  |  char *
        head_size                 |  unsigned int
    '''

    magic1 = binfile.read(64)
    assert magic1, 'invalid binfile'
    assert len(magic1) == 64, 'invalid binfile'
    assert magic1 == struct.pack('64s', 'ZTE SOFTWARE UPDATE PACKAGE'), 'invalid binfile'

    data = binfile.read(4)
    partition_num = struct.unpack('<I', data)
    if debug:
        sys.stderr.write('found %d partitions\n' % partition_num)

    remain = partition_num[0]
    last = binfile.tell()
    while remain > 0:
        binfile.seek(last)
        data = binfile.read(24)
        (   partitionid,
            partition_off,
            partition_size,
            has_head,
            head_off,
            head_size,
        ) = struct.unpack('<IIIIII', data)
        last = binfile.tell()
        filenames = ZTE_PARTITIONS.get(partitionid, "UNKNOWN_PARTITIONS_%d.img,UNKNOWN_PARTITIONS_%d_HD.img" % (partitionid, partitionid)).split(',')
        if debug:
            sys.stderr.write('partition 0x%x: %s, off 0x%x, size %d Bytes\n' % (partitionid, filenames[0], partition_off, partition_size))
            if has_head == 1:
                sys.stderr.write('\thas head %s, off 0x%x, size %d Bytes\n' % (filenames[1], head_off, head_size))
        if has_head == 1:
            sys.stderr.write('output: %s\n' % filenames[1])
            output = open(filenames[1], 'wb')
            binfile.seek(head_off)
            data = binfile.read(head_size)
            output.write(data)
            output.close()
        sys.stderr.write('output: %s\n' % filenames[0])
        output = open(filenames[0], 'wb')
        binfile.seek(partition_off)
        data = binfile.read(partition_size)
        output.write(data)
        output.close()
        remain -= 1

    binfile.read(64)
    magic2 = binfile.read(64)
    assert magic2 == struct.pack('64s', 'ZTE SOFTWARE UPDATE PACKAGE'), 'invalid binfile'

    binfile.close()

def parse_qsb(binfile, debug=False):
    ''' parse qsb file.
        if debug is true or 1 or yes, write debug info to stdout

        image.qsb Structure (only guess)
        ??:0xC
        文件总大小:0x4
        BUILD_ID:0x40
        ??:0x4
        子文件数量:0x4
        ??:0xA8(0x100对齐??)

        {
        文件名:0x40
        分区名:0x20(可选)
        ??:0x8
        文件偏移量:0x4
        文件大小:0x4
        ??:0x10
        ??:0x80(0x100对齐??)
        }

        magic1                    |  char[0x40]  'ZTE SOFTWARE UPDATE PACKAGE'
        partition_num             |  unsigned int
        partitions[partition_num] |  struct partitions
        padding...                |  padding to 0x400 bytes
        content                   |  parse according to partitions[]
        null                      |  char[0x40]
        magic2                    |  char[0x40]  'ZTE SOFTWARE UPDATE PACKAGE'

        struct partitions (only guess)
        partitionid               |  unsigned int
        partition_off             |  char *
        partition_size            |  unsigned int
        has_head                  |  unsigned int
        head_off                  |  char *
        head_size                 |  unsigned int
    '''

    binfile.seek(0x54)
    data = binfile.read(4)
    partition_num = struct.unpack('<I', data)
    if debug:
        sys.stderr.write('found %d partitions\n' % partition_num)

    remain = partition_num[0]
    cur = 1
    last = binfile.tell()
    while cur <= remain:
        binfile.seek(cur * 0x100)
        data = binfile.read(0x80)
        (   file_name,
            part_name,
            null,
            null,
            file_off,
            file_size,
            null,
        ) = struct.unpack('<64s32sIIII16s', data)
        file_name = file_name.strip("\0")
        part_name = part_name.strip("\0")

        if debug:
            sys.stderr.write('partition 0x%x: %s[%s], off 0x%x, size %d Bytes\n' % (cur, part_name, file_name, file_off, file_size))
        sys.stderr.write('output: %s\n' % file_name)
        output = open(file_name, 'wb')
        binfile.seek(file_off)
        data = binfile.read(file_size)
        output.write(data)
        output.close()
        cur += 1

    binfile.close()

def parse_ext4_img(imgfile, output):
    ''' parse ext4_img by lenovo

        ext4_img Structure (only guess)
        UNKNOWN STRUCT            |  0x20
        3AFF 26ED 0100 0000  2000 1000 bbbb bbbb
        xxxx xxxx yyyy yyyy  zzzz zzzz aaaa aaaa
        xxxx xxxx:really block_num, out 0x404~0x407, in + 0x30
        yyyy yyyy:DATA STRUCT num + HOLE STRUCT num
        zzzz zzzz:CRC32 of outfile
        aaaa aaaa:0
        bbbb bbbb:0010(data,system)/0004(pxafs,pxaNVM), block_size
        DATA STRUCT               |  first in 0x20~2x2F,(MAGIC1 [8]=0xCAC1, BLOCK[4], STRUCT SIZE[4]=BLOCK*0x1000+0x10)
        ext4_data                 |  UNKNOWN TAGs, before every struct, always in output 0xXXXXX000
                                  |  out 0x400~403, in + 0x30,*4*block_size=size(Byte)
                                  |  out 0x404~407, in + 0x30, BLOCK NUM, *block_size=size(Byte)unsigned int
        HOLE STRUCT               |  end ,(MAGIC2 [8]=0xCAC3, BLOCK[4], STRUCT SIZE[4]=0x10),
    '''
#DATA STRUCT MAGIC1
    magic1 = 0xCAC1
#HOLE STRUCT MAGIC2
    magic2 = 0xCAC3

    data = imgfile.read(0x10)
    assert len(data) == 0x10, 'bad imgfile'
    (   null,
        null,
        null,
        block_size,
    ) = struct.unpack('<IIII', data)
    sys.stderr.write('block_size: 0x%x\n' % block_size)

#SKIP UNKNOWN STRUCT
    imgfile.seek(0x20, 0)

#data(do use struct info now)
    while True:
        data = imgfile.read(0x10)
        if len(data) == 0:
            break
        assert len(data) == 0x10, 'bad imgfile'
        (   magic,
            magic_null,
            block_num,
            size,
        ) = struct.unpack('<IIII', data)
        sys.stderr.write('magic: 0x%x, magic_null: 0x%x, block_num: 0x%x, size: 0x%x\n' % (magic, magic_null, block_num, size))

        assert (magic_null == 0), 'unknown magic'
        assert (magic == magic1 or magic == magic2), 'unknown magic'
        if (magic == magic2):
            assert (size == 0x10), 'bad hole struct'
            data = struct.pack('%ds' % (block_num * block_size), '')
            output.write(data)
        elif (magic == magic1):
            assert (size == block_num * block_size + 0x10), 'bad data struct'
            data = imgfile.read(size - 0x10)
            output.write(data)

#end(useless now)
#    nowSize = output.tell()
#    imgfile.seek(0x30 + 0x400 + 4, 0)
#    data = imgfile.read(4)
#    block_num = struct.unpack('<I', data)[0]
#    reallySize = block_num * 0x1000
#    addin = reallySize - nowSize
#    data = struct.pack('%ds' % addin, '')
#    output.write(data)

    imgfile.close()
    output.close()

#not use now
def computeFileCRC(filename):
    try:
        blocksize = 1024 * 64
        f = open(filename, "rb")
        str = f.read(blocksize)
        crc = 0
        while len(str) != 0:
            crc = binascii.crc32(str,crc) & 0xffffffff
            str = f.read(blocksize)
        f.close()
    except:
        print("compute file crc failed!")
        return 0
    return crc

def repack_img_ext4(imgfile, output):
    ''' repack ext4_img by lenovo

        ext4_img Structure (only guess)
        UNKNOWN STRUCT            |  0x20
        3AFF 26ED 0100 0000  2000 1000 bbbb bbbb
        xxxx xxxx yyyy yyyy  zzzz zzzz aaaa aaaa
        xxxx xxxx:really block_num, out 0x404~0x407, in + 0x30
        yyyy yyyy:DATA STRUCT num + HOLE STRUCT num
        zzzz zzzz:CRC32 of outfile
        aaaa aaaa:0
        bbbb bbbb:0010(data,system)/0004(pxafs,pxaNVM), block_size
        DATA STRUCT               |  first in 0x20~2x2F,(MAGIC1 [8]=0xCAC1, BLOCK[4], STRUCT SIZE[4]=BLOCK*0x1000+0x10)
        ext4_data                 |  UNKNOWN TAGs, before every struct, always in output 0xXXXXX000
                                  |  Inodes count, out 0x400~403, in + 0x30,*4*block_size=size(Byte)
                                  |  Blocks count, out 0x404~407, in + 0x30, BLOCK NUM, *block_size=size(Byte)unsigned int
        HOLE STRUCT               |  end ,(MAGIC2 [8]=0xCAC3, BLOCK[4], STRUCT SIZE[4]=0x10),
    '''

    imgfile.seek(0x0, 2)
    file_size = imgfile.tell()
    imgfile.seek(0x404, 0)
    data = imgfile.read(4)
    (block_num,) = struct.unpack('<I', data)
    block_size = file_size / block_num
    structnum = 0

    imgfile.seek(0x0, 0)
    data = imgfile.read()
    crc = binascii.crc32(data) & 0xffffffff
    head = struct.pack('<IIIIIIII', 0xED26FF3A, 0x1, 0x100020, block_size,
                                    block_num, structnum, crc, 0)
    output.write(head)

    data_num = 0
    hole_num = 0

    empty_block = struct.pack('%ds' % block_size, '')
    imgfile.seek(0x0, 0)
    while True:
        last_ds = imgfile.tell()
        cur_mode = 0
        cur_block = 0
        while True:
            data = imgfile.read(block_size)
            if len(data) == 0:
                break
            if not (data == empty_block):
                if cur_mode == 1:
                    cur_block += 1
                elif cur_mode == 2:
                    #cur_mode = 1#切换模式并输出
                    break
                else:
                    cur_mode = 1
                    cur_block += 1
            else:
                if cur_mode == 1:
                    #cur_mode = 2#切换模式并输出
                    break
                elif cur_mode == 2:
                    cur_block += 1
                else:
                    cur_mode = 2
                    cur_block += 1
        if cur_mode == 1:
            magic = 0xCAC1
            cur_size = cur_block * block_size + 0x10
            data_num += 1
        elif cur_mode == 2:
            magic = 0xCAC3
            cur_size = 0x10
            hole_num += 1
        else:
            break
        head = struct.pack('<IIII', magic, 0, cur_block, cur_size)
        output.write(head)
        imgfile.seek(last_ds, 0)
        data = imgfile.read(cur_block * block_size)
        if cur_mode == 1:
            output.write(data)

    #renew structnum
    output.seek(0x10, 0)
    structnum = data_num + hole_num
    head = struct.pack('<IIII', block_num, structnum, crc, 0)
    output.write(head)

    imgfile.close()
    output.close()

def write_zte_bin(binfile, debug=False):
    ''' parse ZTE image.bin.
        if debug is true or 1 or yes, write content to [position], else according POSITION

        image.bin Structure (only guess)
        magic1                    |  char[0x40]  'ZTE SOFTWARE UPDATE PACKAGE'
        partition_num             |  unsigned int
        partitions[partition_num] |  struct partitions
        padding...                |  padding to 0x400 bytes
        content                   |  parse according to partitions[]
        null                      |  char[0x40]
        magic2                    |  char[0x40]  'ZTE SOFTWARE UPDATE PACKAGE'

        struct partitions (only guess)
        partitionid               |  unsigned int
        partition_off             |  char *
        partition_size            |  unsigned int
        has_head                  |  unsigned int
        head_off                  |  char *
        head_size                 |  unsigned int
    '''

    magic1 = struct.pack('64s', 'ZTE SOFTWARE UPDATE PACKAGE')
    binfile.write(magic1)

    files = ['partition.mbn,0x1c',
             'partition_zte.mbn,0x1d',
             'qcsblhd_cfgdata.mbn,0x1',
             'qcsbl.mbn,0x2',
             'oemsbl.mbn,0x3,oemsblhd.mbn',
             'amss.mbn,0x4,amsshd.mbn',
             'appsboot.mbn,0x5,appsboothd.mbn',
             'boot.img,0x13',
             'recovery.img,0x15',
             'splash.img,0x19',
             'system.img,0x14',]
    partition_num = struct.pack('<I', len(files))
    binfile.write(partition_num)

    head = binfile.tell()
    info = 0x400

    remain = len(files)

    i = 0
    while i < remain:
        binfile.seek(info)
        file = files[i].split(',')
        has_head = 0
        head_off = 0
        head_size = 0
        if len(file) > 2:
            has_head = 1
            head_off = binfile.tell()
            file_head = file[2]
            f_head = open(file_head, 'rb')
            data = f_head.read()
            head_size = f_head.tell()
            f_head.close()
            binfile.write(data)
        partition_off = binfile.tell()
        partitionid = int(file[1], 16)
        file = file[0]
        f = open(file, 'rb')
        data = f.read()
        partition_size = f.tell()
        f.close()
        binfile.write(data)

        info = binfile.tell()
        binfile.seek(head)
        data = struct.pack('<IIIIII', partitionid,
                                      partition_off,
                                      partition_size,
                                      has_head,
                                      head_off,
                                      head_size)
        binfile.write(data)
        head = binfile.tell()
        i += 1

    binfile.seek(info)
    data = struct.pack('64s', '')
    binfile.write(data)
    magic2 = struct.pack('64s', 'ZTE SOFTWARE UPDATE PACKAGE')
    binfile.write(magic2)

    binfile.close()

def cpio_list(directory, output=None):
    ''' generate gen_cpio_init-compatible list for directory,
        if output is None, write to stdout

        official document:
        http://git.kernel.org/?p=linux/kernel/git/torvalds/linux-2.6.git;a=blob;f=usr/gen_init_cpio.c
    '''

    if not hasattr(output, 'write'):
        output = sys.stdout
    for root, dirs, files in os.walk(directory):
        for file in dirs + files:
            path = os.path.join(root, file)
            info = os.lstat(path)
            name = path.replace(directory, '', 1)
            name = name.replace(os.sep, '/')    # for windows
            if name[:1] == '/':
                name = name[1:]
            mode = oct(S_IMODE(info.st_mode))
            if S_ISLNK(info.st_mode):
                # slink name path mode uid gid
                realpath = os.readlink(path)
                output.write('slink %s %s %s 0 0\n' % (name, realpath, mode))
            elif S_ISDIR(info.st_mode):
                # dir name path mode uid gid
                output.write('dir %s %s 0 0\n' % (name, mode))
            elif S_ISREG(info.st_mode):
                # file name path mode uid gid
                output.write('file %s %s %s 0 0\n' % (name, path, mode))

    if hasattr(output, 'close'):
        output.close()

def parse_cpio(cpio, directory, cpiolist):
    ''' parse cpio, write content under directory.
        cpio: file object
        directory: string
        cpiolist: file object

        official document: (cpio newc structure)
        http://git.kernel.org/?p=linux/kernel/git/torvalds/linux-2.6.git;a=blob;f=usr/gen_init_cpio.c
    '''

    padding = lambda x: (~x + 1) & 3

    def read_cpio_header(cpio):
        assert cpio.read(6).decode('latin') == '070701', 'invalid cpio'
        cpio.read(8) # ignore inode number
        mode = int(cpio.read(8), 16)
        cpio.read(8) # uid
        cpio.read(8) # gid
        cpio.read(8) # nlink
        cpio.read(8) # timestamp
        filesize = int(cpio.read(8), 16)
        cpio.read(8) # major
        cpio.read(8) # minor
        cpio.read(8) # rmajor
        cpio.read(8) # rminor
        namesize = int(cpio.read(8), 16)
        cpio.read(8)
        name = cpio.read(namesize - 1).decode('latin') # maybe utf8?
        cpio.read(1)
        cpio.read(padding(namesize + 110))
        return name, mode, filesize

    os.makedirs(directory)

    while True:
        name, mode, filesize = read_cpio_header(cpio)
        if name == 'TRAILER!!!':
            break

        if name[:1] == '/':
            name = name[1:]

        name = os.path.normpath(name)
        path = '%s/%s' %(directory, name)
        name = name.replace(os.sep, '/') # for windows

        srwx = oct(S_IMODE(mode))
        if S_ISLNK(mode):
            location = cpio.read(filesize)
            cpio.read(padding(filesize))
            cpiolist.write('slink %s %s %s\n' % (name, location, srwx))
        elif S_ISDIR(mode):
            try: os.makedirs(path)
            except os.error: pass
            cpiolist.write('dir %s %s\n' % (name, srwx))
        elif S_ISREG(mode):
            tmp = open(path, 'wb')
            tmp.write(cpio.read(filesize))
            cpio.read(padding(filesize))
            tmp.close()
            cpiolist.write('file %s %s %s\n' % (name, path, srwx))
        else:
            cpio.read(filesize)
            cpio.read(padding(filesize))

    cpio.close()
    cpiolist.close()

#根据system/core/cpio/mkbootfs.c对代码进行修正
def write_cpio(cpiolist, output):
    ''' generate cpio from cpiolist.
        cpiolist: file object
        output: file object
    '''

    padding = lambda x, y: struct.pack('%ds' % ((~x + 1) & (y - 1)), '')

    def write_cpio_header(output, ino, name, mode=0, nlink=1, filesize=0):
        namesize = len(name) + 1
        latin = lambda x: x.encode('latin')
        output.write(latin('070701'))
        output.write(latin('%08x' % ino)) # Android自300000递增 # ino normally only for hardlink

        output.write(latin('%08x' % mode))
        output.write(latin('%08x%08x' % (0, 0))) # uid, gid set to 0
        output.write(latin('%08x' % 1)) # 在Android中恒为1而非nlink
        output.write(latin('%08x' % 0)) # timestamp set to 0
        output.write(latin('%08x' % filesize))
        output.write(latin('%08x%08x' % (0, 0))) # 在Android中为(0, 0) 而非 (3, 1)
        output.write(latin('%08x%08x' % (0, 0))) # dont support rmajor, rminor
        output.write(latin('%08x' % namesize))
        output.write(latin('%08x' % 0)) # chksum always be 0
        output.write(latin(name))
        output.write(struct.pack('1s', ''))
        output.write(padding(namesize + 110, 4))

    def cpio_mkfile(output, ino, name, path, mode, *kw):
        if os.path.split(name)[1] in ('su', 'busybox'):
            mode = '4555'
        mode = int(mode, 8) | S_IFREG
        if os.path.lexists(path):
            filesize = os.path.getsize(path)
            write_cpio_header(output, ino, name, mode, 1, filesize)
            tmp = open(path, 'rb')
            output.write(tmp.read())
            tmp.close()
            output.write(padding(filesize, 4))
        else:
            sys.stderr.write('not found file %s, skip it\n' % path)

    def cpio_mkdir(output, ino, name, mode='755', *kw):
        #if name == 'tmp':
        #    mode = '1777'
        mode = int(mode, 8) | S_IFDIR
        write_cpio_header(output, ino, name, mode, 2, 0)

    def cpio_mkslink(output, ino, name, path, mode='777', *kw):
        mode = int(mode, 8) | S_IFLNK
        filesize = len(path)
        write_cpio_header(output, ino, name, mode, 1, filesize)
        output.write(path)
        output.write(padding(filesize, 4))

    def cpio_mknod(output, ino, *kw):
        sys.stderr.write('nod is not implemented\n')

    def cpio_mkpipe(output, ino, *kw):
        sys.stderr.write('pipe is not implemented\n')

    def cpio_mksock(output, ino, *kw):
        sys.stderr.write('sock is not implemented\n')

    def cpio_tailer(output, ino):
        name = 'TRAILER!!!'
        write_cpio_header(output, ino, name, 0o644) # 8进制权限644, 的确应该为0? 为调用fix_stat引起的bug.

        # normally, padding is ignored by decompresser
        if hasattr(output, 'tell'):
            output.write(padding(output.tell(), 512))

    files = []
    functions = {'dir': cpio_mkdir,
                 'file': cpio_mkfile,
                 'slink': cpio_mkslink,
                 'nod': cpio_mknod,
                 'pipe': cpio_mkpipe,
                 'sock': cpio_mksock}
    next_inode = 300000
    while True:
        line = cpiolist.readline()
        if not line:
            break
        lines = line.split()
        if len(lines) < 1 or lines[0] == '#':
            continue
        function = functions.get(lines[0])
        if not function:
            continue
        lines.pop(0)
        lines[0] = lines[0].replace(os.sep, '/') # if any
        if lines[0] in files:
            sys.stderr.write('ignore duplicate %s\n' % lines[0])
            continue
        files.append(lines[0])
        function(output, next_inode, *lines)
        next_inode += 1

    # for extra in ['/tmp', '/mnt']:
    #    if extra not in files:
    #        sys.stderr.write('add extra %s\n' % extra)
    #        cpio_mkdir(output, extra)

    cpio_tailer(output, next_inode)
    cpiolist.close()
    output.close()

def parse_yaffs2(image, directory):
    ''' parse yaffs2 image.

        official document: (utils/mkyaffs2image)
        http://android.git.kernel.org/?p=platform/external/yaffs2.git
        spare: yaffs_PackedTags2 in yaffs_packedtags2.h
        chunk: yaffs_ExtendedTags in yaffs_guts.h
    '''

    path = '.'
    filelist = {1: '.'}

    class Complete(Exception):
        pass

    def read_chunk(image):
        chunk = image.read(2048)
        spare = image.read(64)
        if not chunk:
            raise Complete
        assert len(spare) >= 16
        return chunk, spare

    def process_chunk(image):
        chunk, spare = read_chunk(image)

        nil, objectid, nil, bytecount = struct.unpack('<4I', spare[:16])

        if bytecount == 0xffff:
            assert len(chunk) >= 460
            (   filetype, parent,
                nil, name, padding, mode,
                uid, gid, atime, mtime, ctime,
                filesize, equivalent, alias
            ) = struct.unpack('<iiH256s2sI5Iii160s', chunk[:460])

            # only for little-endian
            # (   filetype, parent,
            #     nil, name, mode,
            #     uid, gid, atime, mtime, ctime,
            #     filesize, equivalent, alias
            # ) = struct.unpack('iiH256sI5Iii160s', chunk[:460])

            parent = filelist.get(parent)
            assert parent is not None

            name = name.decode('latin').split('\x00')[0]
            path = name and '%s/%s' % (parent, name) or parent
            filelist[objectid] = path
            fullname = '%s/%s' % (directory, path)

            if filetype == 0: # unknown
                pass
            elif filetype == 1: # file
                flag = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
                if hasattr(os, 'O_BINARY'):
                    flag |= os.O_BINARY
                output = os.open(fullname, flag, mode)
                while filesize > 0:
                    chunk, spare = read_chunk(image)
                    nil, nil, nil, bytecount = struct.unpack('<4I', spare[:16])
                    size = filesize < bytecount and filesize or bytecount
                    os.write(output, chunk[:size])
                    filesize -= size
                os.close(output)
            elif filetype == 2: # slink
                alias = alias.decode('latin').split('\x00')[0]
                try: os.symlink(alias, fullname)
                except: sys.stderr.write('soft %s -> %s\n' % (fullname, alias))
            elif filetype == 3: # dir
                if not os.path.isdir(fullname):
                    os.makedirs(fullname, mode)
                try: os.chmod(fullname, mode)
                except: sys.stderr.write('directory mode is not supported')
            elif filetype == 4: # hlink
                link = filelist.get(equivalent)
                try: os.link(filelist.get(equivalent), fullname)
                except: sys.stderr.write('hard %s -> %s\n' % (fullname, link))
            elif filetype == 5: # special
                pass

    while True:
        try: process_chunk(image)
        except Complete: break

    image.close()

from gzip import GzipFile
class CPIOGZIP(GzipFile):
    # dont write filename
    def _write_gzip_header(self):
        self.fileobj.write(struct.pack('4B', 0x1f, 0x8b, 0x08, 0x00))
        self.fileobj.write(struct.pack('4s', ''))
        self.fileobj.write(struct.pack('2B', 0x00, 0x03))

    # don't check crc and length
    def _read_eof(self):
        pass

def parse_rle(rle, raw):
    ''' convert 565-rle format to raw file.

        official document:
        http://android.git.kernel.org/?p=platform/build.git;a=blob;f=tools/rgb2565/to565.c
    '''
    r = lambda x: int(((x >> 11) & 0x1f) << 3)
    g = lambda x: int(((x >> 5) & 0x3f) << 2)
    b = lambda x: int((x & 0x1f) << 3)

    total = 0
    while True:
        data = rle.read(4)
        if not data:
            break
        assert len(data) == 4
        count, color = struct.unpack('<2H', data)
        total += count
        while count:
            count -= 1
            raw.write(struct.pack('3B', r(color), g(color), b(color)))
    rle.close()
    raw.close()
    return total

def parse_565(rle, raw):
    ''' convert 565 format to raw file.

        official document:
        http://android.git.kernel.org/?p=platform/build.git;a=blob;f=tools/rgb2565/to565.c
    '''
    r = lambda x: int(((x >> 11) & 0x1f) << 3)
    g = lambda x: int(((x >> 5) & 0x3f) << 2)
    b = lambda x: int((x & 0x1f) << 3)

    total = 0
    while True:
        data = rle.read(2)
        if not data:
            break
        assert len(data) == 2
        color, = struct.unpack('<H', data)
        total += 1
        raw.write(struct.pack('3B', r(color), g(color), b(color)))
    rle.close()
    raw.close()
    return total

def write_rle(raw, rle):
    ''' convert raw file to 565-rle format.
    '''
    x = lambda r, g, b: ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

    last = None
    total = 0
    while True:
        rgb = raw.read(3)
        if not rgb:
            break
        total += 1
        assert len(rgb) == 3
        color = x(*struct.unpack('3B', rgb))
        if last is None:
            pass
        elif color == last and count != 0xffff:
            count += 1
            continue
        else:
            rle.write(struct.pack('<2H', count, last))
        last = color
        count = 1
    if count:
        rle.write(struct.pack('<2H', count, last))
    raw.close()
    rle.close()
    return total

def write_565(raw, rle):
    ''' convert raw file to 565 format.
    '''
    x = lambda r, g, b: ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

    last = None
    total = 0
    while True:
        rgb = raw.read(3)
        if not rgb:
            break
        total += 1
        assert len(rgb) == 3
        color = x(*struct.unpack('3B', rgb))
        rle.write(struct.pack('<H', color))
    raw.close()
    rle.close()
    return total

__all__ = [ 'parse_updata',
            'parse_bootimg',
            'write_bootimg',
            'parse_cpio',
            'write_cpio',
            'parse_yaffs2',
            'parse_rle',
            'write_rle',
            'parse_565',
            'write_565',
            'cpio_list',
            'POSITION',
            ]

base = None
ramdisk_addr = None
second_addr = None
tags_addr = None
name = None
cmdline = None
page_size = None
padding_size = None

def parse_bootinfo(bootinfo):
#''' parse bootinfo for repack bootimg.
#    bootinfo: file object
#'''
    global base, ramdisk_addr, second_addr, tags_addr, name, cmdline, page_size, padding_size
    def set_base(addr):
        global base
        if base is None:
            base = int(addr, 16)

    def set_ramdisk_addr(addr):
        global ramdisk_addr
        if ramdisk_addr is None:
            ramdisk_addr = int(addr, 16)

    def set_second_addr(addr):
        global second_addr
        if second_addr is None:
            second_addr = int(addr, 16)

    def set_tags_addr(addr):
        global tags_addr
        if tags_addr is None:
            tags_addr = int(addr, 16)

    def set_page_size(size):
        global page_size
        if page_size is None:
            page_size = int(size, 16)

    def set_padding_size(size):
        global padding_size
        if padding_size is None:
            padding_size = int(size, 16)

    def set_name(old_name):
        global name
        if name is None:
            name = old_name.strip()

    def set_cmdline(old_cmdline):
        global cmdline
        if cmdline is None:
            cmdline = old_cmdline.strip()

    functions = {'base': set_base,
                 'ramdisk_addr': set_ramdisk_addr,
                 'second_addr': set_second_addr,
                 'tags_addr': set_tags_addr,
                 'page_size': set_page_size,
                 'padding_size': set_padding_size,
                 'name': set_name,
                 'cmdline': set_cmdline}

    while True:
        line = bootinfo.readline()
        if not line:
            break
        lines = line.split(':')
        if len(lines) < 1 or lines[0][0] == '#':
            continue
        function = functions.get(lines[0])
        if not function:
            continue
        lines.pop(0)
        function(*lines)

# above is the module of bootimg
# below is only for usage...

def repack_bootimg(_base=None, _cmdline=None, _page_size=None, _padding_size=None, cpiolist=None):
    if cpiolist is None:
        cpiolist = 'cpiolist.txt'

    sys.stderr.write('arguments: [cpiolist file]\n')
    sys.stderr.write('cpiolist file: %s\n' % cpiolist)
    sys.stderr.write('output: ramdisk.cpio.gz\n')

    tmp = open('ramdisk.cpio.gz.tmp', 'wb')
    out = open('ramdisk.cpio.gz', 'wb')
    cpiogz = tmp
    
    info = open(cpiolist, 'r')
    compress_level = 6
    
    off2 = info.tell()
    info.seek(0, 0)
    for line in info.readlines():
        lines = line.split(':')
        if len(lines) < 1 or lines[0][0] == '#':
            continue;
        if lines[0].strip() == 'compress_level':
            compress_level = int(lines[1], 10)
            break
    info.seek(off2, 0)

    if compress_level <= 0:
        cpiogz = tmp
    else:
        if compress_level > 9:
            compress_level = 9
        cpiogz = CPIOGZIP(None, 'wb', compress_level, tmp)
    sys.stderr.write('compress_level: %d\n' % compress_level)
    write_cpio(info, cpiogz)
    #cpiogz.close()
    tmp.close()
    #info.close()

    tmp = open('ramdisk.cpio.gz.tmp', 'rb')
    info = open(cpiolist, 'r')
    if try_add_head(tmp, out, info):
        while True:
            data = tmp.read(65536)
            if not data:
                break
            out.write(data)
        tmp.close()
        out.close()
        os.remove('ramdisk.cpio.gz.tmp')
    else:
        tmp.close()
        out.close()
        os.remove('ramdisk.cpio.gz')
        os.rename('ramdisk.cpio.gz.tmp', 'ramdisk.cpio.gz')
    info.close()

    global base, ramdisk_addr, second_addr, tags_addr, name, cmdline, page_size, padding_size
    if os.path.exists('ramdisk.cpio.gz'):
        ramdisk = 'ramdisk.cpio.gz'
    elif os.path.exists('ramdisk'):
        ramdisk = 'ramdisk'
    else:
        ramdisk = 'ramdisk.gz'

    if os.path.exists('second.gz'):
        second = 'second.gz'
    elif os.path.exists('second'):
        second = 'second'
    else:
        second = ''

    if os.path.exists('dt_image.gz'):
        dt_image = 'dt_image.gz'
    elif os.path.exists('dt_image'):
        dt_image = 'dt_image'
    else:
        dt_image = ''

    if _base is not None:
        base = int(_base, 16)

    if _cmdline is not None:
        cmdline = _cmdline

    if _page_size is not None:
        page_size = int(str(_page_size))

    if _padding_size is not None:
        padding_size = int(str(_padding_size))

    if os.path.exists('bootinfo.txt'):
        bootinfo = open('bootinfo.txt', 'r')
        parse_bootinfo(bootinfo)
        bootinfo.close()

    sys.stderr.write('arguments: [base] [cmdline] [page_size] [padding_size]\n')
    sys.stderr.write('kernel: kernel\n')
    sys.stderr.write('ramdisk: %s\n' % ramdisk)
    sys.stderr.write('second: %s\n' % second)
    sys.stderr.write('dt_image: %s\n' % dt_image)
    sys.stderr.write('base: 0x%x\n' % base)
    sys.stderr.write('ramdisk_addr: 0x%x\n' % ramdisk_addr)
    sys.stderr.write('second_addr: 0x%x\n' % second_addr)
    sys.stderr.write('tags_addr: 0x%x\n' % tags_addr)
    sys.stderr.write('name: %s\n' % name)
    sys.stderr.write('cmdline: %s\n' % cmdline)
    sys.stderr.write('page_size: %d\n' % page_size)
    sys.stderr.write('padding_size: %d\n' % padding_size)
    sys.stderr.write('output: boot-new.img\n')

    tmp = open('boot.img.tmp', 'wb')
    options = { 'base': base,
                'ramdisk_addr': ramdisk_addr,
                'second_addr': second_addr,
                'tags_addr': tags_addr,
                'name': name,
                'cmdline': cmdline,
                'output': tmp,
                'kernel': open('kernel', 'rb'),
                'ramdisk': open(ramdisk, 'rb'),
                'second': second and open(second, 'rb') or None,
                'page_size': page_size,
                'padding_size': padding_size,
                'dt_image': dt_image and open(dt_image, 'rb') or None,
                }

    write_bootimg(**options)
    tmp.close()
    if os.path.exists('bootinfo.txt'):
        bootinfo = open('bootinfo.txt', 'r')
        output = open('boot.img', 'wb')
        tmp = open('boot.img.tmp', 'rb')
        if try_add_head(tmp, output, bootinfo):
            bootinfo.close()
            while True:
                data = tmp.read(65536)
                if not data:
                    break
                output.write(data)
            tmp.close()
            os.remove('boot.img.tmp')
            out.close()
            return
        else:
            tmp.close()
            output.close()
            bootinfo.close()
    os.remove('bootinfo.txt')
    os.remove('boot.img')
    os.remove('cpiolist.txt')
    if os.path.exists('ramdisk.gz'):
        os.remove('ramdisk.gz')
    if os.path.exists('ramdisk.cpio.gz'):
        os.remove('ramdisk.cpio.gz')   
    os.remove('kernel')
    if os.path.exists('dt_image'):
        os.remove('dt_image')
    if os.path.exists('ramdisk'):
        os.remove('ramdisk')
    shutil.rmtree('initrd')
    os.rename('boot.img.tmp', 'boot-new.img')

def unpack_bootimg(bootimg=None, ramdisk=None, directory=None):
    shutil.copy('boot.img', 'boot-old.img')
    if bootimg is None:
        bootimg = 'boot.img'
        if os.path.exists('recovery.img') and not os.path.exists('boot.img'):
            bootimg = 'recovery.img'
    sys.stderr.write('arguments: [bootimg file]\n')
    sys.stderr.write('bootimg file: %s\n' % bootimg)
    sys.stderr.write('output: kernel[.gz] ramdisk[.gz] second[.gz]\n')
    parse_bootimg(open(bootimg, 'rb'))
	
    if ramdisk is None:
        if os.path.exists('ramdisk.gz'):
            ramdisk = 'ramdisk.gz'
        elif os.path.exists('ramdisk'):
            ramdisk = 'ramdisk'
        elif os.path.exists('ramdisk.cpio.gz'):
            ramdisk = 'ramdisk.cpio.gz'
        else:
            ramdisk = 'ramdisk.gz'

    if directory is None:
        directory = 'initrd'

    sys.stderr.write('arguments: [ramdisk file] [directory]\n')
    sys.stderr.write('ramdisk file: %s\n' % ramdisk)
    sys.stderr.write('directory: %s\n' % directory)
    sys.stderr.write('output: cpiolist.txt\n')

    if os.path.lexists(directory):
        raise SystemExit('please remove %s' % directory)

    tmp = open(ramdisk, 'rb')
    cpiolist = open('cpiolist.txt', 'w')
    check_mtk_head(tmp, cpiolist)
    pos = tmp.tell()

    compress_level = 0
    magic = tmp.read(6)
    if magic[:3] == struct.pack('3B', 0x1f, 0x8b, 0x08):
        tmp.seek(pos, 0)
        compress_level = 6
        cpio = CPIOGZIP(None, 'rb', compress_level, tmp)
    elif magic.decode('latin') == '070701':
        tmp.seek(pos, 0)
        cpio = tmp
    else:
        tmp.close()
        raise IOError('invalid ramdisk')

    cpiolist.write('compress_level:%d\n' % compress_level)
    sys.stderr.write('compress: %s\n' % (compress_level > 0))
    parse_cpio(cpio, directory, cpiolist)

def unpack_updata(updata=None, debug=False):
    if updata is None and os.path.exists('UPDATA.APP'):
        updata = 'UPDATA.APP'
    sys.stderr.write('arguments: [updata file]\n')
    sys.stderr.write('updata file: %s\n' % updata)
    sys.stderr.write('output: splash.565 (565 file)\n')
    sys.stderr.write('output: boot.img recover.img (bootimg file)\n')
    sys.stderr.write('output: system.img userdata.img (yaffs2 image)\n')
    parse_updata(open(updata, 'rb'), debug)

def unpack_zte_bin(bin=None, debug=False):
    if bin is None and os.path.exists('image.bin'):
        bin = 'image.bin'
    sys.stderr.write('arguments: [bin file]\n')
    sys.stderr.write('bin file: %s\n' % bin)
    parse_zte_bin(open(bin, 'rb'), debug)

def unpack_qsb(bin=None, debug=False):
    if bin is None and os.path.exists('image.bin'):
        bin = 'image.bin'
    sys.stderr.write('arguments: [bin file]\n')
    sys.stderr.write('bin file: %s\n' % bin)
    parse_qsb(open(bin, 'rb'), debug)

def repack_zte_bin(bin=None, debug=False):
    if bin is None:
        bin = 'image.bin'
    sys.stderr.write('arguments: [bin file]\n')
    sys.stderr.write('bin file: %s\n' % bin)
    write_zte_bin(open(bin, 'wb'), debug)

def to_ext4(img=None, outfile=None):
    if img is None and os.path.exists('system_ext4.img'):
        img = 'system_ext4.img'
    sys.stderr.write('arguments: [img file [out file]]\n')
    sys.stderr.write('img file: %s\n' % img)
    if outfile is None:
        outfile = '%s.img.ext4' % img.split('.')[0]
    sys.stderr.write('output: %s\n' % outfile)
    parse_ext4_img(open(img, 'rb'), open(outfile, 'wb'))

def to_img(img=None, outfile=None):
    if img is None and os.path.exists('system_ext4.img.ext4'):
        img = 'system_ext4.img.ext4'
    sys.stderr.write('arguments: [img file [out file]]\n')
    sys.stderr.write('img file: %s\n' % img)
    if outfile is None:
        outfile = '%s_repack.img' % img.split('.')[0]
    sys.stderr.write('output: %s\n' % outfile)
    repack_img_ext4(open(img, 'rb'), open(outfile, 'wb'))

def test_dzlib(img=None, out=None):
    if img is None:
        sys.stderr.write('arguments: [img file [out file]]\n')
        return
    sys.stderr.write('img file: %s\n' % img)
    if out is None:
        out = 'zlib_%s' % os.path.basename(img)
    sys.stderr.write('output: %s\n' % out)
    #open file
    imgfile = open(img, 'rb')
    outfile = open(out, 'wb')

    data = imgfile.read()
    dataz = zlib.decompress(data)
    outfile.write(dataz)

    imgfile.close()
    outfile.close()

def test_czlib(img=None, out=None):
    if img is None:
        sys.stderr.write('arguments: [img file [out file]]\n')
        return
    sys.stderr.write('img file: %s\n' % img)
    if out is None:
        out = 'zlib_%s' % os.path.basename(img)
    sys.stderr.write('output: %s\n' % out)
    #open file
    imgfile = open(img, 'rb')
    outfile = open(out, 'wb')

    data = imgfile.read()
    dataz = zlib.compress(data, zlib.Z_DEFAULT_COMPRESSION)
#Z_BEST_SPEED|Z_BEST_COMPRESSION|Z_DEFAULT_COMPRESSION|Z_FILTERED|Z_HUFFMAN_ONLY|Z_DEFAULT_STRATEGY|Z_FINISH|Z_NO_FLUSH|Z_SYNC_FLUSH|Z_FULL_FLUSH
    outfile.write(dataz)

    imgfile.close()
    outfile.close()

def dcompress_mtk_logo(img=None, out_base=None):
    if img is None:
        sys.stderr.write('arguments: [img file [out file basename]]\n')
        return
    sys.stderr.write('img file: %s\n' % img)
    if out_base is None:
        out_base = os.path.basename(img)
    ext = os.path.splitext(out_base)[1]
    out_base = os.path.splitext(out_base)[0]

    #open file
    offset2 = 0#当前进度
    offset3 = 0
    imgfile = open(img, 'rb')
    outinfo = '%s_info.txt' % out_base
    outinfofile = open(outinfo, 'w')

    check_mtk_head(imgfile, outinfofile)
    offset1 = imgfile.tell()#去除文件头后的真正开头

    data = imgfile.read(0x4)
    assert len(data) == 0x4, 'invalid logo'
    (tag,) = struct.unpack('<I', data)
    logo_num = tag
    sys.stderr.write('Found %d logos.\n' % logo_num)
    outinfofile.write('logo_num:%d\n' % logo_num)
    data = imgfile.read(0x4)
    assert len(data) == 0x4, 'invalid logo'
    (size,) = struct.unpack('<I', data)
    offset2 = imgfile.tell()
    imgfile.seek(0, 2)
    assert size <= imgfile.tell() - offset1, 'invalid logo'
    imgfile.seek(offset2, 0)

    data = imgfile.read(0x4)
    (offset3,) = struct.unpack('<I', data)#当前图片位置(offset1+offset3)

    for i in range(logo_num - 1):
        data = imgfile.read(0x4)
        (offset4,) = struct.unpack('<I', data)#下张图片位置(offset1+offset4)
        offset2 = imgfile.tell()
        imgfile.seek(offset1 + offset3, 0)

        out = '%s_%d%s' %(out_base, i, ext)
        sys.stderr.write('Output: %s\n' % out)
        outfile = open(out, 'wb')

        data = imgfile.read(offset4 - offset3)
        dataz = zlib.decompress(data)

        outfile.write(dataz)
        outfile.close()

        imgfile.seek(offset2, 0)
        offset3 = offset4

    imgfile.seek(offset1 + offset3, 0)

    out = '%s_%d%s' %(out_base, logo_num - 1, ext)
    sys.stderr.write('Output: %s\n' % out)
    outfile = open(out, 'wb')

    data = imgfile.read(size - offset4)
    dataz = zlib.decompress(data)

    outfile.write(dataz)
    outfile.close()

    outinfofile.close()
    imgfile.close()

def compress_mtk_logo(in_base=None, num=None, out=None):
    if in_base is None:
        sys.stderr.write('arguments: logo basename [num [out file]]\n')
        return
    if out is None:
        out = in_base
    ext = os.path.splitext(in_base)[1]
    in_base = os.path.splitext(in_base)[0]
    if num is not None:
        num = int(str(num))

    ininfo = '%s_info.txt' % in_base
    ininfofile = open(ininfo, 'r')

    if num is None:
        for line in ininfofile.readlines():
            lines = line.split(':')
            if len(lines) < 1 or lines[0][0] == '#':
                continue;
            if lines[0].strip() == 'logo_num':
                num = int(lines[1].strip())
                break

    sys.stderr.write('Output: %s\n' % out)
    sys.stderr.write('Compressing %d logos.\n' % num)
    tmp = open('%s.tmp' % out, 'wb')
    data = struct.pack('<II', num, 0)
    tmp.write(data)

    offset1 = 0 #文件头
    offset2 = 4*(2+num) #数据
    offset3 = 0 #

    for i in range(num):
        data = struct.pack('<I', offset2)
        tmp.write(data)

        img = '%s_%d%s' %(in_base, i, ext)
        sys.stderr.write('Processing logo file: %s\n' % img)
        imgfile = open(img, 'rb')
        data = imgfile.read()
        imgfile.close()

        offset1 = tmp.tell()
        tmp.seek(offset2, 0)
        dataz = zlib.compress(data, zlib.Z_BEST_COMPRESSION)
        tmp.write(dataz)

        offset2 = tmp.tell()
        tmp.seek(offset1, 0)

    tmp.seek(0x4, 0)
    data = struct.pack('<I', offset2)
    tmp.write(data)
    tmp.close()

    tmp = open('%s.tmp' % out, 'rb')
    outfile = open(out, 'wb')
    if try_add_head(tmp, outfile, ininfofile):
        while True:
            data = tmp.read(65536)
            if not data:
                break
            outfile.write(data)
        tmp.close()
        os.remove('%s.tmp' % out)
        outfile.close()
    else:
        tmp.close()
        outfile.close()
        os.remove(out)
        os.rename('%s.tmp' % out, out)
    ininfofile.close()

def unpack_mali_logo(img=None):
    if img is None:
        sys.stderr.write('arguments: [img file]\n')
        return
    sys.stderr.write('img file: %s\n' % img)

    #open file
    imgfile = open(img, 'rb')

    while True:
        data = imgfile.read(0x40)
        if len(data) < 0x10:
            imgfile.close()
            return
        assert len(data) == 0x40, 'bad block'
        (tag,size,start,end,id,total,null,name) = struct.unpack('<QIQQBBH32s', data)
        name = name.strip('\x00')
        assert tag == 0x27051956, 'invalid magic'
        sys.stdout.write('img file(%d/%d): %s.bmp, size: %x, start: %x, end: %x\n'
                % (id+1,total,name,size,start,end))
        assert id < total, '\twrong id'
        curoff = imgfile.tell()
        assert start == curoff, '\twrong start'
        assert end >= (start + size) or end == 0, '\twrong size/end'

        data = imgfile.read(size)
        assert len(data) == size, '\tbad data'
        (tagbm,sizebm,null) = struct.unpack('<HQ%ds'%(size-10), data)
        assert tagbm == 0x4D42, '\tnot BMP'
        sys.stdout.write('\t\t, bmp_size: %x\n' % sizebm)
        assert sizebm <= size, '\tsize not match'

        outname = '%s.bmp' %name
        outfile = open(outname, 'wb')
        outfile.write(data)
        outfile.close()
        if end != 0:
            imgfile.seek(end, 0)

    imgfile.close()

def repack_mali_logo(img=None):
    if img is None:
        sys.stderr.write('arguments: [img file]\n')
        return
    sys.stderr.write('img file: %s\n' % img)

    #open file
    imgfile = open(img, 'wb')

    paddingsize = lambda x: ((~x + 1) & (0x10 - 1))
    padding = lambda x: struct.pack('%ds' % paddingsize(x), '')

    total = 8
    files = ['poweron.bmp',
             'battery1.bmp',
             'battery0.bmp',
             'battery2.bmp',
             'batteryfull.bmp',
             'bootup.bmp',
             'batterylow.bmp',
             'battery3.bmp',]
    files = ['poweron.bmp',
             'bootup.bmp',
             'batteryfull.bmp',
             'batterylow.bmp',
             'battery0.bmp',
             'battery1.bmp',
             'battery2.bmp',
             'battery3.bmp',]
    id = 0
    offstart = 0x0
    endoff = 0

    while id<total:
        sys.stdout.write('Processing bmp file(%d/%d): %s\n' % (id+1,total,files[id]))
        bmp = open(files[id], 'rb')
        bmpdata = bmp.read()
        bmp.close()
        bmpsize = len(bmpdata)

        if id+1 == total:
            endoff = 0
        else:
            endoff = offstart + 0x40 + bmpsize + paddingsize(bmpsize)

        head = struct.pack('<QIQQBBH32s', 0x27051956,
            bmpsize, offstart + 0x40, endoff,
            id, total, 0,files[id].split('.')[0])

        imgfile.write(head)
        imgfile.write(bmpdata)
        imgfile.write(padding(bmpsize))
        offstart = imgfile.tell()
        id += 1
    imgfile.close()

def remove_head(img, out=None):
    sys.stderr.write('arguments: img [out]\n')
    sys.stderr.write('img file: %s\n' % img)
    if out is None:
        out = 'removed_%s' % os.path.basename(img)
    sys.stderr.write('out file: %s\n' % out)
    outinfo = '%s_info.txt' % out
    sys.stderr.write('outinfo file: %s\n' % out)
    #open file
    imgfile = open(img, 'rb')
    outfile = open(out, 'wb')
    outinfofile = open(outinfo, 'w')

    if check_mtk_head(imgfile, outinfofile):
        while True:
            data = imgfile.read(65536)
            if not data:
                break
            outfile.write(data)
    else:
        assert False, 'Unsupported mode.'

    imgfile.close()
    outfile.close()
    outinfofile.close()

def check_mtk_head(imgfile, outinfofile):
    #备份原地址
    offset = imgfile.tell()

    #check for magic
    data = imgfile.read(0x4)
    #assert len(data) == 0x4, 'bad imgfile'
    if len(data) != 0x4:
        return False
    (tag,) = struct.unpack('<I', data)

    if tag == 0x58881688:
        sys.stderr.write('Found mtk magic, skip header.\n')
        data = imgfile.read(0x4)
        (size1,) = struct.unpack('<I', data)
        assert len(data) == 0x4, 'bad imgfile'
        imgfile.seek(0, 2)
        size2 = imgfile.tell() - 0x200
        assert size1 == size2, 'Incomplete or wrong file'
        imgfile.seek(0x8, 0)
        data = imgfile.read(0x20)
        assert len(data) == 0x20, 'bad imgfile'
        (name,) = struct.unpack('32s', data)
        sys.stderr.write('Found header name %s\n' % name)
        outinfofile.write('mode:mtk\n')
        outinfofile.write('mtk_header_name:%s\n' % name.decode('latin').strip('\x00'))
        imgfile.seek(0x200, 0)
        return True
    else:
        #assert False, 'Unsupported mode.'
        imgfile.seek(offset, 0)
        return False

def add_head(img, out=None, mode=None, name=None):
    sys.stderr.write('arguments: img [out [mode [name]]]\n')
    sys.stderr.write('mode can be \'auto\' if you want to skip it.\n')
    sys.stderr.write('img file: %s\n' % img)
    imginfo = '%s_info.txt' % img
    sys.stderr.write('imginfo file: %s\n' % imginfo)
    if out is None:
        out = 'added_%s' % os.path.basename(img)
    sys.stderr.write('out file: %s\n' % out)
    #open file
    imgfile = open(img, 'rb')
    imginfofile = open(imginfo, 'r')
    outfile = open(out, 'wb')

    if try_add_head(imgfile, outfile, imginfofile, mode, name):
        while True:
            data = imgfile.read(65536)
            if not data:
                break
            outfile.write(data)
    else:
        assert False, 'Unsupported mode.'
    imgfile.close()
    imginfofile.close()
    outfile.close()

def try_add_head(imgfile, outfile, imginfofile, mode=None, name=None):
    off2 = imginfofile.tell()
    imginfofile.seek(0, 0)
    if mode == 'auto':
        mode = None
    if mode is None:
        for line in imginfofile.readlines():
            lines = line.split(':')
            if len(lines) < 1 or lines[0][0] == '#':
                continue;
            if lines[0].strip() == 'mode':
                mode = lines[1].strip()
                break

    if mode == 'mtk':
        sys.stderr.write('mtk mode\n')
        magic = 0x58881688
        off1 = imgfile.tell()
        imgfile.seek(0, 2)
        size = imgfile.tell()
        name = ''
        off2 = imginfofile.tell()
        imginfofile.seek(0, 0)
        for line in imginfofile.readlines():
            lines = line.split(':')
            if len(lines) < 1 or lines[0][0] == '#':
                continue;
            if lines[0].strip() == 'mtk_header_name':
                name = lines[1].strip()
                break;
        data = struct.pack('<II32s472s', magic, size, name, ''.ljust(472,'\xff'))
        outfile.write(data)

        imgfile.seek(off1, 0)
        imginfofile.seek(off2, 0)
        return True
    else:
        #assert False, 'Unsupported mode.'
        return False

def unpack_ramdisk(ramdisk=None, directory=None):
    if ramdisk is None:
        if os.path.exists('ramdisk.gz'):
            ramdisk = 'ramdisk.gz'
        elif os.path.exists('ramdisk'):
            ramdisk = 'ramdisk'
        elif os.path.exists('ramdisk.cpio.gz'):
            ramdisk = 'ramdisk.cpio.gz'
        else:
            ramdisk = 'ramdisk.gz'

    if directory is None:
        directory = 'initrd'

    sys.stderr.write('arguments: [ramdisk file] [directory]\n')
    sys.stderr.write('ramdisk file: %s\n' % ramdisk)
    sys.stderr.write('directory: %s\n' % directory)
    sys.stderr.write('output: cpiolist.txt\n')

    if os.path.lexists(directory):
        raise SystemExit('please remove %s' % directory)

    tmp = open(ramdisk, 'rb')
    cpiolist = open('cpiolist.txt', 'w')
    check_mtk_head(tmp, cpiolist)
    pos = tmp.tell()

    compress_level = 0
    magic = tmp.read(6)
    if magic[:3] == struct.pack('3B', 0x1f, 0x8b, 0x08):
        tmp.seek(pos, 0)
        compress_level = 6
        cpio = CPIOGZIP(None, 'rb', compress_level, tmp)
    elif magic.decode('latin') == '070701':
        tmp.seek(pos, 0)
        cpio = tmp
    else:
        tmp.close()
        raise IOError('invalid ramdisk')

    cpiolist.write('compress_level:%d\n' % compress_level)
    sys.stderr.write('compress: %s\n' % (compress_level > 0))
    parse_cpio(cpio, directory, cpiolist)


def repack_ramdisk(cpiolist=None):
    if cpiolist is None:
        cpiolist = 'cpiolist.txt'

    sys.stderr.write('arguments: [cpiolist file]\n')
    sys.stderr.write('cpiolist file: %s\n' % cpiolist)
    sys.stderr.write('output: ramdisk.cpio.gz\n')

    tmp = open('ramdisk.cpio.gz.tmp', 'wb')
    out = open('ramdisk.cpio.gz', 'wb')
    cpiogz = tmp
    
    info = open(cpiolist, 'r')
    compress_level = 6
    
    off2 = info.tell()
    info.seek(0, 0)
    for line in info.readlines():
        lines = line.split(':')
        if len(lines) < 1 or lines[0][0] == '#':
            continue;
        if lines[0].strip() == 'compress_level':
            compress_level = int(lines[1], 10)
            break
    info.seek(off2, 0)

    if compress_level <= 0:
        cpiogz = tmp
    else:
        if compress_level > 9:
            compress_level = 9
        cpiogz = CPIOGZIP(None, 'wb', compress_level, tmp)
    sys.stderr.write('compress_level: %d\n' % compress_level)
    write_cpio(info, cpiogz)
    #cpiogz.close()
    tmp.close()
    #info.close()

    tmp = open('ramdisk.cpio.gz.tmp', 'rb')
    info = open(cpiolist, 'r')
    if try_add_head(tmp, out, info):
        while True:
            data = tmp.read(65536)
            if not data:
                break
            out.write(data)
        tmp.close()
        out.close()
        os.remove('ramdisk.cpio.gz.tmp')
    else:
        tmp.close()
        out.close()
        os.remove('ramdisk.cpio.gz')
        os.rename('ramdisk.cpio.gz.tmp', 'ramdisk.cpio.gz')
    info.close()

def unpack_yaffs(image=None, directory=None):
    if image is None:
        image = 'userdata.img'
    if directory is None and image[-4:] == '.img':
        directory = image[:-4]

    sys.stderr.write('arguments: [yaffs2 image] [directory]\n')
    sys.stderr.write('yaffs2 image: %s\n' % image)
    sys.stderr.write('directory: %s\n' % directory)

    if os.path.lexists(directory):
        raise SystemExit('please remove %s' % directory)

    parse_yaffs2(open(image, 'rb'), directory)

SIZE = {320*480: (320, 480),        # HVGA
        240*320: (240, 320),        # QVGA
        240*400: (240, 400),        # WQVGA400
        240*432: (240, 432),        # WQVGA432
        480*800: (480, 800),        # WVGA800
        480*854: (480, 854),        # WVGA854
        }
def unpack_rle_565(rlefile, rawfile, function):
    if rawfile is None:
        if rlefile[-4] == '.':
            rawfile = rlefile[:-4] + '.raw'
        else:
            rawfile = rlefile + '.raw'

    if rawfile[-4] == '.':
        pngfile = rawfile[:-4] + '.png'
    else:
        pngfile = rawfile + '.png'

    sys.stderr.write('output: %s [%s]\n' % (rawfile, pngfile))

    rle = open(rlefile, 'rb')
    raw = open(rawfile, 'wb')
    total = function(rle, raw)

    try: import Image
    except ImportError: return

    size = SIZE.get(total)
    if size is None: return

    data = open(rawfile, 'rb')
    Image.fromstring('RGB',  size, data.read(), 'raw').save(pngfile)
    data.close()

def unpack_rle(rlefile=None, rawfile=None):
    if rlefile is None:
        rlefile = 'initlogo.rle'
    sys.stderr.write('arguments: [rle file] [raw file]\n')
    sys.stderr.write('rle file: %s\n' % (rlefile))
    unpack_rle_565(rlefile, rawfile, parse_rle)

def unpack_565(rlefile=None, rawfile=None):
    if rlefile is None:
        rlefile = 'splash.565'
    sys.stderr.write('arguments: [565 file] [raw file]\n')
    sys.stderr.write('565 file: %s\n' % (rlefile))
    unpack_rle_565(rlefile, rawfile, parse_565)

def repack_rle_565(rawfile, rlefile, function):

    if rawfile[-4:] != '.raw':
        try: import Image
        except ImportError:
            sys.stderr.write('Please Install PIL (python-imaging)\n')
            return None
        try:
            img = Image.open(rawfile)
        except:
            sys.stderr.write('Cannot Open Image File')
            return None

        from JpegImagePlugin import RAWMODE
        if 'transparency' in img.info or img.mode == 'RGBA':
            new = img.mode == 'RGBA' and img or img.convert('RGBA')
            img = Image.new('RGB', new.size)
            img.paste(new, (0, 0), new)
        elif img.mode not in RAWMODE:
            img = img.convert('RGB')

        if img.size not in list(SIZE.values()):
            sys.stderr.write('warning: Image is not HVGA, [W]QVGA, WVGA\n')

        rawfile = rlefile[:-4] + '.raw'
        data = open(rawfile, 'wb')
        data.write(img.tostring())
        data.close()

    raw = open(rawfile, 'rb')
    rle = open(rlefile, 'wb')
    function(raw, rle)

def repack_rle(rawfile=None, rlefile=None):
    if rawfile is None:
        rawfile = 'initlogo.raw'

    if rlefile is None:
        if rawfile[-4] == '.':
            rlefile = rawfile[:-4] + '.rle'
        else:
            rlefile = rawfile + '.rle'

    sys.stderr.write('arguments: [raw file] [rle file]\n')
    sys.stderr.write('raw file: %s\n' % rawfile)
    sys.stderr.write('rle file: %s\n' % rlefile)
    repack_rle_565(rawfile, rlefile, write_rle)

def repack_565(rawfile=None, rlefile=None):
    if rawfile is None:
        rawfile = 'splash.raw'

    if rlefile is None:
        if rawfile[-4] == '.':
            rlefile = rawfile[:-4] + '.565'
        else:
            rlefile = rawfile + '.565'

    sys.stderr.write('arguments: [raw file] [565 file]\n')
    sys.stderr.write('raw file: %s\n' % rawfile)
    sys.stderr.write('565 file: %s\n' % rlefile)
    repack_rle_565(rawfile, rlefile, write_565)

def showVersion():
    sys.stderr.write('bootimg:\n')
    sys.stderr.write('\tUpdate Date:20210717\n')
    sys.stderr.write('\tModified:github.com/keowu\n')

def printErr(s):
    import sys
    type = sys.getfilesystemencoding()
    sys.stderr.write(s.decode('utf-8').encode(type))


if __name__ == '__main__':

    functions = {
                 '--unpack-updata': unpack_updata,
                 '--unpack-zte-bin': unpack_zte_bin,
                 '--unpack-qsb': unpack_qsb,
                 '--unpack-bootimg': unpack_bootimg,
                 '--remove-head': remove_head,
				 '--unpack-ramdisk': unpack_ramdisk,
                 '--unpack-yaffs': unpack_yaffs,
                 '--unpack-yaffs2': unpack_yaffs,
                 '--unpack-yafffs': unpack_yaffs,
                 '--unpack-rle': unpack_rle,
                 '--unpack-565': unpack_565,
                 '--to-ext4': to_ext4,
                 '--to-img': to_img,
                 '--dzlib': test_dzlib,
                 '--czlib': test_czlib,
                 '--dml': dcompress_mtk_logo,
                 '--cml': compress_mtk_logo,
                 '--uml': unpack_mali_logo,
                 '--rml': repack_mali_logo,
                 '--repack-zte-bin': repack_zte_bin,
                 '--repack-ramdisk': repack_ramdisk,
                 '--repack-bootimg': repack_bootimg,
                 '--add-head': add_head,
                 '--repack-rle': repack_rle,
                 '--repack-565': repack_565,
                 '--cpio-list': cpio_list,
                }

    def usage():
        showVersion()
        sys.stderr.write('supported arguments:')
        sys.stderr.write('\n\t')
        sys.stderr.write('\n\t'.join(sorted(functions.keys())))
        sys.stderr.write('\n')
        raise SystemExit(1)

    if len(sys.argv) == 1:
        usage()

    sys.argv.pop(0)
    cmd = sys.argv[0]
    function = functions.get(cmd, None)
    sys.argv.pop(0)
    if not function:
        usage()
    function(*sys.argv)

# vim: set sta sw=4 et:

 
