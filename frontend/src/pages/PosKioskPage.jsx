import React, { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import ProductsPage from './ProductsPage';

/**
 * PosKioskPage — dedicated POS kiosk URL.
 * Reads /pos/:storeId, persists the store binding to localStorage,
 * then renders the regular POS page locked to that store.
 *
 * Use case: each kiosk/till has its own URL like /pos/loc_419f5d5e
 * which auto-binds the kiosk to "58:12 Uganda" so cashiers can't switch.
 */
export default function PosKioskPage() {
  const { storeId } = useParams();

  useEffect(() => {
    if (storeId) {
      localStorage.setItem('5812_pos_store_id', storeId);
      // Mark this device as a kiosk-locked POS so the UI hides cross-store controls
      localStorage.setItem('5812_pos_kiosk', 'true');
    }
  }, [storeId]);

  if (!storeId) return <Navigate to="/sales" replace />;
  // Force-redirect to /sales which now reads the saved store_id from localStorage.
  // Using replace so the dedicated POS URL stays in the history bookmark.
  return <ProductsPage />;
}
