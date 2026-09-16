#!/usr/bin/env python3
"""
Generate branded SAC Story custom CSS.

  build_css.py branded.json --source-theme original.json \
               [--template assets/sap-sample-theme.css] \
               [--reference assets/sac-css-reference.json] \
               [--scope .acmetheme] [--font Inter] \
               [--overrides css-overrides.json] \
               [--emit-map css-overrides.json] \
               --out acme-theme.css

Custom CSS is the third layer of SAC theming, after the colour dialog and the
theme JSON. It wins over both, so a story with stock CSS still shows stock
colours no matter how well the JSON is branded.

The generator does not invent a mapping from swatch roles to selectors. SAP's
own sample CSS already encodes one - the overwhelming majority of its colour
literals are exact theme swatch values - so this rewrites that template with the
branded colours instead. Each substitution is decided from the declaration's
property (a `color:` looks at font swatches, `background-color:` at background
swatches, `fill:` at datapoint swatches), which resolves nearly all of the
ambiguity a plain find-and-replace would hit.

Anything it cannot decide is reported, never guessed. Run with --emit-map to get
those colours as a JSON stub, fill in the replacements, and pass it back with
--overrides.
"""
import argparse
import collections
import json
import os
import re
import sys

# Which swatch families a declaration may be talking about, most likely first.
# The chain is tried in order and the first family holding the colour wins.
#
# datapoint_color appears only under fill and stroke on purpose. Chart
# categorical colours have nothing to do with UI chrome, and letting them act
# as a fallback turns a button's emphasis blue into chart series 7.
#
# Charts colour their axis text with `fill` rather than `color`, so fill has to
# consider font swatches too.
PROP_FAMILY = {
    "color": ("font_color", "border_color", "background_color"),
    "background-color": ("background_color", "border_color", "font_color"),
    "background-image": ("background_color",),
    "border": ("border_color", "background_color", "font_color"),
    "border-top": ("border_color", "background_color", "font_color"),
    "border-right": ("border_color", "background_color", "font_color"),
    "border-bottom": ("border_color", "background_color", "font_color"),
    "border-left": ("border_color", "background_color", "font_color"),
    "border-color": ("border_color", "background_color", "font_color"),
    "box-shadow": ("border_color", "background_color"),
    "outline": ("border_color", "background_color"),
    "fill": ("datapoint_color", "font_color", "background_color"),
    "stroke": ("datapoint_color", "border_color"),
}

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")

# When several swatches in the same family share a stock colour, the selector
# name usually says which role is meant.
ROLE_HINTS = [
    ("data-label", "data label"), ("datalabel", "data label"),
    ("subtitle", "subtitle"), ("sub-label", "label"), ("sublabel", "label"),
    ("title", "title"), ("header", "title"),
    ("label", "label"), ("axis", "label"),
    ("selected", "selected"), ("icon", "icon"),
    ("grid-line", "grid"), ("gridline", "grid"),
]
RGB = re.compile(r"rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)", re.I)


def norm(c):
    c = c.strip()
    if c.startswith("#"):
        if len(c) == 4:
            c = "#" + "".join(ch * 2 for ch in c[1:])
        return c.upper()
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", c, re.I)
    if m:
        return "#%02X%02X%02X" % tuple(int(x) for x in m.groups())
    return None


def like(original, hexv):
    """Re-emit in the notation the template used, keeping any alpha."""
    m = re.match(r"rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*([\d.]+)\s*\)", original, re.I)
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if m:
        return f"rgba({r}, {g}, {b}, {m.group(1)})"
    if original.lower().startswith("rgb("):
        return f"rgb({r}, {g}, {b})"
    return hexv if original.startswith("#") and original[0].isupper() or True else hexv


def lch(h):
    h = h.lstrip("#")
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    X = r * .4124 + g * .3576 + b * .1805
    Y = r * .2126 + g * .7152 + b * .0722
    Z = r * .0193 + g * .1192 + b * .9505
    ff = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = ff(X / .95047), ff(Y), ff(Z / 1.08883)
    L, A, B = 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)
    import math
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def from_lch(L, C, hdeg):
    import math
    A, B = C * math.cos(math.radians(hdeg)), C * math.sin(math.radians(hdeg))
    fy = (L + 16) / 116
    fx, fz = fy + A / 500, fy - B / 200
    g = lambda t: t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787
    X, Y, Z = g(fx) * .95047, g(fy), g(fz) * 1.08883
    r = X * 3.2406 + Y * -1.5372 + Z * -0.4986
    gg = X * -0.9689 + Y * 1.8758 + Z * 0.0415
    b = X * 0.0557 + Y * -0.2040 + Z * 1.0570
    f = lambda c: 12.92 * c if c <= 0.0031308 else 1.055 * (max(c, 0) ** (1 / 2.4)) - 0.055
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, round(f(c) * 255))) for c in (r, gg, b))


def suggest(colour, brand_hues, brand_neutrals):
    """Derive a branded equivalent for a CSS-only tone.

    Keeps the tone's lightness and saturation - which is what makes a pale
    hover fill read as a pale hover fill - and moves only its hue onto the
    nearest brand hue. Near-greys keep their hue, since a grey is already
    brand-neutral.
    """
    L, C, h = lch(colour)
    if C < 8 or not brand_hues:
        return None                       # a grey; leave it alone
    nearest = min(brand_hues, key=lambda bh: min(abs(bh - h), 360 - abs(bh - h)))
    return from_lch(L, C, nearest)


def swatches(doc):
    vals = doc["theme"]["colors"]["preferences"][0]["settings"]["swatches"]["values"]
    return [s for s in vals if not s.get("isUnassigned")]


def protect_comments(css):
    store = []

    def keep(m):
        store.append(m.group(0))
        return f"\x00C{len(store) - 1}\x00"

    return re.sub(r"/\*.*?\*/", keep, css, flags=re.S), store


def restore_comments(css, store):
    return re.sub(r"\x00C(\d+)\x00", lambda m: store[int(m.group(1))], css)


# Role inference for selectors the template never styles. Tokens are tested in
# order and the first match wins, so put the specific ones first.
EXTEND_RULES = [
    ("-page",        [("background-color", "pagebg")]),
    ("grid-line",    [("border-color", "grid")]),
    ("freeze-line",  [("border-color", "grid")]),
    ("axis-line",    [("stroke", "axis"), ("border-color", "axis")]),
    ("sub-label",    [("color", "label"), ("fill", "label")]),
    ("subtitle",     [("color", "subtitle"), ("fill", "subtitle")]),
    ("main-label",   [("color", "label"), ("fill", "label")]),
    ("data-label",   [("color", "datalabel"), ("fill", "datalabel")]),
    ("title",        [("color", "title"), ("fill", "title")]),
    ("header",       [("color", "title"), ("background-color", "container")]),
    ("selected",     [("background-color", "listselected"), ("color", "selected")]),
    ("placeholder",  [("color", "label")]),
    ("label",        [("color", "label"), ("fill", "label")]),
    ("icon",         [("color", "icon"), ("fill", "icon")]),
    ("arrow",        [("color", "icon")]),
    ("-widget",      [("background-color", "container")]),
    ("panel",        [("background-color", "container")]),
    ("item",         [("color", "main"), ("background-color", "container")]),
    ("content",      [("color", "main")]),
    ("value",        [("color", "main")]),
    ("text",         [("color", "main")]),
]

# Which swatch description each role wants, in order of preference.
ROLE_WANTS = {
    "main":         ["main font"],
    "title":        ["titles", "group title", "main font"],
    "subtitle":     ["subtitles", "labels"],
    "label":        ["labels", "main font"],
    "datalabel":    ["data label", "main font"],
    "selected":     ["selected", "main font"],
    "icon":         ["icon default", "selected"],
    "container":    ["containers"],
    "listselected": ["list selected", "containers"],
    "grid":         ["grid lines", "list"],
    "pagebg":       ["main pages", "containers"],
    "axis":         ["axis line", "grid lines"],
}


def role_colour(role, by_desc):
    for want in ROLE_WANTS.get(role, []):
        if want in by_desc:
            return by_desc[want]
    return None


def extend_css(ref, sel_props, covered, by_desc, scope, font, fallback=""):
    """Emit rules for object types the template leaves untouched.

    SAP's sample is an example, not a complete implementation, so a theme built
    from it alone leaves a good number of widget types rendering stock. These
    are generated conservatively - only selectors whose name clearly indicates
    a role, only properties the reference lists as supported.
    """
    out, made = [], collections.Counter()
    for o in sorted(ref["objectTypes"], key=lambda x: x["objectType"]):
        if o["objectType"] in covered:
            continue
        block = []
        for c in o["classes"]:
            sel = c["selector"]
            if not sel.startswith(".") or sel not in sel_props:
                continue
            low = sel.lower()
            decls = []
            for token, pairs in EXTEND_RULES:
                if token not in low:
                    continue
                for prop, role in pairs:
                    if prop not in sel_props[sel]:
                        continue
                    col = role_colour(role, by_desc)
                    if col and col.startswith("#"):
                        decls.append((prop, col))
                break
            if font and "font-family" in sel_props[sel] and decls:
                stack = f"'{font}', {fallback}" if fallback else f"'{font}'"
                decls.append(("font-family", stack))
            if decls:
                seen, uniq = set(), []
                for prop, val in decls:
                    if prop in seen:
                        continue
                    seen.add(prop)
                    uniq.append(f"    {prop}: {val};")
                block.append(f"{scope} {sel} {{\n" + "\n".join(uniq) + "\n}")
                made[o["objectType"]] += 1
        if block:
            out.append(f"/* {o['objectType'].upper()} "
                       + "-" * max(4, 58 - len(o["objectType"])) + " */")
            out.extend(block)
            out.append("")
    return "\n".join(out), made


def load_reference(path):
    d = json.load(open(path))
    sel_props, sel_owner = {}, {}
    for o in d["objectTypes"]:
        for c in o["classes"]:
            s = c["selector"]
            if not s.startswith("."):
                continue
            sel_props.setdefault(s, set()).update(c["properties"])
            sel_owner.setdefault(s, set()).add(o["objectType"])
            for dsc in c.get("descendants", []):
                ds = dsc.get("selector") if isinstance(dsc, dict) else dsc
                if isinstance(ds, str) and ds.startswith("."):
                    sel_props.setdefault(ds, set()).update(
                        dsc.get("properties", c["properties"]) if isinstance(dsc, dict)
                        else c["properties"])
                    sel_owner.setdefault(ds, set()).add(o["objectType"])
    return d, sel_props, sel_owner


def validate(css, sel_props, sel_owner):
    """Report selectors the reference does not know and properties it does not
    list for them. SAC silently ignores both, so a rule that looks fine can do
    nothing at all."""
    bare, css_nc = [], protect_comments(css)[0]
    unknown_sel = collections.Counter()
    bad_prop = collections.Counter()
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css_nc):
        props = {p.strip().lower()
                 for p, _ in re.findall(r"([a-zA-Z-]+)\s*:\s*([^;{}]+)", body)}
        for part in sel.replace("\n", " ").split(","):
            toks = " ".join(part.split()).split()
            if not toks:
                continue
            # Match against the reference's own selector list. Most predefined
            # classes are .sap-custom-*, but not all of them are.
            cand = [re.sub(r"::?[a-z-]+$", "", t) for t in toks if t.startswith(".")]
            known = [t for t in cand if t in sel_props]
            if known:
                t = known[-1]
            else:
                looks = [t for t in cand if t.startswith((".sap-custom", ".sap-plan"))]
                if not looks:
                    continue
                unknown_sel[looks[-1]] += 1
                continue
            if len(toks) == 1:
                bare.append(t)
            for p in props:
                if p not in sel_props[t]:
                    bad_prop[(t, p)] += 1
    return unknown_sel, bad_prop, bare


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("branded")
    ap.add_argument("--source-theme", required=True,
                    help="the original stock export, to read the 'before' colours")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--template", default=os.path.join(here, "assets", "sap-sample-theme.css"))
    ap.add_argument("--reference", default=os.path.join(here, "assets", "sac-css-reference.json"))
    ap.add_argument("--scope", default="",
                    help="scope class to write the rules against, e.g. .acmetheme. "
                         "Defaults to one derived from --brand.")
    ap.add_argument("--brand", default="",
                    help="customer name, used to derive the scope class when "
                         "--scope is not given")
    ap.add_argument("--font", default="")
    ap.add_argument("--font-fallback", default="",
                    help="stack appended where a rule names only one face, e.g. "
                         "'Arial, Helvetica, sans-serif'. Without it, a face that "
                         "fails to load drops to the browser default, which is "
                         "usually a serif.")
    ap.add_argument("--overrides", default="")
    ap.add_argument("--emit-map", default="")
    ap.add_argument("--extend", action="store_true",
                    help="also generate rules for object types the template never styles")
    ap.add_argument("--out", default="theme.css")
    a = ap.parse_args()

    # The template ships scoped under SAP's own class name. Leaving that in a
    # branded deliverable means the customer's designers assign ".saptheme" to
    # their widgets, which reads like the rebrand never happened - so derive a
    # scope from the brand rather than defaulting to SAP's.
    if not a.scope and a.brand:
        slug = re.sub(r"[^a-z0-9]", "", a.brand.split()[0].lower())
        if slug:
            a.scope = f".{slug}theme"
            print(f"scope class derived from --brand: {a.scope}")

    # This script writes a selector, preview_dashboard.py takes a bare class
    # name, and it is easy to hand one the other's form. A dotless scope here
    # compiles every rule to "acmetheme .sap-custom-..." - valid CSS that
    # matches nothing, so the stylesheet is silently inert. On a light theme
    # that is nearly invisible, because unstyled text falls back to black and
    # passes for the intended dark type. Normalise rather than fail.
    if a.scope and not a.scope.startswith("."):
        a.scope = "." + a.scope
        print(f"!! --scope had no leading dot: using {a.scope}\n"
              "   (this script wants a selector; preview_dashboard.py wants the\n"
              "    bare class name)")

    new = json.load(open(a.branded))
    old = json.load(open(a.source_theme))
    css = open(a.template, encoding="utf-8-sig").read()
    ref, sel_props, sel_owner = load_reference(a.reference)

    # colour -> {family: {new colours}} taken from the stock export
    # colour -> family -> [(order, role, new colour)], ordered by swatch number
    # so the family's primary swatch is the natural default.
    idx = collections.defaultdict(lambda: collections.defaultdict(list))
    newmap = {s["id"]: s["baseColor"] for s in swatches(new)}
    for s in swatches(old):
        c = norm(s["baseColor"])
        if c and s["id"] in newmap:
            n = int(re.search(r"(\d+)$", s["id"]).group(1))
            idx[c][s["swatchType"]].append(
                (n, (s.get("description") or "").lower(), newmap[s["id"]]))
    for c in idx:
        for f in idx[c]:
            idx[c][f].sort()

    # Hues a CSS-only tone may snap to. Chart series colours are deliberately
    # excluded: a categorical palette spans the whole wheel, so including it
    # makes "nearest brand hue" always land back on the original hue and the
    # derivation does nothing. What is left is the chrome (overwhelmingly the
    # primary) plus the semantic tones, which is what a stray SAP pastel should
    # actually become.
    SEMANTIC = ("neutral", "positive", "negative", "warning")
    brand_hues, brand_neutrals = [], []
    for s in swatches(new):
        col = norm(s["baseColor"])
        if not col:
            continue
        desc = (s.get("description") or "").lower()
        if s["swatchType"] == "datapoint_color" and not any(w in desc for w in SEMANTIC):
            continue
        L, C, h = lch(col)
        (brand_hues if C >= 12 else brand_neutrals).append(h if C >= 12 else col)

    overrides = {}
    if a.overrides:
        raw = json.load(open(a.overrides))
        overrides = {norm(k) or k.upper(): v
                     for k, v in raw.items() if not k.startswith("_")}

    body, comments = protect_comments(css)

    stats = collections.Counter()
    unmapped = collections.defaultdict(lambda: {"count": 0, "props": set(), "where": []})
    ambiguous = collections.defaultdict(lambda: {"count": 0, "props": set()})

    # Walk rule bodies so each colour is decided with its property in hand.
    def do_rule(m):
        sel, inner = m.group(1), m.group(2)

        def do_decl(dm):
            prop, val = dm.group(1).strip().lower(), dm.group(2)

            def do_colour(cm):
                raw = cm.group(0)
                c = norm(raw)
                if not c:
                    return raw
                if c in overrides:
                    stats["override"] += 1
                    return like(raw, overrides[c])
                rows = []
                if c in idx:
                    for f in PROP_FAMILY.get(prop, ()):
                        if idx[c].get(f):
                            rows = sorted(idx[c][f])   # first family that has it
                            break
                if rows:
                    distinct = {r[2] for r in rows}
                    if len(distinct) == 1:
                        stats["mapped"] += 1
                        return like(raw, rows[0][2])
                    low = " ".join(sel.split()).lower()
                    for token, role in ROLE_HINTS:
                        if token in low:
                            hit = [r for r in rows if role in r[1]]
                            if hit:
                                stats["mapped"] += 1
                                stats["by_role"] += 1
                                return like(raw, hit[0][2])
                    # no hint: take the family's primary swatch, and say so
                    ambiguous[c]["count"] += 1
                    ambiguous[c]["props"].add(prop)
                    ambiguous[c]["chose"] = rows[0][2]
                    ambiguous[c]["among"] = sorted(distinct)
                    stats["mapped"] += 1
                    stats["by_default"] += 1
                    return like(raw, rows[0][2])
                u = unmapped[c]
                u["count"] += 1
                u["props"].add(prop)
                if len(u["where"]) < 3:
                    clean = re.sub(r"\x00C\d+\x00", "", sel)
                    u["where"].append(" ".join(clean.split())[:70])
                stats["unmapped"] += 1
                return raw

            return f"{dm.group(1)}:{HEX.sub(do_colour, RGB.sub(do_colour, val))}"

        inner = re.sub(r"([a-zA-Z-]+)\s*:([^;{}]+)", do_decl, inner)
        return f"{sel}{{{inner}}}"

    body = re.sub(r"([^{}]+)\{([^{}]*)\}", do_rule, body)

    # font family
    # Comments are protected during the colour pass, so any font-family inside
    # one survives. SAP's sample has deliberately commented-out font rules; the
    # line stays commented, but the name in it is updated so the delivered file
    # does not carry a stale typeface for someone to grep up or re-enable.
    if a.font:
        fams = collections.Counter(
            re.findall(r"font-family\s*:\s*([^;}\n]+)", body, re.I))
        n = 0
        for raw, _ in fams.most_common():
            head = raw.strip().strip("'\"").split(",")[0].strip().strip("'\"")
            if head.lower() == a.font.lower():
                continue
            body, k = re.subn(re.escape(head), a.font, body)
            n += k
        if a.font_fallback:
            def add_stack(m):
                decl = m.group(1)
                if "," in decl:
                    return m.group(0)
                return f"font-family:{decl.rstrip()}, {a.font_fallback}"
            body, stacked = re.subn(r"font-family\s*:([^;}\n]+)", add_stack, body)
            stats["font_stack"] = stacked
        stats["font"] = n
        cn = 0
        for i, c in enumerate(comments):
            if "font-family" in c.lower():
                new_c = re.sub(r"font-family\s*:\s*([^;*]+)", lambda mm: re.sub(
                    r"'[^']+'|\"[^\"]+\"|[\w-]+", lambda t: t.group(0)
                    if t.group(0).strip("'\"").lower() in
                    ("arial", "helvetica", "sans-serif", "serif", a.font.lower())
                    else f"'{a.font}'", mm.group(1), count=1),
                    c, flags=re.I)
                if new_c != c:
                    comments[i] = new_c
                    cn += 1
        stats["font_comment"] = cn

    # scope class
    if not a.scope:
        print("!! no --scope or --brand given: the output keeps the template's own\n"
              "   scope class. Check it before shipping - a branded CSS should not\n"
              "   ask designers to assign SAP's sample class name.")
    if a.scope:
        scopes = collections.Counter(
            m.group(1) for m in re.finditer(r"(\.[\w-]+)\s+\.sap-custom", body))
        if scopes:
            top = scopes.most_common(1)[0][0]
            body, k = re.subn(re.escape(top) + r"(?=\s+\.sap-custom)", a.scope, body)
            stats["scope"] = k
            print(f"scope class {top} -> {a.scope} ({k} rules)")

    out_css = restore_comments(body, comments)

    if a.extend:
        _, _, _ = validate(out_css, sel_props, sel_owner)
        covered = set()
        for sel, _b in re.findall(r"([^{}]+)\{([^{}]*)\}",
                                  protect_comments(out_css)[0]):
            for part in sel.replace("\n", " ").split(","):
                for t in " ".join(part.split()).split():
                    if t.startswith("."):
                        covered |= sel_owner.get(re.sub(r"::?[a-z-]+$", "", t), set())
        by_desc = {(s.get("description") or "").lower(): s["baseColor"]
                   for s in swatches(new)}
        scope = a.scope or "." + (
            collections.Counter(m.group(1) for m in
                                re.finditer(r"(\.[\w-]+)\s+\.sap-custom", out_css)
                                ).most_common(1) or [(".saptheme", 0)])[0][0].lstrip(".")
        extra, made = extend_css(ref, sel_props, covered, by_desc, scope,
                                 a.font, a.font_fallback)
        if extra:
            out_css += (
                "\n\n/*==================================================================*/\n"
                "/* GENERATED - object types the source template did not style.      */\n"
                "/* Roles were inferred from selector names; review before shipping. */\n"
                "/*==================================================================*/\n\n"
                + extra)
            print(f"\nextended: {sum(made.values())} rules across {len(made)} "
                  f"previously unstyled object types")
            print(f"   {', '.join(sorted(made))}")

    print(f"colour literals mapped : {stats['mapped']}")
    if stats["override"]:
        print(f"  from overrides       : {stats['override']}")
    if stats["font"]:
        print(f"font-family rewritten  : {stats['font']}"
              + (f" (+{stats['font_comment']} inside comments)"
                 if stats["font_comment"] else ""))
        if stats["font_stack"]:
            print(f"  fallback stack added : {stats['font_stack']}")

    if stats["by_role"]:
        print(f"  resolved by selector role: {stats['by_role']}")
    if ambiguous:
        print(f"\nresolved to the family's primary swatch ({len(ambiguous)} colours, "
              f"{stats['by_default']} uses) - several branded targets and no role hint "
              "in the selector:")
        for c, d in sorted(ambiguous.items(), key=lambda t: -t[1]["count"])[:8]:
            print(f"   {c} x{d['count']:<4} -> {d.get('chose')}   among {d.get('among')}"
                  f"  via {sorted(d['props'])[:3]}")
        print("   override any of these in the map if the default is wrong")

    if unmapped:
        print(f"\nnot in the swatch table ({len(unmapped)} colours, {stats['unmapped']} "
              "uses) - CSS-only tones the JSON theme never carried:")
        for c, d in sorted(unmapped.items(), key=lambda t: -t[1]["count"])[:12]:
            print(f"   {c}  x{d['count']:<4} {sorted(d['props'])[:2]}  {d['where'][0] if d['where'] else ''}")

    if a.emit_map:
        review = []
        stub = {}
        for c, d in sorted(ambiguous.items(), key=lambda t: -t[1]["count"]):
            stub[c] = d.get("chose", "")
            review.append(f"{c} -> {d.get('chose')} (family primary; alternatives "
                          f"{d.get('among')}) x{d['count']}")
        for c, d in sorted(unmapped.items(), key=lambda t: -t[1]["count"]):
            sg = suggest(c, brand_hues, brand_neutrals)
            stub[c] = sg or c
            L, C, _ = lch(c)
            kind = ("grey, left as-is" if not sg
                    else f"hue moved to nearest brand hue, L{L:.0f} C{C:.0f} kept")
            review.append(f"{c} -> {stub[c]} ({kind}) x{d['count']} "
                          f"{sorted(d['props'])[:2]}")
        stub = {"_comment": [
            "Every value below is a DERIVED SUGGESTION, not a decision. Review them.",
            "Two kinds of entry:",
            " - colours where several branded swatches shared one stock colour, set",
            "   to the family's primary swatch;",
            " - CSS-only tones with no swatch behind them (pale fills, hover states,",
            "   semantic pastels), given the brand's nearest hue at the same",
            "   lightness and saturation so a pale fill stays a pale fill.",
            "Greys are left alone - a grey is already brand-neutral.",
            "Edit, then pass back with --overrides."],
            "_review": review, **stub}
        json.dump(stub, open(a.emit_map, "w"), indent=2)
        print(f"\nwrote {a.emit_map} ({len(stub) - 2} colours, all pre-filled with "
              "suggestions to review)")

    unknown_sel, bad_prop, bare = validate(out_css, sel_props, sel_owner)
    print(f"\nvalidated against the reference "
          f"({ref['stats']['uniquePredefinedSelectorCount']} known selectors, "
          f"{ref['stats']['supportedPropertyCount']} supported properties)")
    if unknown_sel:
        print(f"   !! {len(unknown_sel)} selector(s) the reference does not list: "
              f"{list(unknown_sel)[:5]}")
    if bad_prop:
        print(f"   !! {len(bad_prop)} property/selector pairs not documented as supported:")
        for (s, p), n in bad_prop.most_common(6):
            print(f"      {p} on {s}")
        print("      SAC ignores these silently - drop them or accept they do nothing")
    if not unknown_sel and not bad_prop:
        print("   every selector and property is documented as supported")

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(out_css)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
