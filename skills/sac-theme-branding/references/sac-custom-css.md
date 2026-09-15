# The custom CSS layer

Branding a SAC story has three layers, and they do not overlap cleanly:

| Layer | Where | What it reaches |
|---|---|---|
| Theme colour dialog | SAC UI | swatch values |
| Theme JSON | the export you rewrite | swatches, palettes, widget settings, fonts |
| **Custom CSS** | Story &rarr; Custom CSS | widget chrome, states, borders, type, per-element detail |

**CSS wins over the other two.** A story carrying stock CSS will keep showing
stock colours no matter how carefully the JSON is branded. If a customer says
"I applied the theme and half the widgets are still blue", the CSS is the first
place to look.

- [Two kinds of class](#two-kinds-of-class)
- [Scoping is opt-in](#scoping-is-opt-in)
- [What CSS can and cannot set](#what-css-can-and-cannot-set)
- [The bundled reference](#the-bundled-reference)
- [The bundled sample](#the-bundled-sample)
- [How the generator decides a colour](#how-the-generator-decides-a-colour)
- [Caveats to pass on](#caveats-to-pass-on)

## Two kinds of class

**Predefined classes** (`.sap-custom-*`) are SAC's own hooks into widget
internals: `.sap-custom-chart-title`, `.sap-custom-table-data-cell`,
`.sap-custom-dropdown-trigger-arrow`. You do not assign these; SAC puts them on
the right elements. Each accepts a fixed set of properties and ignores the rest.

**Assignable classes** are names the story designer types into a widget's
styling panel. They carry no styling of their own - they exist so a rule can be
aimed at particular widgets. The reference calls these "Widget CSS Class" and
notes they must not collide with a predefined name.

A rule almost always combines the two:

```css
.mytheme .sap-custom-chart-title { color: #1D1D1B; }
```

`.mytheme` is assigned by the designer; `.sap-custom-chart-title` is SAC's.

Note that not every predefined selector starts with `.sap-custom-` - Data Action
Starter uses `.sap-plan-seq-trigger-widget`. Match against the reference's
selector list rather than a name prefix.

## Scoping is opt-in

In SAP's own sample every rule is scoped by an assignable class, and there is a
reason for that: an unscoped `.sap-custom-button { }` restyles every button in
every story that loads the CSS, including ones nobody intended to touch.

The sample uses one broad class for baseline theming plus narrower ones as
variant hooks (`.button--emphasized`, `.table--styled`, `.filter--drop-down`).
Keep that shape. A designer applying the broad class gets the brand; a designer
who wants the emphasized variant adds the second class.

Tell the customer which class names their designers need to assign. A perfect
CSS file does nothing at all if nobody assigns the scope class.

## What CSS can and cannot set

31 properties are supported in total, and not all of them on every selector:

`background-color` `background-image` `color` `fill` `fill-opacity` `stroke`
`stroke-width` `stroke-dasharray` `stroke-opacity` `border` `border-top`
`border-right` `border-bottom` `border-left` `border-color` `border-radius`
`box-shadow` `opacity` `font-family` `font-size` `font-weight` `font-style`
`text-decoration` `text-align` `line-height` `padding` `padding-left`
`padding-right` `height` `rx` `ry`

Two things worth internalising:

- **Charts colour text with `fill`, not `color`.** Axis labels, data labels and
  trellis labels are SVG. Using `color` on them does nothing.
- **Anything not on a selector's list is ignored silently.** No console error,
  no visual change. This is the main way a CSS file ends up half-working, and
  why `validate_css.py` exists.

There is no layout, positioning, or text-transform. Uppercase labels in a
customer's mockup were typed that way.

## The bundled reference

`assets/sac-css-reference.json` is a machine-readable map of what SAC supports:
38 object types, 246 predefined selectors, 283 documented class entries, 31
properties. Per selector it gives the supported properties, a description, any
descendants, and any pseudo-classes (`:hover` and `:active` are the only ones
used in practice).

It also carries `selectorIndex` (selector &rarr; which object types use it) and
`propertyIndex` (property &rarr; where it is accepted), which is the fast way to
answer "can I set a border radius on that?".

Read it with a script rather than into context - it is about 320 KB.

## The bundled sample

`assets/sap-sample-theme.css` is SAP's own sample (the Morning Horizon light
theme), used as the rewrite template.

Two things make it a good template. Its colour literals are overwhelmingly exact
theme-swatch values, so the mapping from swatch role to selector is already done
and done by SAP. And its comments carry section headers per object type, which
survive the rewrite and make the output readable.

One thing to know: **it is an example, not a complete implementation.** It
styles 23 of the 38 object types. Page, Switch, Lane, Image, Comment Widget,
Page Book and others are untouched and will render stock. `build_css.py
--extend` generates conservative rules for the remainder from the reference,
inferring the role from each selector's name. Review that section before
shipping - inference from a name is a good guess, not a fact.

## How the generator decides a colour

For each colour literal, the declaration's property says which swatch family is
in play, and the chain is tried in order:

| Property | Families tried, in order |
|---|---|
| `color` | font &rarr; border &rarr; background |
| `background-color` | background &rarr; border &rarr; font |
| `border*`, `box-shadow` | border &rarr; background &rarr; font |
| `fill` | datapoint &rarr; font &rarr; background |
| `stroke` | datapoint &rarr; border |

Datapoint colours are deliberately absent from the chrome chains. They are chart
series colours; letting them act as a fallback turns a button's emphasis colour
into chart series 7.

The first family holding the stock colour wins. If its swatches all now resolve
to one branded colour, that is the answer. If they diverge, the selector name is
checked for a role hint (`title`, `label`, `subtitle`, `icon`, `grid-line`) and
matched against swatch descriptions. Failing that, the family's lowest-numbered
swatch is used, which is the general-purpose one, and every such case is
reported so you can override it.

Colours with no swatch behind them - pale hover fills, semantic pastels,
disabled greys - get a derived suggestion that keeps the tone's lightness and
saturation and moves only its hue onto the nearest brand hue, so a pale fill
stays a pale fill. Greys are left alone, since a grey is already brand-neutral.
All of these land in the `--emit-map` file for review.

## Caveats to pass on

From the reference's own global caveat, and worth repeating to the customer
verbatim:

- CSS takes priority over other styling settings and may override them.
- Colours set via CSS may override specific colour rules, **including threshold
  colours in charts**. A conditional-formatting rule that turns a bar red can be
  silently defeated by a CSS fill. Check any story that relies on thresholds.
- Widgets may not adapt to font sizes set via CSS, which shows up as truncated
  text. Change font sizes sparingly and check the densest widget.

Two more from practice:

- Name a fallback stack in every font rule. SAP's sample names one face, and a
  brand face that fails to resolve - not registered, typo in the family name,
  weight registered as its own family - drops to the browser default, which is
  usually a serif and unmistakable in a dashboard.
- CSS is set per story, not per tenant. A "company theme" in CSS means every
  story owner pasting the same file. Ask how they intend to distribute it.
- Because CSS outranks the JSON, the two must agree. Rebuild the CSS whenever
  the swatches change, or the story will show two different brand teals.
