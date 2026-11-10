#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Kiikoread-Personal-Study-1.0
"""中文：向 Pico 内建 builtin.ttf 追加越南语轮廓（仅追加字形，原有字形/度量不变）。
English: Append Vietnamese outlines to the Pico builtin.ttf. Glyphs are only appended, so every
original outline, advance and bearing stays byte-identical.

  python3 tools/add_vi_outlines.py --src /usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc

--src accepts a static Noto Sans CJK/SC Medium (.ttf/.otf) or a .ttc (the SC face is picked).
CFF outlines are converted to TrueType quadratics (cu2qu, max error 1 unit at 1000 upm).
Alternative (repo's own pipeline): the code points are also listed in
main/font/reader_extra_outlines.txt, so gen_pico_builtin_font.py --src <static Medium TTF> works too.
"""
import argparse, hashlib, json
from pathlib import Path
from fontTools.ttLib import TTFont, TTCollection
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen

ROOT = Path(__file__).resolve().parents[1]
VI = ([0x102, 0x103, 0x110, 0x111, 0x128, 0x129, 0x168, 0x169, 0x1A0, 0x1A1, 0x1AF, 0x1B0]
      + list(range(0x1EA0, 0x1EFA)) + [0x20AB])


def load_sc(path):
    if str(path).lower().endswith(".ttc"):
        fonts = TTCollection(path).fonts
        for f in fonts:
            if "SC" in (f["name"].getDebugName(1) or ""):
                return f
        raise SystemExit("no SC face in collection")
    return TTFont(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--font", type=Path, default=ROOT / "boards/pico/src/main/assets/builtin.ttf")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    out = a.out or a.font

    src = load_sc(a.src)
    assert src["OS/2"].usWeightClass == 500, "source must be the Medium weight"
    assert src["head"].unitsPerEm == 1000
    scmap, gs = src.getBestCmap(), src.getGlyphSet()

    f = TTFont(a.font, recalcTimestamp=False)
    assert "glyf" in f and f["head"].unitsPerEm == 1000
    have = f.getBestCmap()
    todo = [c for c in VI if c not in have]
    missing = [c for c in todo if c not in scmap]
    assert not missing, [hex(c) for c in missing]

    order = list(f.getGlyphOrder())
    glyf, hmtx = f["glyf"], f["hmtx"]
    names = {}
    for cp in todo:
        name = f"uni{cp:04X}"
        assert name not in order
        pen = TTGlyphPen(None)
        gs[scmap[cp]].draw(Cu2QuPen(pen, max_err=1.0, reverse_direction=True))
        g = pen.glyph()
        g.recalcBounds(glyf)
        hmtx[name] = (gs[scmap[cp]].width, getattr(g, "xMin", 0) if g.numberOfContours else 0)
        glyf[name] = g
        order.append(name)
        names[cp] = name
    f.setGlyphOrder(order)
    for t in f["cmap"].tables:
        if t.isUnicode():
            for cp, name in names.items():
                t.cmap[cp] = name
    for tag in ("hdmx", "LTSH", "VDMX"):
        if tag in f:
            del f[tag]
    out.parent.mkdir(parents=True, exist_ok=True)
    f.save(out)
    data = out.read_bytes()
    print(json.dumps(dict(added=len(todo), glyphs=len(order), bytes=len(data),
                          sha256=hashlib.sha256(data).hexdigest())))


if __name__ == "__main__":
    main()
