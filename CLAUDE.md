# build123d Tests — Local Instructions

## VLM Verification (MANDATORY)

After creating or modifying any brick/model script, you MUST visually verify the output using the render pipeline:

1. Run `./render.sh models/lego/<model>.py` to generate 14-angle diagnostic renders
2. Read the rendered PNGs from `renders/` using the Read tool (VLM)
3. Inspect every angle for geometry problems: exposed cavities, missing features, incorrect proportions, holes, z-fighting
4. Do NOT rationalize away visible problems — if something looks wrong, it IS wrong. Fix it and re-render until clean.

This applies to every individual brick type, not just the collection. Verify each model independently.
