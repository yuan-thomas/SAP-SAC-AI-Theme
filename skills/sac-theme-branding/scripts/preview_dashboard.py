#!/usr/bin/env python3
"""
Render the sample dashboard with a theme and its custom CSS applied.

  preview_dashboard.py branded.json --css acme-theme.css \
      --scope acmetheme --brand "Acme" --font Inter --out dashboard.html

Produces one self-contained HTML file. The markup carries SAC's real predefined
class names, so the generated CSS styles it the same way it will style the
tenant - which makes this the fastest way to see whether a rule actually landed
before anyone imports anything.

Two layers are visible and they come from different places, which is the point:
series colours and swatches are read from the theme JSON, while chrome, borders
and type come from the CSS. If a widget looks unstyled, the CSS has no rule for
it.
"""
import argparse
import html
import json
import os
import re
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("theme")
    ap.add_argument("--css", default="")
    ap.add_argument("--scope", default="",
                    help="scope class the CSS is written against, without the dot. "
                         "Defaults to one derived from --brand; must match whatever "
                         "build_css.py used or nothing will be styled.")
    ap.add_argument("--brand", default="Customer")
    ap.add_argument("--font", default="system-ui")
    ap.add_argument("--font-url", default="auto",
                    help="stylesheet URL for the brand face; 'auto' builds a Google "
                         "Fonts URL from --font, 'none' skips it. A licensed "
                         "corporate face needs its own URL or an @font-face block.")
    ap.add_argument("--out", default="dashboard.html")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--template",
                    default=os.path.join(here, "assets", "dashboard-preview.html"))
    a = ap.parse_args()

    if not a.scope:
        slug = re.sub(r"[^a-z0-9]", "", a.brand.split()[0].lower()) if a.brand else ""
        a.scope = f"{slug}theme" if slug else "saptheme"

    doc = json.load(open(a.theme))
    sw = [s for s in
          doc["theme"]["colors"]["preferences"][0]["settings"]["swatches"]["values"]
          if not s.get("isUnassigned")]
    by_id = {s["id"]: s["baseColor"] for s in sw}
    pal = doc["theme"]["palettes"]["preferences"][0]["settings"]["palettes"]
    cat = pal.get("standard", [{}])[0].get("colors", ["#888888", "#bbbbbb"])
    c1 = cat[0]
    c2 = cat[1] if len(cat) > 1 else cat[0]
    pos = by_id.get("DatapointColor_15", "#2e7d32")
    neg = by_id.get("DatapointColor_17", "#b71c1c")

    css = open(a.css, encoding="utf-8-sig").read() if a.css else \
        "/* no custom CSS supplied - every colour you see is a browser default */"

    # KPI tiles
    kpis = [("Actuals", "4,812,900", "+4.2%", True),
            ("Committed", "612,430", "-1.8%", False),
            ("Forecast", "5,425,330", "+3.1%", True),
            ("Variance", "(184,220)", "-2.6%", False)]
    kpi_html = "".join(
        f'<div class="sap-custom-chart-widget kpi">'
        f'<span class="sap-custom-number-chart-primary-labels">{html.escape(l)}</span>'
        f'<span class="sap-custom-number-chart-primary-values">{v}</span>'
        f'<span class="sap-custom-number-chart-primary-variance-values" '
        f'style="color:{pos if up else neg}">{d}</span></div>'
        for l, v, d, up in kpis)

    # Chart. Axis text uses fill rather than color because that is what SAC's
    # chart classes expose, so the CSS is exercised the way it will be in situ.
    bars = [("P1", 62, 14), ("P2", 71, 9), ("P3", 48, 21),
            ("P4", 88, 12), ("P5", 55, 18), ("P6", 74, 11)]
    W, H, PADB = 560, 250, 30
    mx = max(x + y for _, x, y in bars)
    plot = H - PADB - 22
    step = W / len(bars)
    parts = []
    for i, (nm, v1, v2) in enumerate(bars):
        h1, h2 = v1 / mx * plot, v2 / mx * plot
        x, w = i * step + step * .22, step * .56
        y1 = H - PADB - h1
        parts.append(
            f'<rect x="{x:.0f}" y="{y1:.0f}" width="{w:.0f}" height="{h1:.0f}" fill="{c1}"/>'
            f'<rect x="{x:.0f}" y="{y1 - h2:.0f}" width="{w:.0f}" height="{h2:.0f}" fill="{c2}"/>'
            f'<text class="sap-custom-chart-data-labels" x="{x + w / 2:.0f}" '
            f'y="{y1 - h2 - 6:.0f}" text-anchor="middle" font-size="11">{v1 + v2}</text>'
            f'<text class="sap-custom-chart-category-axis-label" x="{x + w / 2:.0f}" '
            f'y="{H - 10}" text-anchor="middle" font-size="11">{nm}</text>')
    for f in (.25, .5, .75, 1.0):
        y = H - PADB - plot * f
        parts.append(f'<line class="sap-custom-chart-time-series-horizontal-grid-line" '
                     f'x1="34" x2="{W}" y1="{y:.0f}" y2="{y:.0f}" stroke="currentColor" '
                     f'stroke-opacity=".28"/>')
        parts.append(f'<text class="sap-custom-chart-value-axis-label" x="28" '
                     f'y="{y + 4:.0f}" text-anchor="end" font-size="10">'
                     f'{int(mx * f)}</text>')
    parts.append(f'<line class="sap-custom-chart-axis-line" x1="34" x2="{W}" '
                 f'y1="{H - PADB}" y2="{H - PADB}" stroke="currentColor" stroke-opacity=".5"/>')
    parts.append(f'<line class="sap-custom-chart-reference-line" x1="34" x2="{W}" '
                 f'y1="{H - PADB - plot * .82:.0f}" y2="{H - PADB - plot * .82:.0f}" '
                 f'stroke="{c2}" stroke-dasharray="6 4"/>')
    chart = f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Actuals and commitments">' \
            + "".join(parts) + "</svg>"

    legend = (f'<span><i style="background:{c1}"></i>Actuals</span>'
              f'<span><i style="background:{c2}"></i>Committed</span>')

    rows = [("Programme delivery", "2,140,880", "301,220", "+41,900", True),
            ("Platform build", "1,204,880", "96,110", "-33,140", False),
            ("Integration", "742,015", "41,850", "+6,320", True),
            ("Reporting", "725,125", "173,250", "-8,410", False)]
    rows_html = "".join(
        f'<tr class="sap-custom-table-row">'
        f'<td class="sap-custom-table-dimension-member-cell">{html.escape(n)}</td>'
        f'<td class="sap-custom-table-data-cell num">{a1}</td>'
        f'<td class="sap-custom-table-data-cell num">{a2}</td>'
        f'<td class="sap-custom-table-data-cell num" '
        f'style="color:{pos if up else neg}">{v}</td></tr>'
        for n, a1, a2, v, up in rows)

    chips = "".join(
        f'<figure><i style="background:{s["baseColor"]}"></i>'
        f'<figcaption>{html.escape(s["baseColor"])}<br>'
        f'{html.escape(s.get("description") or s["id"])}</figcaption></figure>'
        for s in sw if s["baseColor"].startswith("#"))

    page_bg = by_id.get("BackgroundColor_1", "#f5f5f5")
    cont_bg = by_id.get("BackgroundColor_2", "#ffffff")
    grid = by_id.get("BorderColor_6", by_id.get("BorderColor_2", "#e0e0e0"))
    # a shade behind the page, so the page edge is visible in the preview frame
    canvas = by_id.get("BackgroundColor_9", by_id.get("BackgroundColor_8", "#e9eaea"))

    link = ""
    if a.font_url == "auto" and a.font and a.font != "system-ui":
        fam = a.font.replace(" ", "+")
        link = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
                f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
                f'family={fam}:wght@400;500;600;700&display=swap">')
    elif a.font_url and a.font_url not in ("auto", "none"):
        link = f'<link rel="stylesheet" href="{html.escape(a.font_url)}">'

    meta = (f'Theme {os.path.basename(a.theme)}'
            + (f' with {os.path.basename(a.css)}' if a.css else ' with no custom CSS')
            + f' &middot; scope class .{a.scope}')

    t = open(a.template, encoding="utf-8").read()
    for k, v in (("__BRAND__", html.escape(a.brand)), ("__SCOPE__", a.scope),
                 ("__THEME_CSS__", css), ("__FONT__", a.font), ("__META__", meta),
                 ("__KPIS__", kpi_html), ("__CHART__", chart), ("__LEGEND__", legend),
                 ("__ROWS__", rows_html), ("__SWATCHES__", chips),
                 ("__PAGE_BG__", page_bg), ("__CONTAINER_BG__", cont_bg),
                 ("__CANVAS_BG__", canvas), ("__GRID__", grid),
                 ("__FONT_LINK__", link)):
        t = t.replace(k, v)
    left = re.findall(r"__[A-Z_]+__", t)
    if left:
        print(f"warning: unfilled placeholders {sorted(set(left))}")

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(t)
    print(f"wrote {a.out}")
    print(f"   scope .{a.scope} | series {c1} / {c2} | {len(sw)} swatches")
    print(f"   font {a.font}: " + ("webfont link embedded" if link else
          "NO webfont link - the page will fall back unless the face is "
          "installed locally"))
    if a.css:
        n = len(re.findall(r"\{", css))
        print(f"   {n} CSS rules applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
