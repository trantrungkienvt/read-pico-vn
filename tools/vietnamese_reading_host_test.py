#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""中文：验证双板内建越南语字库、NFD合成、HTML实体、章节识别与横排断行。
English: Verify dual-board Vietnamese built-in font coverage, NFD->NFC composition,
HTML named entities, Vietnamese chapter/volume/front-matter parsing, and reading layout.
"""
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".kiiko-source-view.json"
SOURCE = Path(json.loads(MARKER.read_text())["source"]) if MARKER.exists() else ROOT

sys.path.insert(0, str(ROOT / "tools"))
from font_hanzi_host_support import font_codepoints


def check_fonts():
    pico = (SOURCE / "boards/pico/src/main/assets/builtin.ttf").read_bytes()
    s31 = (SOURCE / "boards/metalio47/src/main/assets/builtin.ttf").read_bytes()
    assert pico == s31, "Pico and S31 builtin.ttf must stay byte-identical"
    native = font_codepoints(pico)
    vi_letters = (
        "ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúý"
        "ĂăĐđĨĩŨũƠơƯư"
        + "".join(chr(c) for c in range(0x1EA0, 0x1EFA))
    )
    vi_punct = "₫«»‹›–—‘’“”…"
    missing = [ch for ch in (vi_letters + vi_punct) if ord(ch) not in native]
    assert not missing, f"Missing Vietnamese codepoints in builtin.ttf: {missing}"
    aa = (SOURCE / "boards/pico/src/main/assets/ui-hanzi.bin").read_bytes()
    count = struct.unpack_from("<I", aa, 4)[0]
    supplement = set(struct.unpack_from("<" + "H" * count, aa, 16))
    assert len(native | supplement) == 7771, len(native | supplement)


def build_nfd_cases():
    # Generate canonical and reversed NFD byte sequences for all 132 accented Vietnamese vowels.
    cases = []
    vowels = (
        "ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúý"
        "ĂăĨĩŨũƠơƯư"
        + "".join(chr(c) for c in range(0x1EA0, 0x1EFA))
    )
    for ch in vowels:
        nfd = unicodedata.normalize("NFD", ch)
        cases.append((nfd.encode("utf-8"), ord(ch)))
        if len(nfd) == 3:
            # Also test reversed combining-mark order (tone before shape modifier).
            rev = nfd[0] + nfd[2] + nfd[1]
            cases.append((rev.encode("utf-8"), ord(ch)))
    return cases


def c_escape(data: bytes) -> str:
    return "".join(f"\\x{b:02x}" for b in data)


def run_c_tests():
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        if "--font-only" in sys.argv:
            return
        raise SystemExit("Host C compiler required (pass --font-only to verify font assets only)")

    nfd_cases = build_nfd_cases()
    nfd_rows = "\n".join(
        f'    {{"{c_escape(raw)}", 0x{cp:04X}u}},' for raw, cp in nfd_cases
    )

    unit = f'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vi_nfc.h"
#include "html_text.h"
#include "book_chapter_label.h"
#include "book_chapter_lead.h"
#include "book_layout.h"
#include "ttf_font.h"

int test_heap_fail_after = -1;
size_t test_heap_largest;
int html_test_fail_after = -1;
int test_guide_segments, test_guide_first_x, test_guide_first_y, test_guide_second_y, test_guide_last_y, test_guide_height;
uint8_t test_guide_gray;

static char captured[64][512];
static unsigned captured_count;
static int fitted_target;
static int test_weight = 400;

int ttf_get_weight(void) {{ return test_weight; }}
void ttf_set_weight(int w) {{ test_weight = w; }}
void ttf_draw_set_runs(const ttf_run_t* runs, size_t count) {{ (void)runs; (void)count; }}
int ttf_font_select(int slot) {{ (void)slot; return 0; }}
int ttf_font_selected(void) {{ return 0; }}
bool ttf_font_slot_ready(int slot) {{ return slot == 0; }}
int ttf_ascender_px(int px) {{ return px; }}
void ttf_measure_line_px(int px, const char* text, int* above, int* below) {{ (void)text; *above = px; *below = 0; }}
int ttf_text_left_bearing_px(int px, const char* text) {{ (void)px; (void)text; return 0; }}

static uint32_t test_decode_utf8(const char** cursor) {{
    const uint8_t* p = (const uint8_t*)*cursor;
    if (!p[0]) return 0;
    uint32_t cp;
    if (p[0] < 0x80) {{ *cursor += 1; cp = p[0]; }}
    else if ((p[0] & 0xE0) == 0xC0 && (p[1] & 0xC0) == 0x80) {{
        *cursor += 2; cp = ((uint32_t)(p[0] & 0x1F) << 6) | (p[1] & 0x3F);
    }} else if ((p[0] & 0xF0) == 0xE0 && (p[1] & 0xC0) == 0x80 && (p[2] & 0xC0) == 0x80) {{
        *cursor += 3; cp = ((uint32_t)(p[0] & 0x0F) << 12) | ((uint32_t)(p[1] & 0x3F) << 6) | (p[2] & 0x3F);
    }} else {{ *cursor += 1; return 0xFFFD; }}
    return vi_nfc_consume_marks(cp, cursor);
}}

int ttf_text_width_px(int px, const char* text) {{
    int width = 0;
    const char* p = text;
    while (*p) {{
        uint32_t cp = test_decode_utf8(&p);
        (void)cp;
        width += px;
    }}
    return width;
}}

void ttf_draw_text_px(uint8_t* fb, int x, int y, int px, const char* text,
                      enum EpdFontFlags align, uint8_t fg, uint8_t bg) {{
    (void)fb; (void)x; (void)y; (void)px; (void)align; (void)fg; (void)bg;
    assert(captured_count < 64 && strlen(text) < sizeof(captured[0]));
    strcpy(captured[captured_count++], text);
}}
void ttf_draw_text_px_spaced(uint8_t* fb, int x, int y, int px, const char* text,
                             int tracking_px, uint8_t fg, uint8_t bg) {{
    (void)tracking_px;
    ttf_draw_text_px(fb, x, y, px, text, EPD_DRAW_ALIGN_LEFT, fg, bg);
}}
void ttf_draw_text_px_fitted(uint8_t* fb, int x, int y, int px, const char* text,
                             int tracking_px, int target_width, uint8_t fg, uint8_t bg) {{
    fitted_target = target_width;
    ttf_draw_text_px_spaced(fb, x, y, px, text, tracking_px, fg, bg);
}}
int ttf_draw_text_px_rotated(uint8_t* fb, int x, int y, int px, const char* text, uint8_t fg, uint8_t bg) {{
    (void)fb; (void)x; (void)y; (void)fg; (void)bg; return ttf_text_width_px(px, text);
}}
int ttf_draw_text_px_vertical(uint8_t* fb, int x, int y, int px, const char* text, int tracking_px, uint8_t fg, uint8_t bg) {{
    (void)fb; (void)x; (void)y; (void)tracking_px; (void)fg; (void)bg; return ttf_text_width_px(px, text);
}}
int ttf_vertical_text_height_px(int px, const char* text, int tracking_px) {{
    (void)tracking_px; return ttf_text_width_px(px, text);
}}

static void test_vi_nfc(void) {{
    static const struct {{ const char* raw; uint32_t expected; }} cases[] = {{
{nfd_rows}
    }};
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {{
        const char* p = cases[i].raw;
        uint32_t cp = test_decode_utf8(&p);
        assert(cp == cases[i].expected && *p == 0);
    }}
    // Non-Vietnamese combining mark must not be eaten.
    const char* non_vi = "c\\xcc\\x81";
    assert(test_decode_utf8(&non_vi) == 'c');
    assert(test_decode_utf8(&non_vi) == 0x0301u && *non_vi == 0);
}}

static void test_html_entities(void) {{
    html_text_t t = {{0}};
    const char* html = "<p>&laquo;Ti&#7871;ng Vi&ecirc;&#803;t &mdash; &Aacute;&agrave;&ocirc;&uacute;&yacute;&hellip;&raquo;</p>";
    assert(html_to_blocks(html, strlen(html), &t) == ESP_OK);
    assert(t.count == 1);
    assert(strstr(t.utf8, "«") && strstr(t.utf8, "»") && strstr(t.utf8, "—") &&
           strstr(t.utf8, "…") && strstr(t.utf8, "Áàôúý"));
    html_text_free(&t);
}}

static void test_chapters(void) {{
    chapter_label_t c = chapter_label_parse("Chương 1: Khởi đầu", true);
    assert(c.kind == CHAPTER_LABEL_CHAPTER && c.number == 1 && !strcmp(c.subtitle, "Khởi đầu"));

    c = chapter_label_parse("CHƯƠNG IV – Bão tố", true);
    assert(c.kind == CHAPTER_LABEL_CHAPTER && c.number == 4 && !strcmp(c.subtitle, "Bão tố"));

    c = chapter_label_parse("Hồi thứ 12: Định mệnh", true);
    assert(c.kind == CHAPTER_LABEL_EPISODE && c.number == 12 && !strcmp(c.subtitle, "Định mệnh"));

    c = chapter_label_parse("Quyển 2 - Gió đông", true);
    assert(c.kind == CHAPTER_LABEL_VOLUME && c.number == 2 && !strcmp(c.subtitle, "Gió đông"));

    c = chapter_label_parse("Tập I", true);
    assert(c.kind == CHAPTER_LABEL_VOLUME && c.number == 1 && !*c.subtitle);

    c = chapter_label_parse("Phần III: Mùa hạ", true);
    assert(c.kind == CHAPTER_LABEL_VOLUME && c.number == 3 && !strcmp(c.subtitle, "Mùa hạ"));

    // False-positive guards on ordinary Vietnamese phrases.
    assert(chapter_label_parse("Chương mở đầu", false).kind == CHAPTER_LABEL_NONE);
    assert(chapter_label_parse("Hồi ức tuổi thơ", false).kind == CHAPTER_LABEL_NONE);
    assert(chapter_label_parse("Phần lớn mọi người", false).kind == CHAPTER_LABEL_NONE);
    assert(chapter_label_parse("Tập hợp các bài viết", false).kind == CHAPTER_LABEL_NONE);

    // Auxiliary / front-matter detection (case-insensitive Vietnamese).
    assert(chapter_label_auxiliary("MỤC LỤC"));
    assert(chapter_label_auxiliary("Lời nói đầu"));
    assert(chapter_label_auxiliary("Lời mở đầu"));
    assert(chapter_label_auxiliary("Bản quyền"));
    assert(chapter_label_auxiliary("Về tác giả"));
    assert(!chapter_label_auxiliary("Lời nói đầu của kẻ thù"));

    // Case-insensitive Vietnamese heading deduplication.
    assert(chapter_label_text_equal("CHƯƠNG 1: KHỞI ĐẦU", "Chương 1: Khởi đầu"));
    assert(chapter_label_repeats("Chương 1: Khởi đầu", "CHƯƠNG 1", true));

    // EPUB chapter lead splitting for Vietnamese headings.
    html_text_t t = {{0}};
    const char* html = "<h1>Chương 1: Khởi đầu</h1><p>Trời hôm nay thật đẹp.</p>";
    assert(html_to_blocks(html, strlen(html), &t) == ESP_OK);
    t.blocks[0].reader_heading = BOOK_HEADING_EPUB;
    t.blocks[0].chapter_start = true;
    char title[128], label[32];
    size_t skip = epub_chapter_lead(&t, "Chương 1: Khởi đầu", title, sizeof(title), label, sizeof(label));
    assert(skip == t.blocks[1].offset && !strcmp(label, "Chương 1") && !strcmp(title, "Khởi đầu"));
    html_text_free(&t);
}}

static void test_layout(void) {{
    uint8_t fb[16] = {{0}};
    book_layout_set_vertical(false);
    book_layout_set_spacing(150, 0);
    book_layout_set_typography(0);
    book_layout_set_first_line_indent(0);
    book_layout_set_chapter_lead(0, 0);
    book_layout_set_runs(NULL, 0);
    book_layout_set_image_dims(NULL, NULL);

    // Vietnamese text must NOT trigger English TeX hyphenation.
    const char* vi = "Đọc sách extraordinary trong trang";
    EpdRect box = {{40, 0, 160, 60}};
    assert(book_layout_build(vi, strlen(vi), box, 10));
    captured_count = 0;
    for (size_t p = 0; p < book_layout_page_count(); ++p) book_layout_draw_page(fb, p, box, 10);
    assert(captured_count == 3);
    assert(!strcmp(captured[0], "Đọc sách"));
    assert(!strcmp(captured[1], "extraordinary"));
    assert(!strcmp(captured[2], "trong trang"));

    // Shrunk Vietnamese line (within word-space shrink budget) must compress to available,
    // not overflow into available + hang.
    // "đọc đọc đọc" = 11 glyphs * 10 = 110px; 2 spaces -> shrink = 2 * (10/3) = 6px; available = 105px fits!
    const char* shrunk = "đọc đọc đọc";
    EpdRect shrink_box = {{40, 0, 105, 30}};
    assert(book_layout_build(shrunk, strlen(shrunk), shrink_box, 10));
    captured_count = 0; fitted_target = 0;
    book_layout_draw_page(fb, 0, shrink_box, 10);
    assert(captured_count == 1 && !strcmp(captured[0], "đọc đọc đọc"));
    assert(fitted_target == 105);

    // Guillemet opener « follows its word to the next line.
    const char* guil = "đọc «sách» hay";
    EpdRect guil_box = {{40, 0, 80, 60}};
    assert(book_layout_build(guil, strlen(guil), guil_box, 10));
    captured_count = 0;
    for (size_t p = 0; p < book_layout_page_count(); ++p) book_layout_draw_page(fb, p, guil_box, 10);
    assert(captured_count == 3 && !strcmp(captured[0], "đọc") && !strcmp(captured[1], "«sách»"));

    // NFD Vietnamese grapheme cluster never splits across a line break.
    const char* nfd = "Ti\\x65\\xcc\\x82\\xcc\\x81ng Vi\\x65\\xcc\\x82\\xcc\\xa3t";
    EpdRect nfd_box = {{40, 0, 50, 60}};
    assert(book_layout_build(nfd, strlen(nfd), nfd_box, 10));
    captured_count = 0;
    for (size_t p = 0; p < book_layout_page_count(); ++p) book_layout_draw_page(fb, p, nfd_box, 10);
    assert(captured_count == 2);
    assert(!strcmp(captured[0], "Ti\\x65\\xcc\\x82\\xcc\\x81ng"));
    assert(!strcmp(captured[1], "Vi\\x65\\xcc\\x82\\xcc\\xa3t"));
}}

int main(void) {{
    test_vi_nfc();
    test_html_entities();
    test_chapters();
    test_layout();
    puts("PASS: Vietnamese NFD->NFC (all 132 vowels + reversed order), HTML entities, chapter/volume/front-matter parsing, whole-word non-hyphenated layout, shrink alignment and guillemet/NFD wrapping");
    return 0;
}}
'''

    with tempfile.TemporaryDirectory(prefix="vi-reading-test-") as d:
        work = Path(d)
        src = work / "test.c"
        src.write_text(unit, encoding="utf-8")
        exe = work / "test"
        subprocess.run(
            [
                cc, "-std=c11", "-D_DEFAULT_SOURCE", "-Wall", "-Wextra", "-Werror",
                "-g", "-fsanitize=address,undefined",
                "-I" + str(ROOT / "main/font"),
                "-I" + str(ROOT / "main/book"),
                "-I" + str(ROOT / "main"),
                "-I" + str(ROOT / "tools/book_layout_stubs"),
                "-I" + str(ROOT / "tools/book_source_host_stubs"),
                str(src),
                str(ROOT / "main/book/book_layout.c"),
                str(ROOT / "main/book/html_text.c"),
                "-o", str(exe),
            ],
            check=True,
        )
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    check_fonts()
    run_c_tests()
    print("PASS: Dual-board Vietnamese built-in font assets (7771 chars, all 134 Vietnamese letters + punctuation)")
