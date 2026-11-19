/*
 * SPDX-FileCopyrightText: 2026 read-pico-vn contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * 中文：越南语组合音标（NFD）实时合成为预组合码位（NFC），不改原文字节偏移。
 * English: On-the-fly Vietnamese NFD combining-mark composition to precomposed NFC codepoints
 * without modifying source byte offsets.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

static inline uint32_t vi_nfc_apply_case(uint16_t low, bool upper) {
    if (!upper) return low;
    return low < 0x100u ? (uint32_t)(low - 0x20u) : (uint32_t)(low - 1u);
}

static inline int vi_nfc_tone_index(uint32_t mark) {
    switch (mark) {
        case 0x0300u: return 0; // combining grave
        case 0x0301u: return 1; // combining acute
        case 0x0309u: return 2; // combining hook above
        case 0x0303u: return 3; // combining tilde
        case 0x0323u: return 4; // combining dot below
        default: return -1;
    }
}

static inline int vi_nfc_vowel_row(uint32_t cp, bool *upper) {
    switch (cp) {
        case 'A': *upper = true;  return 0;
        case 'a': *upper = false; return 0;
        case 'E': *upper = true;  return 1;
        case 'e': *upper = false; return 1;
        case 'I': *upper = true;  return 2;
        case 'i': *upper = false; return 2;
        case 'O': *upper = true;  return 3;
        case 'o': *upper = false; return 3;
        case 'U': *upper = true;  return 4;
        case 'u': *upper = false; return 4;
        case 'Y': *upper = true;  return 5;
        case 'y': *upper = false; return 5;
        case 0x00C2u: *upper = true;  return 6;  // Â
        case 0x00E2u: *upper = false; return 6;  // â
        case 0x0102u: *upper = true;  return 7;  // Ă
        case 0x0103u: *upper = false; return 7;  // ă
        case 0x00CAu: *upper = true;  return 8;  // Ê
        case 0x00EAu: *upper = false; return 8;  // ê
        case 0x00D4u: *upper = true;  return 9;  // Ô
        case 0x00F4u: *upper = false; return 9;  // ô
        case 0x01A0u: *upper = true;  return 10; // Ơ
        case 0x01A1u: *upper = false; return 10; // ơ
        case 0x01AFu: *upper = true;  return 11; // Ư
        case 0x01B0u: *upper = false; return 11; // ư
        default: return -1;
    }
}

// 12 Vietnamese vowel rows (a,e,i,o,u,y,â,ă,ê,ô,ơ,ư) x 5 tones (grave, acute, hook, tilde, dot).
static inline uint32_t vi_nfc_compose_pair(uint32_t base, uint32_t mark) {
    static const uint16_t toned[12][5] = {
        {0x00E0u, 0x00E1u, 0x1EA3u, 0x00E3u, 0x1EA1u}, // a
        {0x00E8u, 0x00E9u, 0x1EBBu, 0x1EBDu, 0x1EB9u}, // e
        {0x00ECu, 0x00EDu, 0x1EC9u, 0x0129u, 0x1ECBu}, // i
        {0x00F2u, 0x00F3u, 0x1ECFu, 0x00F5u, 0x1ECDu}, // o
        {0x00F9u, 0x00FAu, 0x1EE7u, 0x0169u, 0x1EE5u}, // u
        {0x1EF3u, 0x00FDu, 0x1EF7u, 0x1EF9u, 0x1EF5u}, // y
        {0x1EA7u, 0x1EA5u, 0x1EA9u, 0x1EABu, 0x1EADu}, // â
        {0x1EB1u, 0x1EAFu, 0x1EB3u, 0x1EB5u, 0x1EB7u}, // ă
        {0x1EC1u, 0x1EBFu, 0x1EC3u, 0x1EC5u, 0x1EC7u}, // ê
        {0x1ED3u, 0x1ED1u, 0x1ED5u, 0x1ED7u, 0x1ED9u}, // ô
        {0x1EDDu, 0x1EDBu, 0x1EDFu, 0x1EE1u, 0x1EE3u}, // ơ
        {0x1EEBu, 0x1EE9u, 0x1EEDu, 0x1EEFu, 0x1EF1u}, // ư
    };
    int tone = vi_nfc_tone_index(mark);
    if (tone >= 0) {
        bool upper = false;
        int row = vi_nfc_vowel_row(base, &upper);
        if (row < 0) return 0;
        return vi_nfc_apply_case(toned[row][tone], upper);
    }
    if (mark != 0x0302u && mark != 0x0306u && mark != 0x031Bu) return 0;
    // Plain vowel + shape modifier (circumflex, breve, horn).
    switch (base) {
        case 'A': return mark == 0x0302u ? 0x00C2u : mark == 0x0306u ? 0x0102u : 0;
        case 'a': return mark == 0x0302u ? 0x00E2u : mark == 0x0306u ? 0x0103u : 0;
        case 'E': return mark == 0x0302u ? 0x00CAu : 0;
        case 'e': return mark == 0x0302u ? 0x00EAu : 0;
        case 'O': return mark == 0x0302u ? 0x00D4u : mark == 0x031Bu ? 0x01A0u : 0;
        case 'o': return mark == 0x0302u ? 0x00F4u : mark == 0x031Bu ? 0x01A1u : 0;
        case 'U': return mark == 0x031Bu ? 0x01AFu : 0;
        case 'u': return mark == 0x031Bu ? 0x01B0u : 0;
        default: break;
    }
    // Non-canonical order: already-toned plain vowel + shape modifier (e.g. o + dot_below + horn -> ợ).
    static const uint8_t rows[4] = {0, 1, 3, 4};
    for (unsigned i = 0; i < 4; ++i) {
        int r = rows[i];
        int target = -1;
        if (r == 0 && mark == 0x0302u) target = 6;
        else if (r == 0 && mark == 0x0306u) target = 7;
        else if (r == 1 && mark == 0x0302u) target = 8;
        else if (r == 3 && mark == 0x0302u) target = 9;
        else if (r == 3 && mark == 0x031Bu) target = 10;
        else if (r == 4 && mark == 0x031Bu) target = 11;
        if (target < 0) continue;
        for (int t = 0; t < 5; ++t) {
            uint16_t low = toned[r][t];
            if (base == low) return toned[target][t];
            if (base == vi_nfc_apply_case(low, true)) return vi_nfc_apply_case(toned[target][t], true);
        }
    }
    return 0;
}

static inline uint32_t vi_nfc_consume_marks(uint32_t cp, const char **cursor) {
    for (unsigned step = 0; step < 2; ++step) {
        const uint8_t *p = (const uint8_t *)(*cursor);
        if ((p[0] != 0xCCu && p[0] != 0xCDu) || (p[1] & 0xC0u) != 0x80u) break;
        uint32_t mark = ((uint32_t)(p[0] & 0x1Fu) << 6) | (p[1] & 0x3Fu);
        uint32_t composed = vi_nfc_compose_pair(cp, mark);
        if (!composed) break;
        cp = composed;
        *cursor += 2;
    }
    return cp;
}

static inline bool vi_is_combining_mark(uint32_t cp) {
    return cp >= 0x0300u && cp <= 0x036Fu;
}
