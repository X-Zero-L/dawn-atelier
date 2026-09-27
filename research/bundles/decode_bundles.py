"""Version-scoped, offline decoder for The Piper of Dawn YooAsset bundles.

Uses existing cryptography package; recovers constants from the installed metadata.
The game and saves are always opened read-only.
"""
from pathlib import Path
import hashlib
import hmac
import struct
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dump_currency import meta, pe, H, readva, fields, ty


def literal_va(va):
    encoded = readva(va, '<Q')[0]
    if encoded >> 29 != 5:
        raise ValueError('Expected an IL2CPP string literal reference')
    index = (encoded >> 1) & 0x0fffffff
    size, offset = struct.unpack_from('<II', meta, H[0][0] + index * 8)
    return meta[H[1][0] + offset:H[1][0] + offset + size]


def recover_constants():
    defaults = {struct.unpack_from('<i', meta, H[7][0] + j)[0]:
                struct.unpack_from('<3i', meta, H[7][0] + j)[1:]
                for j in range(0, H[7][1], 12)}

    def field_bytes(index, size):
        type_index, field_index = struct.unpack_from('<2i', meta, H[22][0] + index * 8)
        definition_index = int(ty(type_index)[1], 16)
        field = fields(definition_index)[field_index]
        _, offset = defaults[field[0]]
        return meta[H[8][0] + offset:H[8][0] + offset + size]

    references = [31, 29, 30, 25, 17, 20, 28, 24]
    fragments = [field_bytes(i, 8) for i in references]
    permutation = struct.unpack('<4i', field_bytes(11, 16))
    if sorted(permutation) != [0, 1, 2, 3]:
        raise ValueError('Unexpected bundle seed permutation; build may have changed')
    seed = b''.join(bytes(a ^ b for a, b in zip(fragments[i * 2], fragments[i * 2 + 1]))
                    for i in permutation)
    master = hashlib.sha256(seed).digest()
    key_prefix = literal_va(0x182f92660)
    iv_prefix = literal_va(0x182f925a8)
    if (key_prefix, iv_prefix) != (b'bundle-key|', b'bundle-iv|'):
        raise ValueError('Unexpected bundle key derivation; build may have changed')
    return master, {'master_sha256': master.hex(), 'fragment_field_references': references,
                    'fragments_hex': [v.hex() for v in fragments], 'permutation': list(permutation),
                    'key_prefix': key_prefix.decode(), 'iv_prefix': iv_prefix.decode(),
                    'gameassembly_sha256': hashlib.sha256(pe).hexdigest(),
                    'metadata_sha256': hashlib.sha256(meta).hexdigest()}


def decode_bundle(data, bundle_name, master, offset=0):
    name = bundle_name.strip().lower().encode('utf-8')
    key = hmac.new(master, b'bundle-key|' + name, hashlib.sha256).digest()
    nonce = hmac.new(master, b'bundle-iv|' + name, hashlib.sha256).digest()[:8]
    block, skip = divmod(offset, 16)
    decryptor = Cipher(algorithms.AES(key), modes.CTR(nonce + block.to_bytes(8, 'big'))).decryptor()
    return (decryptor.update(b'\0' * skip + data) + decryptor.finalize())[skip:]
