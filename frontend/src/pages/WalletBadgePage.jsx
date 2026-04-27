import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { QRCode as QRCodeLogo } from 'react-qrcode-logo';
import api from '../services/api';
import { getCountryOutline } from '../components/countryOutlines';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';
const STAFF_TYPES = new Set(['staff', 'director', 'volunteer', 'coordinator', 'manager', 'leader', 'hr', 'executive director', 'adviser', 'admin', 'system_admin']);

export default function WalletBadgePage() {
  const { token } = useParams();
  const [badge, setBadge] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/wallet-badge/${token}`).then(r => setBadge(r.data)).catch(() => setError('Badge not found or expired'));
  }, [token]);

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
      {/* Mobile-optimized badge card */}
      <div className="w-full max-w-sm">
        <div style={{
          borderRadius: '16px', overflow: 'hidden', background: '#1a1a2e',
          color: '#fff', fontFamily: 'Arial, sans-serif', boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          position: 'relative',
        }}>
          {/* Country watermark */}
          {outline && (
            <svg viewBox={outline.viewBox} width="140" height="140"
              style={{ position: 'absolute', right: 10, top: '40%', transform: 'translateY(-50%)', pointerEvents: 'none', opacity: 0.06 }}>
              <path d={outline.path} fill="none" stroke="#fff" strokeWidth="4" strokeLinejoin="round" />
            </svg>
          )}

          {/* Header */}
          <div style={{ padding: '14px 18px', borderBottom: '2px solid #fbbf24', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <img src={LOGO_URL} alt="58:12 Global" style={{ height: '22px', filter: 'brightness(0) invert(1)' }} crossOrigin="anonymous" />
            <span style={{ color: '#fbbf24', fontSize: '11px', fontWeight: 700, letterSpacing: '2px' }}>
              {isStaff ? 'STAFF' : (badge.role || 'MEMBER').toUpperCase()}
            </span>
          </div>

          {/* Body */}
          <div style={{ padding: '20px 18px', display: 'flex', gap: '14px', position: 'relative', zIndex: 1 }}>
            <div style={{ flex: 1 }}>
              {badge.photo_url && (
                <img src={badge.photo_url} alt="" style={{ width: '56px', height: '56px', borderRadius: '50%', objectFit: 'cover', border: '2px solid #fbbf24', marginBottom: '8px' }} />
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
              <QRCodeLogo value={badge.qr_data || badge.member_id || ''} size={100} bgColor="transparent" fgColor="#ffffff" ecLevel="H" logoImage={badge.photo_url || ''} logoWidth={34} logoHeight={34} logoPadding={2} logoPaddingStyle="circle" removeQrCodeBehindLogo={true} qrStyle="dots" />
            </div>
          </div>

          {/* Footer */}
          <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '9px', color: '#666' }}>
            <span>ID: {badgeId}</span>
            <span style={{ fontWeight: 600, fontSize: '10px' }}>www.5812-Global.org</span>
            <span>58:12 GLOBAL - {new Date().getFullYear()}</span>
          </div>
        </div>

        {/* Save instructions */}
        <div style={{ textAlign: 'center', marginTop: '20px', color: '#94a3b8', fontSize: '12px' }}>
          <p style={{ fontWeight: 600, marginBottom: '4px' }}>Save to your phone</p>
          <p>iOS: Tap Share then "Add to Home Screen"</p>
          <p>Android: Tap menu then "Add to Home Screen"</p>
        </div>
      </div>
    </div>
  );
}
