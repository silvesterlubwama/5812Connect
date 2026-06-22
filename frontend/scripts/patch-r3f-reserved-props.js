#!/usr/bin/env node
/**
 * Post-install patch for @react-three/fiber v9.
 *
 * R3F's `applyProps` walks every prop key as a Three.js property path
 * (e.g. "rotation-x" → mesh.rotation.x). React's dev JSX transform injects
 * `__source` / `__self` props that R3F treats as paths too, throwing:
 *   "R3F: Cannot set 'x-line-number'. Ensure it is an object before setting
 *    'line-number'."
 *
 * R3F's RESERVED_PROPS filter only covers ['children', 'key', 'ref'].
 * This script appends '__source' and '__self' so the dev props are ignored.
 *
 * Runs via `postinstall` so the patch survives `yarn install` / `yarn add`.
 */
const fs = require('fs');
const path = require('path');

const files = [
  'node_modules/@react-three/fiber/dist/events-b389eeca.esm.js',
  'node_modules/@react-three/fiber/dist/events-f19bcc32.cjs.dev.js',
  'node_modules/@react-three/fiber/dist/events-583399dd.cjs.prod.js',
];

const NEEDLE = "REACT_INTERNAL_PROPS = ['children', 'key', 'ref']";
const REPLACEMENT = "REACT_INTERNAL_PROPS = ['children', 'key', 'ref', '__source', '__self']";

let patched = 0;
let skipped = 0;
for (const rel of files) {
  const full = path.join(__dirname, '..', rel);
  if (!fs.existsSync(full)) continue;
  const src = fs.readFileSync(full, 'utf8');
  if (src.includes(REPLACEMENT)) { skipped++; continue; }
  if (!src.includes(NEEDLE)) {
    console.warn(`[patch-r3f] needle not found in ${rel} — file format may have changed`);
    continue;
  }
  fs.writeFileSync(full, src.replace(NEEDLE, REPLACEMENT));
  patched++;
}
if (patched) console.log(`[patch-r3f] patched ${patched} file(s) (skipped ${skipped} already-patched)`);
