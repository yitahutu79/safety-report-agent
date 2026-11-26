# Offline theme icon subsets

Source collection format: Iconify icon sets, https://github.com/iconify/icon-sets .
Only 16 selected icons from each of Tabler, MingCute and Iconoir are exported to SVG under web/ui-icons; no complete collection or network runtime is shipped.

Each collection directory contains its upstream license and manifest.json, including original author, license source, original icon identifiers, the downloaded JSON SHA-256 and the individual exported SVG SHA-256. Icon bodies are unchanged; the SVG wrapper supplies the documented collection dimensions. Tabler and Iconoir are MIT; MingCute is Apache-2.0. All were downloaded 2026-11-26.

Theme assignment:
- Notion / Claude: existing Phosphor duotone assets.
- Linear / Apple: existing Lucide outline assets.
- Stripe: Tabler outline.
- Fashion: Iconoir thin outline.
- Vivid: MingCute filled.

Navigation, library document glyphs, illustration masks and dock symbols select their matching family at runtime. Universal utility arrows, the brand mark and controls without a semantic match retain their original assets. This is an app integration of offline SVG subsets, not a claim that every named icon project or the Iconify browser runtime is installed.
