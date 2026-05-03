import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../services/api';

const fmt = (n, c = 'UGX') => `${c} ${(Number(n) || 0).toLocaleString()}`;

/**
 * ResourceViewPage — public page rendered when a 58:12 barcode is scanned.
 * Routes from /resource/:serial. No auth required.
 */
export default function ResourceViewPage() {
  const { serial } = useParams();
  const [resource, setResource] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/resources/by-serial/${encodeURIComponent(serial)}`)
      .then(r => setResource(r.data))
      .catch(() => setError('Resource not found'));
  }, [serial]);

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="text-center bg-white rounded-xl shadow p-8 max-w-md">
        <p className="text-lg font-bold text-red-600">Resource Not Found</p>
        <p className="text-sm text-slate-500 mt-2">No item matches "{serial}".</p>
      </div>
    </div>
  );

  if (!resource) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-100 p-4 flex items-center justify-center" data-testid="resource-view-page">
      <div className="w-full max-w-md bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="bg-gradient-to-br from-primary to-primary/80 text-primary-foreground p-5">
          <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1"
               alt="58:12 Global" className="h-10 mb-3 brightness-0 invert" />
          <p className="text-xs opacity-80">Resource Lookup</p>
          <p className="text-2xl font-bold mt-1 truncate">{resource.name}</p>
          <p className="text-xs mt-2 opacity-80 font-mono">{resource.serial_number}</p>
        </div>
        <div className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${resource.available ? 'bg-green-500' : 'bg-amber-500'}`} />
            <p className={`text-sm font-medium ${resource.available ? 'text-green-700' : 'text-amber-700'}`}>
              {resource.available ? 'Available' : 'In use / unavailable'}
            </p>
          </div>

          <div className="bg-slate-50 rounded-lg p-3 space-y-1.5 text-sm">
            {resource.type && <div className="flex justify-between"><span className="text-slate-500">Type</span><span className="font-medium capitalize">{resource.type}</span></div>}
            {resource.category && <div className="flex justify-between"><span className="text-slate-500">Category</span><span className="font-medium">{resource.category}</span></div>}
            {resource.quantity != null && <div className="flex justify-between"><span className="text-slate-500">Quantity</span><span className="font-medium">{resource.quantity}</span></div>}
            {resource.condition && <div className="flex justify-between"><span className="text-slate-500">Condition</span><span className="font-medium">{resource.condition}</span></div>}
            {resource.owner && <div className="flex justify-between"><span className="text-slate-500">Owner</span><span className="font-medium">{resource.owner}</span></div>}
            {resource.purchase_date && <div className="flex justify-between"><span className="text-slate-500">Purchased</span><span className="font-medium">{resource.purchase_date}</span></div>}
            {resource.purchase_value && <div className="flex justify-between"><span className="text-slate-500">Value</span><span className="font-medium">{fmt(resource.purchase_value, resource.location?.currency || 'UGX')}</span></div>}
          </div>

          {resource.location && (
            <div className="bg-primary/5 rounded-lg p-3">
              <p className="text-xs uppercase tracking-wider text-slate-500">Property of</p>
              <p className="font-semibold mt-0.5">{resource.location.name}</p>
              {resource.location.country && <p className="text-xs text-slate-500">{resource.location.country}</p>}
            </div>
          )}

          {resource.description && (
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500 mb-1">Description</p>
              <p className="text-sm whitespace-pre-wrap">{resource.description}</p>
            </div>
          )}

          <p className="text-[10px] text-slate-400 text-center pt-2">58:12 Global Connect · Item registered in central inventory</p>
        </div>
      </div>
    </div>
  );
}
