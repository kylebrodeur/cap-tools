#!/usr/bin/env node
/**
 * SOURCE: an internal reference project's scripts/record-studio.cjs
 * ROLE: Reference implementation — Node.js Playwright CDP driver.
 * Connects to an existing Chrome CDP window and drives named UI beats
 * while Cap records the screen. Handles overlay dismissal, model warm-up,
 * window maximisation via CDP, and Cap start/stop.
 *
 * PROJECT-SPECIFIC: SPACE_URL, beat functions (beatLoad, beatSlice, etc.),
 *   UI selectors (#ce-benchy, .ce-pills, etc.), warm-up wait times.
 * GENERIC: capJson(), capStartDetached(), isRecording(), CDP connect with
 *   retry + hostname rewrite, Browser.setWindowBounds, overlay dismissal.
 *
 * Studio recording driver using npm/pnpm-based Playwright (CommonJS).
 *
 * Run from WSL inside the source project's root:
 *   npx playwright install chromium   # one-time
 *   node scripts/record-studio.cjs
 *
 * This script:
 *   - Sources the Cap CLI skill so `cap` is available.
 *   - Checks/starts a Cap screen recording if none is running.
 *   - Connects to an existing Chrome CDP window (launched by record-studio.sh).
 *   - Clicks WARM UP and waits for the ZeroGPU model.
 *   - Drives the demo beats with generous waits.
 *   - Leaves the raw .cap project in Cap Desktop Studio (no export).
 */

const { exec, execSync, spawn } = require('child_process');
const fs = require('fs');
const { chromium } = require('playwright');

const SPACE_URL = process.env.SPACE_URL || 'https://your-target-app.example.com';
const CDP_URL = process.env.CDP_URL || 'http://172.25.144.1:9222';
const CAP_FPS = '60';
const SKIP_CAP = process.argv.includes('--skip-cap');
const WARMUP_WAIT_MS = Number(process.argv.find(a => a.startsWith("--warmup="))?.split("=")[1] || 20000);
const INFERENCE_WAIT_MS = Number(process.argv.find(a => a.startsWith("--inference="))?.split("=")[1] || 6000);
const PAUSE_S = Number(process.argv.find(a => a.startsWith("--pause="))?.split("=")[1] || 2);
const BEAT_ARG = process.argv.find(a => a.startsWith('--beat='))?.split('=')[1] || 'all';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function capBin() {
  try {
    return execSync('which cap', { encoding: 'utf8' }).trim();
  } catch {
    return '/mnt/c/Users/<your-windows-username>/AppData/Local/Cap/cap-cli.exe';
  }
}

function sleepSync(ms) {
  const start = Date.now();
  while (Date.now() - start < ms) { }
}

function pageOrContextHttpGet(url) {
  return new Promise((resolve, reject) => {
    const http = require('http');
    const u = new URL(url);
    const req = http.get({ hostname: u.hostname, port: u.port || 9222, path: '/json/version' }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch { resolve(null); }
      });
    });
    req.on('error', reject);
    req.setTimeout(5000, () => { req.destroy(new Error('timeout')); });
  });
}

function capStartDetached(args) {
  const tmp = '/tmp/cap-start-output.txt';
  try { fs.unlinkSync(tmp); } catch { }
  const out = fs.openSync(tmp, 'w');
  const child = spawn(capBin(), args, { detached: true, stdio: ['ignore', out, out] });
  child.unref();
  fs.closeSync(out);
  sleepSync(2500);
  try {
    const data = fs.readFileSync(tmp, 'utf8');
    if (!data) return null;
    for (const line of data.split('\n')) {
      const t = line.trim();
      if (t.startsWith('{') && t.endsWith('}')) {
        try { return JSON.parse(t); } catch { }
      }
    }
    let depth = 0; let buf = []; let started = false;
    for (const line of data.split('\n')) {
      const s = line.trim();
      if (!started) {
        for (let i = 0; i < s.length; i++) {
          if (s[i] === '{' || s[i] === '[') { started = true; buf.push(s.slice(i)); depth = 1; break; }
        }
        continue;
      }
      buf.push(line);
      for (const ch of s) { if (ch === '{' || ch === '[') depth++; else if (ch === '}' || ch === ']') depth--; }
      if (depth === 0) { try { return JSON.parse(buf.join('\n')); } catch { return null; } }
    }
  } catch { }
  return null;
}

function capJson(args) {
  let r;
  try {
    r = execSync(`${capBin()} ${args.join(' ')}`, { encoding: 'utf8', timeout: 120000 });
  } catch (err) {
    return null;
  }
  if (!r) return null;
  const trimmed = r.trim();
  if (!trimmed) return null;
  // Single-line JSON object or array
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try { return JSON.parse(trimmed); } catch { }
  }
  // Pretty-printed: collect from first { or [ to matching depth
  let depth = 0;
  let buf = [];
  let started = false;
  let startChar = null;
  for (const line of r.split('\n')) {
    const stripped = line.trim();
    if (!started) {
      for (let i = 0; i < stripped.length; i++) {
        const ch = stripped[i];
        if (ch === '{' || ch === '[') {
          started = true;
          startChar = ch;
          buf.push(stripped.slice(i));
          depth = 1;
          break;
        }
      }
      continue;
    }
    buf.push(line);
    for (const ch of stripped) {
      if (ch === '{' || ch === '[') depth++;
      else if (ch === '}' || ch === ']') depth--;
    }
    if (depth === 0) {
      try { return JSON.parse(buf.join('\n')); } catch { return null; }
    }
  }
  return null;
}

function isRecording() {
  try {
    const status = capJson(['record', 'status', '--json']);
    if (status?.recording || status?.status === 'recording') return true;
    if (Array.isArray(status)) {
      for (const r of status) {
        if (['recording', 'in-progress'].includes(r.state)) return true;
      }
    }
  } catch { }
  try {
    const list = capJson(['recordings', 'list', '--json']);
    if (list?.recordings) {
      for (const r of list.recordings) {
        if (['recording', 'in-progress'].includes(r.state)) return true;
      }
    }
  } catch { }
  return false;
}

function startRecording() {
  if (isRecording()) {
    console.log('  ✓ Cap is already recording');
    return null;
  }
  const targets = capJson(['targets', '--json']);
  const screens = targets?.screens || [];
  const screen = screens.find(s => s.primary) || screens[0];
  if (!screen) throw new Error('no Cap screen target');
  console.log(`  starting Cap recording (screen ${screen.id})...`);
  const rec = capStartDetached(['record', 'start', '--screen', String(screen.id), '--fps', CAP_FPS, '--detach', '--json']);
  if (!rec) throw new Error('failed to start Cap recording');
  console.log(`  ✓ Cap recording started (${rec.recordingId || '?'})`);
  return rec;
}

async function openOverride(page) {
  const popup = page.locator('#ce-popup-override');
  const isOpen = await popup.locator('..').locator('.open, .ce-popup.open').first().isVisible().catch(() => false)
            || await popup.isVisible().catch(() => false);
  if (!isOpen) {
    await page.locator('#ce-override').first().click({ force: true }).catch(() => { });
    await sleep(400);
  }
}

async function closeOverride(page) {
  // Remove the open class from popup + backdrop directly; the click target can be flaky.
  await page.evaluate(() => {
    document.querySelectorAll('.ce-popup.open, .ce-popup-backdrop.open').forEach(x => x.classList.remove('open'));
    document.querySelectorAll('.ce-popup-backdrop').forEach(x => { x.style.display = 'none'; });
  }).catch(() => { });
  await sleep(300);
}

async function ensureNoPopup(page) {
  await closeOverride(page);
}

async function setSensors(page, t, h) {
  const inputs = page.locator('#ce-popup-override .ce-num input');
  await inputs.nth(0).fill(String(t)).catch(() => { });
  await inputs.nth(0).dispatchEvent('change').catch(() => { });
  await inputs.nth(1).fill(String(h)).catch(() => { });
  await inputs.nth(1).dispatchEvent('change').catch(() => { });
}

async function pill(page, value) {
  await page.locator('.ce-pills label', { hasText: value }).first().click();
}

async function waitForHfBannerDismiss(page, timeoutMs = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      await page.evaluate(() => {
        // Hugging Face Space header / banner
        const header = document.getElementById('huggingface-space-header');
        if (header) { header.style.display = 'none'; header.remove(); }
        // Cookie / accept banners
        document.querySelectorAll('div, aside, section').forEach(el => {
          const text = (el.innerText || '').toLowerCase();
          if (/(cookie|accept|we use cookies|privacy)/.test(text) && text.length < 400) {
            el.style.display = 'none';
            el.remove();
          }
        });
        // Any button that says Accept / Allow all / Got it
        document.querySelectorAll('button').forEach(btn => {
          const t = (btn.innerText || '').toLowerCase();
          if (/^(accept|allow all|got it|agree|ok|dismiss|close)$/.test(t)) btn.click();
        });
      });
    } catch { }
    await sleep(500);
  }
}

async function dismissHfBannerOnce(page) {
  // One-shot aggressive removal for post-navigation reuse.
  try {
    await page.evaluate(() => {
      const header = document.getElementById('huggingface-space-header');
      if (header) { header.style.display = 'none'; header.remove(); }
      document.querySelectorAll('div, aside, section').forEach(el => {
        const text = (el.innerText || '').toLowerCase();
        if (/(cookie|accept|we use cookies|privacy)/.test(text) && text.length < 400) {
          el.style.display = 'none'; el.remove();
        }
      });
    });
  } catch { }
}

async function warmModel(page) {
  console.log('  warming the model (WARM UP)...');
  await page.goto(`${SPACE_URL}/?__theme=dark`, { waitUntil: 'domcontentloaded' });
  console.log('  waiting for HF banner/cookie prompt to render...');
  await waitForHfBannerDismiss(page, 8000);
  await sleep(1000);
  await page.locator('#ce-warm').first().click({ timeout: 5000 }).catch(() => {
    console.log('  ⚠ WARM UP button not found — proceeding anyway');
  });
  console.log(`  waiting ${WARMUP_WAIT_MS / 1000}s for model load...`);
  await sleep(WARMUP_WAIT_MS);
  console.log('  warm-up complete');
}

async function beatLoad(page) {
  // LOAD is the default tab when the Space opens; just wait for it to render.
  await page.waitForSelector('button:has-text("LOAD")', { timeout: 15000 }).catch(() => { });
  await sleep(800);
  await pill(page, 'PLA');
  await sleep(300);
  await page.locator('#ce-benchy').first().click();
  await sleep(1500);

  // Show the viewer is interactive: rotate/orbit the loaded Benchy.
  const viewer = page.locator('.ce-part-viewer-col canvas, .ce-part-viewer-col .svelte-3d-viewer, canvas').first();
  const box = await viewer.boundingBox().catch(() => null);
  if (box) {
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.down({ button: 'left' });
    await page.mouse.move(cx - 120, cy + 40, { steps: 20 });
    await page.mouse.up({ button: 'left' });
    await sleep(800);
    await page.mouse.move(cx, cy);
    await page.mouse.down({ button: 'left' });
    await page.mouse.move(cx + 100, cy - 30, { steps: 20 });
    await page.mouse.up({ button: 'left' });
    await sleep(800);
  }

  // Demonstrate RANDOMIZE so viewers see the simulated environment variables change.
  await page.locator('#ce-randomize').first().click();
  await sleep(1200);
  await page.locator('#ce-randomize').first().click();
  await sleep(1200);

  // Click SLICE to move to the read (button has a right-arrow glyph).
  await page.locator('#ce-run').first().click();
  await sleep(INFERENCE_WAIT_MS);
  console.log('  waiting for reasoning to land...');
  await sleep(3000);
}

async function beatSlice(page) {
  await page.evaluate(() => document.querySelector('button[data-tab-id=\"build\"]')?.click());
  await sleep(INFERENCE_WAIT_MS);
  console.log('  waiting for reasoning to land...');
  await sleep(3000);
}

async function beatSecondOpinion(page) {
  await page.evaluate(() => document.querySelector('button[data-tab-id=\"build\"]')?.click());
  await sleep(5000);
}

async function beatScrub(page) {
  const sliders = page.locator('input[type=range]');
  const count = await sliders.count();
  const sl = sliders.nth(count - 1);
  for (const v of [8, 18, 30, 40]) {
    await sl.fill(String(v));
    await sl.dispatchEvent('input');
    await sl.dispatchEvent('change');
    await sleep(1200);
  }
}

async function beatPlacement(page) {
  await page.evaluate(() => document.querySelector('button[data-tab-id=\"studio\"]')?.click());
  await sleep(500);
  await pill(page, 'ABS');
  await pill(page, 'corner');
  await openOverride(page);
  await setSensors(page, 26, 60);
  await closeOverride(page);
  await page.locator('#ce-benchy').first().click();
  await sleep(500);
  await page.locator('#ce-run').first().click();
  await sleep(INFERENCE_WAIT_MS);
  console.log('  waiting for placement reasoning...');
  await sleep(4000);
}

async function beatClimbingJob(page) {
  await page.evaluate(() => document.querySelector('button[data-tab-id=\"studio\"]')?.click());
  await sleep(500);
  await openOverride(page);
  await setSensors(page, 30, 65);
  await closeOverride(page);
  await pill(page, 'PETG');
  await page.locator('#ce-benchy').first().click();
  await sleep(2500);
  await page.locator('#ce-run').first().click();
  await sleep(INFERENCE_WAIT_MS);
  console.log('  waiting for climbing-job reasoning...');
  await sleep(4000);
}

async function beatPrintLoop(page) {
  await page.evaluate(() => document.querySelector('button[data-tab-id=\"print\"]')?.click());
  await sleep(500);
  await page.locator('#ce-print-run, #ce-print').first().click();
  console.log('  waiting for print simulation + curve...');
  await sleep(10000);
}

async function beatReview(page) {
  await page.evaluate(() => document.querySelector('button[data-tab-id=\"review\"]')?.click());
  await sleep(5000);
}

const BEATS = {
  'load': [beatLoad],
  'slice': [beatLoad, beatSlice],
  'second': [beatLoad, beatSlice, beatSecondOpinion],
  'scrub': [beatLoad, beatSlice, beatScrub],
  'placement': [beatPlacement],
  'climb': [beatClimbingJob, beatPrintLoop, beatReview],
  'loop': [beatPrintLoop, beatReview],
  'all': [beatLoad, beatSlice, beatSecondOpinion, beatScrub, beatPlacement, beatClimbingJob, beatPrintLoop, beatReview],
};

async function main() {
  console.log(`\n=== RECORD (studio) via npm/pnpm playwright ===\n`);
  console.log(`  CDP URL: ${CDP_URL}`);
  console.log(`  beat:    ${BEAT_ARG}\n`);

  const rec = SKIP_CAP ? null : startRecording();
  if (!SKIP_CAP && !rec && !isRecording()) {
    console.error('  ✗ could not confirm an active Cap recording');
    process.exit(1);
  }
  const recId = rec?.recordingId;

  console.log(`  connecting to Chrome CDP at ${CDP_URL}...`);
  let wsUrl = null;
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      const info = await pageOrContextHttpGet(CDP_URL);
      const raw = info?.webSocketDebuggerUrl;
      if (raw) {
        const u = new URL(raw);
        const cdp = new URL(CDP_URL);
        u.hostname = cdp.hostname;
        u.port = cdp.port || '9222';
        wsUrl = u.toString();
        console.log(`  ws endpoint: ${wsUrl}`);
        break;
      }
    } catch (e) {
      console.log(`  ⚠ CDP info fetch attempt ${attempt}/5 failed: ${e.message}`);
    }
    await sleep(3000);
  }
  if (!wsUrl) throw new Error('could not retrieve CDP websocket URL');

  let browser = null;
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      browser = await chromium.connectOverCDP(wsUrl);
      console.log('  ✓ connected to Chrome CDP');
      break;
    } catch (e) {
      console.log(`  ⚠ CDP connect attempt ${attempt}/5 failed: ${e.message}`);
      if (attempt === 5) throw e;
      await sleep(3000);
    }
  }
  if (!browser) throw new Error('could not connect to Chrome CDP');
  const context = browser.contexts()[0] || await browser.newContext();
  const page = context.pages()[0] || await context.newPage();
  await page.setViewportSize({ width: 1707, height: 1067 });

  // Maximize and focus the actual OS window via CDP so the recording fills the screen and stays on top.
  try {
    const cdpSession = await page.context().newCDPSession(page);
    const { windowId } = await cdpSession.send('Browser.getWindowForTarget');
    await cdpSession.send('Browser.setWindowBounds', {
      windowId,
      bounds: { windowState: 'maximized' }
    });
    // (Window focus via PowerShell removed to avoid quoting issues; CDP maximize handles sizing.)
    console.log('  ✓ Chrome window maximized + focused');
  } catch (e) {
    console.log(`  ⚠ could not maximize/focus window via CDP: ${e.message}`);
  }

  await warmModel(page);

  console.log('  navigating to Space for recording take...');
  await page.goto(`${SPACE_URL}/?__theme=dark`, { waitUntil: 'domcontentloaded' });
  await waitForHfBannerDismiss(page, 6000);
  await dismissHfBannerOnce(page);
  await sleep(1000);

  const steps = BEATS[BEAT_ARG];
  if (!steps) {
    console.error(`Unknown beat: ${BEAT_ARG}`);
    process.exit(1);
  }
  for (let i = 0; i < steps.length; i++) {
    console.log(`  [${i + 1}/${steps.length}] ${steps[i].name}`);
    await steps[i](page);
    console.log(`  pausing ${PAUSE_S}s between beats...`);
    await sleep(PAUSE_S * 1000);
  }

  console.log('  beats complete — holding 4s for closing shot...');
  await sleep(4000);
  await browser.close();

  console.log('\n  ' + (SKIP_CAP ? 'skipping Cap stop (external recording)' : 'stopping Cap recording...'));
  if (!SKIP_CAP) {
    try {
      execSync(`${capBin()} record stop${recId ? ` --id ${recId}` : ''}`, { encoding: 'utf8', timeout: 120000 });
      console.log('  ✓ Cap recording stopped');
    } catch {
      console.log('  ⚠ Cap stop may have failed — stop it manually in Cap Desktop');
    }
  }

  console.log('\n=== STUDIO MODE DONE ===');
  console.log('  The raw .cap project can now be edited/exported from Cap Desktop Studio.');
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
