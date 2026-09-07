#!/usr/bin/env python3
"""
Render a one-page specimen sheet from a built theme.

  make_preview.py branded.json --out preview.html [--brand "Acme"]
                  [--font Montserrat] [--source "where the palette came from"]

Every colour and the typeface are read out of the theme file, so the sheet
cannot drift from what will actually be imported. Give this to the customer for
sign-off before anyone touches the tenant - it is far cheaper to argue about a
colour here than after the story is themed.

If you have screenshots of their existing reports, mirror that layout in the
mock canvas. A specimen that looks like their own dashboard gets signed off;
a grid of colour chips gets questions.
"""
import argparse
import html
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("theme")
    ap.add_argument("--out", default="preview.html")
    ap.add_argument("--brand", default="Customer")
    ap.add_argument("--font", default="")
    ap.add_argument("--source", default="")
    a = ap.parse_args()

    doc = json.load(open(a.theme))
    S = {s["id"]: s for s in
         doc["theme"]["colors"]["preferences"][0]["settings"]["swatches"]["values"]
         if not s.get("isUnassigned")}
    PAL = doc["theme"]["palettes"]["preferences"][0]["settings"]["palettes"]

    def C(sid, default="#000000"):
        return S[sid]["baseColor"] if sid in S else default

    def lum(h):
        h = h.lstrip("#")
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (f(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
        return .2126 * r + .7152 * g + .0722 * b

    def cr(c, b="#FFFFFF"):
        if not c.startswith("#"):
            return None
        l1, l2 = sorted([lum(c), lum(b)], reverse=True)
        return (l1 + .05) / (l2 + .05)

    header = C("BackgroundColor_30", C("BackgroundColor_4", "#333333"))
    onhdr = C("FontColor_7", "#FFFFFF")
    ink = C("FontColor_1")
    title = C("FontColor_3", ink)
    label = C("FontColor_6", "#666666")
    sub = C("FontColor_4", label)
    page = C("BackgroundColor_1", "#F5F5F5")
    card = C("BackgroundColor_2", "#FFFFFF")
    line = C("BorderColor_22", "#DDDDDD")
    grid = C("BorderColor_6", "#EEEEEE")
    hover = C("BackgroundColor_8", "#EEEEEE")
    emph = C("BackgroundColor_16", header)
    emphb = C("BorderColor_13", emph)
    btn = C("BackgroundColor_10", "#FFFFFF")
    btnb = C("BorderColor_7", line)
    btnf = C("FontColor_10", ink)
    cat = PAL.get("standard", [{}])[0].get("colors", ["#888888"] * 4)
    font = a.font or "system-ui"

    def chips(colors, keys=None, h=48):
        cells = "".join(f'<div style="flex:1;height:{h}px;background:{c}"></div>'
                        for c in colors)
        out = f'<div class="band">{cells}</div>'
        if keys:
            out += ('<div class="keys">'
                    + "".join(f"<span>{html.escape(k)}</span>" for k in keys)
                    + "</div>")
        return out

    def table(prefix):
        rows = []
        for s in S.values():
            if not s["id"].startswith(prefix):
                continue
            c = s["baseColor"]
            swatch = (f'<i style="background:{c}"></i>' if c.startswith("#")
                      else '<i class="tsp"></i>')
            r = cr(c)
            rows.append(
                f'<tr><td>{swatch}</td><td class="mono">{html.escape(c)}</td>'
                f'<td>{html.escape(s.get("description") or "&mdash;")}</td>'
                f'<td class="mono dim">{s["id"]}</td>'
                f'<td class="mono dim n">{f"{r:.1f}" if r else "&mdash;"}</td></tr>')
        return "\n".join(rows)

    # illustrative figures - replace with the customer's own if you have them
    kpis = [("Total actuals", "4,812,900"), ("Committed", "612,430"),
            ("Forecast", "5,425,330"), ("Variance", "(184,220)")]
    bars = [("Q1", 62, 14), ("Q2", 71, 9), ("Q3", 48, 21), ("Q4", 88, 12)]
    rows = [("Programme delivery", "2,140,880", "301,220", "2,442,100"),
            ("Platform build", "1,204,880", "96,110", "1,300,990"),
            ("Integration", "742,015", "41,850", "783,865"),
            ("Total", "4,087,775", "439,180", "4,526,955")]

    BW, BH, PADB = 520, 250, 28
    mx = max(x + y for _, x, y in bars)
    plot = BH - PADB - 20
    step = BW / len(bars)
    svg = "".join(
        f'<line x1="0" x2="{BW}" y1="{BH - PADB - plot * f:.0f}" '
        f'y2="{BH - PADB - plot * f:.0f}" stroke="{grid}"/>'
        for f in (.25, .5, .75, 1))
    for i, (nm, v1, v2) in enumerate(bars):
        h1, h2 = v1 / mx * plot, v2 / mx * plot
        x, w = i * step + step * .22, step * .56
        y1 = BH - PADB - h1
        svg += (f'<rect x="{x:.0f}" y="{y1:.0f}" width="{w:.0f}" height="{h1:.0f}" fill="{cat[0]}"/>'
                f'<rect x="{x:.0f}" y="{y1 - h2:.0f}" width="{w:.0f}" height="{h2:.0f}" '
                f'fill="{cat[1] if len(cat) > 1 else cat[0]}"/>'
                f'<text x="{x + w / 2:.0f}" y="{y1 - h2 - 6:.0f}" text-anchor="middle" '
                f'class="dl">{v1 + v2}</text>'
                f'<text x="{x + w / 2:.0f}" y="{BH - 8}" text-anchor="middle" class="ax">{nm}</text>')
    svg += f'<line x1="0" x2="{BW}" y1="{BH - PADB}" y2="{BH - PADB}" stroke="{C("BorderColor_5", grid)}"/>'

    kpi_html = "".join(f'<div class="kpi"><p class="hbar">{html.escape(k)}</p>'
                       f'<p class="kv">{v}</p></div>' for k, v in kpis)
    row_html = "".join(
        f'<tr{" class=tot" if r[0] == "Total" else ""}><td>{html.escape(r[0])}</td>'
        + "".join(f'<td class="n">{x}</td>' for x in r[1:]) + "</tr>" for r in rows)

    seq = [C(f"DatapointColor_{i}") for i in (29, 28, 27, 21, 22, 23, 24, 25, 26)
           if f"DatapointColor_{i}" in S]
    ibcs = [C(f"DatapointColor_{i}") for i in range(33, 42) if f"DatapointColor_{i}" in S]
    sem = [C(f"DatapointColor_{i}") for i in range(13, 21) if f"DatapointColor_{i}" in S]
    div = PAL.get("diverging", [{}])[0]
    divc = [div.get(k) for k in ("startColor", "midColor", "endColor") if div.get(k)]

    doc_html = f"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(a.brand)} theme for SAP Analytics Cloud</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:{ink};
 font:400 15.5px/1.55 {font},"Segoe UI",system-ui,sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:60px 28px 110px}}
h1{{font-weight:600;font-size:33px;letter-spacing:-.015em;margin:0 0 10px;color:{title}}}
h2{{font-weight:600;font-size:19px;margin:0;color:{title}}}
h3{{font-weight:600;font-size:14px;margin:0 0 10px;color:{sub}}}
p{{margin:0 0 14px;max-width:66ch}}
.meta{{color:{label};font-size:13.5px;margin:0}}
section{{margin-top:52px}}
.shead{{border-top:2px solid {title};padding-top:14px;margin-bottom:20px}}
.shead p{{color:{label};font-size:14px;margin:6px 0 0}}
.canvas{{background:{page};border:1px solid {line};padding:18px}}
.cbar{{display:flex;align-items:center;gap:10px;margin-bottom:14px}}
.cbar .t{{font-weight:600;font-size:16px;margin-right:auto;color:{title}}}
.btn{{font:500 13px/1 {font},sans-serif;padding:8px 14px;border-radius:3px}}
.btn.em{{background:{emph};color:{onhdr};border:1px solid {emphb}}}
.btn.st{{background:{btn};color:{btnf};border:1px solid {btnb}}}
.hbar{{margin:0;background:{header};color:{onhdr};font-size:10.5px;font-weight:600;
 letter-spacing:.06em;text-transform:uppercase;padding:5px 9px;text-align:center}}
.grid4{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}}
.kv{{margin:0;padding:11px 9px;font-size:19px;font-weight:600;text-align:center;
 color:{title};background:{card};border:1px solid {line};border-top:0}}
.two{{display:grid;grid-template-columns:.92fr 1.22fr;gap:12px;align-items:stretch}}
.two>div{{display:flex;flex-direction:column;min-width:0}}
.widget{{background:{card};border:1px solid {line};border-top:0;flex:1;
 display:flex;min-width:0;overflow:hidden}}
.widget .body{{padding:12px 14px 8px;flex:1;display:flex;flex-direction:column}}
.widget .body svg{{flex:1;min-height:0}}
.ws{{margin:0 0 10px;font-size:12px;color:{sub};font-weight:500}}
svg text.dl{{font:500 11px {font},sans-serif;fill:{C("FontColor_13", ink)}}}
svg text.ax{{font:400 11px {font},sans-serif;fill:{label}}}
table{{border-collapse:collapse;width:100%}}
.dt th{{background:{header};color:{onhdr};font-weight:600;font-size:11px;
 text-align:left;padding:7px 8px;white-space:nowrap}}
.dt td{{padding:7px 8px;font-size:12px;white-space:nowrap;border-bottom:1px solid {C("BorderColor_2", grid)}}}
.dt tr:hover td{{background:{hover}}}
.dt tr.tot td{{font-weight:600;border-top:1px solid {C("BorderColor_5", line)};border-bottom:0}}
.dt tr.tot:hover td{{background:transparent}}
.n{{text-align:right;font-variant-numeric:tabular-nums}}
.band{{display:flex;border:1px solid {line};overflow:hidden}}
.keys{{display:flex;margin-top:6px}}
.keys span{{flex:1;text-align:center;font-family:ui-monospace,Menlo,Consolas,monospace;
 font-size:10.5px;color:{label};letter-spacing:-.02em}}
.pal{{margin-bottom:28px}}
.cols{{display:grid;grid-template-columns:1fr 1.12fr;gap:30px}}
@media(max-width:720px){{.cols,.two,.grid4{{grid-template-columns:1fr}}}}
.st td{{padding:6px 8px 6px 0;font-size:12.5px;white-space:nowrap;
 border-bottom:1px solid {C("BorderColor_2", grid)};vertical-align:middle}}
.st i{{display:block;width:26px;height:20px;border:1px solid rgba(0,0,0,.14)}}
.st i.tsp{{background:linear-gradient(45deg,{grid} 25%,transparent 25%,transparent 75%,{grid} 75%),
 linear-gradient(45deg,{grid} 25%,#fff 25%,#fff 75%,{grid} 75%);
 background-size:10px 10px;background-position:0 0,5px 5px}}
.mono{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}}
.dim{{color:{label}}} td.n{{text-align:right}}
</style>
<div class="wrap">
<header>
  <h1>{html.escape(a.brand)} theme for SAP Analytics Cloud</h1>
  <p class="meta">{html.escape(a.source or "Colour, palette and type specification")}</p>
</header>

<section>
  <div class="shead"><h2>How a story renders</h2>
  <p>Every colour and the typeface come from the theme file. Figures are illustrative.</p></div>
  <div class="canvas">
    <div class="cbar"><span class="t">{html.escape(a.brand)} reporting</span>
      <span class="btn st">Export</span><span class="btn em">Apply filters</span></div>
    <div class="grid4">{kpi_html}</div>
    <div class="two">
      <div><p class="hbar">Actuals and commitments by quarter</p>
        <div class="widget"><div class="body">
          <p class="ws">Two-series pairing from palette positions 1 and 2</p>
          <svg viewBox="0 0 {BW} {BH}" width="100%" role="img"
               aria-label="Actuals and commitments by quarter">{svg}</svg>
        </div></div></div>
      <div><p class="hbar">Breakdown by workstream</p>
        <div class="widget"><div class="body">
          <table class="dt"><tr><th>Workstream</th><th class="n">Actuals</th>
          <th class="n">Committed</th><th class="n">Total</th></tr>{row_html}</table>
        </div></div></div>
    </div>
  </div>
</section>

<section>
  <div class="shead"><h2>Chart palettes</h2>
  <p>Categorical order determines which colours the customer sees most.</p></div>
  <div class="pal"><h3>Categorical</h3>{chips(cat, cat, 56)}</div>
  {f'<div class="pal"><h3>Sequential</h3>{chips(seq, None, 40)}</div>' if seq else ''}
  {f'<div class="pal"><h3>Diverging</h3>{chips(divc, None, 40)}</div>' if divc else ''}
  {f'<div class="pal"><h3>IBCS</h3>{chips(ibcs, None, 40)}</div>' if ibcs else ''}
  {f'<div class="pal"><h3>Semantic</h3>{chips(sem, None, 40)}</div>' if sem else ''}
</section>

<section>
  <div class="shead"><h2>Swatch reference</h2>
  <p>Last column is contrast against a white container. Text should clear 4.5:1;
  fills that carry meaning should clear 3:1.</p></div>
  <div class="cols">
    <div><h3>Font</h3><table class="st">{table('FontColor')}</table>
      <h3 style="margin-top:26px">Border</h3><table class="st">{table('BorderColor')}</table></div>
    <div><h3>Background</h3><table class="st">{table('BackgroundColor')}</table></div>
  </div>
  <h3 style="margin-top:32px">Datapoint</h3>
  <table class="st">{table('DatapointColor')}</table>
</section>
</div></html>
"""
    open(a.out, "w").write(doc_html)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
