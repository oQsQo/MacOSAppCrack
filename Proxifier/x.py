#!/usr/bin/env python3
"""
Proxifier for Mac v3.x Registration Key Generator
Reverse engineered from Proxifier.app 3.15.0 (com.initex.proxifier.v3.macos)

Key format: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
Algorithm:  Base32 (little-endian) + XOR stream cipher + CRC-32 checksum

Registration Name (Owner) is NOT cryptographically bound to the key.
Use any name with English letters only.
"""

# ============================================================
# Registration Parameters (modify as needed)
# ============================================================

# Product type: 2 = Mac
PRODUCT_TYPE = 2

# Edition: 0 = Standard
EDITION = 0

# Version code: must be >= 300 (v3.0) for v3.x keys to work
# 300 = v3.0, 315 = v3.15, etc.
VERSION_CODE = 315

# Sub-version: 0-31 (not validated, informational only)
SUB_VERSION = 31

# Expiration: 0 = permanent license (no expiration)
# Set to a value > 0xFFFF for a time-limited license
EXPIRATION = 0

# Segment C: not validated by the application, set to 0
SEGMENT_C = 0

# ============================================================
# Internal Constants (extracted from binary, do not modify)
# ============================================================

XOR_SALT_A = 0x12345678       # Segment A XOR salt
XOR_SALT_B = 0x87654321       # Segment B XOR salt
CRC32_POLY = 0x04C11DB7       # CRC-32 polynomial
CRC32_INIT = 0xFFFFFFFF       # CRC-32 initial value
CRC_MASK   = 0x01FFFFFF       # 25-bit checksum mask

# Base32 alphabet: value 0-31 -> character
# 0-9 = '0'-'9', 10-31 = 'A'-'V'
# (W,X,Y,Z are normalized to 0,O,1,I during decode)
B32_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUV"


# ============================================================
# Core Functions
# ============================================================

def base32_encode(value: int, num_chars: int) -> str:
    """
    Encode an integer to a little-endian Base32 string.
    The first character holds the least significant 5 bits.
    """
    result = []
    for i in range(num_chars):
        result.append(B32_ALPHABET[(value >> (5 * i)) & 0x1F])
    return "".join(result)


def base32_decode(s: str) -> int:
    """
    Decode a little-endian Base32 string to an integer.
    Reads from the last character to the first (matching the binary).
    """
    result = 0
    for ch in reversed(s):
        ch = ch.upper()
        v = ord(ch)
        # Normalize ambiguous characters
        if ch == 'W':
            v = ord('0')
        elif ch == 'X':
            v = ord('O')
        elif ch == 'Y':
            v = ord('1')
        elif ch == 'Z':
            v = ord('I')
        # Compute value
        if 0x30 <= v <= 0x39:        # '0'-'9'
            val = v - 0x30           # 0-9
        elif 0x41 <= v <= 0x5A:     # 'A'-'Z' (after normalization, only A-V remain)
            val = v - 0x37           # 10-31
        else:
            val = 0
        result = (result << 5) | val
    return result & 0xFFFFFFFF


def crc32_custom(data: bytes) -> int:
    """
    Compute CRC-32 with polynomial 0x04C11DB7.
    This is the standard CRC-32 (no final XOR).
    """
    crc = CRC32_INIT
    for byte in data:
        crc ^= (byte << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ CRC32_POLY) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


# ============================================================
# Key Generation
# ============================================================

def generate_key() -> str:
    """Generate a Proxifier registration key."""

    # --- Step 1: Construct plaintext data fields ---
    # decrypted_A bit layout (32 bits):
    #   bits 21-31: product type (2 = Mac)
    #   bits 16-20: edition (0 = Standard)
    #   bits  5-15: version code (>= 300 for v3.x)
    #   bits  0-4:  sub-version (not checked)
    decrypted_a = (
        (PRODUCT_TYPE << 21) |
        (EDITION << 16) |
        (VERSION_CODE << 5) |
        SUB_VERSION
    ) & 0xFFFFFFFF

    # decrypted_B: 0 (or any value <= 0xFFFF) = permanent license
    decrypted_b = EXPIRATION & 0xFFFFFFFF

    # Segment C: not encrypted, not validated
    segment_c = SEGMENT_C & 0xFFFFFFFF

    # --- Step 2: Compute CRC-32 checksum ---
    # CRC over 12 bytes: decrypted_A (LE) + decrypted_B (LE) + segment_C (LE)
    data = (
        decrypted_a.to_bytes(4, "little") +
        decrypted_b.to_bytes(4, "little") +
        segment_c.to_bytes(4, "little")
    )
    crc = crc32_custom(data)
    checksum = crc & CRC_MASK  # 25-bit checksum

    # --- Step 3: Derive XOR key stream from checksum ---
    key_stream = ((checksum << 7) ^ checksum) & 0xFFFFFFFF

    # --- Step 4: Encrypt segments A and B ---
    segment_a = (decrypted_a ^ key_stream ^ XOR_SALT_A) & 0xFFFFFFFF
    segment_b = (decrypted_b ^ key_stream ^ XOR_SALT_B) & 0xFFFFFFFF
    # segment_c is not encrypted

    # --- Step 5: Base32 encode each segment ---
    chars = [""] * 25

    # Segment A -> positions 0-6  (7 chars)
    sa = base32_encode(segment_a, 7)
    for i in range(7):
        chars[i] = sa[i]

    # Segment B -> positions 7-13 (7 chars)
    sb = base32_encode(segment_b, 7)
    for i in range(7):
        chars[7 + i] = sb[i]

    # Position 14 = copy of position 2
    # (validation copies char[14] -> char[2], so they must match)
    chars[14] = chars[2]

    # Segment C -> positions 15-19 (5 chars)
    sc = base32_encode(segment_c, 5)
    for i in range(5):
        chars[15 + i] = sc[i]

    # Segment D (checksum) -> positions 20-24 (5 chars)
    sd = base32_encode(checksum, 5)
    for i in range(5):
        chars[20 + i] = sd[i]

    # --- Step 6: Format key with dashes ---
    raw = "".join(chars)
    key = f"{raw[0:5]}-{raw[5:10]}-{raw[10:15]}-{raw[15:20]}-{raw[20:25]}"
    return key


# ============================================================
# Key Verification (simulates the binary's validation logic)
# ============================================================

def verify_key(key: str) -> bool:
    """Verify a registration key by simulating the validation logic."""

    # Remove dashes
    raw = key.replace("-", "").upper()
    if len(raw) != 25:
        print("  Error: Key must be 25 characters (excluding dashes)")
        return False

    # Copy position 14 to position 2 (matches binary behavior)
    chars = list(raw)
    chars[2] = chars[14]
    raw = "".join(chars)

    # Decode 4 segments
    seg_a = base32_decode(raw[0:7])
    seg_b = base32_decode(raw[7:14])
    seg_c = base32_decode(raw[15:20])
    seg_d = base32_decode(raw[20:25])

    # Derive key stream from checksum
    key_stream = ((seg_d << 7) ^ seg_d) & 0xFFFFFFFF

    # Decrypt segments A and B
    dec_a = (seg_a ^ key_stream ^ XOR_SALT_A) & 0xFFFFFFFF
    dec_b = (seg_b ^ key_stream ^ XOR_SALT_B) & 0xFFFFFFFF

    # Verify CRC-32
    data = (
        dec_a.to_bytes(4, "little") +
        dec_b.to_bytes(4, "little") +
        seg_c.to_bytes(4, "little")
    )
    crc = crc32_custom(data) & CRC_MASK

    if crc != seg_d:
        print("  Error: CRC-32 checksum mismatch")
        return False

    # Extract and display fields
    product  = dec_a >> 21
    edition  = (dec_a >> 16) & 0x1F
    ver_code = (dec_a >> 5) & 0x7FF
    sub_ver  = dec_a & 0x1F

    print(f"  Product type:  {product} ({'Mac' if product == 2 else 'Unknown'})")
    print(f"  Edition:       {edition}")
    print(f"  Version code:  {ver_code} (v{ver_code // 100}.{ver_code % 100})")
    print(f"  Sub-version:   {sub_ver}")

    if dec_b <= 0xFFFF:
        print(f"  Expiration:    Permanent")
    else:
        year  = dec_b // 3 + 2000
        month = (dec_b >> 16) % 12
        print(f"  Expiration:    {year}-{month + 1:02d}")

    print(f"  CRC checksum:  0x{seg_d:07X}")
    print(f"  CRC valid:     True")

    # Validate against expected values
    if product != 2:
        print(f"  FAIL: Product type mismatch (expected 2, got {product})")
        return False
    if edition != 0:
        print(f"  FAIL: Edition mismatch (expected 0, got {edition})")
        return False
    if ver_code < 300:
        print(f"  FAIL: Version too old (need >= 300, got {ver_code})")
        return False

    return True


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    key = generate_key()

    print("=" * 55)
    print("  Proxifier for Mac v3.x Registration Key Generator")
    print("=" * 55)

    print(f"\n  Registration Key: {key}")

    print(f"\n  --- Parameters ---")
    print(f"  Product:        Proxifier for Mac")
    print(f"  Version:        v{VERSION_CODE // 100}.{VERSION_CODE % 100}")
    print(f"  License type:   {'Permanent' if EXPIRATION <= 0xFFFF else 'Limited'}")

    print(f"\n  --- Verification ---")
    ok = verify_key(key)
    print(f"\n  Result:         {'VALID' if ok else 'INVALID'}")

    print(f"\n  --- Note ---")
    print(f"  Registration Name is NOT bound to the key.")
    print(f"  Use any name with English letters only (a-z, A-Z).")
    print(f"  Enter via: Proxifier -> Enter Registration Key...")
    print("=" * 55)
