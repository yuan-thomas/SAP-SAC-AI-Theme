---
name: sac-theme-branding
description: Rebrand an exported SAP Analytics Cloud theme to a customer's visual identity - extract colours and fonts from brand assets (PPTX, brand guide, report screenshots), design an accessible dashboard palette, and rewrite the theme JSON's swatches, palettes, cached colour literals and font families without breaking its schema. Use this whenever someone mentions SAC theming, SAP Analytics Cloud branding, a SAC theme JSON or "sac-theme-preferences" export, applying corporate colours or a corporate font to SAC stories, replacing the SAP stock/default theme, or building a reusable company theme for SAC - and also when they hand over a theme export alongside a deck, style guide or dashboard screenshots and ask to make one look like the other, even if they never say the word "theme".
---

# Branding a SAP Analytics Cloud theme

The customer exports their SAC story theme to JSON (usually via a browser-console
script), you rebrand it, they import it back. Your job is the middle step: turn
brand assets into a palette, and get that palette into the file without breaking
anything.

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

### 5. Preview

```bash
python scripts/make_preview.py out/Acme-theme-branded.json \
  --out out/Acme-theme-preview.html --brand Acme --font Montserrat
```

A single-page specimen: a mock canvas, the palettes, and every swatch with its
role and contrast. If you have their screenshots, edit the mock canvas to mirror
that layout - a specimen that looks like their own dashboard gets signed off,
a grid of colour chips gets questions.

Render it and look at it before sending. Check for text overflow, uneven column
heights, and low-contrast pairings the numbers did not catch.

## Delivering

Lead with the scoped file, not the full one. The customer's stated understanding
is usually that everything outside `theme.colors` and `theme.palettes` resolves
through swatch references - which is *mostly* true, and whether the cached
literals win depends on their import script and SAC version. So: scoped file
first, full file as the fix if widgets still render in stock colours.

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
- `assets/spec.example.json` - a filled-in spec.
- `scripts/` - audit, extract, build, preview.

Dependencies: Python 3, `Pillow` for image sampling. No network needed.
