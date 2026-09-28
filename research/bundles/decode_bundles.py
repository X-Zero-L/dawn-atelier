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
from dump_currency import meta, pe, H, readva, fields, name, s

# Compiler-generated field identities are content hashes. Locate their actual
# initialized bytes in the installed metadata instead of relying on reference
# indexes that move when unrelated game code is added.
FRAGMENT_FIELDS = [
    'C839497618D62DB08FDA9C8D8E48A529FE5664236F0CBB4D8CF10C9C97A14CD8',
    'C59B442A3C14F6A197F0EA0AED407378FFAAAE2171778679BDE6F90844727A6E',
    'C77E1D3BCDF2AE8FC778DA3BFDB8A55143DDC5B8DFA87AEC8EE4318899F19EF6',
    'B12C107FE972523B8558F89F16346ED293DE545CEA38546314A4EB14DBC5521F',
    '716684ADEC32484729E57AB66012FC0CF15BA53489B4A06734B6DAC25532DE38',
    '8853429741E1CAF2D114D120A6A1862F312B83244AF0F7C26C02848C8B7FA357',
    'BF8139486D6839EDA661D84FD76E32CCD231CDC6B9CD0B12D4AF3B709EB9E3E9',
    '9F14BCCB3A0F990417209CC8D319ADC22629F8BE06277450F66EFAF37A58AB40',
]
PERMUTATION_FIELD = '1E6DA613753287DC062AF148289470D936A3CB4B606FF0BAB5A2A26B2A5810F7'


def literal_va(va):
    encoded = readva(va, '<Q')[0]
    if encoded >> 29 != 5:
        raise ValueError('Expected an IL2CPP string literal reference')
    index = (encoded >> 1) & 0x0fffffff
    size, offset = struct.unpack_from('<II', meta, H[0][0] + index * 8)
    return meta[H[1][0] + offset:H[1][0] + offset + size]


def literals():
    for size, offset in struct.iter_unpack('<II', meta[H[0][0]:sum(H[0])]):
        if offset + size > H[1][1]:
            raise ValueError('String literal exceeds the metadata table.')
        yield meta[H[1][0] + offset:H[1][0] + offset + size]


def unique_literal(predicate):
    found = set(value for value in literals() if predicate(value))
    if len(found) != 1:
        raise ValueError('Could not uniquely identify the required game resource constant.')
    return found.pop()


def recover_constants():
    defaults = {struct.unpack_from('<i', meta, H[7][0] + j)[0]:
                struct.unpack_from('<3i', meta, H[7][0] + j)[1:]
                for j in range(0, H[7][1], 12)}

    wanted = set(FRAGMENT_FIELDS + [PERMUTATION_FIELD])
    constants = {}
    for index in range(H[19][1] // 88):
        if name(index) != '<PrivateImplementationDetails>':
            continue
        for field in fields(index):
            field_name = s(field[1])
            if field_name not in wanted or field[0] not in defaults:
                continue
            _, offset = defaults[field[0]]
            size = 16 if field_name == PERMUTATION_FIELD else 8
            if offset < 0 or offset + size > H[8][1]:
                raise ValueError('Resource constant exceeds the metadata table.')
            value = meta[H[8][0] + offset:H[8][0] + offset + size]
            if hashlib.sha256(value).hexdigest().upper() != field_name:
                raise ValueError('Resource constant identity does not match its bytes.')
            constants[field_name] = value
    if set(constants) != wanted:
        raise ValueError('Resource key configuration changed; this build needs a decoder update.')
    fragments = [constants[field_name] for field_name in FRAGMENT_FIELDS]
    permutation = struct.unpack('<4i', constants[PERMUTATION_FIELD])
    if sorted(permutation) != [0, 1, 2, 3]:
        raise ValueError('Unexpected bundle seed permutation; build may have changed')
    seed = b''.join(bytes(a ^ b for a, b in zip(fragments[i * 2], fragments[i * 2 + 1]))
                    for i in permutation)
    master = hashlib.sha256(seed).digest()
    key_prefix = unique_literal(lambda value: value == b'bundle-key|')
    iv_prefix = unique_literal(lambda value: value == b'bundle-iv|')
    if (key_prefix, iv_prefix) != (b'bundle-key|', b'bundle-iv|'):
        raise ValueError('Unexpected bundle key derivation; build may have changed')
    return master, {'master_fingerprint': hashlib.sha256(master).hexdigest(), 'fragment_field_names': FRAGMENT_FIELDS,
                    'permutation': list(permutation),
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
