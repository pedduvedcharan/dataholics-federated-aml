# UI reference — design conventions for the regulator dashboard

Requested by the team lead on Oct 17 2026, 19:15 CDT. The reference is the public marketing page
https://www.hummingbird.co/product/investigations (a compliance and investigations SaaS). Values below
were **measured** with the browser's computed styles on that page on Oct 17, 19:20 CDT, plus visual
reading of its product mock-ups.

## Boundary (non-negotiable)

We follow the reference's **design conventions** (palette logic, type scale, spacing, radii, component
shapes). We do **not** copy its name, logo, wordmark, illustrations, photos, decorative patterns, marketing
copy, proprietary font files, or any of its HTML/CSS/JS source. Every line of our UI is written by the
team (datathon rule), and the page must never look like it *is* their product. Our product name stays
**Dataholics · Regulator view**.

## Measured values

| Token | Reference value | Notes |
|---|---|---|
| page background | `#F4F4F1` (rgb 244 244 241) | warm off-white "paper" |
| ink (all text) | `#272727` (rgb 39 39 39) | near-black, not pure black |
| primary (brand dark green) | `#04433D` (rgb 4 67 61) | filled buttons, ids, KPI numbers, outline-button text and border |
| sage surface | `#CAE3DA` (rgb 202 227 218); translucent form `rgba(76,158,130,0.3)` | feature cards; card border `1px solid #CAE3DA` |
| navy (secondary dark) | `#15295A` (rgb 21 41 90) | deep panel backgrounds in mock-ups |
| chart blue | `#3985BE` (rgb 57 133 190), lighter tints for bars | bar charts |
| hairline / divider | `#E5E7EA` (rgb 229 231 234) | table rules, separators |
| white surface | `#FFFFFF` | floating cards (case card, chart card) |
| tan band | ≈ `#C19B80` | stat strip header ("Credits / Debits / Transfers") |
| lilac | ≈ `#A884BC` | donut progress |
| orange badge | ≈ `#F08A55` | count badges (circle with white digit) |
| cream pill (selected tab) | ≈ `#F7E3B5` | the selected filter pill |
| font | custom neo-grotesk (PP Neue Montreal family, proprietary) | **substitute: Google "Geist"** (similar neo-grotesk), fallback Arial, sans-serif; numbers in "Geist Mono" |
| type scale (px / weight / line-height) | 100/400/0.91 · 60/500/1.10 · 32/500/1.00 · 24/500/1.00 · 22/400/1.30 · 18/400–500/1.11 · 16 · 14/500 · 12 | headings are **regular or medium weight, never bold**; body text 18–22 px |
| card | radius **25px**, padding **32px**, no shadow, 1px sage border | feature cards |
| floating white card | radius ≈ 16px, white, soft shadow | case card, chart card |
| top bar | pill-shaped bar, radius **40px**, height 56px, padding 10px 13px, shadow `0 9.7px 16.7px rgba(0,0,0,0.10)`, translucent white over the page | sticky at the top, centred, max ≈ 1060px |
| nav link | 14px / weight 500 / ink | plain text links |
| button, filled | 14px / 500, white text on `#04433D`, 1px border `#04433D`, radius **30px** (pill), padding 0 13px, height 34px | |
| button, outline | same, transparent fill, `#04433D` text and border | |
| tag / chip | pill (radius 999px), 1px border, 12–13px text, transparent fill; selected/active = filled light | e.g. "Triage", "High Risk", "AML investigation" |
| data table | header row on a dark translucent band with white 14px labels; body rows separated by hairlines; a checkbox column; the **selected row** is a light cream band with the row's chips turned solid white | case list |
| KPI card | label 24px/500 in primary; number ≈ 100px/400 in primary; unit ("total") 22px muted beside it | "Currently open cases 38 total" |
| stat strip | 3 cells on the tan band: small label (12px) above a large value (28–32px), thin dividers | Credits / Debits / Transfers |
| entity card | small label (14px, primary) · id in primary 22px · status in muted 14px · name 40px/400 | "AML Investigation · #ACME-… · Open" |
| alert list | rows on light translucent cards, label left, orange circular count badge right | "Large Transaction ④" |
| charts | rounded-top bars in chart blue, month labels 12px, filter pills above (one selected cream) | no gridlines, no heavy axes |

## How our panels map onto these components

| Our panel (id must not change) | Component to use |
|---|---|
| top of page | pill top bar: "Dataholics · Regulator view" text mark (no logo), panel links as nav (Egress, Training, Privacy, Rogue, Red team, Alerts, Footprint), live/stale status as an outline pill, run tag (dpon / σ 0.5 / local) as a filled pill |
| `p-reg` egress audit | KPI cards ("Transaction rows shared 0" as the hero KPI in primary, then parameters, messages, blocked) + live egress tail as an alert-list (blocked lines get the orange badge) |
| `p-train` training | white floating chart card; rounds as chart; per-round table in the data-table style |
| `p-priv` privacy | stat strip (σ, clip, δ, ε spent, planned ε) + progress bar in primary on hairline track; caption text unchanged |
| `p-rogue` rogue bank | entity-card style header for bank 5; off/on comparison as two KPI cards; AP chart in chart card; per-round accept/exclude table with chips ("✖ bank 5 · rogue" danger chip, "▲ bank 1 · honest" amber chip) |
| `p-red` red team | chart card with the dot-and-whisker chart; table below in data-table style; verdicts as chips |
| `p-alerts` alert queue + report | **case list table** (checkbox-free, rank column, chips for "labelled laundering" / "not labelled", selected row = cream band) on the left; **entity card + report** on the right ("AML alert · A06 · ranked for analyst review", amount as the big line); LLM paragraph keeps its distinct marked box |
| `p-foot` footprint | stat strip + small bar chart per container |
| `p-evidence` evidence footer | plain hairline table, 14px |

## Rules that do not change

All ids (`p-reg p-train p-priv p-rogue p-red p-foot p-alerts p-evidence`), `?solo=<id>` capture mode,
`/api/state` and `/api/sar/<id>` usage, the escape-first markdown renderer, every number, every file-of-origin
row, and the claims wording (ranked for analyst review; near chance at σ 0.5; defense evaluated with DP off)
stay exactly as they are. Status meaning keeps a text label beside any color. Readable at 1280×720.
Light theme is the reference look; keep a dark theme only if it costs nothing, otherwise ship light-only
with explicit colors.
