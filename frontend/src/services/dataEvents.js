/**
 * Simple event bus for cross-component data refresh.
 * Pages emit 'data-changed' events after mutations (create/update/delete).
 * Other pages/components subscribe to refresh their data.
 */
const listeners = {};

export const dataEvents = {
  emit(event, detail) {
    (listeners[event] || []).forEach(cb => cb(detail));
  },
  on(event, callback) {
    if (!listeners[event]) listeners[event] = [];
    listeners[event].push(callback);
    return () => {
      listeners[event] = listeners[event].filter(cb => cb !== callback);
    };
  },
};

// Convenience: emit after any delete operation
export function emitDataChanged(collection, id) {
  dataEvents.emit('data-changed', { collection, id, action: 'delete', timestamp: Date.now() });
}

// Convenience: emit after any create/update
export function emitDataUpdated(collection, id) {
  dataEvents.emit('data-changed', { collection, id, action: 'update', timestamp: Date.now() });
}
