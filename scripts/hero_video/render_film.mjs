// Renders the hero film: film.html (a replica of the contract desk driven by a timeline) is
// drawn in headless Chromium one frame at a time, at 2x, and piped into ffmpeg as a
// near-lossless master. Every frame is a pure function of its time, so renders are identical.
//
//   npm install                                   (fonts + playwright-core; no browser download)
//   CHROME_PATH=/path/to/chrome node render_film.mjs --lang zh --mode landscape --out out/zh-landscape.mkv
//   node render_film.mjs --lang zh --stills 0,5,13 --out out/stills      (PNG stills to check a frame)
//   sh encode.sh                                  (the web encodes into frontend/public/media)
//
// Modes: landscape renders 1920x1080 at 2x (3840x2160 master); portrait 1080x1920 at 2x.
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, cur, i, all) => {
  if (cur.startsWith('--')) acc.push([cur.slice(2), all[i + 1]]);
  return acc;
}, []));
const MODE = args.mode || 'landscape';
const LANG = args.lang === 'en' ? 'en' : 'zh';
const W = +(args.w || (MODE === 'portrait' ? 1080 : 1920)), H = +(args.h || (MODE === 'portrait' ? 1920 : 1080));
const SCALE = +(args.scale || 2);
const FPS = +(args.fps || 30);
const root = path.dirname(new URL(import.meta.url).pathname);

const server = http.createServer((req, res) => {
  const file = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
  const type = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html', '.css': 'text/css', '.woff2': 'font/woff2', '.woff': 'font/woff' }[path.extname(file)] || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': type });
  fs.createReadStream(file).pipe(res);
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || undefined,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--font-render-hinting=none', '--disable-lcd-text'],
});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: SCALE });
page.on('pageerror', (e) => console.log('[pageerror]', e.message));
page.on('console', (m) => { if (m.type() === 'error') console.log('[console]', m.text()); });
await page.goto(`http://127.0.0.1:${port}/film.html?w=${W}&h=${H}&mode=${MODE}&lang=${LANG}`);
await page.waitForFunction(() => window.__ready === true, null, { timeout: 120000 });
const DURATION = await page.evaluate(() => window.__duration);
const TOTAL = Math.round(DURATION * FPS);

async function grab(frame) {
  await page.evaluate(([f, fps]) => window.__seek(f / fps), [frame, FPS]);
  return page.screenshot({ type: 'png', animations: 'disabled', caret: 'hide' });
}
const t0 = Date.now();
if (args.stills) {
  fs.mkdirSync(args.out, { recursive: true });
  for (const sec of args.stills.split(',').map(Number)) {
    fs.writeFileSync(path.join(args.out, `${LANG}-${MODE}-${sec.toFixed(2).replace('.', '_')}s.png`), await grab(Math.round(sec * FPS)));
    console.log('still', sec, ((Date.now() - t0) / 1000).toFixed(1) + 's');
  }
} else {
  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-vcodec', 'png', '-r', String(FPS), '-i', '-',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '8', '-pix_fmt', 'yuv444p', args.out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((resolve, reject) => ff.on('close', (code) => (code === 0 ? resolve() : reject(new Error('ffmpeg ' + code)))));
  const start = +(args.start || 0), end = +(args.end || TOTAL);
  for (let f = start; f < end; f++) {
    const buf = await grab(f);
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    if (f % 30 === 0) console.log(`frame ${f}/${end} ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  }
  ff.stdin.end();
  await done;
}
console.log('done in', ((Date.now() - t0) / 1000).toFixed(1) + 's');
await browser.close();
server.close();
