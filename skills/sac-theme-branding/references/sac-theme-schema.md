# The SAC theme export, and where it bites

Read this before hand-editing anything. The scripts already handle everything
here; this exists so you can reason about failures and answer the customer's
questions.

- [Shape of the file](#shape-of-the-file)
- [Trap 1: the defaultColorSettings mirror](#trap-1-the-defaultcolorsettings-mirror)
- [Trap 2: cached literals outside the theme block](#trap-2-cached-literals-outside-the-theme-block)
- [Trap 3: palettes that disagree with themselves](#trap-3-palettes-that-disagree-with-themselves)
- [Trap 4: font families that are absent, not just empty](#trap-4-font-families-that-are-absent-not-just-empty)
- [Trap 5: unassigned swatch slots](#trap-5-unassigned-swatch-slots)
- [What the theme cannot reach](#what-the-theme-cannot-reach)

## Shape of the file

A typical export (`format: "sac-theme-preferences"`) looks like:

```
format, schemaVersion, exportedAt, source
theme
  colors     -> preferences[0].settings.swatches.values[]     <- the source of truth
               preferences[0].settings.defaultColorSettings   <- a mirror, see Trap 1
  palettes   -> preferences[0].settings.palettes.{standard, waterfall_standard,
                gradient, diverging, sequential, variance, single_color, forceReset}
storySettings[]    page/canvas/threshold/number-format settings
widgetSettings[]   one entry per widget type (button, chart, table, tabstrip, ...)
```

Swatches are identified by `FontColor_N`, `BackgroundColor_N`, `BorderColor_N`,
`DatapointColor_N`, each with a `description` naming its role ("Main Font",
"Grid Lines", "Positive", "IBCS 4"). **Do not memorise the numbering.** Run
`inspect_theme.py` and read the roles out of the file you were given; the count
and the assignments vary by SAC version.

Everything else references swatches by id. `storySettings` and `widgetSettings`
carry `colorSwatchId`, `fontColorSwatchId`, `appBuildingBackgroundColorSwatchId`
and about forty other `*SwatchId` variants.

## Trap 1: the defaultColorSettings mirror

Inside `theme.colors.preferences[0].settings` there is a second, complete copy
of the swatch table under `defaultColorSettings`. In a clean export the two are
identical.

This is SAC's "reset to theme default" reference. Update only the live table and
the theme looks right until somebody hits Reset, at which point the story snaps
back to SAP stock colours. The same mirroring appears throughout
`widgetSettings`, where each preference block repeats its settings under
`defaultColorSettings`.

**Rule: any swatch or setting you change, change in both blocks.**

## Trap 2: cached literals outside the theme block

`storySettings` and `widgetSettings` do not reference swatches purely by id.
Beside each `*SwatchId` sits the resolved colour as a literal:

```json
"contentFontStyle": { "fontFamily": "'72-Web'", "fontSize": "14px", "color": "#0064D9" },
"contentFontColorSwatchId": "FontColor_10"
```

A typical export holds 250+ of these. They are caches written at export time.
Whether a stale cache wins over the swatch on re-import depends on the
customer's import script and their SAC version, and you cannot tell from the
file. That uncertainty is exactly why the build produces two outputs: a scoped
file that leaves them alone, and a full file that refreshes them.

The literal does not always sit under a sibling of the same name. Observed
shapes:

| `*SwatchId` value | Where the literal lives |
|---|---|
| plain string | sibling key with the same stem (`colorSwatchId` -> `color`) |
| plain string | sibling `<stem minus "Color">Style` object (`hoverColorSwatchId` -> `hoverStyle.color`) |
| `{path, value}` | sibling of the same stem, also `{path, value}` |
| `{value}` | sibling of the same stem, also `{value}` |
| `{customValue, defaultValue}` | sibling with matching sub-keys, sometimes nested one deeper (`iconColorSwatchId` -> `icon.customValue.iconColor`) |

Several stems break the pattern outright: `appBuildingBackgroundColor` ->
`backgroundStyle.backgroundColor`, `inactiveBorderColor` -> `borderStyle.borderColor`,
`nodeColor` -> `backgroundColor`.

`build_theme.py` resolves these generically and then **verifies each one against
the source before writing**: it only updates a literal whose original value
provably equalled the original swatch colour. A wrong guess about the shape
produces a skipped entry and a warning, never a silently wrong colour. Entries
that legitimately differ (deliberate overrides, `rgb(...)` strings, empty
values) are reported and left alone.

Some literals have `swatchId: ""` - unbound, carrying a stock colour with no
binding. These get remapped only where the stock colour maps to exactly one
target colour. Where one stock colour was shared across swatches that now
diverge, the remap is ambiguous and is skipped and reported.

## Trap 3: palettes that disagree with themselves

Each palette entry holds both `swatchIds` and a parallel `colors` array. Real
exports routinely ship these out of sync - a palette claiming
`DatapointColor_2` while listing a colour that swatch does not hold.

Always regenerate `colors` from `swatchIds` rather than writing it by hand. That
fixes the drift for free. `inspect_theme.py` reports how much drift the source
had, which is worth mentioning to the customer.

`variance` and `single_color` carry no swatch references, so their values come
from the spec directly. `forceReset` is a boolean flag - leave it as exported.

## Trap 4: font families that are absent, not just empty

Three separate problems, all of which silently fall back to the SAC default:

1. **Empty strings.** `fontFamily: ""` with size and colour set. A search for
   the incumbent font name will never find these.
2. **Missing keys.** Some font-style objects are just `{fontSize, color}` with
   no family key at all, while the equivalent object on a neighbouring widget
   has one. These need the key added.
3. **Three key names, several quoting styles.** SAC writes `fontname`,
   `fontFamily` and `family` depending on the widget's vintage, and quotes the
   value as `'X'`, `"X"` or bare, inconsistently. Preserve whatever convention
   each entry already uses rather than normalising - that is the form SAC is
   known to accept in that slot.

Beware false positives when adding keys. A container object can hold a stray
`fontWeight` alongside child style objects; adding a font family there invents
a setting that never existed. The test that works: the object's keys must be a
subset of known font attributes AND include at least one typographic attribute.

## Trap 5: unassigned swatch slots

An export typically has ~240 slots of which ~106 are assigned; the rest carry
`isUnassigned: true` and `baseColor: "transparent"`. Leave them alone by
default.

You can activate one by dropping `isUnassigned` and setting `description` and
`baseColor`. This is the clean way to add a role the stock set lacks - a widget
header colour, for instance. It is schema-valid but not something the source
export exercised, so flag it to the customer as the one thing to verify on
import, and name the fallback (repoint to an existing swatch of the same colour)
in case their tenant rejects it.

## What the theme cannot reach

Set expectations early on these, because customers ask:

- **Table header fills and banding.** Driven by `stylingTemplate` (e.g.
  `"defaultstyle"`), not by swatch bindings. Needs a table style set on the
  widget or a custom table style, not this file.
- **Text case.** No text-transform exists in this schema. Uppercase labels in a
  mockup were typed that way.
- **Logos and imagery.** Story assets, not theme settings.
- **Custom fonts.** The family name only resolves if the font is registered on
  the tenant. Confirm before applying, and confirm whether weights were
  registered as one family or several - "Montserrat" with a bold flag behaves
  differently from a separate "Montserrat SemiBold" family.
