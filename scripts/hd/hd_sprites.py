#!/usr/bin/env python3
"""4x sprite artwork for The Broken Seal (prototype). Run from the repo root.

  py scripts/hd/hd_sprites.py extract   make local/hd/base from your ROM
  py scripts/hd/hd_sprites.py pack      build local/hd/sprites.pack from local/hd/x4

Put a redrawn sheet in local/hd/x4 under the same path as its base sheet.
Any size works if the grid and proportions are unchanged. Keep the flat
magenta background. Needs Pillow:  py -m pip install pillow
Everything under local/ is ignored by git.
"""
import argparse, json, pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rom_sprites as rs

try:
    from PIL import Image, ImageChops
except ImportError:
    sys.exit("Pillow is missing. Run:  py -m pip install pillow")

HD = pathlib.Path("local") / "hd"
SCALE = 4        # replacement size
SHEET = 8        # base sheets are enlarged this much
COLUMNS, ROWS = 4, 2
MAGENTA = (255, 0, 255)
# Isaac standing, then his walk towards the camera, in animation order.
EXTRA_PAGES = {0: {"walk_front": [3, 58, 33, 38, 43, 48, 53]}}


def frame_image(rom, pixels, width, height):
    image = Image.new("RGB", (width, height), MAGENTA)
    image.putdata([tuple(rs.colour(rom, p)[:3]) if p else MAGENTA for p in pixels])
    return image


def write_page(rom, folder, name, sprite, ids, frames, width, height):
    page = Image.new("RGB", (width * COLUMNS, height * ROWS), MAGENTA)
    for n, i in enumerate(ids):
        page.paste(frame_image(rom, frames[i], width, height),
                   (n % COLUMNS * width, n // COLUMNS * height))
    page.resize((page.width * SHEET, page.height * SHEET), Image.NEAREST).save(folder / f"{name}.png")
    (folder / f"{name}.json").write_text(json.dumps(
        {"sprite": sprite, "frames": ids, "columns": COLUMNS, "rows": ROWS}))


def extract(rom, wanted):
    skipped, sprites, pages = [], 0, 0
    for sprite in wanted:
        info = rs.sprite_info(rom, sprite)
        if not info:
            skipped.append(sprite)
            continue
        width, height, frames = rs.sprite_frames(rom, sprite)
        if not frames:
            skipped.append(sprite)
            continue
        folder = HD / "base" / f"sprite_{sprite:03d}"
        folder.mkdir(parents=True, exist_ok=True)
        (HD / "x4" / folder.name).mkdir(parents=True, exist_ok=True)
        ids = sorted(frames)
        groups = {f"page_{n // (COLUMNS * ROWS):03d}": ids[n:n + COLUMNS * ROWS]
                  for n in range(0, len(ids), COLUMNS * ROWS)}
        for name, chosen in EXTRA_PAGES.get(sprite, {}).items():
            if all(i in frames for i in chosen):
                groups[name] = chosen
        for name, chosen in groups.items():
            write_page(rom, folder, name, sprite, chosen, frames, width, height)
        sprites += 1
        pages += len(groups)
        print(f"sprite {sprite:3d}: {width}x{height}, {len(frames)} frames")
    (HD / "x4").mkdir(parents=True, exist_ok=True)
    print(f"\n{sprites} sprites, {pages} sheets in {(HD / 'base').resolve()}")
    print(f"{len(skipped)} IDs skipped (empty or an unsupported format).")


def foreground(image):
    """Mask (L, 0/255) of everything that is not the magenta background."""
    r, g, b = image.split()
    high = lambda band: ImageChops.subtract(band, g).point(lambda v: 255 if v > 90 else 0)
    return ImageChops.invert(ImageChops.multiply(high(r), high(b)))


def shifted(image, dx, dy):
    out = Image.new(image.mode, image.size)
    out.paste(image, (dx, dy))
    return out


def count(mask):
    return mask.histogram()[255]


def overlap(a, b):
    union = count(ImageChops.lighter(a, b))
    return count(ImageChops.darker(a, b)) / union if union else 0.0


def grow(mask, by):
    out = mask
    for _ in range(by):
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            out = ImageChops.lighter(out, shifted(out, *d))
    return out


def convert_cell(rom, cell, original, width, height, palette):
    """One redrawn cell -> (4x palette indices, outline overlap)."""
    size = (width * SCALE, height * SCALE)
    mask = foreground(cell)
    # Average only foreground pixels, so no magenta bleeds into the edges.
    clean = Image.composite(cell, Image.new("RGB", cell.size), mask)
    cover = mask.resize(size, Image.BOX)
    total = clean.resize(size, Image.BOX)
    raw = total.tobytes()
    colours = Image.frombytes("RGB", size, bytes(
        min(255, raw[n * 3 + c] * 255 // a) if a else 0
        for n, a in enumerate(cover.tobytes()) for c in range(3)))
    solid = cover.point(lambda v: 255 if v > 127 else 0)

    shape = Image.new("L", (width, height))
    shape.putdata([255 if p else 0 for p in original])
    shape = shape.resize(size, Image.NEAREST)
    # Coarse-to-fine search for the small offset redrawn art tends to have.
    score = lambda d: (overlap(shifted(solid, *d), shape), -abs(d[0]) - abs(d[1]))
    best = max(((x, y) for x in range(-12, 13, 4) for y in range(-12, 13, 4)), key=score)
    best = max(((best[0] + x, best[1] + y) for x in range(-3, 4) for y in range(-3, 4)), key=score)
    solid, colours = shifted(solid, *best), shifted(colours, *best)
    agreement = overlap(solid, shape)

    # Fill any gap inside the original outline from the original art.
    base = Image.new("RGB", (width, height))
    base.putdata([tuple(rs.colour(rom, p)[:3]) for p in original])
    colours = Image.composite(colours, base.resize(size, Image.NEAREST), solid)
    near, far = grow(shape, 2), ImageChops.invert(grow(ImageChops.invert(shape), 2))
    keep = ImageChops.lighter(ImageChops.darker(solid, near), far)

    swatch = Image.new("P", (1, 1))
    flat = [c for i in palette for c in rs.colour(rom, i)[:3]]
    swatch.putpalette(flat + flat[:3] * (256 - len(palette)))
    chosen = colours.quantize(palette=swatch, dither=Image.Dither.NONE).tobytes()
    indices = bytes((palette[c] if c < len(palette) else palette[0]) if k else 0
                    for c, k in zip(chosen, keep.tobytes()))
    return indices, agreement


def pack(rom, minimum):
    sheets = sorted((HD / "x4").rglob("*.png"))
    if not sheets:
        sys.exit(f"No sheets in {(HD / 'x4').resolve()}")
    packed, cache = {}, {}
    # Page sheets first, so a hand-picked sheet (walk_front) wins for its frames.
    sheets.sort(key=lambda p: (not p.stem.startswith("page_"), str(p)))
    for path in sheets:
        manifest = (HD / "base" / path.relative_to(HD / "x4")).with_suffix(".json")
        if not manifest.exists():
            print(f"{path}: no base sheet with this name, skipped")
            continue
        m = json.loads(manifest.read_text())
        sprite = m["sprite"]
        if sprite not in cache:
            width, height, frames = rs.sprite_frames(rom, sprite)
            palette = sorted({p for f in frames.values() for p in f if p})
            cache[sprite] = width, height, frames, palette
        width, height, frames, palette = cache[sprite]
        sheet = Image.open(path).convert("RGB")
        want = m["columns"] * width / (m["rows"] * height)
        if abs(sheet.width / sheet.height / want - 1) > 0.03:
            print(f"{path}: wrong proportions ({sheet.width}x{sheet.height}), skipped")
            continue
        cw, ch = sheet.width / m["columns"], sheet.height / m["rows"]
        for n, i in enumerate(m["frames"]):
            x, y = n % m["columns"] * cw, n // m["columns"] * ch
            cell = sheet.crop((round(x), round(y), round(x + cw), round(y + ch)))
            indices, agreement = convert_cell(rom, cell, frames[i], width, height, palette)
            if agreement < minimum:
                print(f"{path} frame {i}: outline overlap {agreement:.0%}, skipped")
                continue
            packed[(sprite, i)] = (width, height, frames[i], indices)
        print(f"{path}: done")
    if not packed:
        sys.exit("No usable frames, pack not written.")
    data = bytearray(b"GSHD" + struct.pack("<III", 1, SCALE, len(packed)))
    for (sprite, i), (width, height, original, indices) in sorted(packed.items()):
        data += struct.pack("<III", sprite * 1000 + i, width, height) + original + indices
    target = HD / "sprites.pack"
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)  # the game may be watching the file
    print(f"\n{len(packed)} frames written to {target.resolve()}")


def main():
    args = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("command", choices=("extract", "pack"))
    args.add_argument("--rom", help="ROM path (default: search ROMs/)")
    args.add_argument("--id", type=int, action="append", help="extract only this sprite ID")
    args.add_argument("--min-overlap", type=float, default=0.75)
    a = args.parse_args()
    _, rom = rs.find_rom(a.rom)
    if a.command == "extract":
        extract(rom, a.id if a.id is not None else range(rs.MAX_SPRITES))
    else:
        pack(rom, a.min_overlap)


if __name__ == "__main__":
    main()
