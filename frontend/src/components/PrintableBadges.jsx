import React, { useRef } from 'react';
import { QRCode as QRCodeLogo } from 'react-qrcode-logo';
import { Button } from './ui/button';
import { Printer } from 'lucide-react';
import DOMPurify from 'dompurify';
import { getCountryOutline } from './countryOutlines';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';

function generateInitialsImg(name, bg = '#fbbf24', fg = '#1a1a2e', sz = 128) {
  const initials = (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  const c = document.createElement('canvas'); c.width = sz; c.height = sz;
  const ctx = c.getContext('2d');
  ctx.beginPath(); ctx.arc(sz/2, sz/2, sz/2, 0, Math.PI*2); ctx.fillStyle = bg; ctx.fill();
  ctx.fillStyle = fg; ctx.font = `bold ${sz*0.42}px Arial`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(initials, sz/2, sz/2);
  return c.toDataURL('image/png');
}

function printElement(ref, title) {
  const html = ref.current?.innerHTML;
  if (!html) return;

  const win = window.open('', '_blank', 'width=500,height=400');
  if (!win) return;
  const doc = win.document;
  doc.open();
  doc.write('<!DOCTYPE html>');
  doc.close();
  doc.head.innerHTML = DOMPurify.sanitize(`<title>${title}</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff}@media print{body{min-height:auto}}</style>`, { FORCE_BODY: true });
  const container = doc.createElement('div');
  container.innerHTML = DOMPurify.sanitize(html);
  doc.body.appendChild(container);
  setTimeout(() => { win.focus(); win.print(); win.close(); }, 300);
}

function CountryWatermarkInline({ country, countryCode, width = 90, height = 90, color = 'rgba(255,255,255,0.08)' }) {
  const outline = getCountryOutline(countryCode || country);
  if (!outline) return null;
  return (
    <svg
      viewBox={outline.viewBox}
      width={width}
      height={height}
      style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
    >
      <path d={outline.path} fill="none" stroke={color} strokeWidth="4" strokeLinejoin="round" />
    </svg>
  );
}

function NfcIcon({ size = 12, color = '#fbbf24' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: 'middle', marginLeft: '4px' }}>
      <path d="M6 8.32a7.43 7.43 0 0 1 0 7.36" />
      <path d="M9.46 6.21a11.76 11.76 0 0 1 0 11.58" />
      <path d="M12.91 4.1a15.91 15.91 0 0 1 .01 15.8" />
      <path d="M16.37 2a20.16 20.16 0 0 1 0 20" />
    </svg>
  );
}

export function StaffBadge({ user, kioskMode = false }) {
  const ref = useRef(null);
  const initials = (user.name || '').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  const memberId = user.id?.slice(-8).toUpperCase() || 'N/A';
  const country = user.country || user.location_country || '';
  const countryCode = user.country_code || user.location_country_code || '';
  const bg = kioskMode ? '#ffffff' : '#1a1a2e';
  const textColor = kioskMode ? '#1a1a2e' : '#ffffff';
  const subColor = kioskMode ? '#555' : '#ccc';
  const footerBg = kioskMode ? '#f5f5f5' : 'rgba(255,255,255,0.05)';
  const footerColor = kioskMode ? '#777' : '#aaa';
  const watermarkColor = kioskMode ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.08)';
  const logoFilter = kioskMode ? 'none' : 'brightness(0) invert(1)';
  const headerBg = kioskMode ? '#f0f0f5' : '#1a1a2e';
  const initialsStyle = kioskMode
    ? { background: '#e8e8f0', color: '#1a1a2e', border: '2px solid #1a1a2e' }
    : { background: 'rgba(255,255,255,0.15)', color: '#fbbf24', border: '2px solid #fbbf24' };

  return (
    <div className="space-y-3">
      <div ref={ref}>
        <div style={{ width: '324px', height: '204px', border: kioskMode ? '1.5px solid #ddd' : 'none', borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: bg, margin: '0 auto', position: 'relative', boxShadow: kioskMode ? '0 1px 4px rgba(0,0,0,0.1)' : '0 4px 12px rgba(0,0,0,0.3)' }}>
          <CountryWatermarkInline country={country} countryCode={countryCode} color={watermarkColor} />
          <div style={{ background: headerBg, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '2px solid #fbbf24' }}>
            <img src={LOGO_URL} alt="58:12" style={{ height: '18px', filter: logoFilter }} crossOrigin="anonymous" />
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <NfcIcon size={11} color="#fbbf24" />
              {user.is_medical && <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M12 14v-4M10 12h4"/></svg>}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            </span>
          </div>
          <div style={{ flex: 1, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px', position: 'relative', zIndex: 1 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: textColor }}>{user.name}</div>
              <div style={{ fontSize: '10px', color: subColor, marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.8px' }}>{user.role}</div>
              {user.department && <div style={{ fontSize: '9px', color: kioskMode ? '#888' : '#666', marginTop: '1px' }}>{user.department}</div>}
              <div style={{ fontSize: '9px', color: kioskMode ? '#aaa' : '#888', marginTop: '4px' }}>ID: {memberId}</div>
            </div>
            <div style={{ flexShrink: 0, borderRadius: '10px', overflow: 'hidden' }}>
              <QRCodeLogo value={user.id || 'N/A'} size={96} bgColor="transparent" fgColor={textColor} ecLevel="H" logoImage={user.photo_url || generateInitialsImg(user.name, '#fbbf24', kioskMode ? '#fff' : '#1a1a2e')} logoWidth={36} logoHeight={36} logoPadding={3} logoPaddingStyle="circle" removeQrCodeBehindLogo={true} qrStyle="dots" />
            </div>
          </div>
          <div style={{ background: footerBg, padding: '4px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '7px', color: footerColor, borderTop: kioskMode ? '1px solid #eee' : 'none' }}>
            <span>ID: {memberId}</span>
            <span style={{ fontWeight: 600 }}>www.5812-Global.org</span>
            <span>58:12 GLOBAL - {new Date().getFullYear()}</span>
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-center">
        <Button size="sm" className="gap-1.5 text-xs" onClick={() => printElement(ref, `Staff Badge - ${user.name}`)} data-testid="print-staff-badge"><Printer size={12} /> Print Badge</Button>
      </div>
    </div>
  );
}

export function ParentBadge({ parent, children: childList, kioskMode = false }) {
  const ref = useRef(null);
  const country = parent.country || parent.location_country || '';
  const countryCode = parent.country_code || parent.location_country_code || '';
  const bg = kioskMode ? '#ffffff' : '#1e3a5f';
  const textColor = kioskMode ? '#1a1a2e' : '#fff';
  const qrColor = kioskMode ? '#1a1a2e' : '#ffffff';
  const watermarkColor = kioskMode ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.08)';
  const logoFilter = kioskMode ? 'none' : 'brightness(0) invert(1)';

  return (
    <div className="space-y-3">
      <div ref={ref}>
        <div style={{ width: '324px', height: '204px', border: kioskMode ? '1.5px solid #ddd' : 'none', borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: bg, margin: '0 auto', position: 'relative', boxShadow: kioskMode ? 'none' : '0 4px 12px rgba(0,0,0,0.3)' }}>
          <CountryWatermarkInline country={country} countryCode={countryCode} color={watermarkColor} />
          <div style={{ background: kioskMode ? '#f0f0f5' : bg, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '2px solid #34d399' }}>
            <img src={LOGO_URL} alt="58:12" style={{ height: '18px', filter: logoFilter }} crossOrigin="anonymous" />
            <span style={{ color: '#34d399', fontSize: '8px', fontWeight: 700, letterSpacing: '1px', marginLeft: 'auto' }}>PARENT</span>
          </div>
          <div style={{ flex: 1, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px', position: 'relative', zIndex: 1 }}>
            <div style={{ flexShrink: 0, borderRadius: '8px', overflow: 'hidden' }}>
              <QRCodeLogo value={parent.id || parent.phone || 'N/A'} size={72} bgColor="transparent" fgColor={qrColor} ecLevel="H" qrStyle="dots" />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: textColor }}>{parent.name}</div>
              {parent.phone && <div style={{ fontSize: '10px', color: kioskMode ? '#555' : '#ccc', marginTop: '2px' }}>{parent.phone}</div>}
              <div style={{ fontSize: '9px', color: kioskMode ? '#888' : '#93c5fd', marginTop: '4px' }}>
                Children: {(childList || []).map(c => c.name?.split(' ')[0]).join(', ') || 'None'}
              </div>
            </div>
          </div>
          <div style={{ background: kioskMode ? '#f5f5f5' : 'rgba(255,255,255,0.05)', padding: '4px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '7px', color: kioskMode ? '#777' : '#aaa', borderTop: kioskMode ? '1px solid #eee' : 'none' }}>
            <span>{parent.location_name || ''}</span>
            <span style={{ fontWeight: 600 }}>www.5812-Global.org</span>
            <span>58:12 GLOBAL - {new Date().getFullYear()}</span>
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-center">
        <Button size="sm" className="gap-1.5 text-xs" onClick={() => printElement(ref, `Parent Badge - ${parent.name}`)} data-testid="print-parent-badge"><Printer size={12} /> Print Badge</Button>
      </div>
    </div>
  );
}

export function ChildTag({ child, parentPhone, eventName, locationName, kioskMode = false, parents = [], campusPhone = '' }) {
  const ref = useRef(null);
  const firstName = (child.name || '').split(' ')[0];
  const phone4 = (parentPhone || '').slice(-4);
  const country = child.country || child.location_country || '';
  const countryCode = child.country_code || child.location_country_code || '';
  const bg = kioskMode ? '#ffffff' : '#0f766e';
  const textColor = kioskMode ? '#1a1a2e' : '#fff';
  const qrColor = kioskMode ? '#1a1a2e' : '#fff';
  const watermarkColor = kioskMode ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.08)';
  const logoFilter = kioskMode ? 'none' : 'brightness(0) invert(1)';
  const parentLines = parents.length > 0
    ? parents.map(p => `${p.name}${p.phone ? ' (' + p.phone + ')' : ''}`).slice(0, 2)
    : phone4 ? [`Parent: ****${phone4}`] : [];

  return (
    <div className="space-y-3">
      <div ref={ref}>
        {/* Front of badge */}
        <div style={{ width: '280px', height: kioskMode ? '160px' : '180px', border: kioskMode ? '1.5px solid #ddd' : 'none', borderRadius: '10px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: bg, margin: '0 auto', position: 'relative', boxShadow: kioskMode ? 'none' : '0 4px 12px rgba(0,0,0,0.3)' }}>
          <CountryWatermarkInline country={country} countryCode={countryCode} width={60} height={60} color={watermarkColor} />
          <div style={{ background: kioskMode ? '#f0f0f5' : bg, padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '6px', borderBottom: '2px solid #a78bfa' }}>
            <img src={LOGO_URL} alt="58:12" style={{ height: '14px', filter: logoFilter }} crossOrigin="anonymous" />
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <NfcIcon size={10} color="#a78bfa" />
              {child.is_medical && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M12 14v-4M10 12h4"/></svg>}
              {child.is_resident && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>}
              {child.is_sponsored && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>}
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 1 0-16 0"/></svg>
            </span>
          </div>
          <div style={{ flex: 1, padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '6px', position: 'relative', zIndex: 1 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '18px', fontWeight: 800, color: textColor, lineHeight: 1.1 }}>{firstName}</div>
              {child.class_group && <div style={{ fontSize: '10px', color: kioskMode ? '#555' : '#5eead4', marginTop: '2px', fontWeight: 600 }}>{child.class_group}</div>}
              {eventName && <div style={{ fontSize: '8px', color: kioskMode ? '#6366f1' : '#a78bfa', marginTop: '1px' }}>{eventName}</div>}
              {parentLines.map((line, i) => (
                <div key={i} style={{ fontSize: '7px', color: kioskMode ? '#666' : '#aaa', marginTop: i === 0 ? '3px' : '0px' }}>{line}</div>
              ))}
            </div>
            <div style={{ flexShrink: 0, borderRadius: '8px', overflow: 'hidden' }}>
              <QRCodeLogo value={child.id || 'N/A'} size={80} bgColor="transparent" fgColor={qrColor} ecLevel="H" logoImage={child.photo_url || generateInitialsImg(child.name, '#a78bfa', '#fff')} logoWidth={30} logoHeight={30} logoPadding={2} logoPaddingStyle="circle" removeQrCodeBehindLogo={true} qrStyle="dots" />
            </div>
          </div>
          <div style={{ background: kioskMode ? '#f5f5f5' : 'rgba(255,255,255,0.05)', padding: '3px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '7px', color: kioskMode ? '#777' : '#aaa', borderTop: kioskMode ? '1px solid #eee' : 'none' }}>
            <span>{locationName || ''}{campusPhone ? ` | ${campusPhone}` : ''}</span>
            <span style={{ fontWeight: 600 }}>www.5812-Global.org</span>
            <span>58:12 GLOBAL - {new Date().toLocaleDateString()}</span>
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-center">
        <Button size="sm" className="gap-1.5 text-xs" onClick={() => printElement(ref, `Child Tag - ${child.name}`)} data-testid="print-child-tag"><Printer size={12} /> Print Tag</Button>
      </div>
    </div>
  );
}
