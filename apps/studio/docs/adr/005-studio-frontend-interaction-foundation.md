# ADR-005: Studio Frontend Interaction Foundation

## Status

Accepted

## Date

2026-07-13

## Context

Studio needs accessible interaction behavior without surrendering ownership of
its visual language. Its imported frontend previously contained source derived
from Tailwind Plus Catalyst. That source is governed by the Tailwind Plus
license, and its broad component APIs also constrain Studio to decisions that
were made for a generic component kit rather than this product.

Studio will need direct control over appearance, density, responsive behavior,
and future user-selectable presentation. Those product concerns must not be
coupled to the library that implements focus management, keyboard interaction,
portals, or dismissal behavior.

## Decision

Studio uses the standalone `@base-ui/react` project as its default foundation
for interaction primitives. Base UI owns low-level behavior such as focus
management, keyboard semantics, form integration, portals, and modal
dismissal. It does not own Studio's visual design.

Junjo owns a small semantic UI layer based on actual Studio needs:

- `ActionButton` represents product actions and their intent;
- `Modal` represents interrupting, labelled application tasks;
- `Switch` represents a labelled boolean setting;
- `AppLink` makes internal route navigation and external navigation explicit;
- `AppShell` owns Studio's responsive frame and authenticated navigation.

Feature code consumes those contracts. It does not import Base UI primitives,
depend on Base UI state attributes, or assemble its own modal and switch
behavior. Native HTML remains the default for text, headings, forms, tables,
and static layout when no interaction primitive is needed.

Tailwind CSS remains the styling engine. Junjo owns the semantic appearance
variables, component styles, layout, responsive rules, and light/dark
presentation. Visual changes therefore do not require changing feature state
or interaction behavior.

The Catalyst-derived component tree is deleted. No compatibility wrapper,
deprecated alias, prop adapter, or fallback remains. Replacement components
are independently authored from Studio's requirements and do not copy or adapt
Catalyst source, markup recipes, APIs, class recipes, or assets.

Existing third-party primitives that are outside the replaced surface may
remain when they are open source under a permissive license suitable for source
and binary redistribution. They are not the default for new shared interaction
behavior.

## Boundaries

- Shared components expose product semantics, not a catalog of arbitrary
  colors or every underlying primitive option.
- New shared interaction machinery uses Base UI, native browser behavior, or a
  similarly permissively licensed open-source primitive. Proprietary,
  commercial-source, and source-available component foundations are excluded.
- Features own content and feature state; shared components own interaction
  behavior and shared presentation.
- Buttons remain buttons and links remain links.
- Every switch has a programmatic label.
- Every modal has a title, description, visible close action, focus
  containment, Escape dismissal, and focus restoration.
- Mobile navigation closes after internal route selection and exposes the same
  authenticated destinations as desktop navigation.
- Third-party notices remain part of Studio source and production artifacts.

## Validation

Component tests cover action submission semantics, disabled state, modal ARIA
relationships, focus containment and restoration, Escape and outside
dismissal, switch pointer and keyboard interaction, internal and external link
semantics, active routes, authenticated navigation, and mobile navigation.

Frontend lint, tests, and production build must pass together. Current source
must contain no Catalyst component or import and no obsolete Headless UI,
Framer Motion, or standalone switch dependency used only by that tree.

## Consequences

Studio can change visual direction without replacing its interaction engine or
rewriting feature state. Base UI supplies maintained accessibility machinery,
while the Junjo layer remains small enough to understand and change directly.

Studio now owns more styling and responsive-layout work. Shared contracts must
remain narrow; adding speculative variants would recreate the generic kit this
decision removes.

Base UI is an implementation dependency of the shared UI layer. A future
primitive change should be contained there, but this ADR does not require a
compatibility surface for such a change.

## Rejected Alternatives

- Retain Catalyst: rejected because it does not provide the desired licensing
  or product-control boundary.
- Change only Catalyst's underlying primitive imports: rejected because the
  derivative source and component contracts would remain.
- Copy Catalyst behind Junjo names: rejected because renaming does not change
  ownership or licensing.
- Use only native elements: rejected because robust modal behavior requires
  maintained focus, dismissal, portal, and accessibility machinery.
- Build a comprehensive design system now: rejected because current Studio
  requirements support a much smaller and clearer semantic layer.

## Related Decisions

- `docs/adr/0002-platform-licensing-and-third-party-material.md`
- `docs/adr/002-redux-toolkit-listener-middleware-pattern.md`
