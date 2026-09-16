---
name: capt-3d-scenes
description: Build and apply 3D camera scenes (orbit/tilt/depth) to Cap 0.6+ screen recordings via cap-tools — use when an agent asks about "3D", "scene", "camera move", "depth", or "demo video polish" for a Cap recording.
metadata:
  requires: Cap Desktop 0.6.0+ with its CLI (`cap`) on PATH; cap-tools checkout for `capt`
---

# 3D camera scenes for Cap recordings (`capt scene`)

Cap 0.6 added `timeline.camera3dSegments`: the camera orbits/tilts/pushes
around the whole recording in 3D, instead of zoom-cropping toward the
cursor (`timeline.zoomSegments`). The two compose — scenes move the
camera, zoom moves the crop. Everything below is headless (no Studio) and
verified end-to-end on 0.6.0: write config → `cap export` → the pose
visibly renders.

## When to pick which style

| Style | What it does | Use for |
|---|---|---|
| `reveal` (default) | One full-clip segment: tiltX 8°, tiltY −12°, zoom 1.08 — the screen leans back in space | Everything; safest polish for any demo |
| `punch` | One segment per click/mark (0.8s before → 2.5s after, gap < 1s merges — same window math as zoom): tiltX 10°, tiltY −15°, zoom 1.12 | Click-through product demos where each click should land with a camera push |
| `orbit` | One segment, tiltY sweeps −20° → +20° across the clip (2-keyframe track) | Hero shots / intros where the camera swings across |
| `flat` | No-op (empty list) | Escape hatch; also removes an existing scene |

## The workflow

```bash
# 1. record as usual (events sidecar lands next to the .cap)
uv run capt demo my-demo --scene orbit          # scenes at record time
# or post-record against the same sidecar:
uv run capt scene apply recordings/my-demo.cap recordings/my-demo.events.json \
  --style orbit --yes

# 2. preview without writing
uv run capt scene propose recordings/my-demo.events.json --style punch

# 3. export — scenes render headlessly, no Studio needed
cap export recordings/my-demo.cap out.mp4 --json
```

> **Cap 0.6.0 export gotcha (verified 2026-09-15):** the FIRST `cap export`
> of a freshly-copied `.cap` runs a publish pass that strips
> `camera3dSegments` from the config and renders WITHOUT the pose. Export
> the project once (a throwaway warmup), then `capt scene apply` again, then
> export for real — from the second export on, segments persist and the 3D
> pose renders (orbit measured 60.8% pixel difference across its swing;
> pose visibly keystoned in-frame, flat outside the segment window). Same
> applies to `reveal` and `punch`.

`capt scene apply` reads the project's CURRENT config, replaces only
`timeline.camera3dSegments` (scenes replace each other; zoom segments are
untouched), and writes the whole document back — never a partial object.

**Demo-timeline note:** for whole-take-then-sections workflows, apply the
scene to the full take, export once, then cut labeled sections with
`capt section cut` — sections inherit the pose. See
`docs/playbook-auto-zoom-recording.md` § "Whole-take-then-sections workflow".

## Segment schema (verified by write→read round-trip on 0.6.0)

```json
{
  "start": 0.0, "end": 4.0, "enabled": true,
  "properties": {"tiltX": 8.0, "tiltY": -25.0, "roll": 0.0, "rotateX": 0.0,
                 "rotateY": 0.0, "zoom": 1.0, "fov": 50.0, "panX": 0.0, "panY": 0.0},
  "tracks": {"tiltY": [{"time": 0.0, "value": 0.0, "outEasing": [0.65, 0.0],
                        "inEasing": [0.35, 1.0]},
                       {"time": 4.0, "value": -18.0}]},
  "blur": {"mode": "radial", "strength": 8.0, "falloff": 0.45, "focusX": 0.5,
           "focusY": 0.5, "focusSize": 0.4, "angle": 0.0, "dirPosition": 0.5,
           "bokeh": false},
  "transitionIn": 0.5, "transitionOut": 0.5
}
```

## Geometry contract (from Cap's own doc-strings; confirmed by render test)

- Content plane's longest side spans **2 world units**, centered at origin,
  facing +Z.
- `tiltX`/`tiltY`/`roll` orbit the **camera** (Euler YXZ, roll innermost);
  `rotateX`/`rotateY` rotate the **content plane**.
- `zoom` = camera **distance**: larger = smaller on screen. To make the
  recording bigger, *decrease* zoom (or increase fov). There is no
  auto-compensation: apparent size ∝ 1/(zoom·tan(fov/2)).
- `panX`/`panY` truck the camera (+x right, +y up).
- **Animatable tracks** (only these): `tiltX, tiltY, rotateX, rotateY, fov,
  blurStrength, blurFalloff, blurFocusSize, blurFocusX, blurFocusY,
  blurAngle, blurDirPosition`. NOT animatable: roll, panX, panY, zoom.
- Keyframes: `{time, value, outEasing, inEasing}` — bezier split-handles;
  omit them for cubic ease-in-out (P1[0.65,0], P2[0.35,1]). `time` is
  seconds **relative to the segment start**.
- Blur: `mode` ∈ none|radial|directional|tiltShift; strength is a px radius
  at 1080p output height, capped at 20.

## Verify a scene actually rendered (headless)

```bash
cap export project.cap out.mp4 --json
ffmpeg -y -ss 2 -i out.mp4 -frames:v 1 mid.png
ffmpeg -y -ss 10 -i out.mp4 -frames:v 1 flat.png
ffmpeg -i mid.png -i flat.png -filter_complex \
  blend=all_mode=difference,scale=64:36,format=gray -f rawvideo - \
  | python3 -c 'import sys; d=sys.stdin.buffer.read(); nz=sum(1 for x in d if x>12); print(f"{100*nz/len(d):.1f}% pixels differ")'
```

A working pose measured 56.2% strongly-differing pixels; a near-zero result
means the segment didn't render — check `enabled: true` and that
`start`/`end` sit inside the recording.

## Background presets that pair with 3D

`capt config --preset gradient|animated` writes 0.6's moving backgrounds
(verified round-trip): `gradient` (static two-color) and `animatedGradient`
(shader-driven flow: colorStops/direction/flowScale/flowStrength/curvature/
detail/relief/shader/grainAmount/grainSize/motionSpeed/seed).