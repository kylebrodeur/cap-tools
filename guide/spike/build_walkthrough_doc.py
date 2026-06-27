#!/usr/bin/env python3
"""
build_walkthrough_doc.py — render an analyzed walkthrough (items.json) into a
single self-contained HTML document with per-item screenshots as named files.

Unlike cap_ingest.py (one card per click), this renders an *analyzed* item
breakdown: each item is documented with the screen at its narration timestamp,
a faithful read of what was said, and the decision. Screenshots are extracted
from the recording's display.mp4 at each item's timestamp and written as
images/<item-id>.jpg, linked relatively.

Usage:
    uv run spike/build_walkthrough_doc.py <items.json> <display.mp4> <out-dir>
"""
import html
import json
import subprocess
import sys
from pathlib import Path

OFFSET_S = 0.3  # nudge past the narration moment so the UI is settled


def extract(display: Path, t: float, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-ss", f"{max(t + OFFSET_S, 0):.3f}", "-i", str(display),
         "-vframes", "1", "-q:v", "2", "-y", str(out)],
        capture_output=True,
    )
    return out.exists()


def ts(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def esc(x: str) -> str:
    return html.escape(x or "")


def load_moves(cursor_path) -> list[dict]:
    if not cursor_path or not Path(cursor_path).exists():
        return []
    d = json.loads(Path(cursor_path).read_text(encoding="utf-8"))
    return sorted(d.get("moves", []), key=lambda m: m.get("time_ms", 0))


def _wpct(pairs: list, p: float):
    sw = sum(w for _, w in pairs)
    if sw <= 0:
        return None
    target, acc = p * sw, 0.0
    for v, w in pairs:
        acc += w
        if acc >= target:
            return v
    return pairs[-1][0]


def region_for(moves: list[dict], t: float, pre: float = 5.0, post: float = 2.0,
               min_pts: int = 6, max_area: float = 0.45, pad: float = 0.03):
    """Dwell-weighted bounding box of where the cursor lingered while this item
    was narrated (the user 'moves the mouse around the area' they describe).
    Returns {x,y,w,h} normalized 0..1, or None if not confident."""
    lo, hi = (t - pre) * 1000.0, (t + post) * 1000.0
    win = [m for m in moves if lo <= m.get("time_ms", -1) <= hi]
    if len(win) < min_pts:
        return None
    weights = []
    for i, m in enumerate(win):
        dt = (win[i + 1]["time_ms"] - m["time_ms"]) if i + 1 < len(win) else 50
        weights.append(min(max(dt, 1), 1500))      # clamp dwell to 1..1500 ms
    xs = sorted((m["x"], w) for m, w in zip(win, weights))
    ys = sorted((m["y"], w) for m, w in zip(win, weights))
    x0, x1 = _wpct(xs, 0.10), _wpct(xs, 0.90)       # trim transit outliers
    y0, y1 = _wpct(ys, 0.10), _wpct(ys, 0.90)
    if None in (x0, x1, y0, y1):
        return None
    x0, y0 = max(0.0, x0 - pad), max(0.0, y0 - pad)
    x1, y1 = min(1.0, x1 + pad), min(1.0, y1 + pad)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0 or w * h > max_area:        # confidence gate: not too spread
        return None
    return {"x": round(x0, 4), "y": round(y0, 4), "w": round(w, 4), "h": round(h, 4)}


def item_card(it: dict, has_img: bool) -> str:
    flag = ""
    if it.get("flag"):
        flag = f'<div class="flag">⚑ {esc(it["flag"])}</div>'
    overlay = ""
    r = it.get("region")
    if r:
        overlay = (f'<span class="region" style="left:{r["x"]*100:.2f}%;top:{r["y"]*100:.2f}%;'
                   f'width:{r["w"]*100:.2f}%;height:{r["h"]*100:.2f}%"></span>')
    img = (f'<div class="shot"><img src="images/{it["id"]}.jpg" '
           f'alt="{esc(it["title"])}" loading="lazy">{overlay}</div>') if has_img else ""
    return f"""
    <article class="item" id="{esc(it.get('id',''))}">
      <div class="item-head">
        <span class="id">{esc(it.get('id',''))}</span>
        <span class="time">{ts(it.get('t', 0))}</span>
        <h3>{esc(it.get('title', it.get('id','')))}</h3>
      </div>
      {img}
      <p class="said"><span class="lbl">You said</span> {esc(it.get('said',''))}</p>
      <p class="decision"><span class="lbl">Decision</span> {esc(it.get('decision',''))}</p>
      {flag}
    </article>"""


def render(data: dict, have_img: set) -> str:
    globals_html = "".join(f"<li>{esc(g)}</li>" for g in data.get("globals", []))
    contra_html = "".join(
        f"<li><strong>{esc(c['title'])}.</strong> {esc(c['resolution'])}</li>"
        for c in data.get("contradictions", [])
    )
    oq_html = "".join(
        f"<li><strong>{esc(q.get('ref',''))}.</strong> {esc(q['q'])}</li>"
        for q in data.get("open_questions", [])
    )

    sections_html = ""
    total = 0
    for sec in data["sections"]:
        cards = ""
        for it in sec["items"]:
            cards += item_card(it, it["id"] in have_img)
            total += 1
        sections_html += f"""
  <section class="tab">
    <h2>{esc(sec['tab'])} <span class="range">{esc(sec.get('range',''))}</span></h2>
    {cards}
  </section>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(data['title'])}</title>
<style>
  *,*::before,*::after{{box-sizing:border-box}}
  body{{font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#222;
       max-width:920px;margin:0 auto;padding:40px 24px 90px;background:#fff}}
  h1{{font-size:24px;color:#1A3A5C;margin:0 0 4px}}
  .sub{{font-size:13px;color:#888;margin:0 0 2px}}
  .summary{{font-size:14px;color:#333;margin:14px 0 28px;padding:14px 18px;background:#F5F8FC;
           border:1px solid #D0DFF0;border-radius:8px}}
  .box{{border-radius:8px;padding:14px 18px;margin:0 0 18px}}
  .box h2{{font-size:15px;margin:0 0 8px}}
  .box ul{{margin:0;padding-left:20px}} .box li{{margin:0 0 6px}}
  .globals{{background:#F0F5FB;border:1px solid #D0DFF0}} .globals h2{{color:#2C5F8A}}
  .contra{{background:#FFF4E8;border-left:5px solid #D4730A}} .contra h2{{color:#8B4000}}
  .oq{{background:#F0FFF4;border:2px solid #1F7A45}} .oq h2{{color:#1F7A45}}
  h2{{font-size:18px;color:#1A3A5C;margin:34px 0 12px;padding-bottom:6px;border-bottom:2px solid #D0DFF0}}
  .range{{font-size:12px;color:#aaa;font-weight:normal}}
  .item{{border:1px solid #E2E8F0;border-radius:8px;padding:14px 16px;margin:0 0 16px}}
  .item-head{{display:flex;align-items:baseline;gap:10px;margin:0 0 8px;flex-wrap:wrap}}
  .item-head h3{{font-size:15px;color:#1A3A5C;margin:0;flex:1 1 60%}}
  .id{{font-family:monospace;font-size:11px;color:#fff;background:#2C5F8A;border-radius:4px;padding:2px 6px}}
  .time{{font-size:12px;color:#888;font-variant-numeric:tabular-nums}}
  .shot{{position:relative;display:inline-block;margin:0 0 10px;max-width:100%}}
  .shot img{{max-width:100%;border:1px solid #ddd;border-radius:5px;display:block}}
  .region{{position:absolute;border:3px dashed #D4730A;border-radius:4px;background:rgba(212,115,10,.10);pointer-events:none}}
  .said,.decision{{margin:0 0 6px}}
  .lbl{{display:inline-block;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
       padding:1px 6px;border-radius:3px;margin-right:6px;vertical-align:1px}}
  .said .lbl{{background:#EEF2F7;color:#566}} .decision{{color:#14361f}}
  .decision .lbl{{background:#1F7A45;color:#fff}}
  .flag{{margin-top:8px;font-size:13px;color:#8B4000;background:#FFF8E1;border-left:4px solid #E6C84A;
        border-radius:0 5px 5px 0;padding:7px 11px}}
  footer{{margin-top:50px;padding-top:14px;border-top:1px solid #e3e3e3;font-size:12px;color:#aaa}}
</style></head><body>
<h1>{esc(data['title'])}</h1>
<p class="sub">{esc(data.get('recording',''))}</p>
<p class="sub">{total} items across {len(data['sections'])} tabs</p>
<p class="summary">{esc(data.get('summary',''))}</p>

<div class="box globals"><h2>Global Rules (apply to every tab)</h2><ul>{globals_html}</ul></div>
<div class="box contra"><h2>Contradictions — resolved to your final word</h2><ul>{contra_html}</ul></div>
<div class="box oq"><h2>Open Questions — need your decision</h2><ul>{oq_html}</ul></div>
{sections_html}
<footer>Generated from a Cap Studio recording — transcript (faster-whisper) + click/cursor data, analyzed into items. Screenshots captured at each item's narration timestamp.</footer>
</body></html>"""


def render_md(data: dict, have_img: set) -> str:
    L: list[str] = []
    total = sum(len(s["items"]) for s in data["sections"])
    L += [f"# {data['title']}", "", f"*{data.get('recording','')}*", "",
          f"**{total} items across {len(data['sections'])} tabs**", "",
          data.get("summary", ""), ""]
    L += ["## Global Rules (apply to every tab)", ""]
    L += [f"- {g}" for g in data.get("globals", [])]
    L += ["", "## Contradictions — resolved to your final word", ""]
    L += [f"- **{c['title']}.** {c['resolution']}" for c in data.get("contradictions", [])]
    L += ["", "## Open Questions — need your decision", ""]
    L += [f"- **{q.get('ref','')}.** {q['q']}" for q in data.get("open_questions", [])]
    for sec in data["sections"]:
        L += ["", f"## {sec['tab']}  ({sec.get('range','')})", ""]
        for it in sec["items"]:
            L += [f"### `{it.get('id','')}` · {ts(it.get('t',0))} · {it.get('title', it.get('id',''))}", ""]
            if it.get("id") in have_img:
                L += [f"![{it['id']}](images/{it['id']}.jpg)", ""]
            L += [f"**You said:** {it.get('said','')}", "", f"**Decision:** {it.get('decision','')}", ""]
            if it.get("flag"):
                L += [f"> ⚑ {it['flag']}", ""]
    return "\n".join(L) + "\n"


def main() -> None:
    items_path, display_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cursor_path = sys.argv[4] if len(sys.argv) > 4 else None   # optional cursor.json
    data = json.loads(items_path.read_text(encoding="utf-8"))
    moves = load_moves(cursor_path)
    images = out_dir / "images"

    have_img: set = set()
    n = regions = 0
    for sec in data["sections"]:
        for it in sec["items"]:
            if moves:
                reg = region_for(moves, float(it["t"]))
                if reg:
                    it["region"] = reg
                    regions += 1
            if extract(display_path, float(it["t"]), images / f"{it['id']}.jpg"):
                have_img.add(it["id"])
                n += 1
            else:
                print(f"  frame FAILED: {it['id']} @ {it['t']}s")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_html = out_dir / "index.html"
    out_html.write_text(render(data, have_img), encoding="utf-8")
    out_md = out_dir / "index.md"
    out_md.write_text(render_md(data, have_img), encoding="utf-8")
    src = Path(cursor_path).name if cursor_path else "none"
    print(f"OK: {n} screenshots, {regions}/{n} cursor-regions (cursor: {src}) -> {images}")
    print(f"    HTML -> {out_html}  ({out_html.stat().st_size // 1024}KB)")
    print(f"    MD   -> {out_md}  ({out_md.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
