# build123d Tests — Local Instructions

## VLM Verification (MANDATORY)

After creating or modifying any brick/model script, you MUST visually verify the output using the render pipeline:

1. Run `./render.sh models/lego/<model>.py` to generate 14-angle diagnostic renders
2. Read the rendered PNGs from `renders/` using the Read tool (VLM)
3. Inspect every angle for geometry problems: exposed cavities, missing features, incorrect proportions, holes, z-fighting
4. Do NOT rationalize away visible problems — if something looks wrong, it IS wrong. Fix it and re-render until clean.

This applies to every individual brick type, not just the collection. Verify each model independently.

## build123d: Consult the Docs First (MANDATORY)

Before writing geometry code, check the build123d docs and cheat sheet to avoid reinventing built-ins:
https://build123d.readthedocs.io/en/latest/cheat_sheet.html

**Things that have built-in solutions** (non-exhaustive — always check):
- Positioning: `GridLocations`, `HexLocations`, `PolarLocations`, `Locations`
- Booleans: `+` (fuse), `-` (cut), `&` (intersect/clip), `Mode` enum
- Shelling: `offset(amount, openings=[faces])` — hollow with selective openings
- Slopes/wedges: `Wedge(dx, dy, dz, xmin, zmin, xmax, zmax)`
- Extrude limits: `extrude(until=Until.NEXT)`, `Until.LAST`, `Until.PREVIOUS`
- Edge selection: `Select.NEW`, `Select.LAST`, `.edges().filter_by()`, `.sort_by()`
- Splitting: `split()` (but beware: doesn't call `clean()` — see manifest)
- Chamfer/fillet: `chamfer()`, `fillet()` on edges
- Mirroring: `mirror()`, `Plane` objects
- Sketch ops: `offset()`, `make_face()`, `make_hull()`
- Assembly: `Compound([parts])` — group without boolean union
- Planes: `Plane.XY`, `.offset()`, custom `Plane(origin, x_dir, z_dir)`

**The principle: if you're writing manual math for positioning, clipping, shelling, or grid layout — you're probably doing it wrong.** Check the docs.
