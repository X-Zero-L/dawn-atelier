"""Decode TextAsset payloads: RSA public-key recovery of first block, then two XOR passes."""
from pathlib import Path
import base64
from cryptography.hazmat.primitives.serialization import load_der_public_key
from decode_bundles import literal_va
from app_config import DATA_ROOT


def public_numbers():
    return load_der_public_key(base64.b64decode(literal_va(0x182f5eb88))).public_numbers()


def decode_table(raw, key):
    if len(raw) < 128:
        raise ValueError('Truncated encrypted table')
    ciphertext = int.from_bytes(raw[:128], 'big')
    if ciphertext >= key.n:
        raise ValueError('Invalid RSA ciphertext')
    block = pow(ciphertext, key.e, key.n).to_bytes(128, 'big')
    if block[:2] != b'\0\1':
        raise ValueError('Invalid RSA PKCS#1 type-1 block')
    separator = block.index(0, 2)
    if separator < 10 or any(byte != 255 for byte in block[2:separator]):
        raise ValueError('Invalid RSA block padding')
    out = bytearray(block[separator + 1:] + raw[128:])
    index, step = 1, 0
    while index < len(out):
        out[index] ^= (index - step) & 255
        index *= 2
        step += 1
    index, step = len(out) - 1, 0
    while index > 0:
        out[index] ^= (index - step) & 255
        index //= 2
        step += 1
    return bytes(out)


if __name__ == '__main__':
    root = DATA_ROOT / 'bundles'
    destination = root / 'tables-decoded'
    destination.mkdir(parents=True, exist_ok=True)
    key = public_numbers()
    inputs = sorted((root / 'tables').glob('*.bytes'))
    for path in inputs:
        (destination / path.name).write_bytes(decode_table(path.read_bytes(), key))
    print(f'Decoded {len(inputs)} table payloads')
