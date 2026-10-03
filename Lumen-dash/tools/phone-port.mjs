#!/usr/bin/env node
/**
 * phone-port.mjs — open a listening port ON the phone using nothing but `adb shell`.
 *
 * Why this is possible with zero installs: every Android box ships `toybox`, whose `nc` has
 * the form
 *     nc -l -p <port> <COMMAND>
 * where COMMAND runs as a child process for each incoming connection. So the phone runs a
 * tiny HTTP responder written in pure shell, and the PC reaches it over `adb forward`.
 *
 * This is the mirror image of the normal setup:
 *     adb reverse = PC listens, phone connects   (serves the web page)
 *     adb forward = phone listens, PC connects   (this file)
 *
 * Verified on a Redmi 8 (Android 10, toybox with nc): a GET from the PC comes back as a
 * real HTTP/1.1 response with no app installed.
 *
 * Usage:
 *   node tools/phone-port.mjs serve [port]   open the port on the phone
 *   node tools/phone-port.mjs check [port]   GET it from the PC and print the response
 *   node tools/phone-port.mjs stop           close it and remove the adb forward
 */
import { spawn } from 'node:child_process';

const sh = (remote) =>
  new Promise((resolve) => {
    const p = spawn('adb', ['shell', remote], { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.stderr.on('data', (d) => (out += d));
    p.on('error', () => resolve(''));
    p.on('close', () => resolve(out.trim()));
  });

/** Run adb on the PC (NOT inside adb shell — there is no adb binary on the phone). */
const adb = (args) =>
  new Promise((resolve) => {
    const p = spawn('adb', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.stderr.on('data', (d) => (out += d));
    p.on('error', () => resolve(''));
    p.on('close', (code) => resolve(code === 0 ? out.trim() : ''));
  });

const PORT = Number(process.argv[3]) || Number(process.env.PHONE_PORT || 9096);
const DIR = '/data/local/tmp/phonecam';
const HANDLER = `${DIR}/handler.sh`;
const BODY = 'phone-port OK — toybox nc, no app\n';

/**
 * The responder, written as a heredoc so the shell itself owns every byte and nothing is
 * mangled by nested quoting. `nc` hands the socket to this script on stdin/stdout.
 *
 * CRITICAL: this handler must NOT read the request. `toybox nc -l COMMAND` gives the child a
 * socket whose stdin never reports EOF when the peer connects through `adb forward` (the
 * forward half-closes the socket), so any `read`/`while read` loop blocks forever and the
 * client times out with no reply. Verified: a handler that only writes answers correctly
 * over adb forward, while an otherwise-identical handler that drains headers never does.
 * We still drain a bounded number of bytes, non-blockingly, so the request bytes do not
 * echo back to the client as garbage before our response.
 */
const HANDLER_SRC = `#!/system/bin/sh
# Bounded, non-blocking drain: never wait for EOF (see note above).
toybox timeout 1 sh -c 'dd bs=1024 count=4 2>/dev/null' >/dev/null 2>&1 &
printf 'HTTP/1.1 200 OK\\r\\n'
printf 'Content-Type: text/plain\\r\\n'
printf 'Content-Length: ${BODY.length}\\r\\n'
printf 'Connection: close\\r\\n'
printf '\\r\\n'
printf '${BODY}'
`;

async function install() {
  await sh(`mkdir -p ${DIR}`);
  // Write via heredoc so no shell-escaping layer can mangle the \r\n sequences.
  await sh(`cat > ${HANDLER} <<'PHONECAM_EOF'\n${HANDLER_SRC}PHONECAM_EOF`);
  await sh(`chmod 755 ${HANDLER}`);
}

/**
 * Kill any previous listener.
 *
 * IMPORTANT: the pattern must NOT contain "-p <port>", because pkill's full-command match
 * also matches the port number inside the *new* process we are about to start, which would
 * make this function kill the listener it just created. Match on the script path instead.
 */
async function killOld() {
  await sh(`pkill -f 'phonecam/handler.sh' 2>/dev/null`);
  await sh('sleep 1');
}

async function serve() {
  console.log(`opening port ${PORT} on the phone via adb shell (toybox nc, no app)...`);
  await install();
  await killOld();

  // -L (capital) = listen for MULTIPLE connections, i.e. a server loop.
  //   The lowercase -l handles exactly ONE connection and then exits, so it dies the moment
  //   the first client disconnects — useless as a server.
  // -4 = bind IPv4 only. Without it toybox binds tcp6 :::PORT, which adb forward cannot reach.
  // nohup + & + </dev/null is required: adb shell kills its children when the session ends.
  await sh(`nohup toybox nc -4 -L -p ${PORT} sh ${HANDLER} </dev/null >${DIR}/nc.log 2>&1 &`);
  await sh('sleep 1');

  const listening = await sh(`toybox netstat -ltn 2>/dev/null | grep -c ':${PORT} '`);
  if (listening && listening !== '0') console.log(`OK: phone is listening on ${PORT}`);
  else console.log(`WARNING: listener not confirmed (netstat said "${listening}")`);

  // NOTE: `adb forward` must run on the PC — there is no adb binary inside the phone shell.
  const fwd = await adb(['forward', `tcp:${PORT}`, `tcp:${PORT}`]);
  if (fwd !== '') {
    console.log(`PC reaches it at http://localhost:${PORT}/`);
  } else {
    console.log(`WARNING: adb forward failed — run manually: adb forward tcp:${PORT} tcp:${PORT}`);
  }
  console.log('verify with:  node tools/phone-port.mjs check');
}

async function check() {
  // The forward may already exist from a previous run; adb tolerates a duplicate.
  await adb(['forward', `tcp:${PORT}`, `tcp:${PORT}`]);
  await new Promise((r) => setTimeout(r, 500));
  const res = await new Promise((resolve) => {
    const p = spawn('curl', ['-sS', '-i', '--max-time', '10', `http://localhost:${PORT}/`], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.stderr.on('data', (d) => (out += d));
    p.on('error', () => resolve('curl unavailable on this PC'));
    p.on('close', () => resolve(out));
  });
  console.log(res || '(no response)');
}

async function stop() {
  await killOld();
  await adb(['forward', '--remove', `tcp:${PORT}`]);
  await sh(`rm -f ${HANDLER}`);
  console.log(`stopped port ${PORT}`);
}

const cmd = process.argv[2] || 'serve';
const actions = { serve, check, stop };
const fn = actions[cmd];
if (!fn) {
  console.error(`unknown command "${cmd}" — use serve | check | stop`);
  process.exit(1);
}
fn().catch((e) => {
  console.error('failed:', e);
  process.exit(1);
});