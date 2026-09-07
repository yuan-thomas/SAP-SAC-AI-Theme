# Designing the palette

A brand palette built for print or slides is not a dashboard palette. Slides
show one colour at a time at large size; a dashboard shows twelve at once in
thin bars next to small text. Most of the work is adapting, not transcribing.

- [Order the categorical palette by evidence](#order-the-categorical-palette-by-evidence)
- [Contrast: where it binds and where it does not](#contrast-where-it-binds-and-where-it-does-not)
- [Splitting a brand colour into a fill and a text tone](#splitting-a-brand-colour-into-a-fill-and-a-text-tone)
- [Separation in the categorical palette](#separation-in-the-categorical-palette)
- [Sequential, diverging, IBCS](#sequential-diverging-ibcs)
- [Semantic colours](#semantic-colours)
- [Chrome and neutrals](#chrome-and-neutrals)
- [When the brand assets are thin](#when-the-brand-assets-are-thin)

## Order the categorical palette by evidence

Position 1 is what every single-series chart in the tenant will use. Positions 1
and 2 are what every actual-versus-plan comparison will use. Getting the order
wrong is more visible than getting a colour slightly wrong.

Rank the evidence:

1. **Screenshots of their existing reports.** If actuals are teal and
   commitments are stone across several charts, and the reference lines are
   stone too, that is the pairing. Use it even if a different colour looks
   better to you.
2. **Usage counts in the deck.** Which theme slot the slides actually lean on,
   not which the brand guide lists first.
3. **The declared accent order** in the theme's colour scheme.

A brand colour that is genuinely part of the identity but too light to work as a
lead series (a pale stone or sand, say) still belongs in the palette. If the
customer's own reports use it in second position, match that and mention the
greyscale trade-off rather than silently demoting it.

## Contrast: where it binds and where it does not

Different swatch roles have different obligations, and treating them all the
same either breaks accessibility or ruins the brand colour:

| Role | Target against its background | Why |
|---|---|---|
| Body text, labels, links, button text | 4.5:1 | WCAG AA normal text |
| Large display figures, KPI values | 3:1 | AA large text |
| Chart fills carrying meaning | 3:1 | must be distinguishable from the canvas |
| Decorative chrome, grid lines, dividers | no floor | they should recede |

Most vivid brand colours land near 2.5:1 on white. That is fine for a fill and
wrong for text.

## Splitting a brand colour into a fill and a text tone

The move that keeps both the brand and the accessibility: use the brand colour
at full strength where it reads as a block of colour, and a darkened version
where it carries text.

```
Brand teal  #00AFAA   2.7:1 on white   selected indicators, switches,
                                       sliders, chart fills, header bars
Darkened    #00726F   5.8:1 on white   links, icons, button labels, subtitles
```

Derive the darker tone by dropping lightness at constant hue until it clears
4.5:1, then check the result still reads as the same colour family. If a white
label sits on the brand colour, the *background* is what must clear 4.5:1
against white - which usually means the emphasised button uses the darker tone,
not the vivid one.

## Separation in the categorical palette

Two series that look alike make a chart useless regardless of how on-brand they
are. Measure it - CIELAB delta-E is quick and good enough:

- **Closest pair anywhere in the palette: aim above dE 25.** Below dE 20 two
  series read as the same colour.
- **Closest adjacent pair: aim above dE 40.** Neighbouring positions get used
  together most often.

`build_theme.py` reports both. If a brand only supplies four or five usable
accents, fill the remaining positions with tints and shades of those accents
rather than importing foreign hues - and place them after all the brand colours
so a typical four-series chart is pure brand.

Check the palette holds up for colour-vision deficiency: avoid putting a red and
a green in adjacent positions, and prefer pairings that differ in lightness as
well as hue.

## Sequential, diverging, IBCS

- **Sequential** should be one hue, usually the primary, from light to dark.
  Take the endpoints from the swatch ramp so the palette and the swatches agree.
- **Diverging** wants a cool-to-warm pair with a light neutral in the middle.
  A brand's primary against a brand warm accent, with a pale brand neutral
  between, stays on-brand and survives colour-vision deficiency.
- **IBCS** ramps should stay achromatic in feel. A warm or cool *tint* of grey
  pulled toward a brand neutral keeps IBCS compliance while still looking like
  the customer rather than like SAP's default blue-grey.

Preserve the source's swatch-to-palette mapping rather than restructuring it.
Some palettes reuse swatches from other groups in deliberate orders (SAC's blue
categories palette shuffles its sequential swatches so adjacent categories
contrast). Recolour the swatches and let the existing mapping do its job.

## Semantic colours

Positive, negative, warning and neutral need to stay legible as *meaning* first.
Derive them from brand hues where the brand has a green, a red-ish and an amber,
but darken to clear 4.5:1 - these often render as text (variance figures) as
well as fills.

If the brand's only warm accents are a rust and an amber that would collide,
keep them distinct: a deeper red for negative, a browner amber for warning. If a
brand has no red at all, a conventional red is the right call - do not use a
brand pink for negative because it happens to be warm.

A brand neutral (stone, sand, warm grey) makes a better chart "Neutral" than
generic grey and costs nothing. Darken it enough to clear 3:1 as a fill.

## Chrome and neutrals

- Page background a hair off white, containers pure white. A flat white-on-white
  canvas gives cards nothing to sit against.
- Borders, grid lines and dividers should be quiet. Grid lines lighter than
  borders; axis lines darker than grid lines.
- Reuse the brand's own light grey for hover and list states if it has one - it
  is free brand consistency in a place nobody expects it.
- Keep pure black for display figures only if the brand actually uses it. Sample
  a screenshot before assuming; a lot of brands sit at an off-black.

## When the brand assets are thin

Sometimes all you get is a logo and two colours. Build outward:

1. Primary from the dominant brand colour; derive a full ramp (light tint
   through to a dark shade) for sequential and states.
2. Secondary from whatever else the brand supplies, even a neutral.
3. Fill remaining categorical positions with hues spaced evenly around from the
   primary, desaturated to sit alongside it rather than compete.
4. Neutrals tinted very slightly toward the primary's temperature.

Say plainly which colours came from the brand and which you derived, so the
customer knows what is up for debate.
