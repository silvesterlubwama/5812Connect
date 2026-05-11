// POS peripherals — Web Serial (cash drawer + ESC/POS printer) + Web Audio (beeps).
// Permission-gated: browser prompts user once per device; selection is remembered.

let cachedSerialPort = null;

/**
 * Check whether the browser supports Web Serial (Chrome / Edge / Opera desktop only).
 */
export const isWebSerialSupported = () => typeof navigator !== 'undefined' && 'serial' in navigator;

/**
 * Prompt user to pick a serial device (cash drawer / receipt printer / scale).
 * The selection persists until tab closes; subsequent calls reuse it.
 */
export async function requestSerialPort(opts = {}) {
  if (!isWebSerialSupported()) throw new Error('Web Serial not supported in this browser. Use Chrome/Edge on desktop.');
  // Try cached, then auto-grant previously-paired ports, else prompt
  if (cachedSerialPort && cachedSerialPort.readable) return cachedSerialPort;
  const granted = await navigator.serial.getPorts();
  if (granted && granted.length === 1) {
    cachedSerialPort = granted[0];
  } else {
    cachedSerialPort = await navigator.serial.requestPort({});
  }
  if (!cachedSerialPort.readable) {
    await cachedSerialPort.open({ baudRate: opts.baudRate || 9600 });
  }
  return cachedSerialPort;
}

export async function disconnectSerial() {
  if (cachedSerialPort) {
    try { await cachedSerialPort.close(); } catch (e) { /* ignore */ }
    cachedSerialPort = null;
  }
}

/**
 * Send ESC/POS bytes to the connected serial device.
 * Useful for kicking a cash drawer via a thermal receipt printer's RJ12 jack.
 */
async function writeBytes(bytes) {
  const port = await requestSerialPort();
  const writer = port.writable.getWriter();
  try {
    await writer.write(new Uint8Array(bytes));
  } finally {
    writer.releaseLock();
  }
}

/**
 * Send the standard ESC/POS "open cash drawer" pulse.
 * Default pin 2 (most thermal printers). Some printers use pin 5 — pass pulse: 1.
 * Bytes: ESC p m t1 t2
 */
export async function kickCashDrawer(pulse = 0) {
  const m = pulse === 0 ? 0x00 : 0x01;
  await writeBytes([0x1B, 0x70, m, 0x32, 0xC8]);
}

/**
 * Print raw ESC/POS receipt bytes to the connected printer.
 * Caller assembles the byte stream (text + alignment + cut).
 */
export async function printEscPos(bytes) {
  await writeBytes(bytes);
}

// ====================== AUDIO FEEDBACK ======================
let audioCtx = null;

function getAudioCtx() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) audioCtx = new Ctx();
  }
  return audioCtx;
}

/**
 * Play a single short tone — useful for scan feedback.
 * freq: Hz, duration: ms, volume: 0-1.
 */
export function beep({ freq = 1000, duration = 80, volume = 0.15 } = {}) {
  try {
    const ctx = getAudioCtx();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = freq;
    osc.type = 'sine';
    gain.gain.value = volume;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    setTimeout(() => { try { osc.stop(); } catch (e) {} }, duration);
  } catch (e) { /* audio blocked — silent fail */ }
}

/** Play a sequence of tones. */
export function beepSequence(tones) {
  let delay = 0;
  for (const t of tones) {
    setTimeout(() => beep(t), delay);
    delay += (t.duration || 80) + 20;
  }
}

// Pre-set sounds
export const SOUNDS = {
  scanSuccess: () => beep({ freq: 1500, duration: 70 }),
  scanFail: () => beepSequence([{ freq: 400, duration: 150 }, { freq: 280, duration: 200 }]),
  saleComplete: () => beepSequence([{ freq: 900, duration: 90 }, { freq: 1400, duration: 140 }]),
  saleError: () => beepSequence([{ freq: 600, duration: 100 }, { freq: 400, duration: 150 }, { freq: 300, duration: 200 }]),
  drawerOpen: () => beepSequence([{ freq: 1200, duration: 50 }, { freq: 1600, duration: 50 }]),
};

// ====================== HAPTIC FEEDBACK ======================
export function haptic(pattern = 30) {
  if (typeof navigator !== 'undefined' && navigator.vibrate) {
    try { navigator.vibrate(pattern); } catch (e) {}
  }
}
