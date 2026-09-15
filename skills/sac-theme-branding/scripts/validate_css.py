#!/usr/bin/env python3
"""
Check a SAC custom CSS file against the support reference.

  validate_css.py theme.css [--reference assets/sac-css-reference.json]
                  [--colours] [--verbose]

SAC ignores unsupported selectors and properties silently - no error, no
warning, the rule simply does nothing. That makes a CSS file easy to get
subtly wrong and hard to debug in the tenant, which is what this is for.

Run it on the customer's existing CSS before you start, to see what they
already cover, and on anything you hand-edit afterwards.

Reports:
  - selectors the reference does not list at all
  - properties not documented as supported on the selector they are used with
  - unscoped rules, which apply to every widget of that type rather than only
    the ones a designer opts in
  - which of the object types your CSS reaches, and which it leaves untouched
  - with --colours, every colour literal and where it is used
"""
import argparse
import collections
import json
import os
import re
import sys


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
            for p in c.get("pseudos", []):
                sel_props.setdefault(s + p, set()).update(c["properties"])
                sel_owner.setdefault(s + p, set()).add(o["objectType"])
    return d, sel_props, sel_owner


def rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        props = [(p.strip().lower(), v.strip())
                 for p, v in re.findall(r"([a-zA-Z-]+)\s*:([^;{}]+)", body)]
        for part in sel.replace("\n", " ").split(","):
            toks = " ".join(part.split()).split()
            if toks:
                yield toks, props


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("css")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--reference",
                    default=os.path.join(here, "assets", "sac-css-reference.json"))
    ap.add_argument("--colours", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    css = open(a.css, encoding="utf-8-sig").read()
    ref, sel_props, sel_owner = load_reference(a.reference)

    unknown = collections.Counter()
    badprop = collections.Counter()
    unscoped = collections.Counter()
    touched = collections.Counter()
    scopes = collections.Counter()
    colours = collections.defaultdict(lambda: {"n": 0, "props": set(), "where": []})
    n_rules = 0

    for toks, props in rules(css):
        n_rules += 1
        # Match against the reference's selector list rather than a name
        # prefix: most predefined classes are .sap-custom-*, but not all.
        cand = [re.sub(r"::?[a-z-]+$", "", t) for t in toks if t.startswith(".")]
        known = [t for t in cand if t in sel_props]
        if known:
            base = known[-1]
        else:
            looks = [t for t in cand if t.startswith((".sap-custom", ".sap-plan"))]
            if not looks:
                continue
            unknown[looks[-1]] += 1
            continue
        for ot in sel_owner[base]:
            touched[ot] += 1
        if len(toks) == 1:
            unscoped[base] += 1
        else:
            scopes[toks[0]] += 1
        for p, v in props:
            if p not in sel_props[base]:
                badprop[(base, p)] += 1
            if a.colours:
                for c in re.findall(r"#[0-9A-Fa-f]{3,8}\b|rgba?\([^)]*\)", v):
                    d = colours[c.upper()]
                    d["n"] += 1
                    d["props"].add(p)
                    if len(d["where"]) < 2:
                        d["where"].append(base)

    print(f"{a.css}: {n_rules} rules")
    print(f"reference: {ref['stats']['uniquePredefinedSelectorCount']} selectors, "
          f"{ref['stats']['supportedPropertyCount']} properties, "
          f"{ref['stats']['objectTypeCount']} object types\n")

    if unknown:
        print(f"UNKNOWN SELECTORS ({len(unknown)}) - not in the reference, so SAC will "
              "ignore them:")
        for s, n in unknown.most_common(15):
            print(f"   {s}  x{n}")
        print()

    if badprop:
        print(f"UNSUPPORTED PROPERTIES ({len(badprop)}) - the selector exists but does "
              "not accept these:")
        for (s, p), n in badprop.most_common(20):
            print(f"   {p:<18} on {s}  x{n}")
        print()

    if scopes:
        print("SCOPE CLASSES - rules apply only to widgets assigned these classes:")
        for s, n in scopes.most_common(12):
            print(f"   {s:<32} {n} rules")
        print()

    if unscoped:
        print(f"UNSCOPED ({len(unscoped)}) - these hit every widget of the type, whether "
              "or not the designer opted in:")
        for s, n in unscoped.most_common(10):
            print(f"   {s}  x{n}")
        print()

    all_types = {o["objectType"] for o in ref["objectTypes"]}
    missed = sorted(all_types - set(touched))
    print(f"COVERAGE: {len(touched)} of {len(all_types)} object types styled")
    if a.verbose and touched:
        for t, n in touched.most_common():
            print(f"   {t:<34} {n} rules")
    if missed:
        print(f"   not styled ({len(missed)}): {', '.join(missed)}")
        print("   unstyled widgets fall back to SAC defaults, which will look stock")

    if a.colours and colours:
        print(f"\nCOLOURS ({len(colours)} distinct):")
        for c, d in sorted(colours.items(), key=lambda t: -t[1]["n"])[:30]:
            print(f"   {c:<24} x{d['n']:<4} {sorted(d['props'])[:3]}  {d['where'][0]}")

    problems = len(unknown) + len(badprop)
    print(f"\n{'OK - nothing SAC will silently ignore' if not problems else f'{problems} issue(s) to fix'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
