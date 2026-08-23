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

// 40' high-cube interior in cm — matches backend CONTAINER_40FT_HC. Default,
// overridable per-shipment via the `container` prop on the visualizer.
const CONTAINER = { length: 1203, width: 235, height: 269 };

/** Compute the layout from shipment data — returns { boxes:[], total_volume_m3, fill_pct, scenes:'ok'|'overflow' }.
 *  Accepts BOTH `pallets` (legacy) and `packing_units` (iter223+) merged into
 *  a single list keyed by id, so callers don't have to choose.
 */
function computeLayout(items, pallets, containerOverride, packingUnits = []) {
  const CONT = containerOverride && containerOverride.length_cm ? {
    length: containerOverride.length_cm,
    width: containerOverride.width_cm,
    height: containerOverride.height_cm,
  } : CONTAINER;
  // iter228 — unify legacy pallets + new packing_units (pallets/boxes/totes/crates)
  // Packing-unit fields use L_cm/W_cm/H_cm; legacy pallets use length_cm/width_cm/height_cm.
  // We normalise packing_units to the pallet shape so downstream code is identical.
  const unifiedPallets = [
    ...(pallets || []),
    ...((packingUnits || []).map(u => ({
      id: u.id,
      label: u.name || u.preset_key || u.type || 'Unit',
      length_cm: u.L_cm ?? u.length_cm,
      width_cm: u.W_cm ?? u.width_cm,
      height_cm: u.H_cm ?? u.height_cm,
      x_cm: u.x_cm,
      y_cm: u.y_cm,
      color: u.color || null,
      _packing_unit_type: u.type,
      // iter 251 — surface the shape (box|cylinder) + diameter so the 3D
      // renderer can pick the right geometry for round bins.
      shape: u.shape || (u.type === 'bin' ? 'cylinder' : 'box'),
      diameter_cm: u.diameter_cm || 0,
    }))),
  ];
  // Group items by pallet_id OR packing_unit_id (both supported)
  const groups = new Map();
  items.forEach(it => {
    const acquired = Number(it.qty_acquired || 0);
    if (acquired <= 0) return;
    // iter 252 — loose items (no pallet/packing_unit) render individually so
    // each one is draggable on the floor plan. Every loose item becomes its
    // own group keyed by `_loose:<item_id>` — this also lets us honor a
    // per-item `floor_x_cm/floor_y_cm` so packers can lay them out anywhere
    // on the container floor.
    const key = it.pallet_id || it.packing_unit_id || `_loose:${it.id}`;
    if (!groups.has(key)) {
      groups.set(key, { id: key, items: [], total_weight: 0, total_volume: 0, loose_item: null });
    }
    const g = groups.get(key);
    g.items.push(it);
    g.total_weight += (Number(it.weight_kg) || 0) * acquired;
    const d = it.dims_cm || {};
    const vol = (Number(d.length) || 0) * (Number(d.width) || 0) * (Number(d.height) || 0) * acquired;
    g.total_volume += vol;
    if (key.startsWith('_loose:')) g.loose_item = it;
  });
  // Ensure every explicit pallet/unit appears even if empty (so users see them
  // on the floor plan before assigning items)
  unifiedPallets.forEach(p => {
    if (!groups.has(p.id)) {
      groups.set(p.id, { id: p.id, items: [], total_weight: 0, total_volume: 0 });
    }
  });
  if (groups.size === 0) return { boxes: [], total_volume_m3: 0, fill_pct: 0, container: CONT };

  const PALLET_L = 120;
  const PALLET_W = 100;
  const sorted = Array.from(groups.values()).sort((a, b) => b.total_weight - a.total_weight);
  const boxes = [];
  const palletMeta = new Map(unifiedPallets.map(p => [p.id, p]));
  let row = 0;
  let col = 0;
  const totalVolume = sorted.reduce((s, g) => s + g.total_volume, 0);
  for (const g of sorted) {
    const looseItem = g.loose_item;
    // Loose-item render uses the item's own name + dims + persisted floor
    // position. Falls back to compact 30×30 for items without dims_cm.
    // iter 253 — an item.shape3d (AI-derived from photo) overrides the
    // plain box: L/W/H come from shape3d.primary, colour from
    // primary_color, and shape.kind flows into the box entry so the 3D
    // renderer picks the right geometry (cylinder / sphere / compound).
    const shape3d = looseItem && looseItem.shape3d;
    const meta = looseItem ? {
      label: looseItem.name || 'Item',
      length_cm: (shape3d && shape3d.primary?.L_cm) || (looseItem.dims_cm && looseItem.dims_cm.length) || 30,
      width_cm: (shape3d && shape3d.primary?.W_cm) || (looseItem.dims_cm && looseItem.dims_cm.width) || 30,
      height_cm: (shape3d && shape3d.primary?.H_cm) || (looseItem.dims_cm && looseItem.dims_cm.height) || 30,
      x_cm: looseItem.floor_x_cm,
      y_cm: looseItem.floor_y_cm,
      color: (shape3d && shape3d.primary_color) || '#94a3b8',
      _loose_item_id: looseItem.id,
      shape: shape3d ? (shape3d.kind === 'sphere' ? 'sphere' : shape3d.kind === 'cylinder' ? 'cylinder' : shape3d.kind === 'compound' ? 'compound' : 'box') : 'box',
      shape3d,
    } : (palletMeta.get(g.id) || { label: g.id });
    // Use explicit pallet dims when admin set them, otherwise estimate
    const L = Number(meta.length_cm) || PALLET_L;
    const W = Number(meta.width_cm) || PALLET_W;
    // Use explicit pallet height when set; otherwise scale by relative volume
    const baseHeight = meta.height_cm ? Number(meta.height_cm) : (g.total_volume > 0
      ? Math.max(40, Math.min(220, (g.total_volume / Math.max(totalVolume, 1)) * 1200))
      : 40 + Math.min(120, g.items.length * 5));
    // Use explicit x_cm/y_cm if admin positioned; otherwise greedy grid
    let x, y;
    if (meta.x_cm != null && meta.y_cm != null && (meta.x_cm || meta.y_cm || meta._loose_item_id)) {
      x = Math.max(0, Math.min(CONT.length - L, Number(meta.x_cm) || 0));
      y = Math.max(0, Math.min(CONT.width - W, Number(meta.y_cm) || 0));
    } else {
      x = row * PALLET_L;
      y = col * PALLET_W;
      col++;
      if (col >= 2) { col = 0; row++; }
    }
    boxes.push({
      id: g.id,
      label: meta.label,
      x, y, z: 0,
      length: L,
      width: W,
      height: baseHeight,
      weight_kg: Math.round(g.total_weight),
      item_count: g.items.length,
      color: meta.color || (looseItem ? '#94a3b8' : palletColor(g.id)),
      // iter 252 — loose items are now individually draggable. The move
      // handler downstream detects the "_loose:" prefix and PUTs to the
      // /items/{id} endpoint with floor_x_cm/floor_y_cm rather than the
      // /pallets endpoint.
      draggable: true,
      loose_item_id: meta._loose_item_id || null,
      // iter 251 — round-bin support: cylinder shape uses L as diameter so
      // 2D + 3D both render a disc/cylinder instead of a rectangle.
      // iter 253 — extended to also support sphere + compound (AI-derived
      // from photos) so mixers/blenders/lamps render properly.
      shape: meta.shape || 'box',
      diameter_cm: meta.diameter_cm || 0,
      shape3d: meta.shape3d || null,
    });
    if (row >= 10 && !meta.x_cm) break;  // out of floor space — overflow indicator below
  }
  const overflow = boxes.length < sorted.length;
  const totalVolumeM3 = totalVolume / 1e6;
  const containerVolumeM3 = (CONT.length * CONT.width * CONT.height) / 1e6;
  return {
    boxes,
    total_volume_m3: Number(totalVolumeM3.toFixed(1)),
    container_volume_m3: Number(containerVolumeM3.toFixed(1)),
    fill_pct: Math.min(100, Math.round((totalVolumeM3 / containerVolumeM3) * 100)),
    container: CONT,
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
// 2D — top-down SVG floor plan (with optional drag-to-reposition pallets)
// ───────────────────────────────────────────────────────────────
function FloorPlan2D({ layout, editable, onPalletMove }) {
  const svgRef = React.useRef(null);
  const [draggingId, setDraggingId] = React.useState(null);
  const [dragGhost, setDragGhost] = React.useState(null);   // {id,x,y}
  if (!layout || layout.boxes.length === 0) return null;
  const { container, boxes } = layout;
  const PAD = 16;
  const targetWidth = 700;
  const scale = (targetWidth - PAD * 2) / container.length;
  const w = container.length * scale + PAD * 2;
  const h = container.width * scale + PAD * 2;

  const beginDrag = (e, b) => {
    if (!editable || !b.draggable) return;
    e.preventDefault();
    setDraggingId(b.id);
    setDragGhost({ id: b.id, x: b.x, y: b.y, length: b.length, width: b.width, color: b.color });
  };
  const onPointerMove = (e) => {
    if (!draggingId || !svgRef.current) return;
    const pt = svgRef.current.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const ctm = svgRef.current.getScreenCTM();
    if (!ctm) return;
    const loc = pt.matrixTransform(ctm.inverse());
    const cx = (loc.x - PAD) / scale - (dragGhost?.length || 0) / 2;
    const cy = (loc.y - PAD) / scale - (dragGhost?.width || 0) / 2;
    const x = Math.max(0, Math.min(container.length - (dragGhost?.length || 0), cx));
    const y = Math.max(0, Math.min(container.width - (dragGhost?.width || 0), cy));
    setDragGhost(g => g ? { ...g, x, y } : g);
  };
  const endDrag = async () => {
    if (!draggingId || !dragGhost) { setDraggingId(null); return; }
    const id = draggingId; const x = dragGhost.x; const y = dragGhost.y;
    setDraggingId(null); setDragGhost(null);
    if (onPalletMove) await onPalletMove(id, x, y);
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${w} ${h}`}
      className="w-full"
      role="img"
      aria-label="2D floor plan of container packing"
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerLeave={endDrag}
      style={{ cursor: draggingId ? 'grabbing' : 'default', userSelect: 'none', touchAction: 'none' }}
    >
      {/* Container outline */}
      <rect x={PAD} y={PAD} width={container.length * scale} height={container.width * scale}
        fill="#f8fafc" stroke="#94a3b8" strokeWidth="2" />
      {/* Door side marker (right edge) */}
      <text x={w - PAD - 4} y={PAD - 4} fontSize="9" fill="#64748b" textAnchor="end">← Doors (load last)</text>
      <text x={PAD + 2} y={PAD - 4} fontSize="9" fill="#64748b">Back wall (heavy first) →</text>
      {/* Pallets */}
      {boxes.map(b => {
        const isDragging = draggingId === b.id;
        const px = isDragging ? dragGhost.x : b.x;
        const py = isDragging ? dragGhost.y : b.y;
        return (
          <g key={b.id} onPointerDown={(e) => beginDrag(e, b)} style={{ cursor: (editable && b.draggable) ? 'grab' : 'default' }} data-testid={`viz-pallet-${b.id}`}>
            {(b.shape === 'cylinder' || b.shape === 'sphere' || b.shape === 'compound') ? (
              // iter 251/253 — top-down disc for any round shape (round bins,
              // AI-derived cylinders/spheres, and compound items like mixers
              // whose base is round anyway).
              <circle
                cx={PAD + (px + b.length / 2) * scale}
                cy={PAD + (py + b.width / 2) * scale}
                r={(b.length / 2) * scale}
                fill={b.color} fillOpacity={isDragging ? 0.55 : 0.75}
                stroke="#1e293b" strokeWidth={isDragging ? 2 : 1}
              />
            ) : (
              <rect
                x={PAD + px * scale} y={PAD + py * scale}
                width={b.length * scale} height={b.width * scale}
                fill={b.color} fillOpacity={isDragging ? 0.55 : 0.75} stroke="#1e293b" strokeWidth={isDragging ? 2 : 1}
              />
            )}
            <text
              x={PAD + (px + b.length / 2) * scale}
              y={PAD + (py + b.width / 2) * scale}
              fontSize={Math.max(8, scale * 8)} fill="#fff" textAnchor="middle" dominantBaseline="middle"
              style={{ paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.35)', strokeWidth: 2 }}
            >{(b.label || '').length > 14 ? b.label.slice(0, 12) + '…' : b.label}</text>
            <text
              x={PAD + (px + b.length / 2) * scale}
              y={PAD + (py + b.width / 2) * scale + Math.max(10, scale * 9)}
              fontSize={Math.max(7, scale * 6)} fill="#fff" textAnchor="middle" opacity="0.9"
            >{b.weight_kg} kg</text>
          </g>
        );
      })}
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

    // Lights — softer ambient + warmer key light that casts shadows
    const amb = new THREE.AmbientLight(0xffffff, 0.42);
    root.add(amb);
    const dir1 = new THREE.DirectionalLight(0xfff5e6, 0.85);
    dir1.position.set(80, 120, 60);
    dir1.castShadow = true;
    dir1.shadow.mapSize.width = 1024;
    dir1.shadow.mapSize.height = 1024;
    dir1.shadow.camera.left = -40;
    dir1.shadow.camera.right = 40;
    dir1.shadow.camera.top = 40;
    dir1.shadow.camera.bottom = -40;
    dir1.shadow.bias = -0.0008;
    root.add(dir1);
    const dir2 = new THREE.DirectionalLight(0xc6d4ff, 0.25);
    dir2.position.set(-60, 80, -40);
    root.add(dir2);

    // Subtle hemisphere fill — adds the warm/cool gradient real warehouses have
    const hemi = new THREE.HemisphereLight(0xfff4e0, 0x202833, 0.45);
    root.add(hemi);

    // Container wireframe — keep it light so contents stay the visual focus
    const containerGeo = new THREE.BoxGeometry(c.length / 10, c.height / 10, c.width / 10);
    const containerMat = new THREE.MeshBasicMaterial({ color: 0x64748b, wireframe: true, transparent: true, opacity: 0.6 });
    const containerMesh = new THREE.Mesh(containerGeo, containerMat);
    containerMesh.position.set(c.length / 20, c.height / 20, c.width / 20);
    root.add(containerMesh);

    // Floor — soft warehouse-concrete grey with subtle roughness
    const floorGeo = new THREE.PlaneGeometry(c.length / 10 + 4, c.width / 10 + 4);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0xd8d3cb, roughness: 0.95, metalness: 0.02,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.position.set(c.length / 20, -0.1, c.width / 20);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    root.add(floor);

    // Pallets / boxes — colour by category-aware palette + warm wood pallet base
    // (any object with kind==='pallet' gets the wood look; items inherit their
    //  category colour from the layout caller and pick up cardboard-ish texture).
    const palletWood = new THREE.MeshStandardMaterial({
      color: 0xb38b5d, roughness: 0.85, metalness: 0.05,
    });
    for (const b of layout.boxes) {
      const sx = b.length / 10;
      const sy = b.height / 10;
      const sz = b.width / 10;
      const cx = (b.x + b.length / 2) / 10;
      const cy = ((b.z || 0) + b.height / 2) / 10;   // honor z-offset for stacking
      const cz = (b.y + b.width / 2) / 10;
      // iter 251/253 — geometry per shape. box (default), cylinder (round
      // bins / round appliances), sphere (round objects like balls/lamps),
      // compound (mixer-style base+head — two stacked cylinders).
      const isCylinder = b.shape === 'cylinder';
      const isSphere = b.shape === 'sphere';
      const isCompound = b.shape === 'compound';
      let geo;
      if (isCylinder) {
        geo = new THREE.CylinderGeometry(sx / 2, sx / 2, sy, 32, 1, false);
      } else if (isSphere) {
        // Use the smallest axis as radius so the ball fits its bounding box
        const r = Math.min(sx, sy, sz) / 2;
        geo = new THREE.SphereGeometry(r, 24, 16);
      } else if (isCompound) {
        // Base cylinder = 60% of total height; head cylinder = 30% stacked on top
        geo = null; // rendered as two meshes below
      } else {
        geo = new THREE.BoxGeometry(sx, sy, sz);
      }
      const isPallet = b.kind === 'pallet';
      const mat = isPallet ? palletWood.clone() : new THREE.MeshStandardMaterial({
        color: new THREE.Color(b.color || 0xb45309),
        roughness: 0.78,
        metalness: 0.04,
        transparent: !isPallet,
        opacity: isPallet ? 1 : 0.92,
      });

      if (isCompound) {
        // Base cylinder (60% height) + head (30% height, offset up). Keeps
        // the overall bounding box the same as the primary dims so packing
        // stays consistent.
        const baseH = sy * 0.6;
        const headH = sy * 0.35;
        const baseR = sx / 2;
        const headR = sx / 2.8;
        const baseGeo = new THREE.CylinderGeometry(baseR, baseR, baseH, 24);
        const baseMesh = new THREE.Mesh(baseGeo, mat);
        baseMesh.position.set(cx, cy - sy / 2 + baseH / 2, cz);
        baseMesh.castShadow = true; baseMesh.receiveShadow = true;
        root.add(baseMesh);
        const headGeo = new THREE.CylinderGeometry(headR, headR, headH, 24);
        const headMesh = new THREE.Mesh(headGeo, mat.clone());
        headMesh.position.set(cx, cy - sy / 2 + baseH + headH / 2, cz);
        headMesh.castShadow = true; headMesh.receiveShadow = true;
        root.add(headMesh);
        continue;   // skip the shared mesh add below
      }

      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(cx, cy, cz);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      root.add(mesh);

      // Subtle edge outline for clarity at any distance
      const edges = new THREE.EdgesGeometry(geo);
      const lineMat = new THREE.LineBasicMaterial({ color: 0x1f2937, transparent: true, opacity: 0.45 });
      const wire = new THREE.LineSegments(edges, lineMat);
      wire.position.copy(mesh.position);
      root.add(wire);
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
          shadows: true,
          style: { width: '100%', height: 380, borderRadius: 8, background: 'linear-gradient(to bottom, #1e293b 0%, #475569 60%, #94a3b8 100%)' },
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
export default function ContainerVisualizer({ items = [], pallets = [], packing_units = [], container, editable = false, onPalletMove, defaultMode = '2d' }) {
  const [mode, setMode] = useState(defaultMode);
  const layout = useMemo(() => computeLayout(items, pallets, container, packing_units), [items, pallets, container, packing_units]);

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

        {mode === '2d' && <FloorPlan2D layout={layout} editable={editable} onPalletMove={onPalletMove} />}
        {mode === '2d' && editable && (
          <p className="text-[10px] text-muted-foreground text-center -mt-1">Tip: click + drag pallets to reposition. Container floor is {layout.container.length} × {layout.container.width} cm.</p>
        )}

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
