# `project-config.json` Schema

Full annotated schema for Cap's `project-config.json` — the document that
controls everything Cap Desktop Studio exposes as a UI. Written via
`cap project config set <project.cap> --settings-json '<json>'`.

Derived from real `.cap` projects produced by Cap Desktop. Field names are
camelCase. Omitting a field resets it to the Cap default.

---

## Top-level structure

```json
{
  "aspectRatio": null,
  "background": { ... },
  "camera": { ... },
  "audio": { ... },
  "cursor": { ... },
  "hotkeys": { ... },
  "timeline": { ... },
  "captions": null | { ... },
  "keyboard": null | { ... },
  "clips": [ ... ],
  "annotations": [],
  "screenMotionBlur": 0.5,
  "screenMovementSpring": { ... }
}
```

---

## `background`

Controls the desktop background / framing that appears behind the recording.

```json
"background": {
  "source": {
    "type": "wallpaper",
    "path": "\\\\?\\C:\\Users\\<user>\\AppData\\Local\\Cap\\assets\\backgrounds\\cities\\sf.jpg"
  },
  "blur": 0.0,
  "padding": 10.0,
  "rounding": 7.5,
  "roundingType": "squircle",
  "inset": 0,
  "crop": null,
  "shadow": 73.6,
  "advancedShadow": {
    "size": 14.4,
    "opacity": 68.1,
    "blur": 3.8
  },
  "border": null
}
```

### `background.source`

| Type | Example | Notes |
|---|---|---|
| `"wallpaper"` | `{"type":"wallpaper","path":"...\\sf.jpg"}` | Path to a wallpaper image. Cap ships backgrounds at `AppData\Local\Cap\assets\backgrounds\`. |
| `"color"` | `{"type":"color","value":[255,255,255],"alpha":255}` | Solid RGBA colour. `value` is `[R, G, B]`; `alpha` is 0–255. |

### `background` layout fields

| Field | Type | Description |
|---|---|---|
| `padding` | float | Space between the recording and the background edge. `0.0` = full-bleed, `10.0` = standard framed look. |
| `rounding` | float | Corner rounding radius. `0.0` = sharp, `7.5` = subtle squircle. |
| `roundingType` | string | `"squircle"` (observed). |
| `shadow` | float | Overall shadow intensity, 0–100. `73.6` = prominent demo shadow. |
| `advancedShadow.size` | float | Shadow spread size. |
| `advancedShadow.opacity` | float | Shadow opacity 0–100. |
| `advancedShadow.blur` | float | Shadow blur radius. |
| `blur` | float | Background blur. `0.0` = no blur. |
| `inset` | int | Inset amount. `0` = none. |
| `border` | null \| object | Border around the recording. `null` = none. |
| `crop` | null \| object | Crop the recording. `null` = no crop. |

### Common presets

```jsonc
// Raw / no background (clean full-screen)
"background": {
  "source": {"type":"color","value":[0,0,0],"alpha":255},
  "padding": 0.0,
  "rounding": 0.0,
  "shadow": 0.0
}

// Framed / demo look (wallpaper, padding, shadow)
"background": {
  "source": {"type":"wallpaper","path":"\\\\?\\C:\\Users\\<user>\\AppData\\Local\\Cap\\assets\\backgrounds\\cities\\sf.jpg"},
  "padding": 10.0,
  "rounding": 7.5,
  "shadow": 73.6
}
```

---

## `cursor`

Controls cursor appearance and animation.

```json
"cursor": {
  "hide": false,
  "hideWhenIdle": false,
  "hideWhenIdleDelay": 2.0,
  "size": 100,
  "type": "auto",
  "animationStyle": "mellow",
  "tension": 470.0,
  "mass": 3.0,
  "friction": 70.0,
  "raw": false,
  "motionBlur": 0.5,
  "useSvg": true,
  "rotationAmount": 0.15,
  "baseRotation": 0.0,
  "clickSpring": null,
  "stopMovementInLastSeconds": null
}
```

| Field | Type | Description |
|---|---|---|
| `hide` | bool | `true` = cursor not rendered in export. |
| `hideWhenIdle` | bool | Hide cursor after `hideWhenIdleDelay` seconds of no movement. |
| `size` | int | Cursor size. `100` = standard, `200` = large/prominent. |
| `type` | string | `"auto"` uses the OS cursor graphic. |
| `animationStyle` | string | `"mellow"` = smooth spring follow (the demo-recording style). |
| `tension`, `mass`, `friction` | float | Spring physics for cursor follow animation. |
| `motionBlur` | float | 0–1. Blur trail behind cursor. `0.5` = visible trail, `0.0` = crisp. |
| `raw` | bool | `false` = animated cursor. `true` = raw OS cursor position (no spring). |
| `clickSpring` | null \| object | Override click animation. `null` = default. |

---

## `camera`

Controls the webcam overlay (picture-in-picture).

```json
"camera": {
  "hide": false,
  "mirror": false,
  "position": {"x": "right", "y": "bottom"},
  "size": 30.0,
  "zoomSize": 60.0,
  "rounding": 100.0,
  "shadow": 62.5,
  "shape": "square",
  "roundingType": "squircle",
  "scaleDuringZoom": 0.7,
  "backgroundBlur": {"mode": "off"}
}
```

Set `"hide": true` to suppress the camera overlay entirely (recommended for
screen-only recordings).

---

## `audio`

```json
"audio": {
  "mute": false,
  "improve": false,
  "micVolumeDb": 0.0,
  "micStereoMode": "stereo",
  "systemVolumeDb": 0.0
}
```

Set `"mute": true` to silence all audio in the export.

---

## `hotkeys`

```json
"hotkeys": {
  "show": false
}
```

`show: true` renders a hotkey indicator overlay.

---

## `timeline`

The timeline controls trim, zoom, scenes, masks, text, captions, and keyboard
overlay segments. **All segment arrays contain time-ranged objects with `start`
and `end` in seconds from the start of the recording.**

```json
"timeline": {
  "segments": [
    {
      "recordingSegment": 0,
      "timescale": 1.0,
      "start": 0.0,
      "end": 120.5
    }
  ],
  "zoomSegments": [],
  "sceneSegments": [],
  "maskSegments": [],
  "textSegments": [],
  "captionSegments": [],
  "keyboardSegments": []
}
```

### `timeline.segments`

Defines which portion of the raw recording is included. `timescale: 1.0` =
normal speed. Set `end` to trim. Multiple segments = multi-clip edit.

### `timeline.zoomSegments` ← the key field

Each entry zooms into the recording between `start` and `end`.

```json
{
  "start": 12.5,
  "end": 18.0,
  "amount": 2.0,
  "mode": "auto",
  "glideDirection": "none",
  "glideSpeed": 0.5,
  "instantAnimation": false,
  "edgeSnapRatio": 0.25
}
```

| Field | Type | Description |
|---|---|---|
| `start` | float | Start of zoom, seconds from recording start. |
| `end` | float | End of zoom (zoom out). |
| `amount` | float | Zoom level. `1.5` = subtle, `2.0` = strong demo zoom. |
| `mode` | string | `"auto"` = Cap follows cursor/activity. `"manual"` = fixed position. |
| `glideDirection` | string | `"none"`, or a direction for a glide pan. |
| `glideSpeed` | float | Speed of glide pan. `0.5` = default. |
| `instantAnimation` | bool | `false` = animated zoom in/out. `true` = cut. |
| `edgeSnapRatio` | float | How close to edges before the zoom clamps. `0.25` = standard. |

**Workflow pattern:** When driving the browser with Playwright, record event
timestamps (click times, navigation times). After the recording, build
`zoomSegments` from those timestamps and write them to the project config
before exporting.

```js
// Example: zoom in for 3 seconds around each recorded click
const zoomSegments = clickTimestamps.map(t => ({
  start: Math.max(0, t - 0.5),
  end: t + 2.5,
  amount: 2.0,
  mode: "auto",
  glideDirection: "none",
  glideSpeed: 0.5,
  instantAnimation: false,
  edgeSnapRatio: 0.25
}));
```

### `timeline.captionSegments`

Timed caption overlays. Each segment has `start`, `end`, and caption content.
(Schema not yet fully observed — use `captions.segments` instead.)

### `timeline.keyboardSegments`

Auto-populated during recording with keystroke events. Each segment has:

```json
{
  "id": "kb-1",
  "start": 13.27,
  "end": 14.07,
  "displayText": "⌃C",
  "keys": [{"key": "c", "timeOffset": 0.0}],
  "fadeDurationOverride": null,
  "positionOverride": null,
  "colorOverride": null,
  "backgroundColorOverride": null,
  "fontSizeOverride": null,
  "uppercaseOverride": null
}
```

---

## `captions`

```json
"captions": {
  "segments": [],
  "settings": {
    "enabled": true,
    "font": "System Sans-Serif",
    "size": 50,
    "color": "#FFFFFF",
    "backgroundColor": "#000000",
    "backgroundOpacity": 95,
    "position": "bottom-center",
    "italic": false,
    "fontWeight": 400,
    "outline": false,
    "outlineColor": "#000000",
    "exportWithSubtitles": false,
    "highlightColor": "#FFFFFF",
    "fadeDuration": 0.2,
    "lingerDuration": 0.4,
    "wordTransitionDuration": 0.25,
    "activeWordHighlight": false
  }
}
```

Set `"captions": null` to disable the caption overlay entirely.

---

## `keyboard`

```json
"keyboard": {
  "settings": {
    "enabled": true,
    "font": "System Sans-Serif",
    "size": 50,
    "color": "#FFFFFF",
    "backgroundColor": "#000000",
    "backgroundOpacity": 95,
    "position": "bottom-center",
    "fontWeight": 400,
    "fadeDuration": 0.15,
    "lingerDuration": 0.8,
    "groupingThresholdMs": 500.0,
    "showModifiers": true,
    "showSpecialKeys": true,
    "uppercase": false
  }
}
```

Set `"keyboard": null` to disable keystroke display entirely.

---

## `screenMotionBlur` and `screenMovementSpring`

```json
"screenMotionBlur": 0.5,
"screenMovementSpring": {
  "stiffness": 200.0,
  "damping": 40.0,
  "mass": 2.25
}
```

`screenMotionBlur` (0–1) adds a velocity-proportional blur to the screen
during zoom transitions. `0.0` = crisp, `0.5` = noticeable trail.

`screenMovementSpring` controls the physics of zoom animation:

| Preset | stiffness | damping | mass | Feel |
|---|---|---|---|---|
| Snappy (demo) | `200.0` | `40.0` | `2.25` | Quick, confident zoom |
| Smooth/elastic | `120.0` | `14.0` | `1.0` | Bouncy, organic zoom |

---

## `clips`

```json
"clips": [
  {
    "index": 0,
    "offsets": {
      "camera": 0.0,
      "mic": 0.0,
      "system_audio": 0.0
    }
  }
]
```

One entry per recording segment. `offsets` sync-align the camera, mic, and
system audio streams relative to the screen recording. `0.0` = perfectly
aligned (the default).

---

## Complete minimal config templates

### Clean export (no background, no camera, no cursor, max quality)

```json
{
  "aspectRatio": null,
  "background": {
    "source": {"type": "color", "value": [0, 0, 0], "alpha": 255},
    "blur": 0.0, "padding": 0.0, "rounding": 0.0, "shadow": 0.0,
    "roundingType": "squircle", "inset": 0, "crop": null, "border": null
  },
  "camera": {"hide": true},
  "audio": {"mute": false},
  "cursor": {"hide": false, "size": 100, "animationStyle": "mellow", "motionBlur": 0.0, "type": "auto"},
  "hotkeys": {"show": false},
  "timeline": {"segments": [{"recordingSegment": 0, "timescale": 1.0, "start": 0.0, "end": 9999}],
               "zoomSegments": [], "sceneSegments": [], "maskSegments": [],
               "textSegments": [], "captionSegments": [], "keyboardSegments": []},
  "captions": null,
  "keyboard": null,
  "clips": [{"index": 0, "offsets": {"camera": 0.0, "mic": 0.0, "system_audio": 0.0}}],
  "annotations": [],
  "screenMotionBlur": 0.0,
  "screenMovementSpring": {"stiffness": 200.0, "damping": 40.0, "mass": 2.25}
}
```

### Demo/presentation (wallpaper background, auto-zoom, animated cursor)

```json
{
  "aspectRatio": null,
  "background": {
    "source": {"type": "wallpaper", "path": "\\\\?\\C:\\Users\\<user>\\AppData\\Local\\Cap\\assets\\backgrounds\\cities\\sf.jpg"},
    "blur": 0.0, "padding": 10.0, "rounding": 7.5, "roundingType": "squircle",
    "inset": 0, "crop": null, "shadow": 73.6,
    "advancedShadow": {"size": 14.4, "opacity": 68.1, "blur": 3.8}, "border": null
  },
  "camera": {"hide": true},
  "audio": {"mute": false},
  "cursor": {
    "hide": false, "size": 100, "type": "auto", "animationStyle": "mellow",
    "motionBlur": 0.5, "raw": false, "useSvg": true
  },
  "hotkeys": {"show": false},
  "timeline": {
    "segments": [{"recordingSegment": 0, "timescale": 1.0, "start": 0.0, "end": 9999}],
    "zoomSegments": [
      {"start": 5.0, "end": 10.0, "amount": 2.0, "mode": "auto",
       "glideDirection": "none", "glideSpeed": 0.5, "instantAnimation": false, "edgeSnapRatio": 0.25}
    ],
    "sceneSegments": [], "maskSegments": [], "textSegments": [],
    "captionSegments": [], "keyboardSegments": []
  },
  "captions": null,
  "keyboard": null,
  "clips": [{"index": 0, "offsets": {"camera": 0.0, "mic": 0.0, "system_audio": 0.0}}],
  "annotations": [],
  "screenMotionBlur": 0.5,
  "screenMovementSpring": {"stiffness": 200.0, "damping": 40.0, "mass": 2.25}
}
```
