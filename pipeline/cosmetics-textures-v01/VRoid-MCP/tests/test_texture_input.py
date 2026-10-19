"""Native writes must never receive an unsafe or changed texture input."""
import hashlib,struct,zlib
import pytest
from vroid_mcp.texture_input import read_texture_input

def png(width=1,height=1):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\0\0\xff'))+chunk(b'IEND',b'')

@pytest.fixture
def source(tmp_path):
    (tmp_path/'saves').mkdir();data=png();(tmp_path/'saves/input.png').write_bytes(data)
    return tmp_path,data,hashlib.sha256(data).hexdigest()

def test_valid_input_reads_exact_bytes(source):
    lab,data,sha=source;assert read_texture_input(lab,'input.png',sha,'Face overlay')==(data,1,1)

@pytest.mark.parametrize('filename',['../input.png','C:/input.png','input.png:stream','input.png ','input\n.png','bad?.png'])
def test_unsafe_names_rejected(source,filename):
    lab,_,sha=source
    with pytest.raises(ValueError):read_texture_input(lab,filename,sha,'overlay')

def test_changed_file_rejected(source):
    lab,_,sha=source;(lab/'saves/input.png').write_bytes(png(2,1))
    with pytest.raises(ValueError,match='hash changed'):read_texture_input(lab,'input.png',sha,'overlay')

@pytest.mark.parametrize('width,height',[(0,1),(1,0),(4097,1),(2049,2048)])
def test_image_size_boundaries_rejected(source,width,height):
    lab,_,_=source;data=png(width,height);(lab/'saves/input.png').write_bytes(data)
    with pytest.raises(ValueError,match='size exceeds'):read_texture_input(lab,'input.png',hashlib.sha256(data).hexdigest(),'overlay')

@pytest.mark.parametrize('name',['','x'*81])
def test_bad_layer_names_rejected(source,name):
    lab,_,sha=source
    with pytest.raises(ValueError,match='Layer name'):read_texture_input(lab,'input.png',sha,name)

def test_truncated_png_rejected(source):
    lab,_,_=source;data=b'\x89PNG\r\n\x1a\n';(lab/'saves/input.png').write_bytes(data)
    with pytest.raises(ValueError,match='complete IHDR'):read_texture_input(lab,'input.png',hashlib.sha256(data).hexdigest(),'overlay')
