# 4x upscaled textures: investigation notes

Status: investigation only. Based on reading the code at `1669a14`; nothing
here has been built, run or measured. No code changes.

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

## Suggested prototype

Render at 4x and replace Isaac's walk frames using original palette indices.
Measure scaling correctness, matching and performance.

The decoder reads colour indices up to `0xDF`, which suggests field sprites are
8bpp. If confirmed, the existing 4bpp-only fingerprint needs an 8bpp version.

Generate textures locally from the user's own ROM; the repository ships no
game data.
