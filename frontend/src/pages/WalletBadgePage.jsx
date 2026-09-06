import React, { useState, useEffect, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import html2canvas from 'html2canvas';
import { Download, Printer } from 'lucide-react';
import api from '../services/api';
import { UnifiedBadge } from '../components/UnifiedBadge';

/*
 * iter309 — Wallet badge now delegates to <UnifiedBadge /> so it stays byte-
 * for-byte identical with every other place the badge renders (print dialog,
 * kiosk display, PrintableBadges bulk sheet). Old ad-hoc layout is gone.
 */
export default function WalletBadgePage() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const autoPrint = searchParams.get('print') === '1';
  const [badge, setBadge] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const badgeRef = useRef(null);

  useEffect(() => {
    api.get(`/wallet-badge/${token}`).then(r => {
      setBadge(r.data);
      if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({
          type: 'prefetch-wallet-pass',
          urls: [`/api/wallet-badge/${token}`, `/badge/${token}`],
        });
      }
      if (autoPrint) {
        setTimeout(() => { try { window.print(); } catch (e) { console.warn('auto-print:', e); } }, 700);
      }
    }).catch(() => setError('Badge not found or expired'));
  }, [token, autoPrint]);

  // Render the styled card into a PNG that includes photo + QR pixels.
  const downloadPng = async () => {
    if (!badgeRef.current) return;
    setBusy(true);
    try {
      const canvas = await html2canvas(badgeRef.current, {
        backgroundColor: null,
        scale: 2,
        useCORS: true,
        allowTaint: true,
        logging: false,
      });
      const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const safe = (badge?.name || 'badge').replace(/[^a-z0-9-]+/gi, '_').toLowerCase();
      a.href = url; a.download = `5812-badge-${safe}.png`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) {
      alert('Could not save badge image. Try again or use Print.');
    }
    setBusy(false);
  };

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white p-4">
      <div className="text-center">
        <p className="text-lg font-bold">Badge Not Found</p>
        <p className="text-sm text-slate-400 mt-1">{error}</p>
      </div>
    </div>
  );
  if (!badge) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
    </div>
  );

  // UnifiedBadge expects a `person` shape — map the wallet payload onto it.
  const person = {
    id: badge.member_id || badge.id,
    member_id: badge.member_id,
    name: badge.name,
    role: badge.role,
    title: badge.title,
    department: badge.department,
    location_name: badge.location_name,
    country: badge.country,
    country_code: badge.country_code,
    photo_url: badge.photo_url,
    is_medical: badge.is_medical,
    is_resident: badge.is_resident,
    is_sponsored: badge.is_sponsored,
    qr_data: badge.qr_data,
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4" data-testid="wallet-badge-page">
      <div className="w-full flex flex-col items-center">
        <div ref={badgeRef} data-testid="badge-card">
          <UnifiedBadge person={person} showActions={false} />
        </div>

        {/* Action buttons — hidden in print + PNG capture */}
        <div className="mt-5 flex gap-2 no-print w-full max-w-sm">
          <button
            onClick={downloadPng}
            disabled={busy}
            data-testid="badge-download-png"
            className="flex-1 flex items-center justify-center gap-2 bg-amber-400 hover:bg-amber-300 disabled:opacity-60 text-slate-900 font-semibold rounded-lg py-3 text-sm">
            <Download size={16} /> {busy ? 'Saving…' : 'Save to Photos'}
          </button>
          <button
            onClick={() => window.print()}
            data-testid="badge-print"
            className="flex-1 flex items-center justify-center gap-2 bg-slate-700 hover:bg-slate-600 text-white font-semibold rounded-lg py-3 text-sm">
            <Printer size={16} /> Print
          </button>
        </div>
        <p className="text-center text-[11px] text-slate-500 mt-3 no-print max-w-sm">
          Save downloads the badge (photo + QR) as PNG to your device.
          Print opens your device's print dialog — for kiosk PDF printing, some
          browsers let you "Save as PDF" from there.
        </p>
      </div>

      <style>{`
        @media print {
          body, html { background: #fff !important; }
          .no-print { display: none !important; }
        }
      `}</style>
    </div>
  );
}
