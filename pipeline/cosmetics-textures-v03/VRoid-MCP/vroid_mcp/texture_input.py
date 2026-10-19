"""Validate texture inputs fully before any native layer mutation."""
import hashlib
import struct

def read_texture_input(lab,filename,expected_sha256,layer_name):
    if (not isinstance(filename,str) or not filename.lower().endswith('.png')
        or any(ord(c)<32 or c in '\\/:<>"|?*' for c in filename)
        or filename.rstrip(' .')!=filename):
        raise ValueError('Use a plain PNG filename in this lab saves directory')
    target=lab.resolve()/'saves'/filename
    if not target.is_file() or target.is_symlink() or target.resolve()!=target:
        raise ValueError('PNG input must be a regular file in saves')
    if target.stat().st_size>16*1024*1024:raise ValueError('PNG input exceeds 16 MiB')
    data=target.read_bytes()
    if len(data)<33 or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':
        raise ValueError('A PNG with a complete IHDR is required')
    if hashlib.sha256(data).hexdigest()!=expected_sha256:raise ValueError('PNG input hash changed')
    width,height=struct.unpack('>II',data[16:24])
    if not 1<=width<=4096 or not 1<=height<=4096 or width*height>4194304:
        raise ValueError('PNG size exceeds validated range')
    if not isinstance(layer_name,str) or not 1<=len(layer_name)<=80:
        raise ValueError('Layer name must be 1..80 characters')
    return data,width,height
