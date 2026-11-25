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

## Suggested prototype

Render at 4x and replace one 4bpp character sprite using its original palette
indices. Measure scaling correctness, matching and performance.

Generate textures locally from the user's own ROM; the repository ships no
game data.
