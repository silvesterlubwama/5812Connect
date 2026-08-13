/**
 * Cross-platform drag-and-drop primitives for the shipment packing UI.
 *
 * Wraps `react-dnd` with a multi-backend that mounts HTML5 on desktop (mouse)
 * and Touch on tablets/phones (finger). Historically the packing panel used
 * native HTML5 drag events which are completely inert on touch devices — so
 * users on iPad / Android tablets couldn't pack anything.
 *
 * Public API:
 *   • <PackingDndProvider>       — wrap once, high up in the page tree
 *   • useShipItemDrag(itemId)    — bind to draggable item cards
 *   • useShipDropZone(onDrop)    — bind to droppable container tiles
 *
 * Kept intentionally small so existing components can adopt it with a
 * two-line diff each.
 */
import React from 'react';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { TouchBackend } from 'react-dnd-touch-backend';

const SHIP_ITEM = 'SHIP_ITEM';

// Touch devices we detect once at mount; the choice is stable for the session.
const isTouchDevice = () => {
  if (typeof window === 'undefined') return false;
  return ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
};

export function PackingDndProvider({ children }) {
  const backend = isTouchDevice() ? TouchBackend : HTML5Backend;
  const options = isTouchDevice()
    ? { enableMouseEvents: true, delayTouchStart: 120 }   // 120 ms hold before drag starts — prevents accidental drags while scrolling
    : undefined;
  return <DndProvider backend={backend} options={options}>{children}</DndProvider>;
}

// Hook for the item card. Returns a `ref` to attach + `isDragging` for styling.
export function useShipItemDrag(itemId) {
  const [{ isDragging }, dragRef] = useDrag(() => ({
    type: SHIP_ITEM,
    item: { id: itemId },
    collect: (m) => ({ isDragging: m.isDragging() }),
  }), [itemId]);
  return { dragRef, isDragging };
}

// Hook for a container tile (pallet / box / suitcase). Passes the item id
// into the provided `onDrop(itemId)` callback.
export function useShipDropZone(onDrop) {
  const [{ isOver, canDrop }, dropRef] = useDrop(() => ({
    accept: SHIP_ITEM,
    drop: (dragged) => { onDrop?.(dragged.id); },
    collect: (m) => ({ isOver: m.isOver(), canDrop: m.canDrop() }),
  }), [onDrop]);
  return { dropRef, isOver, canDrop };
}
