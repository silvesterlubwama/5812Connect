/**
 * ContainerVisualizer — 2D + 3D rendering of a 40' container packing layout.
 *
 * Computes deterministic pallet positions from the shipment's items + pallets
 * by:
 *   1. Grouping items by pallet_id (loose items grouped into "Loose")
 *   2. Sizing each pallet box by its total volume (sum of item dims × qty)
 *      falling back to weight when dims missing
 *   3. Greedy-packing pallets into the container floor (front-back, side-side)
 *      heaviest-first so dense pallets land near the back walls
 *
 * The 3D mode uses @react-three/fiber + @react-three/drei OrbitControls.
 * 2D mode is a top-down SVG floor plan — no extra deps.
 *
 * Both consume the SAME computed layout array so what the donor sees in 2D
 * matches what staff sees rotating in 3D.
 */
import React, { useMemo, useState, Suspense } from 'react';
import * as THREE from 'three';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Box, RotateCw, Grid3x3 } from 'lucide-react';

// 40' high-cube interior in cm — matches backend CONTAINER_40FT_HC
const CONTAINER = { length: 1203, width: 235, height: 269 };

/** Compute the layout from shipment data — returns { boxes:[], total_volume_m3, fill_pct, scenes:'ok'|'overflow' }. */
function computeLayout(items, pallets) {
  // Group items by pallet (or null for "Loose")
  const groups = new Map();
  items.forEach(it => {
    const acquired = Number(it.qty_acquired || 0);
    if (acquired <= 0) return;  // only render what's actually in the container
    const key = it.pallet_id || '_loose';
    if (!groups.has(key)) {
      groups.set(key, { id: key, items: [], total_weight: 0, total_volume: 0 });
    }
    const g = groups.get(key);
    g.items.push(it);
    g.total_weight += (Number(it.weight_kg) || 0) * acquired;
    const d = it.dims_cm || {};
    const vol = (Number(d.length) || 0) * (Number(d.width) || 0) * (Number(d.height) || 0) * acquired;
    g.total_volume += vol;
  });
  if (groups.size === 0) return { boxes: [], total_volume_m3: 0, fill_pct: 0, container: CONTAINER };

  // Standardize pallet footprint: 120 x 100 cm. Height grows with item volume.
  // For items without dims, fall back to 40 cm height per pallet (typical box stack).
  const PALLET_L = 120;
  const PALLET_W = 100;

  // Sort heaviest-first so heavy pallets pack against the back wall
  const sorted = Array.from(groups.values()).sort((a, b) => b.total_weight - a.total_weight);

  // Bin-pack pallets into the container floor — 2 columns × 10 rows = 20 slots
  // (1203 cm / 120 cm ≈ 10 rows, 235 cm / 100 cm = 2 columns + leftover walkway).
  const boxes = [];
  const palletMeta = new Map((pallets || []).map(p => [p.id, p]));
  let row = 0;
  let col = 0;
  const totalVolume = sorted.reduce((s, g) => s + g.total_volume, 0);
  for (const g of sorted) {
    const meta = palletMeta.get(g.id) || { label: g.id === '_loose' ? 'Loose items' : g.id };
    // Height proportional to relative volume; floor at 40 cm so loose pallets are visible
    const baseHeight = g.total_volume > 0
      ? Math.max(40, Math.min(220, (g.total_volume / Math.max(totalVolume, 1)) * 1200))
      : 40 + Math.min(120, g.items.length * 5);
    boxes.push({
      id: g.id,
      label: meta.label,
      x: row * PALLET_L,
      y: col * PALLET_W,
      z: 0,
      length: PALLET_L,
      width: PALLET_W,
      height: baseHeight,
      weight_kg: Math.round(g.total_weight),
      item_count: g.items.length,
      color: g.id === '_loose' ? '#94a3b8' : palletColor(g.id),
    });
    col++;
    if (col >= 2) { col = 0; row++; }
    if (row >= 10) break;  // out of floor space — overflow indicator below
  }
  const overflow = boxes.length < sorted.length;
  const totalVolumeM3 = totalVolume / 1e6;
  const containerVolumeM3 = (CONTAINER.length * CONTAINER.width * CONTAINER.height) / 1e6;
  return {
    boxes,
    total_volume_m3: Number(totalVolumeM3.toFixed(1)),
    container_volume_m3: Number(containerVolumeM3.toFixed(1)),
    fill_pct: Math.min(100, Math.round((totalVolumeM3 / containerVolumeM3) * 100)),
    container: CONTAINER,
    overflow,
    overflow_count: sorted.length - boxes.length,
  };
}

// Stable per-pallet color from id hash so the same pallet keeps the same color
// across renders and across 2D / 3D modes.
function palletColor(id) {
  let h = 0;
  for (let i = 0; i < (id || '').length; i++) h = (h * 31 + id.charCodeAt(i)) & 0xffffff;
  const hue = h % 360;
  return `hsl(${hue}, 65%, 55%)`;
}

// ───────────────────────────────────────────────────────────────
// 2D — top-down SVG floor plan
// ───────────────────────────────────────────────────────────────
function FloorPlan2D({ layout }) {
  if (!layout || layout.boxes.length === 0) return null;
  const { container, boxes } = layout;
  const PAD = 16;
  const targetWidth = 700;
  const scale = (targetWidth - PAD * 2) / container.length;
  const w = container.length * scale + PAD * 2;
  const h = container.width * scale + PAD * 2;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="2D floor plan of container packing">
      {/* Container outline */}
      <rect x={PAD} y={PAD} width={container.length * scale} height={container.width * scale}
        fill="#f8fafc" stroke="#94a3b8" strokeWidth="2" />
      {/* Door side marker (right edge) */}
      <text x={w - PAD - 4} y={PAD - 4} fontSize="9" fill="#64748b" textAnchor="end">← Doors (load last)</text>
      <text x={PAD + 2} y={PAD - 4} fontSize="9" fill="#64748b">Back wall (heavy first) →</text>
      {/* Pallets */}
      {boxes.map(b => (
        <g key={b.id}>
          <rect
            x={PAD + b.x * scale} y={PAD + b.y * scale}
            width={b.length * scale} height={b.width * scale}
            fill={b.color} fillOpacity="0.75" stroke="#1e293b" strokeWidth="1"
          />
          <text
            x={PAD + (b.x + b.length / 2) * scale}
            y={PAD + (b.y + b.width / 2) * scale}
            fontSize={Math.max(8, scale * 8)} fill="#fff" textAnchor="middle" dominantBaseline="middle"
            style={{ paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.35)', strokeWidth: 2 }}
          >{b.label.length > 14 ? b.label.slice(0, 12) + '…' : b.label}</text>
          <text
            x={PAD + (b.x + b.length / 2) * scale}
            y={PAD + (b.y + b.width / 2) * scale + Math.max(10, scale * 9)}
            fontSize={Math.max(7, scale * 6)} fill="#fff" textAnchor="middle" opacity="0.9"
          >{b.weight_kg} kg</text>
        </g>
      ))}
    </svg>
  );
}

// ───────────────────────────────────────────────────────────────
// 3D — @react-three/fiber + drei OrbitControls
// We construct THREE objects directly and pass via <primitive object>
// to bypass JSX prop walking (which conflicts with CRA's __source dev prop
// and R3F's applyProps key-path resolution).
// ───────────────────────────────────────────────────────────────
function useScene3DObjects(layout) {
  return useMemo(() => {
    if (!layout || layout.boxes.length === 0) return null;
    const c = layout.container;
    const root = new THREE.Group();

    // Lights
    const amb = new THREE.AmbientLight(0xffffff, 0.6);
    root.add(amb);
    const dir1 = new THREE.DirectionalLight(0xffffff, 0.7);
    dir1.position.set(80, 100, 60);
    root.add(dir1);
    const dir2 = new THREE.DirectionalLight(0xffffff, 0.3);
    dir2.position.set(-60, 80, -40);
    root.add(dir2);

    // Container wireframe
    const containerGeo = new THREE.BoxGeometry(c.length / 10, c.height / 10, c.width / 10);
    const containerMat = new THREE.MeshBasicMaterial({ color: 0x94a3b8, wireframe: true });
    const containerMesh = new THREE.Mesh(containerGeo, containerMat);
    containerMesh.position.set(c.length / 20, c.height / 20, c.width / 20);
    root.add(containerMesh);

    // Floor
    const floorGeo = new THREE.PlaneGeometry(c.length / 10 + 4, c.width / 10 + 4);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0xf1f5f9 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.position.set(c.length / 20, -0.1, c.width / 20);
    floor.rotation.x = -Math.PI / 2;
    root.add(floor);

    // Pallets
    for (const b of layout.boxes) {
      const sx = b.length / 10;
      const sy = b.height / 10;
      const sz = b.width / 10;
      const cx = (b.x + b.length / 2) / 10;
      const cy = (b.height / 2) / 10;
      const cz = (b.y + b.width / 2) / 10;
      const geo = new THREE.BoxGeometry(sx, sy, sz);
      const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(b.color), transparent: true, opacity: 0.85 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(cx, cy, cz);
      root.add(mesh);
    }
    return root;
  }, [layout]);
}

// Defer the @react-three imports to runtime so the rest of the page doesn't pay
// the bundle cost if the user never opens 3D mode.
const ThreeCanvas = React.lazy(async () => {
  const { Canvas } = await import('@react-three/fiber');
  const { OrbitControls } = await import('@react-three/drei');
  return {
    default: function ThreeCanvasInner({ layout }) {
      const c = layout?.container || CONTAINER;
      const sceneRoot = useScene3DObjects(layout);
      if (!sceneRoot) return null;
      // NOTE: We use React.createElement (not JSX) for <primitive> and
      // <OrbitControls> deliberately. The @emergentbase/visual-edits Babel
      // plugin injects x-file-name / x-line-number / x-component props on
      // every JSX element, and react-three-fiber's applyProps walker treats
      // hyphenated prop names as Three.js property paths (e.g. "x-line-number"
      // → tries to set mesh.x.line.number) and throws. createElement calls
      // are NOT visited by the visual-edits transform, so the R3F children
      // stay clean.
      return React.createElement(
        Canvas,
        {
          camera: { position: [c.length / 6, c.height / 5, c.width / 2], fov: 50 },
          style: { width: '100%', height: 380, borderRadius: 8, background: '#fafafa' },
        },
        React.createElement('primitive', { object: sceneRoot }),
        React.createElement(OrbitControls, { makeDefault: true, target: [c.length / 20, c.height / 30, c.width / 20] }),
      );
    },
  };
});

// ───────────────────────────────────────────────────────────────
// Public component
// ───────────────────────────────────────────────────────────────
export default function ContainerVisualizer({ items = [], pallets = [], defaultMode = '2d' }) {
  const [mode, setMode] = useState(defaultMode);
  const layout = useMemo(() => computeLayout(items, pallets), [items, pallets]);

  if (!layout.boxes.length) {
    return (
      <div className="p-4 rounded-lg border bg-muted/30 text-xs text-muted-foreground italic" data-testid="ship-viz-empty">
        Nothing in the container yet — items added &amp; marked acquired will appear here.
      </div>
    );
  }

  return (
    <Card className="rounded-xl" data-testid="ship-viz">
      <CardContent className="p-3 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold flex items-center gap-1.5">
              <Box size={13} className="text-primary" /> Container layout
            </p>
            <Badge variant="outline" className="text-[10px]">
              {layout.boxes.length} pallet{layout.boxes.length === 1 ? '' : 's'}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              vol ~{layout.total_volume_m3} / {layout.container_volume_m3} m³ ({layout.fill_pct}%)
            </Badge>
            {layout.overflow && (
              <Badge className="text-[10px] bg-rose-100 text-rose-700">+{layout.overflow_count} pallets beyond floor</Badge>
            )}
          </div>
          <div className="flex rounded border overflow-hidden text-[11px]">
            <button
              className={`px-2.5 py-1 ${mode === '2d' ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
              onClick={() => setMode('2d')}
              data-testid="ship-viz-2d-btn"
            ><Grid3x3 size={10} className="inline mr-1" />2D</button>
            <button
              className={`px-2.5 py-1 border-l ${mode === '3d' ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
              onClick={() => setMode('3d')}
              data-testid="ship-viz-3d-btn"
            ><RotateCw size={10} className="inline mr-1" />3D</button>
          </div>
        </div>

        {mode === '2d' && <FloorPlan2D layout={layout} />}

        {mode === '3d' && (
          <Suspense fallback={<div className="text-xs text-muted-foreground py-8 text-center">Loading 3D…</div>}>
            <ThreeCanvas layout={layout} />
            <p className="text-[10px] text-muted-foreground text-center">Click + drag to orbit · scroll to zoom · right-click + drag to pan</p>
          </Suspense>
        )}
      </CardContent>
    </Card>
  );
}
