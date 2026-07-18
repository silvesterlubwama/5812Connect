/* eslint-disable react/no-unknown-property */
/**
 * Suitcase3DScene — mini react-three-fiber scene rendering a suitcase's
 * interior with each item as a colored box. Items are auto-arranged using
 * a naive shelf-pack algorithm (row + wrap) inside the suitcase's L×W×H.
 *
 * Lazy-loaded from ShipmentPackingPanel to keep three.js out of the main bundle.
 */
import React, { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Text } from '@react-three/drei';
import * as THREE from 'three';

const CM_TO_UNIT = 0.01; // 1 cm = 0.01 world units → keeps everything readable

// Naive shelf-pack: fill left→right, wrap on Y (depth), stack on Z (height)
function packItemsInSuitcase(suitcase, items) {
  const L = suitcase.L_cm || 66;
  const W = suitcase.W_cm || 46;
  const H = suitcase.H_cm || 27;
  const placed = [];
  let cursorX = 0, cursorY = 0, cursorZ = 0;
  let rowDepth = 0, layerHeight = 0;
  const palette = [
    '#f97316', '#eab308', '#22c55e', '#06b6d4', '#3b82f6',
    '#8b5cf6', '#ec4899', '#ef4444', '#14b8a6', '#a3e635',
  ];
  items.forEach((it, idx) => {
    const d = it.dims_cm || {};
    // Default dims if none provided — cube-ish 15×10×5cm
    const iL = Math.min(L, Math.max(3, parseFloat(d.length) || 15));
    const iW = Math.min(W, Math.max(3, parseFloat(d.width) || 10));
    const iH = Math.min(H, Math.max(3, parseFloat(d.height) || 5));
    // Wrap to next row if this item overflows the suitcase width in X
    if (cursorX + iL > L) {
      cursorX = 0;
      cursorY += rowDepth;
      rowDepth = 0;
      if (cursorY + iW > W) {
        // Start a new layer
        cursorY = 0;
        cursorZ += layerHeight;
        layerHeight = 0;
      }
    }
    // If item too tall for remaining Z, skip visualising it
    if (cursorZ + iH > H) return;
    placed.push({
      id: it.id, name: it.name, qty: it.qty_acquired,
      x: cursorX, y: cursorY, z: cursorZ,
      L: iL, W: iW, H: iH,
      color: palette[idx % palette.length],
    });
    cursorX += iL;
    rowDepth = Math.max(rowDepth, iW);
    layerHeight = Math.max(layerHeight, iH);
  });
  return { placed, suitcaseDims: { L, W, H } };
}

function ItemBox({ item }) {
  // Center the box on its origin corner so we can position by min-corner
  const cx = (item.x + item.L / 2) * CM_TO_UNIT;
  const cy = (item.z + item.H / 2) * CM_TO_UNIT; // three.js Y = up, so use z as height
  const cz = (item.y + item.W / 2) * CM_TO_UNIT;
  return (
    <group position={[cx, cy, cz]}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[item.L * CM_TO_UNIT, item.H * CM_TO_UNIT, item.W * CM_TO_UNIT]} />
        <meshStandardMaterial color={item.color} roughness={0.7} metalness={0.05} />
      </mesh>
      {/* Item label above the box */}
      {item.name && item.L * CM_TO_UNIT > 0.1 && (
        <Text position={[0, item.H * CM_TO_UNIT / 2 + 0.02, 0]} fontSize={0.03} color="#0f172a" anchorX="center" anchorY="bottom" maxWidth={item.L * CM_TO_UNIT}>
          {item.name.slice(0, 20)}
        </Text>
      )}
    </group>
  );
}

function SuitcaseFrame({ dims }) {
  const L = dims.L * CM_TO_UNIT;
  const W = dims.W * CM_TO_UNIT;
  const H = dims.H * CM_TO_UNIT;
  return (
    <group position={[L / 2, H / 2, W / 2]}>
      {/* Transparent walls to show the suitcase interior */}
      <mesh>
        <boxGeometry args={[L, H, W]} />
        <meshStandardMaterial color="#1e293b" transparent opacity={0.08} depthWrite={false} />
      </mesh>
      {/* Wireframe outline for clarity */}
      <lineSegments>
        <edgesGeometry attach="geometry" args={[new THREE.BoxGeometry(L, H, W)]} />
        <lineBasicMaterial attach="material" color="#334155" linewidth={2} />
      </lineSegments>
    </group>
  );
}

export default function Suitcase3DScene({ suitcase, items }) {
  const { placed, suitcaseDims } = useMemo(() => packItemsInSuitcase(suitcase, items), [suitcase, items]);
  const maxDim = Math.max(suitcaseDims.L, suitcaseDims.W, suitcaseDims.H) * CM_TO_UNIT;
  const camDist = maxDim * 2.2;
  return (
    <Canvas shadows camera={{ position: [camDist, camDist * 0.9, camDist * 1.1], fov: 45 }} data-testid="suitcase-3d-canvas">
      <ambientLight intensity={0.6} />
      <directionalLight position={[3, 5, 4]} intensity={0.8} castShadow />
      <pointLight position={[-3, 2, -3]} intensity={0.3} />
      <SuitcaseFrame dims={suitcaseDims} />
      {placed.map(p => <ItemBox key={p.id} item={p} />)}
      {/* Floor grid for spatial reference */}
      <gridHelper args={[2, 20, '#94a3b8', '#e2e8f0']} position={[maxDim / 2, 0, maxDim / 2]} />
      <OrbitControls target={[suitcaseDims.L * CM_TO_UNIT / 2, suitcaseDims.H * CM_TO_UNIT / 2, suitcaseDims.W * CM_TO_UNIT / 2]} enableDamping />
    </Canvas>
  );
}
