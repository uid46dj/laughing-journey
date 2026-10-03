#!/usr/bin/env node
/**
 * phonecam-server.mjs — turns a phone's browser camera into a webcam for the PC.
 *
 * No app, no driver, no cloud. The phone opens a plain web page (served by this
 * process over `adb reverse`, so it is a secure context and getUserMedia works),
 * grabs its rear camera, and continuously POSTs JPEG frames here.
 *
 * This server keeps ONLY the newest frame, so a slow consumer can never build up
 * a backlog — the PC always receives the most recent image (lowest possible latency).
 *
 * Zero dependencies: plain Node http.
 *
 *   node tools/phonecam-server.mjs [--port 8080]
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const argPort = process.argv.indexOf('--port');
const PORT = Number(
  argPort !== -1 && process.argv[argPort + 1] ? process.argv[argPort + 1] : process.env.PHONE_CAM_PORT || 8080,
);
const PHONE_PAGE = path.join(__dirname, 'phonecam-phone.html');

/** Newest frame only. seq lets the PC tell "did I get something new". */
const latest = { buf: null, seq: 0, tsSent: 0, width: 0, height: 0 };
const waiters = new Set();
const stats = { frames: 0, bytes: 0, startedAt: Date.now() };

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const notify = () => {
  for (const w of [...waiters]) {
    waiters.delete(w);
    try {
      w();
    } catch {
      /* ignore */
    }
  }
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const send = (code, type, body, extra = {}) => {
    res.writeHead(code, { 'Content-Type': type, 'Cache-Control': 'no-store', ...CORS, ...extra });
    res.end(body);
  };

  if (req.method === 'OPTIONS') return send(204, 'text/plain', '');

  // ---- phone pushes a frame here -------------------------------------------
  if (req.method === 'POST' && url.pathname === '/frame') {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      // hard cap so a runaway phone cannot exhaust memory
      if (size > 4 * 1024 * 1024) {
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      if (!chunks.length) return send(400, 'text/plain', 'empty');
      const buf = Buffer.concat(chunks);
      latest.buf = buf;
      latest.seq++;
      latest.tsSent = Number(url.searchParams.get('t')) || 0;
      latest.width = Number(url.searchParams.get('w')) || 0;
      latest.height = Number(url.searchParams.get('h')) || 0;
      stats.frames++;
      stats.bytes += buf.length;
      notify();
      send(200, 'text/plain', 'ok');
    });
    return;
  }

  // ---- PC pulls the newest frame (long-poll) --------------------------------
  if (req.method === 'GET' && url.pathname === '/latest') {
    const since = Number(url.searchParams.get('since') || 0);
    const deliver = () => {
      if (!latest.buf) return send(204, 'text/plain', 'no frame yet');
      const lag = latest.tsSent ? Math.max(0, Date.now() - latest.tsSent) : -1;
      send(200, 'image/jpeg', latest.buf, {
        'X-Seq': String(latest.seq),
        'X-Sent-At': String(latest.tsSent),
        'X-Lag-Ms': String(lag),
        'X-Frame-W': String(latest.width),
        'X-Frame-H': String(latest.height),
      });
    };
    if (latest.buf && latest.seq > since) return deliver();
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      waiters.delete(waiter);
      if (!latest.buf) return send(204, 'text/plain', 'timeout');
      deliver();
    };
    const timer = setTimeout(() => {
      waiters.delete(waiter);
      done = true;
      send(204, 'text/plain', 'timeout');
    }, 500);
    const waiter = finish;
    waiters.add(waiter);
    req.on('close', () => {
      clearTimeout(timer);
      waiters.delete(waiter);
    });
    return;
  }

  if (url.pathname === '/health') {
    return send(
      200,
      'application/json',
      JSON.stringify({
        ok: true,
        streaming: !!latest.buf,
        seq: latest.seq,
        frameBytes: latest.buf ? latest.buf.length : 0,
        width: latest.width,
        height: latest.height,
        frames: stats.frames,
        avgFps: Math.round(stats.frames / Math.max(0.001, (Date.now() - stats.startedAt) / 1000)),
      }),
    );
  }

  if (url.pathname === '/stats') {
    return send(200, 'application/json', JSON.stringify(stats));
  }

  // ---- the phone page -------------------------------------------------------
  if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/phone')) {
    try {
      const html = fs.readFileSync(PHONE_PAGE, 'utf8');
      return send(200, 'text/html; charset=utf-8', html);
    } catch (e) {
      return send(500, 'text/plain', `Cannot read ${PHONE_PAGE}: ${e.message}`);
    }
  }

  return send(404, 'text/plain', 'not found');
});

server.listen(PORT, '127.0.0.1', () => {
  console.log('');
  console.log('  PhoneCam server ready');
  console.log('  ---------------------------------------------');
  console.log(`  On the PC        : http://localhost:${PORT}/health`);
  console.log(`  On the PHONE     : http://localhost:${PORT}/`);
  console.log('');
  console.log('  Next: let the phone reach this PC (USB tunnel):');
  console.log(`      adb reverse tcp:${PORT} tcp:${PORT}`);
  console.log('');
  console.log(`  Stop with Ctrl+C.`);
  console.log('');
});