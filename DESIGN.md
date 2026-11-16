---
name: "Линия"
description: "Живая линия: персональный VPN в светлой минеральной палитре с кобальтовым маршрутом."
colors:
  bg: "#f5f6f8"
  surface: "#ffffff"
  raised: "#eceef3"
  line: "#dce0e8"
  text: "#18202e"
  muted: "#626b7c"
  accent: "#1759e8"
  accent-hover: "#0646ce"
  green: "#177950"
  danger: "#bf3345"
  navy: "#0d1525"
  sidebar: "#f0f2f6"
  selected: "#e0e9fc"
  account-term: "#123d92"
  notice-warning-bg: "#fff0d8"
  notice-warning-text: "#765010"
  notice-critical-bg: "#fce9ec"
  notice-critical-text: "#972a3e"
  notice-ok-bg: "#e8f2ed"
  notice-ok-text: "#246449"
typography:
  display:
    fontFamily: "Onest Variable, Onest, sans-serif"
    fontSize: "clamp(76px, 8.8vw, 126px)"
    fontWeight: 550
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  heading:
    fontFamily: "Onest Variable, Onest, sans-serif"
    fontSize: "clamp(36px, 4.6vw, 64px)"
    fontWeight: 550
    lineHeight: 1.08
    letterSpacing: "-0.035em"
  body:
    fontFamily: "Onest Variable, Onest, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  lead:
    fontFamily: "Onest Variable, Onest, sans-serif"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "Onest Variable, Onest, sans-serif"
    fontSize: "14px"
    fontWeight: 550
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  field: "12px"
  panel: "16px"
  control: "100px"
spacing:
  compact: "8px"
  control-gap: "12px"
  phone-inset: "20px"
  panel-inset: "30px"
  desktop-inset: "56px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "13px 23px"
  button-secondary:
    backgroundColor: "#e9edf5"
    textColor: "#263650"
    rounded: "{rounded.control}"
    padding: "13px 23px"
  button-danger:
    backgroundColor: "#fbe6e9"
    textColor: "#a42337"
    rounded: "{rounded.control}"
    padding: "13px 23px"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "14px 16px"
  navigation-active:
    backgroundColor: "{colors.selected}"
    textColor: "#124cc4"
    rounded: "{rounded.field}"
    padding: "14px 16px"
---

# Design System: Линия

## Overview

**Живая линия / Living line.** The user-requested replacement for the former dark/gold Navigator identity. The name becomes one large, looping cobalt route: it connects the idea of personal access to a real subscription form. The visual language pairs cool light surfaces with oversized Cyrillic typography and one authored geometric motion sequence.

The public page invites and guides. Personal access and administration use the same materials with compact type and information density. The previous Navigator comp is superseded; this build is code-led and has no approved image comp. Ground truth is the current shipped source and rendered screenshots.

## Colors

Cobalt marks actions, focus, selected controls and measured traffic. Mineral ground and white panels separate groups. Navy is reserved for the footer and YouTube story. Semantic green and red describe status and errors, always with text.

**The useful color rule.** Keep routine information neutral so selection, state and the next action remain clear. The legacy `--gold` custom property is an alias of the blue accent, not a gold color commitment. Placeholders and inactive client labels use the muted token; their measured contrast is 4.96:1 and 4.70:1 on their respective backgrounds.

## Typography

Self-hosted Onest Variable carries the entire interface, including Cyrillic. Large public type has tight tracking and a compact line height. The phone hero uses `clamp(62px,16.5vw,98px)`; phone section headings use 44px. Utility labels and table metadata retain their smaller operational hierarchy. Counts, limits and traffic use tabular numerals.

The footer wordmark scales with the configured brand-name length. Do not invent a second display family, technical monospace styling or synthetic performance statistics.

## Layout

The public canvas is capped at 1440px with 56px desktop side insets, reducing through 36px and 28px to 20px on phones. The sticky top navigation becomes an expandable menu at 650px. The hero keeps text, decorative route and working subscription form separate; on phones the route occupies its own region above the stacked form.

The service explanation and FAQ use asymmetric two-column layouts, collapsing into reading order on phones. Device tabs stay in a single row; the setup panel places a large platform symbol beside the instructions on desktop and a compact identifier above them on phones.

Administration retains a fixed sidebar (245px, then 215px and 185px), replaced by a compact header and full-height menu at 650px. Metric summaries become two columns. Tables scroll locally; the page must fit its viewport. Drawers become full-width on phones.

## Elevation & Depth

Resting content uses tonal separation. The route is intentionally dimensional geometric artwork, with blue material shading confined to that signature. A translucent sticky navigation keeps orientation while scrolling. Menus, toasts and the access drawer use soft offset shadows; the drawer backdrop subordinates the page with a restrained blur. Primary hover feedback has a small blue shadow.

## Shapes

Primary actions and segmented selections use fully rounded silhouettes. Panels use 16px radii; ordinary fields use 12px. Phone panels use 14px where present in source. Lucide and the two-stroke brand mark form the icon vocabulary. QR codes remain actual server-generated images on white plates.

## Components

Buttons respond to press with a subtle scale; hover feedback is restricted to hover-capable devices. Fields show a visible focus treatment, themed caret and accessible labels. Error text is linked to the subscription field. Device tabs retain roving focus, arrow/Home/End handling and selected state. Client choices retain pressed state. FAQ answers follow their question in document order and expose expanded state. Native modal dialogs retain focus handling, Escape dismissal, a close control and background scroll locking.

**The one authored motion rule.** The cobalt route combines a slow float, pointer depth, scroll parallax and a moving signal. Entering content uses a short upward reveal from an already-visible default. Everyday controls remain quick; no motion owns application state or blocks reading. The global reduced-motion query and presentation hook remove movement while preserving content. No frame-rate guarantee is inferred from still screenshots.

The chart continues to render measured bytes and a truthful flat zero state. The personal page preserves subscription import/copy, usage, expiration and status explanations. No imagery replaces working controls. Text about YouTube, domain routing and ISP whitelists states actual limitations, rather than promising ad-free video or universal bypass.


The personal cabinet is an Operate surface at `/connect/{token}` (also `/account/{token}`); `/account` is its primary username/password entry, with a secondary personal-link entry at `/account/link`. It inherits the light/cobalt system with a compact footer and contextual overview/subscription/device navigation. A blue term panel and white traffic panel carry actual access conditions; amber and rose inline notifications communicate approaching expiry and quota exhaustion. Keep account headings fixed, instructions compact, long names wrapped and links selectable. Do not repeat the landing sculpture or monumental footer inside the cabinet.

Cabinet notifications are derived from the current API data and time: expiry at seven days and an urgent tier at one day; usage at 80% and an urgent tier at 95%. Actual expiry, exhaustion and pause states remain explicit. Dates and update times use Krasnoyarsk (UTC+7). A transient refresh error preserves labelled stale data; a revoked link clears personal content. The cabinet refreshes every 15 seconds while visible and on returning to the tab. Warnings live in the cabinet, with no promise of email, push or messaging delivery.

Password entry uses the existing rounded field with a named show/hide control, normal browser autocomplete, an optional remembered-login checkbox and an inline error. The admin access form groups credentials in a fieldset. Issued credentials use a blue-tinted notice, a masked password and an explicit copy action; closing the detail removes the cleartext from UI state. Reset confirmation explains that account sessions end while the VPN subscription remains unchanged. Drawers start at the top when opened so newly issued credentials remain discoverable.

Self-service password changes live in an inline Security section after usage. The existing password field appears three times with explicit labels, current/new autocomplete and visibility controls. A short note explains that other sessions end; confirmation and current-password failures are inline, and a successful save clears all three fields and shows a written success state. Only username/password-authenticated cabinets expose this form; a bearer-link cabinet keeps its existing setup controls.

## Do's and Don'ts

- Keep the light mineral ground, cobalt actions, Onest typography and single route signature across future surfaces.
- Keep routine management calm, statuses labelled, focus visible and table overflow local.
- Preserve real links, QR output, data, server behavior and subscription handlers.
- Do not restore the superseded dark/gold world or use its old comp as visual authority.
- Do not add fake metrics, ad-removal guarantees, universal whitelist-bypass claims or decorative charts.
- Do not use repeated floating illustrations to compete with the route.

<!-- Recorded from final src/style.css, src/main.jsx, src/experience.jsx and index.html. Independent finish review: both contrast findings resolved. Local fixture flows and public production smoke checks are separate evidence in .impeccable/review/. -->
