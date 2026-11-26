// hd_sprites.h -- prototype: 4x replacement artwork for chosen sprites.
//
// The finished native picture is enlarged 4x. Where it shows a pixel of a
// sprite the pack has artwork for, the 4x4 block takes the replacement's
// pixels instead. Replacement pixels are object-palette indices, so the
// game's palette changes still apply.
//
// A pixel counts as "showing the sprite" only if the picture holds the colour
// that sprite pixel should have. Anything drawn over it, or a blend or
// brightness effect, therefore leaves the original in place. The replacement
// cannot extend outside the original sprite's outline.
//
// The pack is made by scripts/hd/hd_sprites.py from the user's own ROM:
//   "GSHD", u32 version 1, u32 scale 4, u32 frame count, then per frame
//   u32 id, u32 width, u32 height, width*height original indices,
//   width*height*16 replacement indices. Little-endian; index 0 is clear.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <unordered_map>
#include <vector>

#include "field_scene.h"

namespace gsr::hd {

constexpr int kScale = 4;
constexpr int kMinMatchedPixels = 32;  // fewer could match by accident

struct Frame {
    std::uint32_t id = 0;
    int width = 0, height = 0;
    std::vector<std::uint8_t> original;     // width x height
    std::vector<std::uint8_t> replacement;  // (width*4) x (height*4)
    bool reported = false;
};

// What an object's artwork turned out to be, so each is searched for once.
struct Match {
    int frame = -1;  // index into Pack::frames, -1 none
    int ox = 0, oy = 0;
};

struct Pack {
    std::vector<Frame> frames;
    std::unordered_map<std::uint64_t, Match> seen;
};

// False (pack left empty) on a missing or malformed file.
inline bool load_pack(const char* path, Pack* pack) {
    pack->frames.clear();
    pack->seen.clear();
    std::FILE* f = std::fopen(path, "rb");
    if (!f) return false;
    const auto word = [f](std::uint32_t* v) {
        std::uint8_t b[4];
        if (std::fread(b, 1, 4, f) != 4) return false;
        *v = b[0] | b[1] << 8 | b[2] << 16 | std::uint32_t(b[3]) << 24;
        return true;
    };
    char magic[4];
    std::uint32_t version = 0, scale = 0, count = 0;
    bool ok = std::fread(magic, 1, 4, f) == 4 && std::memcmp(magic, "GSHD", 4) == 0 &&
              word(&version) && word(&scale) && word(&count) && version == 1 &&
              scale == kScale && count > 0 && count <= 65536;
    for (std::uint32_t i = 0; ok && i < count; ++i) {
        Frame frame;
        std::uint32_t w = 0, h = 0;
        ok = word(&frame.id) && word(&w) && word(&h) && w > 0 && h > 0 && w <= 64 && h <= 64;
        if (!ok) break;
        frame.width = int(w);
        frame.height = int(h);
        frame.original.resize(std::size_t(w) * h);
        frame.replacement.resize(frame.original.size() * kScale * kScale);
        ok = std::fread(frame.original.data(), 1, frame.original.size(), f) == frame.original.size() &&
             std::fread(frame.replacement.data(), 1, frame.replacement.size(), f) ==
                 frame.replacement.size();
        if (ok) pack->frames.push_back(std::move(frame));
    }
    std::fclose(f);
    if (!ok) pack->frames.clear();
    return ok;
}

// One object's artwork as object-palette indices, unflipped. Same tile
// addressing as the object shader (field_scene_renderer.cpp). False when it
// reaches past the memory given.
inline bool object_indices(const FieldScene& scene, const SceneObject& o,
                           const std::vector<std::uint8_t>& vram,
                           std::vector<std::uint8_t>* out) {
    if (o.width <= 0 || o.height <= 0 || o.width > 64 || o.height > 64) return false;
    const bool eight = o.palette < 0;
    const int step = eight ? 2 : 1;
    out->assign(std::size_t(o.width) * o.height, 0);
    for (int y = 0; y < o.height; ++y)
        for (int x = 0; x < o.width; ++x) {
            int tile = scene.one_dimensional_objects
                ? int(o.tile) + ((y >> 3) * (o.width >> 3) + (x >> 3)) * step
                : int(o.tile) + (y >> 3) * 32 + (x >> 3) * step;
            tile = int(o.tile & 0x400u) | (tile & 0x3FF);
            const std::size_t base = 0x10000u + std::size_t(tile) * 32u;
            const std::size_t at = base + (eight ? (y & 7) * 8 + (x & 7)
                                                 : (y & 7) * 4 + ((x & 7) >> 1));
            if (at >= vram.size()) return false;
            int index = vram[at];
            if (!eight) {
                index = (x & 1) ? index >> 4 : index & 15;
                if (index) index += o.palette * 16;
            }
            (*out)[std::size_t(y) * o.width + x] = std::uint8_t(index);
        }
    return true;
}

// Whether the object shows frame `f` (or a piece of it) when its top-left is
// at frame position (ox, oy). Every object pixel must equal the frame's.
inline bool matches_at(const std::vector<std::uint8_t>& art, int w, int h,
                       const Frame& f, int ox, int oy) {
    int matched = 0;
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            const int fx = x + ox, fy = y + oy;
            const std::uint8_t want =
                fx >= 0 && fy >= 0 && fx < f.width && fy < f.height
                    ? f.original[std::size_t(fy) * f.width + fx] : 0;
            if (art[std::size_t(y) * w + x] != want) return false;
            matched += want != 0;
        }
    return matched >= kMinMatchedPixels;
}

// An object smaller or larger than a frame is tried at whole-tile offsets.
inline Match search(const Pack& pack, const std::vector<std::uint8_t>& art, int w, int h) {
    if (art.size() - std::size_t(std::count(art.begin(), art.end(), 0)) <
        std::size_t(kMinMatchedPixels))
        return {};
    for (std::size_t i = 0; i < pack.frames.size(); ++i) {
        const Frame& f = pack.frames[i];
        const int dx = f.width - w, dy = f.height - h;
        for (int y = std::min(0, dy); y <= std::max(0, dy); y += 8)
            for (int x = std::min(0, dx); x <= std::max(0, dx); x += 8)
                if (matches_at(art, w, h, f, x, y)) return {int(i), x, y};
    }
    return {};
}

inline Frame* find_frame(Pack& pack, const std::vector<std::uint8_t>& art, int w, int h,
                         int* ox, int* oy) {
    std::uint64_t key = UINT64_C(14695981039346656037);  // FNV-1a
    const auto mix = [&key](unsigned v) { key = (key ^ v) * UINT64_C(1099511628211); };
    mix(unsigned(w));
    mix(unsigned(h));
    for (const std::uint8_t v : art) mix(v);
    auto found = pack.seen.find(key);
    if (found == pack.seen.end()) {
        if (pack.seen.size() >= 8192) pack.seen.clear();
        found = pack.seen.emplace(key, search(pack, art, w, h)).first;
    }
    const Match& m = found->second;
    if (m.frame < 0) return nullptr;
    // The hash only picks the candidate; the pixels decide.
    Frame& f = pack.frames[std::size_t(m.frame)];
    if (!matches_at(art, w, h, f, m.ox, m.oy)) return nullptr;
    *ox = m.ox;
    *oy = m.oy;
    return &f;
}

inline int expand5(int v) { return (v << 3) | (v >> 2); }

inline void rgb_of(std::uint16_t c, int out[3]) {
    out[0] = expand5(c & 31);
    out[1] = expand5((c >> 5) & 31);
    out[2] = expand5((c >> 10) & 31);
}

// Within rounding of the two ways the renderers widen 5-bit colour.
inline bool same_colour(const std::uint8_t* p, std::uint16_t c) {
    int want[3];
    rgb_of(c, want);
    for (int i = 0; i < 3; ++i)
        if (std::abs(int(p[i]) - want[i]) > 2) return false;
    return true;
}

// Builds the 4x picture in `out`. Returns the number of native pixels that
// took replacement artwork; 0 means `out` is not worth showing.
// `rgb` is the finished native picture, width x height, centred on the
// console's 240x160 as the renderer centres it.
inline int compose(Pack& pack, const FieldScene& scene,
                   const std::vector<std::uint8_t>& vram, const std::uint8_t* rgb,
                   int width, int height, std::vector<std::uint8_t>* out) {
    if (pack.frames.empty() || !scene.valid || !rgb || width <= 0 || height <= 0) return 0;
    const int camera_x = (240 - width) / 2, camera_y = (160 - height) / 2;
    const std::size_t out_row = std::size_t(width) * kScale * 3u;
    int replaced = 0;
    std::vector<std::uint8_t> art;
    // Last slot first, so the front-most object (lowest slot) writes last.
    for (int slot = FieldScene::kObjects - 1; slot >= 0; --slot) {
        const SceneObject& o = scene.objects[slot];
        if (!o.present || o.window || o.mosaic) continue;
        if (!object_indices(scene, o, vram, &art)) continue;
        int ox = 0, oy = 0;
        Frame* f = find_frame(pack, art, o.width, o.height, &ox, &oy);
        if (!f) continue;
        if (!f->reported) {
            f->reported = true;
            std::fprintf(stderr, "[gsr-hd] frame %u matched: %dx%d %s object at %d,%d\n",
                         unsigned(f->id), o.width, o.height,
                         o.palette < 0 ? "8-bit" : "4-bit", o.x, o.y);
        }
        if (replaced == 0) {  // first match: enlarge the picture
            out->resize(out_row * height * kScale);
            for (int y = 0; y < height; ++y) {
                std::uint8_t* row = out->data() + out_row * y * kScale;
                for (int x = 0; x < width * kScale; ++x)
                    std::memcpy(row + x * 3, rgb + (std::size_t(y) * width + x / kScale) * 3u, 3);
                for (int k = 1; k < kScale; ++k) std::memcpy(row + out_row * k, row, out_row);
            }
        }
        const int box_w = o.affine && o.double_size ? o.width * 2 : o.width;
        const int box_h = o.affine && o.double_size ? o.height * 2 : o.height;
        const int group = o.affine_index >= 0 && o.affine_index < FieldScene::kTransforms
            ? o.affine_index : 0;
        const auto& t = scene.object_transforms[group];
        for (int by = 0; by < box_h; ++by) {
            const int py = o.y - camera_y + by;
            if (py < 0 || py >= height) continue;
            for (int bx = 0; bx < box_w; ++bx) {
                const int px = o.x - camera_x + bx;
                if (px < 0 || px >= width) continue;
                // The texel the console shows at this pixel.
                int lx = bx, ly = by;
                const float cx = bx - box_w * 0.5f, cy = by - box_h * 0.5f;
                if (o.affine) {
                    lx = int(std::floor(t[0] * cx + t[1] * cy + o.width * 0.5f));
                    ly = int(std::floor(t[2] * cx + t[3] * cy + o.height * 0.5f));
                    if (lx < 0 || ly < 0 || lx >= o.width || ly >= o.height) continue;
                } else {
                    if (o.hflip) lx = o.width - 1 - lx;
                    if (o.vflip) ly = o.height - 1 - ly;
                }
                const int index = art[std::size_t(ly) * o.width + lx];
                if (!index) continue;
                const std::uint8_t* shown = rgb + (std::size_t(py) * width + px) * 3u;
                if (!same_colour(shown, scene.palette[256 + index])) continue;
                ++replaced;
                for (int sy = 0; sy < kScale; ++sy)
                    for (int sx = 0; sx < kScale; ++sx) {
                        int u, v;  // replacement pixel, object space
                        if (o.affine) {
                            const float ax = cx + (sx + 0.5f) / kScale;
                            const float ay = cy + (sy + 0.5f) / kScale;
                            u = int(std::floor((t[0] * ax + t[1] * ay + o.width * 0.5f) * kScale));
                            v = int(std::floor((t[2] * ax + t[3] * ay + o.height * 0.5f) * kScale));
                        } else {
                            u = lx * kScale + (o.hflip ? kScale - 1 - sx : sx);
                            v = ly * kScale + (o.vflip ? kScale - 1 - sy : sy);
                        }
                        u += ox * kScale;
                        v += oy * kScale;
                        if (u < 0 || v < 0 || u >= f->width * kScale || v >= f->height * kScale)
                            continue;
                        const int hd = f->replacement[std::size_t(v) * f->width * kScale + u];
                        if (!hd) continue;
                        int colour[3];
                        rgb_of(scene.palette[256 + hd], colour);
                        std::uint8_t* dst = out->data() + out_row * (py * kScale + sy) +
                                            std::size_t(px * kScale + sx) * 3u;
                        for (int i = 0; i < 3; ++i) dst[i] = std::uint8_t(colour[i]);
                    }
            }
        }
    }
    return replaced;
}

}  // namespace gsr::hd
