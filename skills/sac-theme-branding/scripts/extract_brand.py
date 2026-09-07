#!/usr/bin/env python3
"""
Pull brand colours and typefaces out of whatever the customer supplied.

  extract_brand.py deck.pptx [more.pptx ...] [screenshot.png ...]

A .pptx/.potx carries a declared theme (ppt/theme/theme1.xml) AND evidence of
how that theme is actually used across the slides. Both matter: the declared
scheme tells you the brand's official accents, the usage counts tell you which
of them the brand actually leans on.

An image (a screenshot of an existing report, a brand-guide page) gets its
colours counted by frequency and by region. Screenshots are the single most
valuable input because they show the palette IN USE - which colour is the
primary series, which is the secondary, what the chrome looks like.

Nothing here decides anything. It reports, and you design from the report.
"""
import collections
import os
import re
import sys
import zipfile

SCHEME_ROLES = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3",
                "accent4", "accent5", "accent6", "hlink", "folHlink"]


# --------------------------------------------------------------------- pptx
def read_pptx(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()

    print(f"\n{'=' * 68}\n{os.path.basename(path)}\n{'=' * 68}")

    # The first theme part belongs to the main slide master. Later ones are
    # usually the notes/handout masters carrying stock Office colours - ignore
    # those or you will "discover" that the brand colour is #4F81BD.
    themes = sorted(n for n in names if re.match(r"ppt/theme/theme\d+\.xml$", n))
    for tn in themes[:1]:
        x = z.read(tn).decode("utf8", "replace")
        m = re.search(r"<a:clrScheme[^>]*name=\"([^\"]*)\"(.*?)</a:clrScheme>", x, re.S)
        if m:
            print(f"\n-- declared colour scheme: {m.group(1)!r}")
            body = m.group(2)
            for role in SCHEME_ROLES:
                mm = re.search(rf"<a:{role}>\s*<a:(?:srgbClr val=\"([0-9A-Fa-f]{{6}})\"|"
                               rf"sysClr[^>]*lastClr=\"([0-9A-Fa-f]{{6}})\")", body)
                if mm:
                    print(f"   {role:<10} #{(mm.group(1) or mm.group(2)).upper()}")
        m = re.search(r"<a:fontScheme[^>]*name=\"([^\"]*)\"(.*?)</a:fontScheme>", x, re.S)
        if m:
            print(f"\n-- declared fonts: {m.group(1)!r}")
            for kind in ("majorFont", "minorFont"):
                mm = re.search(rf"<a:{kind}>\s*<a:latin typeface=\"([^\"]*)\"", m.group(2))
                if mm:
                    label = "headings" if kind == "majorFont" else "body"
                    print(f"   {label:<10} {mm.group(1)!r}")

    slides = [n for n in names if re.match(r"ppt/(slides|slideMasters|slideLayouts)/\w+\.xml$", n)]
    hexes, schemes, fonts = collections.Counter(), collections.Counter(), collections.Counter()
    for n in slides:
        x = z.read(n).decode("utf8", "replace")
        for v in re.findall(r'srgbClr val="([0-9A-Fa-f]{6})"', x):
            hexes[v.upper()] += 1
        if "/slides/" in n:
            for v in re.findall(r'schemeClr val="(\w+)"', x):
                schemes[v] += 1
            for v in re.findall(r'typeface="([^"+][^"]*)"', x):
                fonts[v] += 1

    print(f"\n-- theme slots actually used across {sum(1 for n in slides if '/slides/' in n)} slides")
    print("   (heavy accent1 use means accent1 is the real primary, whatever the guide says)")
    for k, v in schemes.most_common(10):
        print(f"   {k:<10} {v}")
    print("\n-- literal colours hard-coded on slides (off-theme, but often revealing)")
    for k, v in hexes.most_common(15):
        print(f"   #{k:<9} {v}")
    if fonts:
        print("\n-- explicit typefaces on slides")
        for k, v in fonts.most_common(8):
            print(f"   {k:<28} {v}")


# -------------------------------------------------------------------- image
def read_image(path):
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed: pip install Pillow --break-system-packages")
        return

    im = Image.open(path).convert("RGB")
    w, h = im.size
    print(f"\n{'=' * 68}\n{os.path.basename(path)}   {w}x{h}\n{'=' * 68}")

    px = list(im.getdata())
    c = collections.Counter(px)
    total = len(px)

    def hx(t):
        return "#%02X%02X%02X" % t

    print("\n-- dominant colours (whole image)")
    for rgb, n in c.most_common(18):
        print(f"   {hx(rgb)}  {n / total * 100:5.2f}%  {n}")

    # Near-duplicates from antialiasing cluster around the true value. Collapse
    # them so a single brand colour does not look like eight different ones.
    print("\n-- after merging antialiasing neighbours (within 6/255 per channel)")
    merged, seen = [], []
    for rgb, n in c.most_common(400):
        for i, (base, tot) in enumerate(seen):
            if all(abs(a - b) <= 6 for a, b in zip(rgb, base)):
                seen[i] = (base, tot + n)
                break
        else:
            seen.append((rgb, n))
    for rgb, n in sorted(seen, key=lambda t: -t[1])[:14]:
        if n / total < 0.0008:
            break
        merged.append(hx(rgb))
        print(f"   {hx(rgb)}  {n / total * 100:5.2f}%")

    # Text colour is never dominant - it lives in the dark tail. Reporting it
    # separately stops you guessing "probably near-black" when the brand may
    # well use a specific off-black.
    dark = [(hx(rgb), n) for rgb, n in c.items()
            if sum(rgb) < 300 and n > total * 0.00004]
    dark.sort(key=lambda t: -t[1])
    if dark:
        print("\n-- dark tones (text, rules, marks)")
        for hexv, n in dark[:8]:
            print(f"   {hexv}  {n}")

    print("\n   Crop and re-run on a region to read one widget precisely, e.g.")
    print("   python -c \"from PIL import Image; Image.open('%s').crop((L,T,R,B))"
          ".save('crop.png')\"" % os.path.basename(path))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    for p in args:
        if not os.path.exists(p):
            print(f"missing: {p}")
            continue
        if p.lower().endswith((".pptx", ".potx")):
            read_pptx(p)
        elif p.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
            read_image(p)
        else:
            print(f"skipping {p} (not a pptx or image)")
    print("\nNext: decide the palette, then write the spec. See references/palette-design.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
