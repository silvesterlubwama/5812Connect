import React, { useState, useEffect, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { QRCode as QRCodeLogo } from 'react-qrcode-logo';
import html2canvas from 'html2canvas';
import { Download, Printer } from 'lucide-react';
import api from '../services/api';
import { getCountryOutline } from '../components/countryOutlines';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';
const STAFF_TYPES = new Set(['staff', 'director', 'volunteer', 'coordinator', 'manager', 'leader', 'hr', 'executive director', 'adviser', 'admin', 'system_admin']);

function genInitials(name, bg = '#fbbf24', fg = '#1a1a2e', sz = 128) {
  const ini = (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  const c = document.createElement('canvas'); c.width = sz; c.height = sz;
  const ctx = c.getContext('2d');
  ctx.beginPath(); ctx.arc(sz/2, sz/2, sz/2, 0, Math.PI*2); ctx.fillStyle = bg; ctx.fill();
  ctx.fillStyle = fg; ctx.font = `bold ${sz*0.42}px Arial`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(ini, sz/2, sz/2);
  return c.toDataURL('image/png');
}

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
  // Uses html2canvas at 2× resolution for a retina-quality save; the resulting
  // Blob is downloaded so mobile browsers save it straight to the camera roll.
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

  const isStaff = STAFF_TYPES.has((badge.role || '').toLowerCase());
  const firstName = (badge.name || '').split(' ')[0];
  const lastName = (badge.name || '').split(' ').slice(1).join(' ');
  const badgeId = (badge.member_id || '').slice(-8).toUpperCase();
  const outline = getCountryOutline(badge.country_code || badge.country);

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4" data-testid="wallet-badge-page">
      <div className="w-full max-w-sm">
        <div
          ref={badgeRef}
          data-testid="badge-card"
          style={{
            borderRadius: '16px', overflow: 'hidden', background: '#1a1a2e',
            color: '#fff', fontFamily: 'Arial, sans-serif', boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            position: 'relative',
          }}>
          {outline && (
            <svg viewBox={outline.viewBox} width="140" height="140"
              style={{ position: 'absolute', right: 10, top: '40%', transform: 'translateY(-50%)', pointerEvents: 'none', opacity: 0.06 }}>
              <path d={outline.path} fill="none" stroke="#fff" strokeWidth="4" strokeLinejoin="round" />
            </svg>
          )}

          <div style={{ padding: '14px 18px', borderBottom: '2px solid #fbbf24', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <img src={LOGO_URL} alt="58:12 Global" style={{ height: '22px', filter: 'brightness(0) invert(1)' }} crossOrigin="anonymous" />
            <span style={{ color: '#fbbf24', fontSize: '11px', fontWeight: 700, letterSpacing: '2px' }}>
              {isStaff ? 'STAFF' : (badge.role || 'MEMBER').toUpperCase()}
            </span>
          </div>

          <div style={{ padding: '20px 18px', display: 'flex', gap: '14px', position: 'relative', zIndex: 1 }}>
            <div style={{ flex: 1 }}>
              {badge.photo_url && (
                <img src={badge.photo_url} alt="" style={{ width: '56px', height: '56px', borderRadius: '50%', objectFit: 'cover', border: '2px solid #fbbf24', marginBottom: '8px' }} crossOrigin="anonymous" />
              )}
              <div style={{ fontSize: '30px', fontWeight: 800, lineHeight: 1.1 }}>{firstName}</div>
              {lastName && <div style={{ fontSize: '16px', color: '#ccc', marginTop: '3px' }}>{lastName}</div>}
              <div style={{ fontSize: '11px', color: '#fbbf24', marginTop: '10px', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 600 }}>
                {badge.title || badge.role || ''}
              </div>
              {badge.department && <div style={{ fontSize: '10px', color: '#888', marginTop: '3px' }}>{badge.department}</div>}
              {badge.location_name && <div style={{ fontSize: '10px', color: '#666', marginTop: '3px' }}>{badge.location_name}</div>}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <QRCodeLogo value={badge.qr_data || badge.member_id || ''} size={120} bgColor="transparent" fgColor="#ffffff" ecLevel="H" logoImage={badge.photo_url || genInitials(badge.name, '#fbbf24', '#1a1a2e')} logoWidth={44} logoHeight={44} logoPadding={3} logoPaddingStyle="circle" removeQrCodeBehindLogo={true} qrStyle="dots" />
            </div>
          </div>

          <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '9px', color: '#666' }}>
            <span>ID: {badgeId}</span>
            <span style={{ fontWeight: 600, fontSize: '10px' }}>www.5812-Global.org</span>
            <span>58:12 GLOBAL - {new Date().getFullYear()}</span>
          </div>
        </div>

        {/* Action buttons — screened out of print/PNG capture */}
        <div className="mt-5 flex gap-2 no-print">
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
        <p className="text-center text-[11px] text-slate-500 mt-3 no-print">
          Save downloads the badge (photo + QR) as PNG to your device.
          Print opens your device's print dialog — for kiosk PDF printing, some
          browsers let you "Save as PDF" from there.
        </p>
      </div>

      {/* Print-only stylesheet: hide the action buttons + slate background */}
      <style>{`
        @media print {
          body, html { background: #fff !important; }
          .no-print { display: none !important; }
        }
      `}</style>
    </div>
  );
}
