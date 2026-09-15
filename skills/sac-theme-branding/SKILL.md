---
name: sac-theme-branding
description: Rebrand SAP Analytics Cloud to a customer's visual identity end to end - extract colours and fonts from brand assets (PPTX, brand guide, report screenshots), design an accessible dashboard palette, rewrite the theme JSON's swatches, palettes, cached colour literals and font families without breaking its schema, and generate matching SAC Story Custom CSS validated against SAP's supported-selector reference. Use this whenever someone mentions SAC theming, SAP Analytics Cloud branding, a SAC theme JSON or "sac-theme-preferences" export, SAC Custom CSS or sap-custom selectors, applying corporate colours or a corporate font to SAC stories, replacing the SAP stock/default theme, or building a reusable company theme for SAC - and also when they hand over a theme export alongside a deck, style guide or dashboard screenshots and ask to make one look like the other, even if they never say the word "theme".
---

# Branding a SAP Analytics Cloud theme

The customer exports their SAC story theme to JSON (usually via a browser-console
script), you rebrand it, they import it back. Your job is the middle step: turn
brand assets into a palette, and get that palette into everything that carries
colour without breaking anything.

Branding SAC is three layers, not one. The colour dialog sets swatches. The
theme JSON carries those swatches plus palettes, widget settings and fonts. And
**Story Custom CSS sits on top of both and wins.** A story with stock CSS keeps
showing stock colours however well the JSON is branded, which is the usual
answer to "I applied the theme and half the widgets are still blue".

Two things make this harder than a find-and-replace. The export is a real
artefact with real inconsistencies - self-contradicting palettes, colour caches
that shadow the swatch bindings, font slots that are empty or missing entirely.
And the brand assets never state what a dashboard needs; they state what a slide
needs.

The scripts handle the mechanical half so you can spend your attention on the
palette. All of them are self-checking and refuse to write a file whose schema
drifted from the source.

## Before anything else: ask about mockups

**Ask whether they have screenshots or mockups of existing reports** - theirs or
a comparable one - before you design anything. Also ask what the theme is for
(a single story, or a reusable company theme new reports will apply), and
whether any custom font is already registered on the tenant.

Also ask **whether the story already uses Custom CSS**, and get the current file
if so. Anything in it overrides the theme, so it is both a constraint and a
source of truth about what they expect.

This matters more than it sounds. A brand guide tells you which colours exist.
A screenshot tells you which one is the primary series, which is the secondary,
what the chrome looks like, and what the customer already expects a report to
look like. Palette *order* in particular is almost impossible to get right from
a deck alone, and getting it wrong is the most visible mistake available: it
changes what every single-series chart in the tenant looks like.

If they have nothing, say so plainly and design from the assets you have, then
flag the order as the thing most likely to need a second pass.

## Workflow

### 1. Audit the export

```bash
python scripts/inspect_theme.py theme.json --emit-spec spec.json
```

Read the whole report. It tells you which swatches exist and what roles they
play *in this file* (never assume - the set varies by SAC version), whether the
`defaultColorSettings` mirror is present, how many cached literals live outside
the theme block, how much the palettes already disagree with themselves, and
where font families are empty or absent.

The emitted `spec.json` is keyed to this file's actual swatch ids and roles,
with every colour still at its source value. You edit it; you never hand-write
one from memory.

### 2. Extract the brand

```bash
python scripts/extract_brand.py deck.pptx screenshot.png
```

For a PPTX this reads the declared colour scheme and fonts from
`ppt/theme/theme1.xml`, then counts how the slides actually use them. Both
halves matter: the scheme says what the brand owns, the counts say what it
leans on. For images it reports dominant colours, merges antialiasing
neighbours, and separately reports the dark tail where text colours hide.

Cross-check. When a screenshot's dominant colour matches the deck's `accent1`
exactly, you have a confirmed primary. When they disagree, the screenshot is
usually closer to what the customer expects.

If the assets are a PDF or images only, sample the images and say which values
you derived rather than found.

### 3. Design the palette

Read `references/palette-design.md`. The parts that matter most:

- Order the categorical palette by evidence, screenshots first.
- Split vivid brand colours into a full-strength fill tone and a darkened text
  tone. A brand colour at 2.5:1 is fine behind a bar and wrong under a label.
- Check separation - the script reports delta-E; aim above dE 25 for the closest
  pair and dE 40 for adjacent positions.
- Semantic colours must read as meaning first, brand second.

Fill in the `color` values in `spec.json`. Set `font.family` and
`font.apply: true` only if the font is confirmed on the tenant. Add a
`headerBar` block if the customer's reports put a coloured bar behind widget
titles; if the swatch set has no role for that, activate a spare slot via
`activate` (see `references/sac-theme-schema.md`, Trap 5).

`assets/spec.example.json` shows a filled-in spec.

### 4. Build

```bash
python scripts/build_theme.py theme.json spec.json --out-dir out --prefix Acme
```

Produces two files:

- `Acme-theme-branded.json` - swatches and palettes only.
- `Acme-theme-branded-full.json` - plus refreshed colour caches, font applied
  and gaps filled, and any header-bar binding.

Both are schema-verified against the source; the build aborts rather than write
a file whose schema drifted. Read the report:

- **unmapped swatches / ghost ids** - spec and export disagree about what exists.
- **ambiguous unbound literals** - one source colour shared by swatches that now
  differ, so the script will not guess. Resolve with `literalOverrides` in the
  spec if the colour is visible.
- **off-palette coloured literals** - widget fallbacks bound to no swatch. Greys
  are ignored; anything with real hue is listed because the customer may spot it.
- **contrast per font role** and **categorical separation** - see below.

Fix anything surprising in the spec and rebuild. Do not hand-edit the output;
the next rebuild would silently discard it.

### 5. Generate the custom CSS

```bash
python scripts/build_css.py out/Acme-theme-branded-full.json \
  --source-theme theme.json --font Inter \
  --font-fallback "Arial, Helvetica, sans-serif" \
  --brand Acme --extend \
  --emit-map out/css-map.json --out out/acme-theme.css
```

This rewrites SAP's bundled sample CSS with the branded colours rather than
inventing a selector mapping, because the sample's colour literals are already
exact swatch values - SAP did the mapping. Each substitution is decided from the
declaration's property, so `color:` looks at font swatches and `fill:` at
datapoint swatches.

The sample styles 23 of the 38 object types. `--extend` generates conservative
rules for the rest from the reference; review that section, since it infers each
role from the selector's name.

Read the `--emit-map` file. Every value in it is a *suggestion*, not a decision:
colours where several branded swatches shared one stock colour, and CSS-only
tones (pale hover fills, semantic pastels) given the brand's nearest hue at the
same lightness. Edit it, then pass it back with `--overrides` and rebuild.

Check any existing CSS, and anything you hand-edit:

```bash
python scripts/validate_css.py out/acme-theme.css --colours
```

SAC ignores unsupported selectors and properties silently, so a rule that reads
fine can do nothing. This also reports which object types the file leaves
unstyled.

The scope class comes from `--brand` (Acme becomes `.acmetheme`), or pass
`--scope` to set it directly. Give one or the other: with neither, the output
keeps the template's own scope class and the customer's designers end up
assigning SAP's sample class name to their widgets. The build warns when that
happens. Whatever you choose, `preview_dashboard.py` must be told the same one.

Pass `--font-fallback` unless there is a reason not to. SAP's sample names a
single face in most rules, and a face that fails to load drops to the browser
default, which is usually a serif - conspicuous in a dashboard.

`references/sac-custom-css.md` covers the layer properly - read it before
hand-writing any rule.

### 6. Preview

```bash
python scripts/make_preview.py out/Acme-theme-branded.json \
  --out out/Acme-theme-preview.html --brand Acme --font Inter
```

A single-page specimen: a mock canvas, the palettes, and every swatch with its
role and contrast. If you have their screenshots, edit the mock canvas to mirror
that layout - a specimen that looks like their own dashboard gets signed off,
a grid of colour chips gets questions.

Then render the sample dashboard, which is the one that shows the CSS working:

```bash
python scripts/preview_dashboard.py out/Acme-theme-branded-full.json \
  --css out/acme-theme.css --brand Acme --font Inter \
  --out out/acme-dashboard.html
```

The markup carries SAC's real predefined class names under the scope class, so
the generated CSS styles it the same way it will style the tenant. Series
colours and container fills are read from the theme JSON, chrome and type from
the CSS - if a widget looks unstyled, the CSS genuinely has no rule for it.

The page fetches the brand face itself, since a local HTML file has no tenant to
get it from. `--font-url auto` builds a Google Fonts URL from `--font`; pass a
real URL for a licensed corporate face, or `none` to skip. Without it the whole
preview renders in a fallback and tells you nothing about the typography, so
check the console if the type looks wrong before you blame the CSS.

Render both and look at them before sending. Check for text overflow, uneven
column heights, and low-contrast pairings the numbers did not catch.

## Delivering

Lead with the scoped file, not the full one. The customer's stated understanding
is usually that everything outside `theme.colors` and `theme.palettes` resolves
through swatch references - which is *mostly* true, and whether the cached
literals win depends on their import script and SAC version. So: scoped file
first, full file as the fix if widgets still render in stock colours.

Ship the CSS alongside the JSON, and be explicit that **it must be kept in step
with the theme**. Because CSS outranks the JSON, a swatch change without a CSS
rebuild leaves the story showing two different brand colours.

Tell them, briefly:

- Which colours came from the brand and which you derived, so they know what is
  open for debate.
- The `defaultColorSettings` mirror, if their import script only writes the live
  swatch table. This is the most commonly missed thing in the file and it
  surfaces later as "Reset put SAP blue back".
- Anything you activated or added (a spare swatch, font keys), named as the
  thing to verify on import, with the fallback if their tenant rejects it.
- What the theme cannot reach - table header fills, text case, logos. Set that
  expectation early; they will ask.
- Which **scope class** their designers must assign in each widget's styling
  panel. A perfect CSS file does nothing if nobody assigns the class.
- That CSS is per story, not per tenant, so a "company theme" in CSS means every
  story owner applying the same file. Ask how they plan to distribute it.
- That CSS colours can override chart **threshold and conditional formatting**
  colours. Any story relying on those needs a look.

## Things worth being honest about

The customer often scopes the job to colours and palettes. Respect that scope in
the primary deliverable, and report what you found outside it rather than
silently expanding. The two-file split exists for exactly this reason.

When a check fails - a literal that does not match its swatch, an ambiguous
remap, a font object you were not certain about - leave it alone and say so. A
reported skip is recoverable; a silently wrong colour in a tenant-wide theme is
not.

## Files

- `references/sac-theme-schema.md` - the export's structure and its five traps.
  Read before hand-editing anything or when a build reports something odd.
- `references/palette-design.md` - how to adapt brand colours for dashboards.
  Read at step 3, every time.
- `references/sac-custom-css.md` - how the CSS layer works, what it can set,
  and the caveats to pass on. Read at step 5.
- `assets/spec.example.json` - a filled-in spec.
- `assets/sac-css-reference.json` - SAP's supported selectors and properties:
  38 object types, 246 selectors, 31 properties. Query it with a script; at
  ~320 KB it does not belong in context.
- `assets/sap-sample-theme.css` - SAP's own sample theme, used as the rewrite
  template. An example, not a complete implementation.
- `assets/dashboard-preview.html` - the sample dashboard, in SAC-accurate markup.
- `scripts/` - `inspect_theme`, `extract_brand`, `build_theme`, `build_css`,
  `validate_css`, `make_preview`, `preview_dashboard`.

Dependencies: Python 3, `Pillow` for image sampling. No network needed.
