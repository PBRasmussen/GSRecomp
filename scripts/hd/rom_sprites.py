"""Reads field sprites from a Golden Sun (USA/Europe) ROM.

The frame decoder follows decode() in shared_game/djinn_tracker.h.
"""
import hashlib, pathlib, sys

SHA1 = "5c4695205413df7db52b9a184815a07783999971"
RECORDS = 0x185024   # 20-byte sprite records
PALETTE = 0x00779C   # object palette
BASE = 0x08000000
CODEC = 3
MAX_SPRITES = 512    # IDs tried; the table stores no length


def u8(rom, at):
    return rom[at] if 0 <= at < len(rom) else 0


def u16(rom, at):
    return u8(rom, at) | u8(rom, at + 1) << 8


def u32(rom, at):
    return u16(rom, at) | u16(rom, at + 2) << 16


def is_pointer(rom, value):
    return BASE <= value < BASE + len(rom)


def decode_frame(rom, at, width, height):
    """Return width*height palette indices (0 = clear)."""
    limit = width * height * 4
    base = at + 2
    stream = bytearray()
    control_offset = u16(rom, at)
    if control_offset == 0:
        i = base
        while i < len(rom) and len(stream) < limit:
            stream.append(rom[i])
            if not rom[i]:
                break
            i += 1
    else:
        control, literal = at + control_offset, base
        flags = u8(rom, control) | 0x100
        control += 1
        while True:
            if flags == 1:
                flags = u8(rom, control) | 0x100
                control += 1
            is_literal = flags & 1
            flags >>= 1
            if len(stream) > limit:
                raise ValueError("unpacked data is too long")
            if is_literal:
                stream.append(u8(rom, literal))
                literal += 1
                continue
            word = u8(rom, control) << 8 | u8(rom, control + 1)
            control += 2
            if not word:
                break
            count = word >> 12
            if not count:
                count = u8(rom, control) + 0x10
                control += 1
            count += 2
            distance = word & 0xFFF
            if distance > base:
                raise ValueError("bad copy distance")
            for k in range(count):
                stream.append(u8(rom, base - distance + k))

    pixels = bytearray(width * height)
    p = 0
    for b in stream:
        if not b or p >= len(pixels):
            break
        if b > 0xDF:
            p += b - 0xDF
            continue
        pixels[p] = b
        p += 1
    return bytes(pixels)


def colour(rom, index):
    c = u16(rom, PALETTE + index * 2)
    return bytes([*((v << 3 | v >> 2) for v in (c & 31, c >> 5 & 31, c >> 10 & 31)), 255])


def find_rom(explicit):
    if explicit:
        paths = [pathlib.Path(explicit)]
    else:
        paths = sorted(p for p in pathlib.Path("ROMs").rglob("*") if p.is_file())
    for path in paths:
        data = path.read_bytes()
        if hashlib.sha1(data).hexdigest() == SHA1:
            return path, data
    sys.exit("No matching Broken Seal (USA/Europe) ROM found. Looked at: " +
             (", ".join(map(str, paths)) or "nothing in ROMs/") +
             ". Zipped ROMs must be extracted first.")


def sprite_info(rom, sprite):
    """(width, height, frame table address), or None if unsupported."""
    record = RECORDS + sprite * 20
    width, height = u8(rom, record), u8(rom, record + 1)
    frames = u32(rom, record + 0xC)
    if (u8(rom, record + 0xA) != CODEC or not 8 <= width <= 64 or not 8 <= height <= 64
            or frames & 3 or not is_pointer(rom, frames)):
        return None
    return width, height, frames


def sprite_frames(rom, sprite):
    """(width, height, {frame number: palette indices}) for a supported sprite."""
    info = sprite_info(rom, sprite)
    if not info:
        return 0, 0, {}
    width, height, table = info
    # The table has no stored length: stop at the next sprite's table.
    others = (sprite_info(rom, i) for i in range(MAX_SPRITES))
    end = min((o[2] for o in others if o and o[2] > table), default=table + 256 * 4)
    decoded = {}
    for i in range(min((end - table) // 4, 256)):
        pointer = u32(rom, table - BASE + i * 4)
        if not is_pointer(rom, pointer):
            break
        try:
            pixels = decode_frame(rom, pointer - BASE, width, height)
        except ValueError:
            continue
        if any(pixels):
            decoded[i] = pixels
    return width, height, decoded
