// Renders the landing page's hero film: an original Three.js scene (scene.js) drawn frame by
// frame in headless Chromium, piped as raw RGBA into ffmpeg as a near-lossless master.
// No stock footage, no contract data. Every motion in scene.js loops on a 12-second period,
// so the last frame joins the first seamlessly.
//
//   npm install                     (three + playwright-core)
//   CHROME_PATH=/path/to/chrome npm run render   then   npm run encode
//   node render.mjs --mode landscape --w 960 --h 540 --stills 0,90,180 --out out/stills
//
// WebGL runs on SwiftShader, so no GPU is needed (about 2 s per 1080p frame on 4 cores).
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, cur, i, all) => {
  if (cur.startsWith('--')) acc.push([cur.slice(2), all[i + 1]]);
  return acc;
}, []));
const W = +(args.w || 1920), H = +(args.h || 1080), MODE = args.mode || 'landscape';
const FPS = +(args.fps || 30), LOOP = 12, TOTAL = FPS * LOOP;
const root = path.dirname(new URL(import.meta.url).pathname);

const server = http.createServer((req, res) => {
  const file = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
  const type = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': type });
  fs.createReadStream(file).pipe(res);
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || undefined,
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--disable-dev-shm-usage'],
});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('[page]', m.text()); });
page.on('pageerror', (e) => console.log('[pageerror]', e.message));
await page.goto(`http://127.0.0.1:${port}/index.html?w=${W}&h=${H}&mode=${MODE}`);
await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
console.log('crossings', JSON.stringify(await page.evaluate(() => window.__crossings)));

async function grab(frame) {
  const b64 = await page.evaluate(([f, fps]) => {
    window.__render(f, fps);
    const px = window.__grab();
    let s = '';
    for (let i = 0; i < px.length; i += 0x8000) s += String.fromCharCode.apply(null, px.subarray(i, i + 0x8000));
    return btoa(s);
  }, [frame, FPS]);
  return Buffer.from(b64, 'base64');
}

function ffmpeg(argsList) {
  const p = spawn('ffmpeg', argsList, { stdio: ['pipe', 'inherit', 'inherit'] });
  return p;
}

const t0 = Date.now();
if (args.stills) {
  fs.mkdirSync(args.out, { recursive: true });
  for (const f of args.stills.split(',').map(Number)) {
    const buf = await grab(f);
    await new Promise((resolve, reject) => {
      const p = ffmpeg(['-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-i', '-', '-vf', 'vflip', path.join(args.out, `${MODE}-${String(f).padStart(4, '0')}.png`)]);
      p.on('close', (code) => (code === 0 ? resolve() : reject(new Error('ffmpeg ' + code))));
      p.stdin.end(buf);
    });
    console.log('still', f, ((Date.now() - t0) / 1000).toFixed(1) + 's');
  }
} else {
  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  const p = ffmpeg(['-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-r', String(FPS), '-i', '-',
    '-vf', 'vflip', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '6', '-pix_fmt', 'yuv444p', args.out]);
  const done = new Promise((resolve, reject) => p.on('close', (code) => (code === 0 ? resolve() : reject(new Error('ffmpeg ' + code)))));
  const start = +(args.start || 0), end = +(args.end || TOTAL);
  for (let f = start; f < end; f++) {
    const buf = await grab(f);
    if (!p.stdin.write(buf)) await new Promise((r) => p.stdin.once('drain', r));
    if (f % 15 === 0) console.log(`frame ${f}/${end} ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  }
  p.stdin.end();
  await done;
}
console.log('done in', ((Date.now() - t0) / 1000).toFixed(1) + 's');
await browser.close();
server.close();
