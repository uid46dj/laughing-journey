#!/usr/bin/env node
/**
 * dev-with-phonecam.mjs — one command that runs everything.
 *
 * Starts, in a single terminal, with no manual steps:
 *   1. the phonecam relay server   (tools/phonecam-server.mjs)
 *   2. the Vite dev server         (so the game is live-reloading)
 *   3. `adb reverse` over USB      (auto-detects the phone, retries if not plugged in yet)
 *
 * Prints a ready banner with the exact URL to open on the phone, then keeps running.
 * Ctrl+C shuts every child process down and removes the adb tunnel.
 *
 * Usage:  npm run dev:cam
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PORT = Number(process.env.PHONE_CAM_PORT || 8080);

const c = {
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  b: (s) => `\x1b[1m${s}\x1b[0m`,
  g: (s) => `\x1b[32m${s}\x1b[0m`,
  y: (s) => `\x1b[33m${s}\x1b[0m`,
  r: (s) => `\x1b[31m${s}\x1b[0m`,
  c: (s) => `\x1b[36m${s}\x1b[0m`,
};

const children = [];
let adbSerial = null;

/** Prefixed, colourised pass-through so you can tell the three streams apart. */
function start(label, color, cmd, args, opts = {}) {
  const child = spawn(cmd, args, {
    cwd: opts.cwd ?? ROOT,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  });
  const pipe = (stream, isErr) => {
    let buf = '';
    stream.setEncoding('utf8');
    stream.on('data', (d) => {
      buf += d;
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const t = `${color(`[${label}]`)} ${line}`;
        if (isErr) process.stderr.write(t + '\n');
        else process.stdout.write(t + '\n');
      }
    });
  };
  pipe(child.stdout, false);
  pipe(child.stderr, true);
  child.on('exit', (code) => {
    if (code !== 0 && code !== null) process.stderr.write(`${c.r(`[${label}]`)} exited with code ${code}\n`);
  });
  children.push(child);
  return child;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const run = (cmd, args) =>
  new Promise((resolve) => {
    const p = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'], shell: false });
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.on('error', () => resolve(''));
    p.on('close', () => resolve(out.trim()));
  });

/** Locate adb: PATH first, then the usual Android SDK locations. */
async function findAdb() {
  if (await run('adb', ['version'])) return 'adb';
  const home = os.homedir();
  const roots = [
    process.env.ANDROID_HOME,
    process.env.ANDROID_SDK_ROOT,
    path.join(home, 'AppData', 'Local', 'Android', 'Sdk'),
    path.join(home, 'Library', 'Android', 'sdk'),
    path.join(home, 'Android', 'Sdk'),
    'C:\\Android\\Sdk',
    '/usr/lib/android-sdk',
  ].filter(Boolean);
  for (const r of roots) {
    const exe = path.join(r, 'platform-tools', process.platform === 'win32' ? 'adb.exe' : 'adb');
    if (fs.existsSync(exe)) return exe;
  }
  return null;
}

/** First connected device serial, or null. */
async function firstDevice(adb) {
  const out = await run(adb, ['devices']);
  for (const line of out.split('\n').slice(1)) {
    const m = line.trim().match(/^(\S+)\s+(device|unauthorized|offline)\b/);
    if (m && m[2] === 'device') return m[1];
  }
  return null;
}

/** Point the phone's localhost:PORT at this PC. Safe to call repeatedly. */
async function setupTunnel(adb, serial) {
  await run(adb, ['-s', serial, 'reverse', `tcp:${PORT}`, `tcp:${PORT}`]);
  const list = await run(adb, ['-s', serial, 'reverse', '--list']);
  return list.includes(`tcp:${PORT}`);
}

/**
 * Keep trying in the background, so plugging the phone in at any moment just works.
 */
function watchForPhone(adb) {
  let done = false;
  const tick = async () => {
    if (done) return;
    const serial = await firstDevice(adb);
    if (serial && serial !== adbSerial) {
      adbSerial = serial;
      const ok = await setupTunnel(adb, serial);
      console.log(
        ok
          ? c.g(`  ✓ phone ${serial} connected — tunnel tcp:${PORT} ready`)
          : c.y(`  ! phone ${serial} found but the tunnel did not stick`),
      );
      if (ok) {
        console.log(c.dim(`  On the phone, open http://localhost:${PORT}/ and tap "Start streaming".`));
        done = true;
        return;
      }
    }
    if (!done) setTimeout(tick, 3000);
  };
  void tick();
}

async function main() {
  console.log('');
  console.log(c.b('  Lumen Dash — dev server + phone camera'));
  console.log(c.dim('  One command. Keep this terminal open.'));
  console.log('');

  // 1. relay server that receives the phone's frames
  start('relay', c.c, process.execPath, [path.join(__dirname, 'phonecam-server.mjs')]);

  // 2. adb tunnel: phone -> this PC
  const adb = await findAdb();
  if (!adb) {
    console.log(c.y('  ! adb not found — install Android platform-tools or add adb to PATH.'));
    console.log(c.dim('    Game + relay still run; the phone camera will not work.'));
  } else {
    const serial = await firstDevice(adb);
    if (serial) {
      adbSerial = serial;
      const ok = await setupTunnel(adb, serial);
      console.log(
        ok
          ? c.g(`  ✓ phone ${serial} connected — tunnel tcp:${PORT} ready`)
          : c.y(`  ! phone ${serial} found but the tunnel did not stick`),
      );
    } else {
      console.log(c.y('  ! no phone detected yet — plug it in with USB debugging ON and it will connect automatically.'));
      watchForPhone(adb);
    }
  }

  // 3. Vite dev server, so the game hot-reloads
  start('vite', c.g, process.execPath, [path.join(ROOT, 'node_modules', 'vite', 'bin', 'vite.js')]);

  // Only print the banner once the relay actually answers.
  let ready = false;
  for (let i = 0; i < 25 && !ready; i++) {
    await sleep(200);
    try {
      ready = (await fetch(`http://127.0.0.1:${PORT}/health`)).ok;
    } catch {
      /* still starting */
    }
  }

  console.log('');
  console.log(c.b('  Ready.'));
  console.log('');
  console.log(`    ${c.b('Game (PC):     ')} http://localhost:5173`);
  console.log(`    ${c.b('Phone camera:  ')} http://localhost:${PORT}/`);
  console.log('');
  console.log(c.dim('  1. On the phone, open the phone-camera URL and tap "Start streaming".'));
  console.log(c.dim('  2. In the game: Settings -> "Use phone as camera" ON.'));
  console.log(c.dim('  3. Click "Play with Camera" and allow the camera permission.'));
  if (!ready) console.log(c.y('\n  (relay still starting — wait a second, then reload the phone page)'));
  console.log('');
  console.log(c.dim('  Ctrl+C stops everything.'));
  console.log('');
}

/** Ctrl+C: kill both children and remove the adb tunnel so nothing is left behind. */
let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  console.log('\n' + c.dim('  Shutting down...'));
  for (const child of children) {
    try {
      child.kill('SIGINT');
    } catch {
      /* already gone */
    }
  }
  await sleep(300);
  for (const child of children) {
    try {
      child.kill();
    } catch {
      /* already gone */
    }
  }
  const adb = await findAdb();
  if (adb && adbSerial) await run(adb, ['-s', adbSerial, 'reverse', '--remove', `tcp:${PORT}`]);
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
if (process.platform === 'win32') process.on('SIGBREAK', shutdown);

main().catch((e) => {
  console.error(c.r('  Failed to start:'), e);
  void shutdown();
});