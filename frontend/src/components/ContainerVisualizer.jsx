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
import { Box, RotateCw, Grid3x3, Maximize2, Minimize2 } from 'lucide-react';

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
      x_cm: u.x_cm ?? u.floor_x_cm,
      y_cm: u.y_cm ?? u.floor_y_cm,
      color: u.color || null,
      _packing_unit_type: u.type,
      // iter 260 — parent_id enables Stack Tower View: a unit whose parent
      // is another unit inherits the parent's (x,y) and its height gets
      // added to the parent's z-offset in the 3D scene.
      parent_id: u.parent_id || null,
      rotation_deg: Number(u.rotation_deg) || 0,
      // iter 251 — surface the shape (box|cylinder) + diameter so the 3D
      // renderer can pick the right geometry for round bins.
      shape: u.shape || (u.type === 'bin' ? 'cylinder' : 'box'),
      diameter_cm: u.diameter_cm || 0,
    }))),
  ];
  // iter 260 — Stack Tower View: resolve each packing unit's z-offset by
  // walking its parent_id chain and summing parent heights. Children of a
  // stacked parent inherit the parent's floor (x,y) so the tower renders
  // as one column in 3D and only the top-most box shows in 2D. We build a
  // lookup keyed by unit id containing {z_offset, floor_x, floor_y, root_id,
  // stack_depth} so downstream layout code can apply it uniformly.
  const unitById = new Map(unifiedPallets.map(p => [p.id, p]));
  const stackInfo = new Map();
  const resolveStack = (uid, visited = new Set()) => {
    if (stackInfo.has(uid)) return stackInfo.get(uid);
    if (visited.has(uid)) {
      const self = { z_offset: 0, floor_x: 0, floor_y: 0, root_id: uid, stack_depth: 0 };
      stackInfo.set(uid, self); return self;
    }
    visited.add(uid);
    const u = unitById.get(uid);
    if (!u) {
      const self = { z_offset: 0, floor_x: 0, floor_y: 0, root_id: uid, stack_depth: 0 };
      stackInfo.set(uid, self); return self;
    }
    if (!u.parent_id || !unitById.has(u.parent_id)) {
      const self = { z_offset: 0, floor_x: Number(u.x_cm) || 0, floor_y: Number(u.y_cm) || 0, root_id: uid, stack_depth: 0 };
      stackInfo.set(uid, self); return self;
    }
    const parent = unitById.get(u.parent_id);
    const parentInfo = resolveStack(u.parent_id, visited);
    const info = {
      z_offset: parentInfo.z_offset + (Number(parent.height_cm) || 40),
      floor_x: parentInfo.floor_x,
      floor_y: parentInfo.floor_y,
      root_id: parentInfo.root_id,
      stack_depth: parentInfo.stack_depth + 1,
    };
    stackInfo.set(uid, info);
    return info;
  };
  unifiedPallets.forEach(u => resolveStack(u.id));

  // Group items by pallet_id OR packing_unit_id (both supported)
  const groups = new Map();
  items.forEach(it => {
    const acquired = Number(it.qty_acquired || 0);
    if (acquired <= 0) return;
    // iter 259 — per user request the visualiser now shows BOXES / PALLETS
    // only. Individual items that aren't assigned to a packing_unit or
    // pallet are no longer drawn on the floor plan — EXCEPT ...
    // iter 260 — ... loose items with an AI-derived shape3d or a floor
    // position of their own render as their own draggable block, staged
    // outside the container by default. Packers can drag them into place
    // and, once dropped inside a box, they'll auto-link (or the packer
    // can assign them). Items still inside a box/pallet stay hidden.
    const key = it.pallet_id || it.packing_unit_id;
    if (!key) {
      const hasStagingCoords = it.floor_x_cm != null || it.floor_y_cm != null;
      if (!it.shape3d && !hasStagingCoords) return;
      const looseKey = `_loose:${it.id}`;
      groups.set(looseKey, {
        id: looseKey,
        items: [it],
        total_weight: (Number(it.weight_kg) || 0) * acquired,
        total_volume: (Number((it.dims_cm || {}).length) || 0)
          * (Number((it.dims_cm || {}).width) || 0)
          * (Number((it.dims_cm || {}).height) || 0)
          * acquired,
        loose_item: it,
      });
      return;
    }
    if (!groups.has(key)) {
      groups.set(key, { id: key, items: [], total_weight: 0, total_volume: 0, loose_item: null });
    }
    const g = groups.get(key);
    g.items.push(it);
    g.total_weight += (Number(it.weight_kg) || 0) * acquired;
    const d = it.dims_cm || {};
    const vol = (Number(d.length) || 0) * (Number(d.width) || 0) * (Number(d.height) || 0) * acquired;
    g.total_volume += vol;
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
    // iter 254 — prefer the item's stored dims_cm (what the user actually
    // measured) over shape3d.primary. The AI classifier over-estimated
    // dimensions on some appliance photos (blender came back at 60cm
    // wide), so we now only let shape3d override the *kind* (cylinder /
    // sphere / compound), not the L/W/H. Real dims stay authoritative.
    const meta = looseItem ? {
      label: looseItem.name || 'Item',
      length_cm: (looseItem.dims_cm && looseItem.dims_cm.length) || (shape3d && shape3d.primary?.L_cm) || 30,
      width_cm: (looseItem.dims_cm && looseItem.dims_cm.width) || (shape3d && shape3d.primary?.W_cm) || 30,
      height_cm: (looseItem.dims_cm && looseItem.dims_cm.height) || (shape3d && shape3d.primary?.H_cm) || 30,
      x_cm: looseItem.floor_x_cm,
      y_cm: looseItem.floor_y_cm,
      color: (shape3d && shape3d.primary_color) || '#94a3b8',
      _loose_item_id: looseItem.id,
      shape: shape3d ? (shape3d.kind === 'sphere' ? 'sphere' : shape3d.kind === 'cylinder' ? 'cylinder' : shape3d.kind === 'compound' ? 'compound' : shape3d.kind === 'appliance' ? 'appliance' : 'box') : 'box',
      shape3d,
      // iter 254 — plumb the item's primary photo through so the 3D
      // renderer can map it onto the front (door-facing) face of the
      // block, giving packers a visual ID without hovering for the label.
      photo_url: looseItem.photo_url || (looseItem.image_urls && looseItem.image_urls[0]) || null,
    } : (palletMeta.get(g.id) || { label: g.id });
    // Use explicit pallet dims when admin set them, otherwise estimate
    const L = Number(meta.length_cm) || PALLET_L;
    const W = Number(meta.width_cm) || PALLET_W;
    // Use explicit pallet height when set; otherwise scale by relative volume
    const baseHeight = meta.height_cm ? Number(meta.height_cm) : (g.total_volume > 0
      ? Math.max(40, Math.min(220, (g.total_volume / Math.max(totalVolume, 1)) * 1200))
      : 40 + Math.min(120, g.items.length * 5));
    // iter 254 — NO auto-snap for anything (loose items, pallets, or
    // packing units). Un-positioned units land at (0,0); admin can drag
    // them wherever they want, including past the container walls in
    // full-screen mode. No greedy grid, no wall clamping in layout.
    let x = Number(meta.x_cm) || 0;
    let y = Number(meta.y_cm) || 0;
    let z = 0;
    // iter 260 — apply stack tower z-offset when this unit is stacked on a
    // parent. Stacked boxes inherit the root's (x,y) so they render as a
    // vertical column in 3D. In 2D we hide them from the floor plan
    // (they'd only overlap the parent) and surface a small stack badge
    // on the root instead.
    const si = stackInfo.get(g.id);
    let stackDepth = 0;
    if (si && si.stack_depth > 0) {
      x = si.floor_x;
      y = si.floor_y;
      z = si.z_offset;
      stackDepth = si.stack_depth;
    }
    boxes.push({
      id: g.id,
      label: meta.label,
      x, y, z,
      length: L,
      width: W,
      height: baseHeight,
      // iter 260 — parent chain data for consumers (2D hides stacked
      // children, 3D uses `z` directly which already includes offset).
      parent_id: (palletMeta.get(g.id) && palletMeta.get(g.id).parent_id) || null,
      stack_depth: stackDepth,
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
      photo_url: meta.photo_url || null,
      // iter 254 — rotation about the vertical axis (Y in 3D, Z in 2D).
      // Applied at render time so packers can turn a long crate lengthwise.
      rotation_deg: Number((looseItem && looseItem.rotation_deg) || (palletMeta.get(g.id) && palletMeta.get(g.id).rotation_deg) || 0),
    });
  }
  const overflow = false;
  const totalVolumeM3 = totalVolume / 1e6;
  const containerVolumeM3 = (CONT.length * CONT.width * CONT.height) / 1e6;
  // iter 260 — Stack Tower View: count how many boxes are stacked on each
  // root box so the 2D floor plan can render a "×N stacked" badge on the
  // parent (children themselves are hidden in 2D — they'd only overlap).
  const stackChildrenByRoot = new Map();
  for (const b of boxes) {
    if (b.stack_depth > 0) {
      const rootId = (stackInfo.get(b.id) || {}).root_id || b.id;
      stackChildrenByRoot.set(rootId, (stackChildrenByRoot.get(rootId) || 0) + 1);
    }
  }
  for (const b of boxes) {
    b.stack_children = stackChildrenByRoot.get(b.id) || 0;
  }
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
function FloorPlan2D({ layout, editable, onPalletMove, onPalletRotate, onStack, fullscreen = false }) {
  const svgRef = React.useRef(null);
  const [draggingId, setDraggingId] = React.useState(null);
  const [dragGhost, setDragGhost] = React.useState(null);   // {id,x,y}
  const [hoverTargetId, setHoverTargetId] = React.useState(null);
  if (!layout || layout.boxes.length === 0) return null;
  const { container, boxes: allBoxes } = layout;
  // iter 260 — Stack Tower View: hide stacked children in 2D (they'd only
  // overlap the parent). The parent shows a small "×N" badge instead.
  const boxes = allBoxes.filter(b => !b.stack_depth);
  const PAD = 16;
  // iter 254 — full-screen mode extends the SVG canvas well beyond the
  // container walls so items can be dragged / seen past the container's
  // physical footprint. Compact mode stays tight around the container.
  // iter 260 — always leave a strip to the RIGHT of the container so
  // newly-derived loose items staged outside (floor_x_cm >= container.length)
  // are visible in the compact view too. Packers can drag from that strip
  // into the container without opening fullscreen.
  const targetWidth = fullscreen ? 1600 : 700;
  const OVER_X_RIGHT = fullscreen ? container.length * 0.5 : container.length * 0.25;
  const OVER_X_LEFT = fullscreen ? container.length * 0.5 : 0;
  const OVER_Y = fullscreen ? container.width * 0.6 : 0;
  const totalCmWidth = container.length + OVER_X_LEFT + OVER_X_RIGHT;
  const scale = (targetWidth - PAD * 2) / totalCmWidth;
  const w = totalCmWidth * scale + PAD * 2;
  const h = (container.width + OVER_Y * 2) * scale + PAD * 2;
  // Origin offset so container walls sit at (OVER_X_LEFT, OVER_Y) in cm-space.
  const OX = OVER_X_LEFT;
  const OY = OVER_Y;

  const beginDrag = (e, b) => {
    if (!editable || !b.draggable) return;
    e.preventDefault();
    setDraggingId(b.id);
    setDragGhost({ id: b.id, x: b.x, y: b.y, length: b.length, width: b.width, color: b.color });
    setHoverTargetId(null);
  };
  // iter 260 — Drag-to-stack: while dragging one packing unit, detect
  // whether its centre is over another packing unit's footprint. If so,
  // highlight the target and — on drop — call onStack instead of
  // onPalletMove. Loose items (loose_item_id) never participate as either
  // child or parent in a stack.
  const findStackTarget = (dragId, gx, gy, gL, gW) => {
    if (!onStack) return null;
    const dragBox = boxes.find(bx => bx.id === dragId);
    if (!dragBox || dragBox.loose_item_id) return null;
    const cx = gx + gL / 2;
    const cy = gy + gW / 2;
    for (const t of boxes) {
      if (t.id === dragId) continue;
      if (t.loose_item_id) continue;
      if (cx >= t.x && cx <= t.x + t.length && cy >= t.y && cy <= t.y + t.width) {
        return t.id;
      }
    }
    return null;
  };
  const onPointerMove = (e) => {
    if (!draggingId || !svgRef.current) return;
    const pt = svgRef.current.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const ctm = svgRef.current.getScreenCTM();
    if (!ctm) return;
    const loc = pt.matrixTransform(ctm.inverse());
    const cx = (loc.x - PAD) / scale - OX - (dragGhost?.length || 0) / 2;
    const cy = (loc.y - PAD) / scale - OY - (dragGhost?.width || 0) / 2;
    // iter 254 — NO wall clamping. Items can be positioned anywhere
    // (including past the container walls) so admins can stage / overflow
    // items while planning the layout.
    setDragGhost(g => g ? { ...g, x: cx, y: cy } : g);
    const target = findStackTarget(draggingId, cx, cy, dragGhost?.length || 0, dragGhost?.width || 0);
    setHoverTargetId(target);
  };
  const endDrag = async () => {
    if (!draggingId || !dragGhost) { setDraggingId(null); setHoverTargetId(null); return; }
    const id = draggingId; const x = dragGhost.x; const y = dragGhost.y;
    const target = hoverTargetId;
    setDraggingId(null); setDragGhost(null); setHoverTargetId(null);
    // iter 260 — if the drop centre lies inside another box, stack rather
    // than move. Silent auto-stack per user spec (no confirm popup).
    if (target && onStack) {
      await onStack(id, target);
      return;
    }
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
      <rect x={PAD + OX * scale} y={PAD + OY * scale} width={container.length * scale} height={container.width * scale}
        fill="#f8fafc" stroke="#94a3b8" strokeWidth="2" />
      {/* iter 260 — Staging strip to the RIGHT of the container. Newly
          AI-derived loose items land here so packers can drag them into
          the container. Subtle amber tint + dashed outline so it reads as
          a holding area, not part of the container floor. */}
      {OVER_X_RIGHT > 0 && (
        <g data-testid="viz-staging-strip">
          <rect
            x={PAD + (OX + container.length + 8) * scale}
            y={PAD + OY * scale}
            width={(OVER_X_RIGHT - 8) * scale}
            height={container.width * scale}
            fill="#fef3c7" fillOpacity="0.35"
            stroke="#f59e0b" strokeOpacity="0.55" strokeDasharray="6 4" strokeWidth="1.5"
          />
          <text
            x={PAD + (OX + container.length + OVER_X_RIGHT / 2) * scale}
            y={PAD + OY * scale - 4}
            fontSize="10" fill="#b45309" textAnchor="middle" fontWeight="600"
          >Staging — drag items into container</text>
        </g>
      )}
      {/* Door side marker (right edge) */}
      <text x={PAD + (OX + container.length) * scale - 4} y={PAD + OY * scale - 4} fontSize="9" fill="#64748b" textAnchor="end">← Doors (load last)</text>
      <text x={PAD + OX * scale + 2} y={PAD + OY * scale - 4} fontSize="9" fill="#64748b">Back wall (heavy first) →</text>
      {/* Pallets */}
      {boxes.map(b => {
        const isDragging = draggingId === b.id;
        const isStackTarget = hoverTargetId === b.id;
        const px = isDragging ? dragGhost.x : b.x;
        const py = isDragging ? dragGhost.y : b.y;
        const rot = Number(b.rotation_deg) || 0;
        // Rotate about the shape's own centre so it stays in place visually.
        const cxScreen = PAD + (OX + px + b.length / 2) * scale;
        const cyScreen = PAD + (OY + py + b.width / 2) * scale;
        // iter 260 — Stack target gets a bright ring while a compatible
        // box is dragged over it, telling the packer "let go here to
        // stack". Uses the same colour scheme as the primary CTA.
        const stroke = isStackTarget ? '#2563eb' : '#1e293b';
        const strokeW = isStackTarget ? 3 : (isDragging ? 2 : 1);
        return (
          <g
            key={b.id}
            onPointerDown={(e) => beginDrag(e, b)}
            onDoubleClick={(e) => {
              if (!editable || !b.draggable || !onPalletRotate) return;
              e.preventDefault();
              const next = (rot + 90) % 360;
              onPalletRotate(b.id, next);
            }}
            transform={rot ? `rotate(${rot} ${cxScreen} ${cyScreen})` : undefined}
            style={{ cursor: (editable && b.draggable) ? 'grab' : 'default' }}
            data-testid={`viz-pallet-${b.id}`}
          >
            {(b.shape === 'cylinder' || b.shape === 'sphere' || b.shape === 'compound') ? (
              // iter 251/253 — top-down disc for any round shape (round bins,
              // AI-derived cylinders/spheres, and compound items like mixers
              // whose base is round anyway).
              <circle
                cx={PAD + (OX + px + b.length / 2) * scale}
                cy={PAD + (OY + py + b.width / 2) * scale}
                r={(b.length / 2) * scale}
                fill={b.color} fillOpacity={isDragging ? 0.55 : (isStackTarget ? 0.9 : 0.75)}
                stroke={stroke} strokeWidth={strokeW}
              />
            ) : (
              <rect
                x={PAD + (OX + px) * scale} y={PAD + (OY + py) * scale}
                width={b.length * scale} height={b.width * scale}
                fill={b.color} fillOpacity={isDragging ? 0.55 : (isStackTarget ? 0.9 : 0.75)} stroke={stroke} strokeWidth={strokeW}
              />
            )}
            <text
              x={PAD + (OX + px + b.length / 2) * scale}
              y={PAD + (OY + py + b.width / 2) * scale}
              fontSize={Math.max(8, scale * 8)} fill="#fff" textAnchor="middle" dominantBaseline="middle"
              style={{ paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.35)', strokeWidth: 2 }}
            >{(b.label || '').length > 14 ? b.label.slice(0, 12) + '…' : b.label}</text>
            <text
              x={PAD + (OX + px + b.length / 2) * scale}
              y={PAD + (OY + py + b.width / 2) * scale + Math.max(10, scale * 9)}
              fontSize={Math.max(7, scale * 6)} fill="#fff" textAnchor="middle" opacity="0.9"
            >{b.weight_kg} kg</text>
            {/* iter 259 — rotate handle. Small circle in the top-right
                corner of every box. Click rotates 90° (same action as
                double-clicking the box) so packers see a discoverable
                affordance instead of guessing at the gesture. */}
            {editable && b.draggable && onPalletRotate && (
              <g
                onPointerDown={(e) => { e.stopPropagation(); }}
                onClick={(e) => {
                  e.stopPropagation();
                  onPalletRotate(b.id, (rot + 90) % 360);
                }}
                style={{ cursor: 'pointer' }}
                data-testid={`viz-pallet-rotate-${b.id}`}
              >
                <circle
                  cx={PAD + (OX + px + b.length) * scale - 8}
                  cy={PAD + (OY + py) * scale + 8}
                  r="8"
                  fill="#ffffff" fillOpacity="0.9"
                  stroke="#1e293b" strokeWidth="1"
                />
                <text
                  x={PAD + (OX + px + b.length) * scale - 8}
                  y={PAD + (OY + py) * scale + 8}
                  fontSize="10" fill="#1e293b" textAnchor="middle" dominantBaseline="central"
                  style={{ pointerEvents: 'none', fontFamily: 'sans-serif' }}
                >↻</text>
              </g>
            )}
            {/* iter 260 — Stack Tower badge. When this box has children
                stacked on top, show a small pill on the top-left corner
                so packers see how tall the column is. Click un-stacks
                the top child. */}
            {b.stack_children > 0 && (
              <g
                onPointerDown={(e) => { e.stopPropagation(); }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!editable || !onStack) return;
                  // Un-stack the newest child of this root. Callers can
                  // use the picker for finer control.
                  const child = layout.boxes.find(x => x.parent_id === b.id);
                  if (child) onStack(child.id, null);
                }}
                style={{ cursor: editable && onStack ? 'pointer' : 'default' }}
                data-testid={`viz-pallet-stack-badge-${b.id}`}
              >
                <rect
                  x={PAD + (OX + px) * scale + 2}
                  y={PAD + (OY + py) * scale + 2}
                  width={26} height={14} rx={7}
                  fill="#2563eb" fillOpacity="0.95"
                  stroke="#1e40af" strokeWidth="1"
                />
                <text
                  x={PAD + (OX + px) * scale + 15}
                  y={PAD + (OY + py) * scale + 9}
                  fontSize="9" fontWeight="700" fill="#ffffff" textAnchor="middle" dominantBaseline="central"
                  style={{ pointerEvents: 'none', fontFamily: 'sans-serif' }}
                >×{b.stack_children + 1}</text>
              </g>
            )}
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
      // compound (mixer-style base+head), appliance (box body + decal on
      // the front / door-facing face for washers, microwaves, TVs, fridges).
      const isCylinder = b.shape === 'cylinder';
      const isSphere = b.shape === 'sphere';
      const isCompound = b.shape === 'compound';
      const isAppliance = b.shape === 'appliance';
      let geo;
      if (isCylinder) {
        geo = new THREE.CylinderGeometry(sx / 2, sx / 2, sy, 32, 1, false);
      } else if (isSphere) {
        // Use the smallest axis as radius so the ball fits its bounding box
        const r = Math.min(sx, sy, sz) / 2;
        geo = new THREE.SphereGeometry(r, 24, 16);
      } else if (isCompound || isAppliance) {
        // rendered as two meshes below (base + head or box + decal)
        geo = null;
      } else {
        geo = new THREE.BoxGeometry(sx, sy, sz);
      }
      const isPallet = b.kind === 'pallet';
      // iter 254 — photo-textured box faces. When an item has a photo, load
      // it as a texture and put it on the door-facing (+X) face so packers
      // can visually identify items without hovering for the label. Only
      // applies to plain box geometry (cylinders/spheres/compounds wrap
      // textures poorly and their shape already conveys identity).
      const wantPhotoFaces = !isPallet && !isCylinder && !isSphere && !isCompound && !isAppliance && !!b.photo_url;
      let mat;
      if (isPallet) {
        mat = palletWood.clone();
      } else if (wantPhotoFaces) {
        const baseColor = new THREE.Color(b.color || 0xb45309);
        const solid = () => new THREE.MeshStandardMaterial({
          color: baseColor, roughness: 0.85, metalness: 0.04,
        });
        const photoMat = new THREE.MeshStandardMaterial({
          color: 0xffffff, roughness: 0.72, metalness: 0.02,
        });
        // Absolute-ify relative /api URLs so THREE's fetch resolves correctly
        // (works in both dev and prod because REACT_APP_BACKEND_URL is set).
        const url = /^https?:/i.test(b.photo_url)
          ? b.photo_url
          : `${process.env.REACT_APP_BACKEND_URL || ''}${b.photo_url}`;
        const loader = new THREE.TextureLoader();
        loader.setCrossOrigin('anonymous');
        loader.load(url, (tex) => {
          if ('colorSpace' in tex) tex.colorSpace = THREE.SRGBColorSpace;
          tex.anisotropy = 8;
          photoMat.map = tex;
          photoMat.needsUpdate = true;
        }, undefined, () => { /* keep white fallback on load error */ });
        // BoxGeometry face order: [+X, -X, +Y, -Y, +Z, -Z]. Doors are at
        // the +X end of the container in our layout (see 2D floor plan
        // labels), so put the photo on +X.
        mat = [photoMat, solid(), solid(), solid(), solid(), solid()];
      } else {
        mat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(b.color || 0xb45309),
          roughness: 0.78,
          metalness: 0.04,
          transparent: true,
          opacity: 0.92,
        });
      }

      // iter 254 — apply rotation about vertical axis (Y). Matches 2D SVG
      // where the group is rotated about its centre.
      const rotY = (Number(b.rotation_deg) || 0) * Math.PI / 180;

      if (isAppliance) {
        // Body cube + a decal plane on the +X face (the container's door
        // side). Decal type comes from shape3d.secondary.decal:
        //   circle → circular window (washers/dryers/microwaves)
        //   rect   → rectangular screen (TVs, dishwashers, fridges)
        //   grid   → shelving grid (bookcases)
        const bodyGeo = new THREE.BoxGeometry(sx, sy, sz);
        const bodyMesh = new THREE.Mesh(bodyGeo, mat);
        bodyMesh.position.set(cx, cy, cz);
        bodyMesh.rotation.y = rotY;
        bodyMesh.castShadow = true; bodyMesh.receiveShadow = true;
        root.add(bodyMesh);
        const sec = b.shape3d?.secondary || {};
        const decalKind = sec.decal || 'rect';
        const decalSize = Math.min(0.98, Math.max(0.2, Number(sec.decal_size) || 0.7));
        const dW = sz * decalSize;    // decal width along Z (container's Y)
        const dH = sy * decalSize;    // decal height along Y
        // Place the decal ~0.1cm off the +X face, facing outward.
        const decalX = cx + sx / 2 + 0.02;
        const decalMat = new THREE.MeshStandardMaterial({
          color: decalKind === 'circle' ? 0x1e293b : (sec.screen ? 0x0f172a : 0x475569),
          roughness: 0.6, metalness: 0.1, transparent: false,
        });
        let decalGeo;
        if (decalKind === 'circle') {
          decalGeo = new THREE.CircleGeometry(Math.min(dW, dH) / 2, 32);
        } else {
          decalGeo = new THREE.PlaneGeometry(dW, dH);
        }
        const decal = new THREE.Mesh(decalGeo, decalMat);
        decal.position.set(decalX, cy, cz);
        // Rotate so the plane's normal is +X.
        decal.rotation.y = Math.PI / 2;
        decal.rotation.z = 0;
        if (rotY) {
          // If the whole body is rotated, wrap decal in same rotation about body centre.
          const dx = decal.position.x - cx;
          const dz = decal.position.z - cz;
          decal.position.x = cx + dx * Math.cos(rotY) - dz * Math.sin(rotY);
          decal.position.z = cz + dx * Math.sin(rotY) + dz * Math.cos(rotY);
          decal.rotation.y += rotY;
        }
        root.add(decal);
        // Fine outline on the body for definition
        const bEdges = new THREE.EdgesGeometry(bodyGeo);
        const bLine = new THREE.LineBasicMaterial({ color: 0x1f2937, transparent: true, opacity: 0.45 });
        const bWire = new THREE.LineSegments(bEdges, bLine);
        bWire.position.copy(bodyMesh.position);
        bWire.rotation.y = rotY;
        root.add(bWire);
        continue;
      }

      if (isCompound) {
        const sec = b.shape3d?.secondary || {};
        const headShape = sec.shape || 'cylinder';
        const headRatio = Math.min(0.95, Math.max(0.1, (sec.H_cm && sy > 0 ? (sec.H_cm / (sy * 10)) : 0.35)));
        const baseH = sy * (1 - headRatio);
        const headH = sy * headRatio;
        const baseR = Math.min(sx, sz) / 2;
        const headR = Math.min(sx, sz) / 2.6;
        // Base — cylinder for round bases (mixers, lamps), box for
        // furniture-style bases (chairs, sofas, tables).
        let baseGeo;
        if (['cylinder', 'cone', 'wheel', 'tilt'].includes(headShape)) {
          baseGeo = new THREE.CylinderGeometry(baseR, baseR, baseH, 24);
        } else {
          baseGeo = new THREE.BoxGeometry(sx, baseH, sz);
        }
        const baseMesh = new THREE.Mesh(baseGeo, mat);
        baseMesh.position.set(cx, cy - sy / 2 + baseH / 2, cz);
        baseMesh.rotation.y = rotY;
        baseMesh.castShadow = true; baseMesh.receiveShadow = true;
        root.add(baseMesh);
        // Head — geometry depends on secondary.shape
        let headGeo;
        if (headShape === 'cylinder') {
          headGeo = new THREE.CylinderGeometry(headR, headR, headH, 24);
        } else if (headShape === 'cone') {
          headGeo = new THREE.ConeGeometry(headR, headH, 24);
        } else if (headShape === 'wheel') {
          // Bicycle wheels — two thin tori side by side
          headGeo = new THREE.TorusGeometry(Math.min(sx, sy) / 2, Math.min(sx, sy) / 20, 12, 24);
        } else if (headShape === 'tilt') {
          // Mixer head — tilted cylinder off-axis
          headGeo = new THREE.CylinderGeometry(headR, headR * 0.7, headH, 24);
        } else {
          // box head (chair back, sofa back, table top)
          const hW = sec.position === 'top' ? sx : sx * 0.9;
          const hD = sec.position === 'top' ? sz : sz * 0.4;
          headGeo = new THREE.BoxGeometry(hW, headH, hD);
        }
        const headMesh = new THREE.Mesh(headGeo, mat.clone());
        if (headShape === 'wheel') {
          headMesh.rotation.z = Math.PI / 2;
          headMesh.position.set(cx - sx / 3, cy - sy / 2 + Math.min(sx, sy) / 2, cz);
        } else if (headShape === 'tilt') {
          headMesh.rotation.z = Math.PI / 6;
          headMesh.position.set(cx + sx * 0.15, cy - sy / 2 + baseH + headH / 2 - 0.5, cz);
        } else if (sec.position === 'end') {
          // Guitar head — offset to +X end
          headMesh.position.set(cx + sx / 2 - (sx * 0.075), cy, cz);
        } else if (headShape === 'box' && sec.position === 'top') {
          // Table top slab
          headMesh.position.set(cx, cy - sy / 2 + baseH + headH / 2, cz);
        } else if (headShape === 'box') {
          // Chair/sofa back — offset to back (−Z) so seat + back are visible
          headMesh.position.set(cx, cy - sy / 2 + baseH + headH / 2, cz - sz / 2 + (sz * 0.3));
        } else {
          headMesh.position.set(cx, cy - sy / 2 + baseH + headH / 2, cz);
        }
        headMesh.rotation.y += rotY;
        headMesh.castShadow = true; headMesh.receiveShadow = true;
        root.add(headMesh);
        continue;   // skip the shared mesh add below
      }

      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(cx, cy, cz);
      mesh.rotation.y = rotY;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      root.add(mesh);

      // Subtle edge outline for clarity at any distance
      const edges = new THREE.EdgesGeometry(geo);
      const lineMat = new THREE.LineBasicMaterial({ color: 0x1f2937, transparent: true, opacity: 0.45 });
      const wire = new THREE.LineSegments(edges, lineMat);
      wire.position.copy(mesh.position);
      wire.rotation.y = rotY;
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
    default: function ThreeCanvasInner({ layout, fullscreen = false }) {
      const c = layout?.container || CONTAINER;
      const sceneRoot = useScene3DObjects(layout);
      if (!sceneRoot) return null;
      return React.createElement(
        Canvas,
        {
          camera: { position: [c.length / 6, c.height / 5, c.width / 2], fov: 50 },
          shadows: true,
          style: { width: '100%', height: fullscreen ? '75vh' : 380, borderRadius: 8, background: 'linear-gradient(to bottom, #1e293b 0%, #475569 60%, #94a3b8 100%)' },
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
export default function ContainerVisualizer({ items = [], pallets = [], packing_units = [], container, editable = false, onPalletMove, onPalletRotate, onStack, defaultMode = '2d' }) {
  const [mode, setMode] = useState(defaultMode);
  const [fullscreen, setFullscreen] = useState(false);
  const [stackChild, setStackChild] = useState('');
  const [stackParent, setStackParent] = useState('');
  const layout = useMemo(() => computeLayout(items, pallets, container, packing_units), [items, pallets, container, packing_units]);

  // iter 254 — Esc closes fullscreen; body scroll is locked while open.
  React.useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e) => { if (e.key === 'Escape') setFullscreen(false); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [fullscreen]);

  if (!layout.boxes.length) {
    return (
      <div className="p-4 rounded-lg border bg-muted/30 text-xs text-muted-foreground italic" data-testid="ship-viz-empty">
        Nothing in the container yet — items added &amp; marked acquired will appear here.
      </div>
    );
  }

  const shell = (
    <Card className={`rounded-xl ${fullscreen ? 'h-full' : ''}`} data-testid="ship-viz">
      <CardContent className={`p-3 space-y-3 ${fullscreen ? 'h-full flex flex-col' : ''}`}>
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
          </div>
          <div className="flex items-center gap-1.5">
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
            {editable && (
              <button
                className="px-2 py-1 text-[11px] rounded border bg-background hover:bg-muted flex items-center gap-1"
                onClick={() => setFullscreen(v => !v)}
                data-testid="ship-viz-fullscreen-btn"
                title={fullscreen ? 'Exit full screen (Esc)' : 'Edit in full screen — items can sit past container walls'}
              >
                {fullscreen ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
                {fullscreen ? 'Exit' : 'Full screen'}
              </button>
            )}
          </div>
        </div>

        <div className={fullscreen ? 'flex-1 overflow-auto' : ''}>
          {/* iter 259 — Stack-on picker (packers can put one box on top of
              another). Only shown in fullscreen edit mode to keep the
              default view uncluttered. Uses the existing
              PUT /packing-units/{uid} { parent_id } contract. */}
          {editable && fullscreen && onStack && packing_units.length >= 2 && (
            <div className="flex items-center gap-2 flex-wrap text-xs mb-2 p-2 rounded border bg-muted/30" data-testid="ship-viz-stack-picker">
              <span className="font-semibold text-muted-foreground">Stack</span>
              <select className="border rounded px-1.5 py-1 bg-background" value={stackChild} onChange={e => setStackChild(e.target.value)} data-testid="ship-viz-stack-child">
                <option value="">— pick a box —</option>
                {packing_units.map(u => <option key={u.id} value={u.id}>{u.name || u.id.slice(-6)}</option>)}
              </select>
              <span className="text-muted-foreground">on top of</span>
              <select className="border rounded px-1.5 py-1 bg-background" value={stackParent} onChange={e => setStackParent(e.target.value)} data-testid="ship-viz-stack-parent">
                <option value="">— pick a parent —</option>
                {packing_units.filter(u => u.id !== stackChild).map(u => <option key={u.id} value={u.id}>{u.name || u.id.slice(-6)}</option>)}
              </select>
              <button
                className="px-2 py-1 rounded bg-primary text-primary-foreground disabled:opacity-40"
                disabled={!stackChild || !stackParent || stackChild === stackParent}
                onClick={async () => {
                  await onStack(stackChild, stackParent);
                  setStackChild(''); setStackParent('');
                }}
                data-testid="ship-viz-stack-apply"
              >Stack</button>
              <button
                className="px-2 py-1 rounded border hover:bg-muted"
                disabled={!stackChild}
                onClick={async () => { await onStack(stackChild, null); setStackChild(''); setStackParent(''); }}
                title="Un-stack — put the box back on the floor"
                data-testid="ship-viz-unstack"
              >Un-stack</button>
            </div>
          )}
          {mode === '2d' && <FloorPlan2D layout={layout} editable={editable} onPalletMove={onPalletMove} onPalletRotate={onPalletRotate} onStack={onStack} fullscreen={fullscreen} />}
          {mode === '2d' && editable && (
            <p className="text-[10px] text-muted-foreground text-center mt-1">
              {fullscreen
                ? `Full-screen edit — drag to reposition · drop one box onto another to stack · double-click to rotate 90° · click ×N badge to un-stack. Items can sit past the container walls. Container floor is ${layout.container.length} × ${layout.container.width} cm.`
                : `Tip: drag to reposition · drop onto another box to stack · double-click to rotate 90° · click the ×N badge to un-stack. Container floor is ${layout.container.length} × ${layout.container.width} cm.`}
            </p>
          )}

          {mode === '3d' && (
            <Suspense fallback={<div className="text-xs text-muted-foreground py-8 text-center">Loading 3D…</div>}>
              <ThreeCanvas layout={layout} fullscreen={fullscreen} />
              <p className="text-[10px] text-muted-foreground text-center">Click + drag to orbit · scroll to zoom · right-click + drag to pan</p>
            </Suspense>
          )}
        </div>
      </CardContent>
    </Card>
  );

  if (!fullscreen) return shell;
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/70 backdrop-blur-sm p-4 md:p-6 flex flex-col" data-testid="ship-viz-fullscreen">
      <div className="flex-1 min-h-0">{shell}</div>
    </div>
  );
}
