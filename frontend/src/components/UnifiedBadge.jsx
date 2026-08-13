import React, { useRef, useState } from 'react';
import { Download, Printer, Smartphone, Wifi } from 'lucide-react';
import { Button } from './ui/button';
import DOMPurify from 'dompurify';
import { toast } from 'sonner';
import { QRCode as QRCodeLogo } from 'react-qrcode-logo';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';
import { getCountryOutline } from './countryOutlines';

const BADGE_COLORS = {
  staff: { bg: '#1a1a2e', accent: '#fbbf24', label: 'STAFF' },
  volunteer: { bg: '#1a1a2e', accent: '#22c55e', label: 'VOL' },
  director: { bg: '#1a1a2e', accent: '#8b5cf6', label: 'DIR' },
  guest: { bg: '#334155', accent: '#60a5fa', label: 'GUEST' },
  visitor: { bg: '#334155', accent: '#60a5fa', label: 'GUEST' },
  child: { bg: '#0f766e', accent: '#5eead4', label: 'CHILD' },
  parent: { bg: '#1e3a5f', accent: '#93c5fd', label: 'PARENT' },
  member: { bg: '#1a1a2e', accent: '#e2e8f0', label: 'MBR' },
};

// Badge type icons (inline SVG) — replace text labels
function BadgeTypeIcon({ type, size = 14, color }) {
  const s = size;
  switch (type) {
    case 'staff': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>;
    case 'director': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7Z"/><path d="M4 22h16"/></svg>;
    case 'volunteer': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>;
    case 'child': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 1 0-16 0"/></svg>;
    case 'parent': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>;
    case 'guest': case 'visitor': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 20a6 6 0 0 0-12 0"/><circle cx="12" cy="10" r="4"/><circle cx="12" cy="12" r="10"/></svg>;
    default: return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>;
  }
}

// Status symbols (medical, resident, sponsored)
function MedicalIcon({ size = 11, color = '#ef4444' }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M12 14v-4M10 12h4"/></svg>;
}
function ResidentIcon({ size = 11, color = '#3b82f6' }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>;
}
function SponsorIcon({ size = 11, color = '#8b5cf6' }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>;
}

const STAFF_TYPES = new Set(['staff', 'director', 'volunteer']);

function getBadgeType(person) {
  const role = (person.role || person.type || '').toLowerCase();
  if (['admin', 'system_admin', 'executive director', 'adviser'].includes(role)) return 'director';
  if (['director', 'manager', 'coordinator', 'leader', 'staff', 'hr'].includes(role)) return 'staff';
  if (role === 'volunteer') return 'volunteer';
  if (role === 'parent' || person.is_parent) return 'parent';
  if (role === 'child' || person.age || person.class_group || person.grade) return 'child';
  if (role === 'guest' || role === 'visitor') return 'guest';
  return 'member';
}

function CountryWatermark({ country, countryCode, width, height, color }) {
  const outline = getCountryOutline(countryCode || country);
  if (!outline) return null;
  return (
    <svg
      viewBox={outline.viewBox}
      width={width}
      height={height}
      style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
    >
      <path d={outline.path} fill="none" stroke={color} strokeWidth="4" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Generate a base64 data URL with initials on a colored circle.
 * Used as logo fallback when no photo_url is available.
 */
function generateInitialsImage(name, bgColor = '#fbbf24', textColor = '#1a1a2e', size = 128) {
  const initials = (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.beginPath(); ctx.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2); ctx.fillStyle = bgColor; ctx.fill();
  ctx.fillStyle = textColor; ctx.font = `bold ${size * 0.42}px Arial`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(initials, size / 2, size / 2);
  return canvas.toDataURL('image/png');
}



function NfcSymbol({ size = 14, color = '#fbbf24' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: 'middle' }}>
      <path d="M6 8.32a7.43 7.43 0 0 1 0 7.36" />
      <path d="M9.46 6.21a11.76 11.76 0 0 1 0 11.58" />
      <path d="M12.91 4.1a15.91 15.91 0 0 1 .01 15.8" />
      <path d="M16.37 2a20.16 20.16 0 0 1 0 20" />
    </svg>
  );
}

export function UnifiedBadge({ person, size = 'normal', showActions = true, kioskMode = false, canWriteNfc = false }) {
  const badgeRef = useRef(null);
  const [downloading, setDownloading] = useState(false);
  const [nfcWriting, setNfcWriting] = useState(false);
  const type = getBadgeType(person);
  const colors = BADGE_COLORS[type] || BADGE_COLORS.member;
  const firstName = (person.name || '').split(' ')[0] || '';
  const lastName = (person.name || '').split(' ').slice(1).join(' ') || '';
  const title = person.title || person.role || type;
  const qrData = person.id || person.name || '';
  const badgeId = (person.id || '').slice(-8).toUpperCase();
  const country = person.country || person.location_country || '';
  const countryCode = person.country_code || person.location_country_code || '';
  const isStaffType = STAFF_TYPES.has(type);
  const isSmall = size === 'small';

  // Kiosk prints use white bg for ink saving
  const bgColor = kioskMode ? '#ffffff' : colors.bg;
  const textColor = kioskMode ? '#1a1a2e' : '#ffffff';
  const subTextColor = kioskMode ? '#555' : '#ccc';
  const footerBg = kioskMode ? '#f5f5f5' : 'rgba(255,255,255,0.05)';
  const footerColor = kioskMode ? '#777' : '#666';
  const watermarkColor = kioskMode ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.06)';
  const qrFg = kioskMode ? '#1a1a2e' : '#ffffff';
  const headerBg = kioskMode ? '#f0f0f5' : undefined; // kiosk uses light header
  const headerBorder = kioskMode ? `2px solid ${colors.accent}` : `2px solid ${colors.accent}`;
  const logoFilter = kioskMode ? 'none' : 'brightness(0) invert(1)';

  const printBadge = () => {
    const html = badgeRef.current?.innerHTML;
    if (!html) return;
    const win = window.open('', '_blank', 'width=420,height=320');
    if (!win) return;
    const doc = win.document;
    doc.open(); doc.write('<!DOCTYPE html>'); doc.close();
    doc.head.innerHTML = DOMPurify.sanitize('<title>Badge</title><style>*{margin:0;padding:0;box-sizing:border-box;-webkit-print-color-adjust:exact !important;print-color-adjust:exact !important;color-adjust:exact !important}body{display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff;font-family:Arial,sans-serif}@media print{body{min-height:auto;background:#fff !important}}</style>', { FORCE_BODY: true });
    const container = doc.createElement('div');
    container.innerHTML = DOMPurify.sanitize(html);
    doc.body.appendChild(container);
    setTimeout(() => { win.focus(); win.print(); win.close(); }, 300);
  };

  const downloadBadge = async () => {
    setDownloading(true);
    try {
      const el = badgeRef.current;
      if (!el) return;
      const canvas = document.createElement('canvas');
      const scale = 3;
      canvas.width = 340 * scale;
      canvas.height = 216 * scale;
      const ctx = canvas.getContext('2d');
      ctx.scale(scale, scale);
      ctx.fillStyle = bgColor;
      ctx.roundRect(0, 0, 340, 216, 12);
      ctx.fill();
      ctx.fillStyle = colors.accent;
      ctx.font = 'bold 10px Arial';
      ctx.fillText(colors.label, 16, 24);
      ctx.fillStyle = textColor;
      ctx.font = 'bold 28px Arial';
      ctx.fillText(firstName, 16, 100);
      ctx.font = '16px Arial';
      ctx.fillText(lastName, 16, 122);
      ctx.font = '12px Arial';
      ctx.fillStyle = colors.accent;
      ctx.fillText(title.toUpperCase(), 16, 145);
      ctx.fillStyle = footerColor;
      ctx.font = '10px Arial';
      ctx.fillText(`ID: ${badgeId}`, 16, 195);
      ctx.fillText('58:12 GLOBAL', 130, 208);
      ctx.fillText('www.5812-Global.org', 110, 195);
      canvas.toBlob(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `badge-${firstName.toLowerCase()}-${type}.png`;
        a.click();
        URL.revokeObjectURL(url);
        toast.success('Badge downloaded!');
      }, 'image/png');
    } catch { toast.error('Download failed'); }
    finally { setDownloading(false); }
  };

  const addToWallet = async () => {
    const memberId = person.member_id || person.id;
    if (!memberId) { toast.error('No member ID'); return; }
    try {
      const { default: api } = await import('../services/api');
      const res = await api.post(`/members/${memberId}/wallet-badge`);
      const badgeUrl = `${window.location.origin}/badge/${res.data.token}`;
      window.open(badgeUrl, '_blank');
      toast.success('Badge page opened — save to Home Screen for wallet access');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create wallet badge');
      downloadBadge();
    }
  };

  const writeToNfc = async () => {
    if (!('NDEFReader' in window)) {
      toast.error('Built-in NFC requires Chrome on Android. On desktop, use a USB NFC reader (which presents as a keyboard or HID) — your barcode scanner shortcut handles those automatically.');
      return;
    }
    setNfcWriting(true);
    try {
      const ndef = new window.NDEFReader();
      const memberId = person.member_id || person.id;
      // Get signed payload from backend
      const { default: api } = await import('../services/api');
      const payloadRes = await api.post(`/members/${memberId}/nfc-payload`);
      const signedPayload = payloadRes.data.payload;
      toast.info('Hold a blank NFC tag near the device...');
      // Write encrypted signed payload
      await ndef.write({
        records: [
          { recordType: 'text', data: signedPayload },
        ]
      });
      // Lock tag as read-only (permanent — cannot be overwritten)
      try {
        await ndef.makeReadOnly();
        toast.success('NFC tag written and locked (read-only)');
      } catch (lockErr) {
        console.warn('Could not lock tag:', lockErr);
        toast.success('NFC tag written (lock not supported on this tag)');
      }
      // Record the write on the backend
      try {
        const scanResult = await new Promise((resolve) => {
          ndef.scan().then(() => {
            ndef.addEventListener('reading', ({ serialNumber }) => resolve(serialNumber), { once: true });
            setTimeout(() => resolve('unknown'), 3000);
          }).catch(() => resolve('unknown'));
        });
        await api.post(`/members/${memberId}/nfc-write`, { serial_number: scanResult || 'written-tag', written_data: signedPayload, label: `Badge: ${person.name}` });
      } catch (err) { console.warn('NFC write log failed:', err); }
    } catch (err) {
      if (err.name === 'NotAllowedError') toast.error('NFC permission denied');
      else if (err.name === 'NotSupportedError') toast.error('NFC not supported on this device');
      else toast.error('NFC write failed: ' + (err.message || err));
    }
    finally { setNfcWriting(false); }
  };

  return (
    <div className="space-y-3">
      <div ref={badgeRef}>
        <div style={{
          width: isSmall ? '240px' : '340px', height: isSmall ? '152px' : '216px',
          borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column',
          background: bgColor, color: textColor, fontFamily: 'Arial, sans-serif',
          boxShadow: kioskMode ? '0 1px 4px rgba(0,0,0,0.12)' : '0 4px 12px rgba(0,0,0,0.3)',
          margin: '0 auto', position: 'relative',
          border: kioskMode ? '1.5px solid #ddd' : 'none',
        }}>
          {/* Country watermark */}
          <CountryWatermark
            country={country}
            countryCode={countryCode}
            width={isSmall ? 80 : 120}
            height={isSmall ? 80 : 120}
            color={watermarkColor}
          />

          {/* Header — logo | status symbols + badge type icon */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: isSmall ? '6px 10px' : '8px 14px',
            borderBottom: headerBorder,
            background: headerBg,
          }}>
            <img src={LOGO_URL} alt="58:12" style={{ height: isSmall ? '14px' : '18px', filter: logoFilter }} crossOrigin="anonymous" />
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              {(isStaffType || type === 'child') && <NfcSymbol size={isSmall ? 9 : 11} color={colors.accent} />}
              {person.is_medical && <MedicalIcon size={isSmall ? 9 : 11} color="#ef4444" />}
              {person.is_resident && <ResidentIcon size={isSmall ? 9 : 11} color="#3b82f6" />}
              {person.is_sponsored && <SponsorIcon size={isSmall ? 9 : 11} color="#8b5cf6" />}
              <BadgeTypeIcon type={type} size={isSmall ? 11 : 13} color={colors.accent} />
            </div>
          </div>

          {/* Body — left: plain QR | center: name+info | right: LARGE photo
              Rearranged Feb 2026 so the photo is prominent for visual ID
              checks by security and scanners can still hit the QR from the
              edge without hunting past the portrait. */}
          <div style={{ flex: 1, display: 'flex', padding: isSmall ? '8px 10px' : '10px 14px', gap: isSmall ? '8px' : '12px', position: 'relative', zIndex: 1, alignItems: 'center' }}>
            {/* QR code — plain (no embedded logo) so scanners get max contrast */}
            <div style={{ flexShrink: 0, borderRadius: '8px', overflow: 'hidden', background: kioskMode ? '#fff' : 'transparent', padding: kioskMode ? '2px' : 0 }}>
              <QRCodeLogo
                value={qrData}
                size={isSmall ? 72 : 96}
                bgColor="transparent"
                fgColor={qrFg}
                ecLevel="H"
                qrStyle="dots"
              />
            </div>
            {/* Name + info */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: isSmall ? '15px' : '20px', fontWeight: 800, lineHeight: 1.1, color: textColor }}>{firstName}</div>
              {lastName && <div style={{ fontSize: isSmall ? '10px' : '12px', fontWeight: 400, color: subTextColor, marginTop: '2px' }}>{lastName}</div>}
              <div style={{ fontSize: isSmall ? '7px' : '9px', color: colors.accent, marginTop: isSmall ? '3px' : '5px', textTransform: 'uppercase', letterSpacing: '0.8px', fontWeight: 600 }}>{title}</div>
              {person.department && <div style={{ fontSize: '8px', color: kioskMode ? '#999' : '#888', marginTop: '1px' }}>{person.department}</div>}
              {type === 'child' && (person.parents || []).length > 0 && (person.parents || []).slice(0, 2).map((p, i) => (
                <div key={i} style={{ fontSize: '7px', color: kioskMode ? '#666' : '#aaa', marginTop: i === 0 ? '3px' : '0px' }}>{p.name}{p.phone ? ` (${p.phone})` : ''}</div>
              ))}
              {type === 'child' && person.location_name && <div style={{ fontSize: '7px', color: kioskMode ? '#777' : '#999', marginTop: '2px' }}>{person.location_name}{person.campus_phone ? ` | ${person.campus_phone}` : ''}</div>}
            </div>
            {/* Large photo — the primary visual ID check for security personnel */}
            <div style={{
              flexShrink: 0,
              width: isSmall ? '78px' : '110px',
              height: isSmall ? '78px' : '110px',
              borderRadius: '10px',
              overflow: 'hidden',
              background: '#fff',
              border: `2px solid ${colors.accent}`,
              boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <img
                src={person.photo_url || generateInitialsImage(person.name, colors.accent, kioskMode ? '#fff' : '#1a1a2e', 220)}
                alt={person.name || 'photo'}
                crossOrigin="anonymous"
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                onError={(e) => { e.currentTarget.src = generateInitialsImage(person.name, colors.accent, kioskMode ? '#fff' : '#1a1a2e', 220); }}
              />
            </div>
          </div>

          {/* Footer */}
          <div style={{
            background: footerBg, padding: isSmall ? '3px 10px' : '4px 14px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            fontSize: isSmall ? '7px' : '8px', color: footerColor,
          }}>
            <span>ID: {badgeId}</span>
            <span style={{ fontWeight: 600 }}>www.5812-Global.org</span>
            <span>58:12 GLOBAL - {new Date().getFullYear()}</span>
          </div>
        </div>
      </div>

      {showActions && (
        <div className="flex justify-center gap-2 flex-wrap">
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={printBadge} data-testid="print-badge">
            <Printer size={12} /> Print
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={downloadBadge} disabled={downloading} data-testid="download-badge">
            <Download size={12} /> {downloading ? 'Saving...' : 'Download'}
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={addToWallet} data-testid="wallet-badge">
            <Smartphone size={12} /> Wallet
          </Button>
          {canWriteNfc && (isStaffType || type === 'child') && (
            <Button size="sm" variant="outline" className="gap-1.5 text-xs text-blue-600 border-blue-200 hover:bg-blue-50" onClick={writeToNfc} disabled={nfcWriting} data-testid="write-nfc-badge">
              <Wifi size={12} /> {nfcWriting ? 'Writing...' : 'Write NFC'}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export function BadgePreview({ person }) {
  return <UnifiedBadge person={person} size="small" showActions={false} />;
}
