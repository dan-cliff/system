# Map shapes

Simplified from [Natural Earth](https://www.naturalearthdata.com/) (public domain):

- `world.json`: 1:50m Admin 0 countries. Each shape's `id` is the ISO 3166-1
  alpha-2 code (`ISO_A2_EH`, falling back to `ADM0_A3`).
- `admin1/<CC>.json`: 1:10m Admin 1 states and provinces, one file per country.
  Each shape's `id` is its ISO 3166-2 code (e.g. `AU-VIC`); parts sharing a code
  are dissolved into one shape.

Built with mapshaper: `-simplify 25%` (countries) / `-simplify 10%` (states),
TopoJSON with `quantization=100000`.
