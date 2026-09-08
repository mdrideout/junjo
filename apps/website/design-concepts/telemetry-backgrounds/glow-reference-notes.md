# Astra reference and Junjo glow study

Inspected on September 6, 2026. This is a rendering study of the
[Astra hero](https://openai.com/index/gpt-6-astra/), based on its visible output,
canvas attributes, and public JavaScript loaded by the browser.

## What the reference does

The hero is an interactive WebGL scene; its canvas identifies Three.js r180.
Its stars combine tiny sharp centers with diffuse blue and warm light. A small
number of bright stars stand out against much dimmer particles and background.

The [particle module](https://openai.com/_next/static/immutable/chunks/1rfzm7jt1igp4.js)
uses curve-driven points and custom shaders. Per-particle properties control
color, brightness, size, depth, and twinkle. Bright cores shift toward white;
light is combined additively, so nearby particles reinforce each other. This
creates the impression of emitted light rather than flat colored circles.

The [rendering module](https://openai.com/_next/static/immutable/chunks/1uq8b6yni-tzr.js)
adds luminance-selected bloom with blurred reconstruction, ACES filmic tone
mapping, and optional optical halos, streaks, and procedural lens texture.
The halo surrounds an existing sharp source rather than replacing its center.

My design takeaway: keep sharp detail inside the glow and vary brightness
between elements. Uniform large blurs would obscure the structure we need to
communicate in Junjo.

## Applied to study 22

Junjo keeps its Canvas 2D renderer. Three cached radial glow sprites provide
blue, amber, and yellow halos. Each particle has a colored body and a smaller,
pale center. Additive compositing lets nearby lights combine. Graph outlines
use faint wider strokes around a crisp line and narrow highlight.

Glow follows each particle's existing opacity, including the faint archive
layers. The staged sequence, orange migrated span starts, empty new trace,
graph assembly, hero copy, and shading remain in place. All drawing state is
restored before the next frame's background is rendered. Cached sprites avoid
applying an expensive blur separately to every moving particle each frame.
