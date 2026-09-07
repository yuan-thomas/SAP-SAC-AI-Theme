#!/usr/bin/env python3
"""
Apply a brand spec to an exported SAC theme.

  build_theme.py theme.json spec.json --out-dir ./out [--prefix Acme]

Writes two files:

  <prefix>-theme-branded.json       colours and palettes only. Matches the
                                    common assumption that everything else
                                    resolves through swatch references.
  <prefix>-theme-branded-full.json  the above, plus cached literals refreshed,
                                    font applied and gaps filled, and any
                                    header-bar binding from the spec.

Give the customer the scoped file first. If widgets still render in stock
colours after import, the full file is the fix. The split exists because
whether the cached literals win is a property of their import script and their
SAC version, and you cannot know that from the export alone.

Everything here is mechanical and self-checking. The literal sync only writes
where the original literal provably equalled the original swatch colour, so a
wrong guess about the file's shape produces a skipped entry and a warning
rather than a silently wrong colour.
"""
import argparse
import collections
import copy
import json
import math
import os
import re
import sys

FAM_KEYS = ("fontname", "fontFamily", "family")
COLOUR_KEYS = ("color", "backgroundColor", "borderColor", "forecolor",
               "iconColor", "value")
TYPO = {"fontsize", "fontSize", "fontWeight", "bold", "regular", "fontStyle"}
FONT_ATTRS = {"fontsize", "fontSize", "bold", "italic", "underline", "strikethrough",
              "forecolor", "color", "fontWeight", "fontStyle", "black", "regular",
              "commentstyle", "defaultFont", "fontColorSwatchId", "includeUndo",
              "title", "subtitle", "footer"}

# Where the cached literal does not sit under a sibling of the same name.
STYLE_ALIAS = {
    "appBuildingBackgroundColor": ("backgroundStyle", "backgroundColor"),
    "appBuildingBorderColor":     ("borderStyle", "borderColor"),
    "inactiveBackgroundColor":    ("backgroundStyle", "backgroundColor"),
    "inactiveBorderColor":        ("borderStyle", "borderColor"),
    "nodeColor":                  (None, "backgroundColor"),
}


# ----------------------------------------------------------------- colour
def _srgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def lum(h):
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in _srgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


RGB_RE = re.compile(r"^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$", re.I)


def as_hex(v):
    """Normalise a colour literal to #RRGGBB, or None if it is not one.

    SAC writes some literals as rgb(...) and some as hex, for the same colour.
    Comparing without normalising leaves the rgb() ones behind.
    """
    if not isinstance(v, str):
        return None
    v = v.strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        return v.upper()
    m = RGB_RE.match(v)
    if m:
        r, g, b = (int(x) for x in m.groups())
        if max(r, g, b) < 256:
            return "#%02X%02X%02X" % (r, g, b)
    return None


def like_source(v, hexv):
    """Re-emit hexv in whatever notation v used, so the file stays consistent."""
    if RGB_RE.match(v.strip()):
        h = hexv.lstrip("#")
        return "rgb(%d, %d, %d)" % tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return hexv


def contrast(a, b="#FFFFFF"):
    if not (a.startswith("#") and b.startswith("#")):
        return None
    l1, l2 = sorted([lum(a), lum(b)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def lab(h):
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in _srgb(h))
    X = r * .4124 + g * .3576 + b * .1805
    Y = r * .2126 + g * .7152 + b * .0722
    Z = r * .0193 + g * .1192 + b * .9505
    ff = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = ff(X / .95047), ff(Y), ff(Z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def dE(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(lab(a), lab(b))))


# ----------------------------------------------------------------- swatches
def swatch_settings(doc):
    return doc["theme"]["colors"]["preferences"][0]["settings"]


def swatch_map(doc):
    return {s["id"]: s["baseColor"]
            for s in swatch_settings(doc)["swatches"]["values"]}


def apply_swatches(doc, spec):
    """Write colours into the live table AND the defaultColorSettings mirror.

    Missing the mirror means SAC's reset-to-default reverts to stock colours.
    """
    st = swatch_settings(doc)
    blocks = [st["swatches"]["values"]]
    if "defaultColorSettings" in st:
        blocks.append(st["defaultColorSettings"]["swatches"]["values"])

    want = {k: v["color"] if isinstance(v, dict) else v
            for k, v in spec.get("swatches", {}).items()}
    activate = spec.get("activate", {})

    seen, unmapped, activated = set(), set(), set()
    for vals in blocks:
        for s in vals:
            if s["id"] in activate:
                cfg = activate[s["id"]]
                s.pop("isUnassigned", None)
                s["description"] = cfg.get("description", "")
                s["baseColor"] = cfg["color"]
                activated.add(s["id"])
            elif s.get("isUnassigned"):
                continue
            elif s["id"] in want:
                s["baseColor"] = want[s["id"]]
                seen.add(s["id"])
            else:
                unmapped.add(s["id"])
    return seen, sorted(unmapped), sorted(activated), set(want) - seen


def rebuild_palettes(doc, spec):
    """Regenerate every palette colour from its own swatchIds.

    Exports routinely ship palettes whose literal colours disagree with the
    swatches they claim to reference. Deriving rather than copying fixes that.
    """
    m = swatch_map(doc)
    pal = doc["theme"]["palettes"]["preferences"][0]["settings"]["palettes"]
    n = 0
    missing = set()

    def look(sid, fallback):
        # A palette can name a swatch the table does not declare. Keep the
        # existing colour and report it rather than dying on a KeyError.
        if sid in m:
            return m[sid]
        missing.add(sid)
        return fallback

    for group in ("standard", "waterfall_standard"):
        for e in pal.get(group, []):
            old = e.get("colors", [])
            e["colors"] = [look(i, old[j] if j < len(old) else "#000000")
                           for j, i in enumerate(e.get("swatchIds", []))]
            n += 1
    for e in pal.get("gradient", []):
        old = e.get("gradient", {})
        e["gradient"] = {k: look(v, old.get(k, "#000000"))
                         for k, v in e.get("swatchIds", {}).items()}
        n += 1
    for e in pal.get("diverging", []):
        for a, b in (("startColor", "startColorSwatchId"),
                     ("midColor", "midColorSwatchId"),
                     ("endColor", "endColorSwatchId")):
            if b in e:
                e[a] = look(e[b], e.get(a, "#000000"))
        n += 1
    for e in pal.get("sequential", []):
        for a, b in (("startColor", "startColorSwatchId"),
                     ("endColor", "endColorSwatchId")):
            if b in e:
                e[a] = look(e[b], e.get(a, "#000000"))
        n += 1
    # variance and single_color hold no swatchIds - take them from the spec
    if spec.get("palettes", {}).get("variance"):
        for e in pal.get("variance", []):
            e["colors"] = list(spec["palettes"]["variance"])
            n += 1
    if spec.get("palettes", {}).get("single_color"):
        for e, c in zip(pal.get("single_color", []), spec["palettes"]["single_color"]):
            e["color"] = c
            n += 1
    if missing:
        print(f"  !! palettes reference {len(missing)} swatch id(s) this export does "
              f"not declare, left at their existing colour: {sorted(missing)[:6]}")
    return n


# ------------------------------------------------- literal <-> swatch binding
def _holder(node, key):
    if key == "swatchId":
        for ck in ("color", "value"):
            if ck in node:
                return node[ck] if isinstance(node[ck], dict) else (node, ck)
        return None
    stem = key[:-len("SwatchId")]
    if stem in STYLE_ALIAS:
        style, ck = STYLE_ALIAS[stem]
        if style is None:
            return (node, ck) if ck in node else None
        if isinstance(node.get(style), dict) and ck in node[style]:
            return (node[style], ck)
        return None
    if stem in node:
        v = node[stem]
        return v if isinstance(v, dict) else (node, stem)
    base = stem[:-5] if stem.endswith("Color") else stem
    style = base + "Style"
    if isinstance(node.get(style), dict):
        for ck in COLOUR_KEYS:
            if isinstance(node[style].get(ck), str):
                return (node[style], ck)
    for ck in COLOUR_KEYS:
        if isinstance(node.get(ck), str):
            return (node, ck)
    return None


def _descend(container, subkey):
    if subkey is not None:
        if subkey not in container:
            return None
        v = container[subkey]
        if isinstance(v, str):
            return (container, subkey)
        if isinstance(v, dict):
            for ck in COLOUR_KEYS:
                if isinstance(v.get(ck), str):
                    return (v, ck)
        return None
    for ck in COLOUR_KEYS:
        if isinstance(container.get(ck), str):
            return (container, ck)
    return None


def resolve(node, key):
    """-> [(container, literal_key, swatch_id)] for one *SwatchId key.

    The reference is sometimes a bare string and sometimes a wrapper dict
    ({path, value} or {customValue, defaultValue}); the literal beside it takes
    the matching shape.
    """
    sv = node[key]
    if isinstance(sv, str):
        slots = [(None, sv)]
    elif isinstance(sv, dict):
        slots = [(k, sv[k]) for k in ("value", "customValue", "defaultValue")
                 if isinstance(sv.get(k), str)]
    else:
        return []
    h = _holder(node, key)
    if h is None:
        return []
    out = []
    for subkey, sid in slots:
        if not sid:
            continue
        if isinstance(h, tuple):
            cont, ck = h
            if subkey is None or subkey == ck:
                out.append((cont, ck, sid))
            elif isinstance(cont.get(ck), dict):
                t = _descend(cont[ck], subkey)
                if t:
                    out.append((t[0], t[1], sid))
        else:
            t = _descend(h, subkey)
            if t:
                out.append((t[0], t[1], sid))
    return out


def sync_literals(doc, original, old_map, new_map, sections, overrides=None):
    """Refresh cached literals, verifying each against the source first.

    The check is the whole point: if the original literal does not equal the
    original swatch colour, the binding is not what it looks like (or the value
    is a deliberate override) and the entry is reported instead of written.
    """
    stats = {"synced": 0, "free": 0, "unresolved": [], "drift": [], "ambiguous": []}
    written = set()   # slots the binding pass owns; the free pass must not touch them

    # Unbound literals (swatchId "") that still carry a stock colour. Only remap
    # where that stock colour maps to exactly one new colour, else it is a guess.
    fwd = collections.defaultdict(set)
    for sid, old in old_map.items():
        h = as_hex(old)
        if h:
            fwd[h].add(new_map[sid])
    free = {k: next(iter(v)) for k, v in fwd.items() if len(v) == 1}
    ambiguous = {k for k, v in fwd.items() if len(v) > 1}
    # A source colour shared by swatches that now diverge cannot be remapped
    # automatically. spec.literalOverrides resolves those by hand.
    for k, v in (overrides or {}).items():
        h = as_hex(k) or k.upper()
        free[h] = v
        ambiguous.discard(h)

    def walk(node, orig):
        if isinstance(node, dict):
            for k in list(node):
                if not k.lower().endswith("swatchid"):
                    continue
                hits = resolve(node, k)
                ohits = resolve(orig, k) if isinstance(orig, dict) and k in orig else []
                if not hits:
                    sv = node[k]
                    sid = sv if isinstance(sv, str) else (
                        sv.get("value") if isinstance(sv, dict) else None)
                    if sid:
                        stats["unresolved"].append((k, sid))
                    continue
                for (cont, ck, sid), (ocont, ock, _) in zip(hits, ohits or hits):
                    if sid not in new_map:
                        continue
                    was = ocont.get(ock) if ohits else None
                    if was is None or str(was).lower() != str(old_map[sid]).lower():
                        stats["drift"].append((k, sid, was, old_map[sid]))
                        continue
                    cont[ck] = new_map[sid]
                    written.add((id(cont), ck))
                    stats["synced"] += 1
            for k in list(node):
                v = node.get(k)
                if isinstance(v, str) and k in COLOUR_KEYS and (id(node), k) not in written:
                    h = as_hex(v)
                    if h in free:
                        node[k] = like_source(v, free[h])
                        stats["free"] += 1
                    elif h in ambiguous:
                        stats["ambiguous"].append((k, v))
            for k, v in node.items():
                walk(v, orig.get(k) if isinstance(orig, dict) else None)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, orig[i] if isinstance(orig, list) and i < len(orig) else None)

    walk({s: doc[s] for s in sections}, {s: original[s] for s in sections})
    return stats


# ---------------------------------------------------------------- typography
def _conventions(entry, fallback):
    found = {k: collections.Counter() for k in FAM_KEYS}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in FAM_KEYS and isinstance(v, str) and v.strip():
                    found[k][v] += 1
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(entry)
    return {k: (c.most_common(1)[0][0] if c else fallback[k]) for k, c in found.items()}


def apply_font(doc, family, sections, fallback_stack=""):
    """Swap the incumbent family for the brand family, preserving quoting.

    SAC writes the same family three different ways in three different key
    names. Rewriting the token in place keeps each slot in the form SAC itself
    produced, which is the form known to work there.
    """
    tokens = collections.Counter()
    for _, node in _nodes({s: doc[s] for s in sections}):
        for k in FAM_KEYS:
            v = node.get(k)
            if isinstance(v, str) and v.strip():
                tokens[re.sub(r'^[\'"]|[\'"]$', "", v.split(",")[0].strip())] += 1
    if not tokens:
        return 0, None, collections.Counter()
    incumbent = tokens.most_common(1)[0][0]
    n = 0
    for _, node in _nodes({s: doc[s] for s in sections}):
        for k in FAM_KEYS:
            v = node.get(k)
            if isinstance(v, str) and v.strip():
                new = re.sub(re.escape(incumbent), family, v, flags=re.I)
                if fallback_stack and "," not in new:
                    new = f"{new}, {fallback_stack}"
                if new != v:
                    node[k] = new
                    n += 1
    # A theme should speak in one voice. Anything still naming a different face
    # is swept too, and reported so the change stays visible and reversible.
    strays = collections.Counter()
    generic = {"sans-serif", "serif", "monospace", "arial", "helvetica",
               "system-ui", family.lower()}
    for _, node in _nodes({s: doc[s] for s in sections}):
        for k in FAM_KEYS:
            v = node.get(k)
            if not (isinstance(v, str) and v.strip()):
                continue
            head = re.sub(r'^[\'"]|[\'"]$', "", v.split(",")[0].strip())
            if head.lower() == family.lower():
                continue
            strays[head] += 1
            node[k] = re.sub(re.escape(head), family, v, flags=re.I)
            n += 1
    return n, incumbent, strays


def _nodes(o, path=""):
    if isinstance(o, dict):
        yield path, o
        for k, v in o.items():
            yield from _nodes(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _nodes(v, f"{path}[{i}]")


def fill_font_gaps(doc, family, sections, fallback_stack=""):
    """Pin every font slot that is empty or has no family key at all.

    Both cases fall back to the SAC default at render time, which quietly
    defeats a brand font in exactly the widgets nobody thinks to check.
    """
    base = family if "," not in family else family
    quoted = {"fontname": f"'{base}'", "fontFamily": base, "family": f'"{base}"'}
    if fallback_stack:
        quoted = {k: f"{v}, {fallback_stack}" for k, v in quoted.items()}
    filled, added = 0, 0

    def go(o, conv):
        nonlocal filled, added
        if isinstance(o, dict):
            fam = [k for k in FAM_KEYS if k in o]
            if fam:
                for k in fam:
                    if isinstance(o[k], str) and not o[k].strip():
                        o[k] = conv[k]
                        filled += 1
            elif set(o) <= FONT_ATTRS and set(o) & TYPO:
                # a real font-style object that never had a family key.
                # The subset test keeps container objects (which merely hold a
                # stray fontWeight) from acquiring a font family they never had.
                k = ("fontname" if ("fontsize" in o or "forecolor" in o)
                     else "family" if ("regular" in o or "fontStyle" in o)
                     else "fontFamily")
                items = [(k, conv[k])] + list(o.items())
                o.clear()
                o.update(items)
                added += 1
            for v in list(o.values()):
                go(v, conv)
        elif isinstance(o, list):
            for v in o:
                go(v, conv)

    for sec in sections:
        for entry in doc[sec]:
            go(entry, _conventions(entry, quoted))
    return filled, added


# -------------------------------------------------------------- header bars
def apply_header_bar(doc, cfg, m):
    """Bind widget title bars to a background swatch, as many brands expect."""
    if not cfg:
        return 0
    target = cfg.get("widgetId", "sap.fpa.story.theme.tile.header")
    w = next((x for x in doc.get("widgetSettings", []) if x["id"] == target), None)
    if w is None:
        return 0
    hits = 0
    for p in w["preferences"]:
        blocks = [p["settings"]]
        if isinstance(p["settings"].get("defaultColorSettings"), dict):
            blocks.append(p["settings"]["defaultColorSettings"])
        for b in blocks:
            if (p["type"].endswith("unifiedBackgroundColor") and cfg.get("swatch")
                    and cfg["swatch"] in m):
                b["color"]["value"] = m[cfg["swatch"]]
                b["colorSwatchId"]["value"] = cfg["swatch"]
                hits += 1
            elif (p["type"].endswith("titleProperties") and cfg.get("fontSwatch")
                    and cfg["fontSwatch"] in m):
                f = b["font"]["value"]
                f["forecolor"] = m[cfg["fontSwatch"]]
                f["fontColorSwatchId"] = cfg["fontSwatch"]
                if cfg.get("fontSize"):
                    f["fontsize"] = cfg["fontSize"]
                if "bold" in cfg:
                    f["bold"] = bool(cfg["bold"])
                hits += 1
    return hits


# ------------------------------------------------------------- verification
def struct_diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a) - {"isUnassigned"}, set(b) - {"isUnassigned"}
        out += [("added", path, k) for k in kb - ka]
        out += [("removed", path, k) for k in ka - kb]
        for k in ka & kb:
            out += struct_diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(("length", path, f"{len(a)}->{len(b)}"))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += struct_diff(x, y, f"{path}[{i}]")
    elif type(a) is not type(b):
        out.append(("type", path, f"{type(a).__name__}->{type(b).__name__}"))
    return out


def report(doc, full_doc, original, spec):
    m = swatch_map(doc)
    print("\n-- contrast against the container background")
    bg = spec.get("checkAgainst", "#FFFFFF")
    rows = [(s.get("description", s["id"]), s["id"])
            for s in swatch_settings(doc)["swatches"]["values"]
            if not s.get("isUnassigned") and s["swatchType"] == "font_color"]
    # Roles meant to sit on a dark fill are measured against that fill, not the
    # canvas, so flagging them here would just train you to ignore the report.
    ON_DARK = ("contrast", "inverse", "invert")
    for name, sid in rows:
        c = contrast(m[sid], bg)
        if c is None:
            continue
        if any(t in name.lower() for t in ON_DARK):
            print(f"   {name:<20} {m[sid]:<10}    n/a   for use on dark fills")
            continue
        flag = "" if c >= 4.5 else "  <-- under 4.5:1"
        print(f"   {name:<20} {m[sid]:<10} {c:5.2f}:1{flag}")
    pal = doc["theme"]["palettes"]["preferences"][0]["settings"]["palettes"]
    cat = pal.get("standard", [{}])[0].get("colors", [])
    if len(cat) > 2:
        adj = min(dE(cat[i], cat[i + 1]) for i in range(len(cat) - 1))
        allp = min(dE(cat[i], cat[j])
                   for i in range(len(cat)) for j in range(i + 1, len(cat)))
        print(f"\n-- categorical separation: closest neighbours dE {adj:.1f}, "
              f"closest pair anywhere dE {allp:.1f}")
        if allp < 20:
            print("   under dE 20 two series will read as the same colour; reorder or respace")
    om = {s["baseColor"] for s in
          original["theme"]["colors"]["preferences"][0]["settings"]["swatches"]["values"]
          if not s.get("isUnassigned")}
    keep = {c.lower() for c in m.values()}          # colours the brand also uses
    for label, d in (("scoped", doc), ("full", full_doc)):
        blob = json.dumps(d).lower()
        left = sorted(c for c in om
                      if c.startswith("#") and c.lower() not in keep and c.lower() in blob)
        print(f"\n-- source-only colours left in the {label} file: {len(left)}")
        if left:
            print(f"   {left[:10]}{' ...' if len(left) > 10 else ''}")
    print("   (expected in the scoped file, which leaves the caches alone;")
    print("    anything left in the full file is worth investigating)")

    # Literals that match no swatch at all - widget fallbacks SAC ships with.
    # Greys are harmless; anything with real hue is an off-palette colour the
    # customer may well spot. Resolve with spec "literalOverrides" if it matters.
    orphans = collections.Counter()
    for _, node in _nodes(full_doc):
        for k, v in node.items():
            if k not in COLOUR_KEYS:
                continue
            h = as_hex(v)
            if not h or h.lower() in keep:
                continue
            r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
            if max(r, g, b) - min(r, g, b) >= 12:      # has a hue, not a grey
                orphans[v] += 1
    if orphans:
        print(f"\n-- off-palette coloured literals bound to no swatch: {len(orphans)}")
        for v, n in orphans.most_common(6):
            print(f"   {v:<22} x{n}")
        print('   add to spec "literalOverrides" if the customer would notice them')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("theme")
    ap.add_argument("spec")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()

    original = json.load(open(a.theme))
    spec = json.load(open(a.spec))
    prefix = a.prefix or re.sub(r"\W+", "-", spec.get("brand", "customer")).strip("-")
    os.makedirs(a.out_dir, exist_ok=True)

    sections = [k for k in original
                if k not in ("theme", "format", "schemaVersion", "exportedAt", "source")]

    scoped = copy.deepcopy(original)
    seen, unmapped, activated, ghosts = apply_swatches(scoped, spec)
    n_pal = rebuild_palettes(scoped, spec)
    old_map = swatch_map(original)
    new_map = swatch_map(scoped)

    print(f"swatches recoloured   : {len(seen)}")
    print(f"spare slots activated : {activated or 'none'}")
    print(f"palette entries rebuilt: {n_pal}")
    if unmapped:
        print(f"  !! assigned but absent from the spec, left at source colour: {unmapped}")
    if ghosts:
        print(f"  !! spec names swatches this export does not have: {sorted(ghosts)}")

    full = copy.deepcopy(scoped)
    st = sync_literals(full, original, old_map, new_map, sections,
                       spec.get("literalOverrides"))
    print(f"cached literals synced: {st['synced']}")
    print(f"  unbound literals remapped : {st['free']}")
    print(f"  unresolved references     : {len(st['unresolved'])}")
    print(f"  literal/swatch mismatches : {len(st['drift'])} (left alone by design)")
    if st["ambiguous"]:
        vals = sorted({v for _, v in st["ambiguous"]})
        print(f"  ambiguous unbound literals: {len(st['ambiguous'])} {vals[:6]}")
        print("     one source colour, several possible targets - resolve with")
        print('     spec "literalOverrides": {"#xxxxxx": "#yyyyyy"} if they matter')

    fnt = spec.get("font", {})
    if fnt.get("apply") and fnt.get("family"):
        stack = fnt.get("fallback", "")
        n_font, incumbent, strays = apply_font(full, fnt["family"], sections, stack)
        n_fill, n_add = fill_font_gaps(full, fnt["family"], sections, stack)
        print(f"font {incumbent!r} -> {fnt['family']!r}: {n_font} rewritten, "
              f"{n_fill} empty filled, {n_add} family keys added")
        if strays:
            print(f"  other faces also swept: {dict(strays)}")

    n_head = apply_header_bar(full, spec.get("headerBar"), new_map)
    if n_head:
        print(f"header-bar bindings   : {n_head}")

    for path, doc, label in (
            (os.path.join(a.out_dir, f"{prefix}-theme-branded.json"), scoped, "scoped"),
            (os.path.join(a.out_dir, f"{prefix}-theme-branded-full.json"), full, "full")):
        diffs = struct_diff(original, doc)
        stray = [d for d in diffs
                 if not (d[0] == "added" and d[2] in FAM_KEYS)]
        if stray:
            print(f"\nABORT: {label} file changed the schema in {len(stray)} place(s):")
            for d in stray[:6]:
                print(f"   {d}")
            return 1
        with open(path, "w") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        extra = f", {len(diffs)} intentional font-key additions" if diffs else ""
        print(f"wrote {path}  (schema verified{extra})")

    report(scoped, full, original, spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
