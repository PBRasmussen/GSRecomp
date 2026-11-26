# 4x upscaled textures: investigation notes

Status: a prototype exists for *The Broken Seal* field sprites (see
"Prototype" below). It has not been tried in the real game. The investigation
notes after that section were written first, from reading the code at
`1669a14`.

## Prototype

### Use

From the repository root, with your ROM in `ROMs/`:

```text
py -m pip install pillow
py scripts/hd/hd_sprites.py extract
```

This makes `local/hd/base/sprite_NNN/*.png` (sheets of 4x2 frames, enlarged
8x on magenta, each with a `.json` describing it) and matching empty folders
under `local/hd/x4`. Add `--id 0` for Isaac only.

1. Redraw a base sheet. Keep the grid, proportions and flat magenta
   background; any resolution works.
2. Save it under the same path in `x4`, for example
   `local/hd/x4/sprite_000/walk_front.png`. Only put redrawn sheets there.
3. Pack: `py scripts/hd/hd_sprites.py pack`
4. Build. On a fresh clone, install MSYS2 and these packages, then run
   `py scripts/setup_dev.py`, which generates the game code from your ROM,
   configures the build and runs it:

   ```powershell
   winget install --id MSYS2.MSYS2
   C:\msys64\usr\bin\pacman.exe -Syu --noconfirm
   C:\msys64\usr\bin\pacman.exe -S --needed --noconfirm mingw-w64-x86_64-gcc mingw-w64-x86_64-make mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja mingw-w64-x86_64-SDL2 mingw-w64-x86_64-zlib
   ```

   Later builds: add `C:\msys64\mingw64\bin` to `PATH`, then
   `.\build_dev.bat -Game BrokenSeal`.
5. Set `GSR_HD_PACK` to the full path of `local/hd/sprites.pack` and start
   the launcher from the same shell:

```powershell
$env:GSR_HD_PACK = "$PWD\local\hd\sprites.pack"
.\GoldenSunLauncher.exe
```

Packing again while the game runs reloads the pack within about a second.
Lines starting `[gsr-hd]` in `logs/session_*.log` should show the pack loading
and each frame the first time it is matched.

### How it works

The finished native picture is enlarged 4x. Where it shows a pixel of a
sprite in the pack, in the expected colour, the 4x4 block takes the
replacement pixels (`engine/src/field/hd_sprites.h`). The window shows that
copy only for the exact picture it was made from
(`engine/src/runtime/hd_frame.h`). Replacements are palette indices, so
palette changes apply. This differs from the shader route suggested below: it
is a smaller change for testing artwork.

### Limitations

- *The Broken Seal* only, and the graphics-card renderer must be on.
- Only codec 3 field sprites are extracted, using one shared palette, which
  may be wrong for some. Sheets are in frame order, so directions are mixed.
- Replacement art stays within about 2 of the 4x pixels of the original
  outline.
- Sprites under fades, blends or other artwork keep original pixels there.
- Screen filters, the native renderer and Android's direct display path show
  the native picture.
- Everything else on screen is a plain 4x enlargement.

### Tested

- The engine runtime library builds on Linux and `runner_main.cpp` passes a
  syntax check (with a placeholder `recompiled.h`). No game or Windows build.
- The compositor was tested with synthetic scenes under ASan/UBSan.
- Extract and pack were run on a stand-in ROM made from an exported Isaac
  sheet, with an AI-redrawn walk sheet.
- `setup_dev.py` was run on Linux up to code generation with a blank
  stand-in ROM; not run on Windows.
- Unconfirmed: that video memory in the real game matches the ROM frames.

## Summary

4x textures look feasible. The graphics-card renderer
(`engine/src/field/field_scene_renderer.cpp`), enabled by default in the
launcher, is the natural place to add them.

## What helps

- The renderer uploads raw video memory and palettes, and its shaders do the
  tile and pixel lookup.
- The sprite shader and background lookup floor to whole console pixels, so a
  4x path could use the fraction to choose a sub-pixel.
- `engine/src/field/object_artwork.h` fingerprints 4bpp sprite artwork
  independently of palette, position and sprite memory layout.
- `shared_game/rom_unpack.h` unpacks the games' compressed assets, which may
  help with extracting art from the user's own ROM.

## What needs work

- **Output size:** render targets follow the console-pixel view size. Screen
  coordinate calculations, effects and rotated sprites need checking at 4x.
- **Presentation:** direct texture presentation is Android only
  (`engine/src/runtime/gpu_present.h`); desktop reads frames back to the CPU.
  4x means 16 times the pixels.
- **Colour:** layer records pack the raw 15-bit palette colour into RGBA8.
  Full-colour textures need a different record format and blending changes.
- **Fallbacks:** the renderer declines some frames, including bitmap modes
  and mosaic.
- **Matching:** backgrounds reuse 8x8 tiles, so per-tile replacement risks
  seams and lost context. Sprite fingerprinting does not cover 8bpp objects.

## Options

| Route | Effort (estimate) | Result |
|---|---|---|
| Existing xBR screen filter (developer test option) | None | Smooths the final image only |
| Upscaling in the shaders | Medium | Sharper art, no texture files |
| 4x palette-indexed texture packs | Large | Custom art; can keep palette effects |
| Full-colour texture packs | Largest | Most freedom; palette effects need extra work |

## AI-generated textures

The plan is to generate textures with ChatGPT's image tools. Expected issues:
shifted outlines, added colours, inexact sizes and inconsistency between
animation frames.

1. Export assembled sprites and scenery as labelled, well-spaced sheets.
2. Generate one sheet at a time with a fixed style reference and prompt.
3. Align and resize to exactly 4x; constrain transparency to the original
   outline.
4. Quantise to the original palette (palette-indexed route).
5. Cut the sheets into replacements, matched by fingerprint.

Test one character's walk cycle through steps 1-4, viewed animated, before
changing the renderer.

## First test sprite: Isaac's field walk cycle

*The Broken Seal*, walking towards the camera, plus the standing frame.

There is **no image file** for this sprite in the repository. The art is
inside the user's own ROM (USA/Europe, SHA-1
`5c4695205413df7db52b9a184815a07783999971`).

**Start with `shared_game/djinn_tracker.h`**, function `decode()`. It reads a
field sprite from the ROM into a picture (frame 0 only, codec 3), and is the
basis for an exporter.

| Item | Location | Source file |
|---|---|---|
| Sprite ID | Isaac = 0 (Young Isaac = 18) | `shared_game/field_character.h`, `The Broken Seal/src/runner_main.cpp` |
| Sprite records | `0x08185024 + id * 20`; Isaac at ROM file offset `0x185024` | `The Broken Seal/src/runner_main.cpp` |
| Record fields | +0 width, +1 height, +5 pose count, +0xA codec, +0xC frame table, +0x10 pose table | `field_character.h`, `djinn_tracker.h` |
| Poses | 1 = stand, 2 = walk | `field_character.h` |
| Field sprite palette | `0x0800779C` (used for Djinn sprites) | `The Broken Seal/src/trackers_tbs.h` |

Still to confirm against a ROM:

- Isaac's frame size and codec.
- Which frames and view angle are the walk towards the camera.
- That the palette above is right for Isaac.

## Originally suggested prototype

Render at 4x and replace Isaac's walk frames using original palette indices.
Measure scaling correctness, matching and performance.

The decoder reads colour indices up to `0xDF`, which suggests field sprites are
8bpp. If confirmed, the existing 4bpp-only fingerprint needs an 8bpp version.

Generate textures locally from the user's own ROM; the repository ships no
game data.
