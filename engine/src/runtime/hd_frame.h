// hd_frame.h -- hands a larger copy of the current picture to the host window.
//
// A game runner that can add detail to a finished frame offers it here. The
// window shows it only while it is still being asked to present the exact
// native picture the copy was made from, so a stale copy can never appear.
// Nothing is ever offered unless a runner opts in.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <utility>
#include <vector>

namespace gbarecomp {

struct HdFrame {
    int base_w = 0, base_h = 0, scale = 0;  // scale 0: nothing on offer
    std::vector<std::uint8_t> source;       // RGB888, base_w x base_h
    std::vector<std::uint8_t> pixels;       // RGB888, base size times scale
};

inline HdFrame& hd_frame_slot() {
    static HdFrame frame;
    return frame;
}

inline void hd_frame_withdraw() { hd_frame_slot().scale = 0; }

inline void hd_frame_offer(const std::uint8_t* source, int base_w, int base_h,
                           int scale, std::vector<std::uint8_t>& pixels) {
    HdFrame& f = hd_frame_slot();
    f.base_w = base_w;
    f.base_h = base_h;
    f.scale = scale;
    f.source.assign(source, source + std::size_t(base_w) * base_h * 3u);
    f.pixels.swap(pixels);  // the caller reuses the old buffer
}

// The copy made from exactly this picture, else null.
inline const HdFrame* hd_frame_for(const std::uint8_t* rgb, int base_w, int base_h) {
    const HdFrame& f = hd_frame_slot();
    if (!rgb || f.scale <= 1 || f.base_w != base_w || f.base_h != base_h) return nullptr;
    return std::memcmp(rgb, f.source.data(), f.source.size()) == 0 ? &f : nullptr;
}

}  // namespace gbarecomp
