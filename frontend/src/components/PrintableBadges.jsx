import React, { useRef } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Button } from './ui/button';
import { Printer } from 'lucide-react';
import DOMPurify from 'dompurify';
import { getCountryOutline } from './countryOutlines';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';

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
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
              <NfcIcon size={12} color="#fbbf24" />
              <span style={{ color: '#fbbf24', fontSize: '8px', fontWeight: 700, letterSpacing: '1px', marginLeft: '4px' }}>STAFF</span>
            </span>
          </div>
          <div style={{ flex: 1, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px', position: 'relative', zIndex: 1 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
              {user.photo_url ? (
                <img src={user.photo_url} alt="" style={{ width: '48px', height: '48px', borderRadius: '50%', objectFit: 'cover', border: `2px solid ${kioskMode ? '#1a1a2e' : '#fbbf24'}` }} />
              ) : (
                <div style={{ width: '48px', height: '48px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px', fontWeight: 700, ...initialsStyle }}>{initials}</div>
              )}
              <QRCodeSVG value={user.id || 'N/A'} size={48} level="L" bgColor="transparent" fgColor={textColor} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: textColor }}>{user.name}</div>
              <div style={{ fontSize: '10px', color: subColor, marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.8px' }}>{user.role}</div>
              {user.department && <div style={{ fontSize: '9px', color: kioskMode ? '#888' : '#666', marginTop: '1px' }}>{user.department}</div>}
              <div style={{ fontSize: '9px', color: kioskMode ? '#aaa' : '#888', marginTop: '4px' }}>ID: {memberId}</div>
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
            <QRCodeSVG value={parent.id || parent.phone || 'N/A'} size={72} level="L" bgColor="transparent" fgColor={qrColor} />
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
            <span style={{ color: '#a78bfa', fontSize: '7px', fontWeight: 700, letterSpacing: '1px', marginLeft: 'auto' }}>CHILD TAG</span>
          </div>
          <div style={{ flex: 1, padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '8px', position: 'relative', zIndex: 1 }}>
            {child.photo_url ? (
              <img src={child.photo_url} alt="" style={{ width: '56px', height: '56px', borderRadius: '8px', objectFit: 'cover' }} />
            ) : (
              <QRCodeSVG value={child.id || 'N/A'} size={56} level="L" bgColor="transparent" fgColor={qrColor} />
            )}
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '18px', fontWeight: 800, color: textColor, lineHeight: 1.1 }}>{firstName}</div>
              {child.class_group && <div style={{ fontSize: '11px', color: kioskMode ? '#555' : '#5eead4', marginTop: '2px', fontWeight: 600 }}>{child.class_group}</div>}
              {eventName && <div style={{ fontSize: '9px', color: kioskMode ? '#6366f1' : '#a78bfa', marginTop: '1px' }}>{eventName}</div>}
              {/* Parents */}
              {parentLines.map((line, i) => (
                <div key={i} style={{ fontSize: '8px', color: kioskMode ? '#666' : '#aaa', marginTop: i === 0 ? '4px' : '1px' }}>{line}</div>
              ))}
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
