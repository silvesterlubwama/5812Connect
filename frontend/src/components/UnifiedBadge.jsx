import React, { useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Download, Printer, Smartphone, Wifi } from 'lucide-react';
import { Button } from './ui/button';
import DOMPurify from 'dompurify';
import { toast } from 'sonner';
import { getCountryOutline } from './countryOutlines';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';

const BADGE_COLORS = {
  staff: { bg: '#1a1a2e', accent: '#fbbf24', label: 'STAFF' },
  volunteer: { bg: '#1a1a2e', accent: '#22c55e', label: 'VOLUNTEER' },
  director: { bg: '#1a1a2e', accent: '#8b5cf6', label: 'DIRECTOR' },
  guest: { bg: '#334155', accent: '#60a5fa', label: 'GUEST' },
  visitor: { bg: '#334155', accent: '#60a5fa', label: 'VISITOR' },
  child: { bg: '#0f766e', accent: '#5eead4', label: 'CHILD' },
  parent: { bg: '#1e3a5f', accent: '#93c5fd', label: 'PARENT' },
  member: { bg: '#1a1a2e', accent: '#e2e8f0', label: 'MEMBER' },
};

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
    doc.head.innerHTML = DOMPurify.sanitize('<title>Badge</title><style>*{margin:0;padding:0;box-sizing:border-box}body{display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff;font-family:Arial,sans-serif}@media print{body{min-height:auto}}</style>', { FORCE_BODY: true });
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
      toast.error('NFC not supported on this device/browser. Use Chrome on Android with NFC enabled.');
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

          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: isSmall ? '6px 10px' : '8px 14px',
            borderBottom: headerBorder,
            background: headerBg,
          }}>
            <img src={LOGO_URL} alt="58:12" style={{ height: isSmall ? '14px' : '18px', filter: logoFilter }} crossOrigin="anonymous" />
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              {(isStaffType || type === 'child') && <NfcSymbol size={isSmall ? 10 : 13} color={colors.accent} />}
              <span style={{ color: colors.accent, fontSize: isSmall ? '8px' : '10px', fontWeight: 700, letterSpacing: '1.5px', textTransform: 'uppercase' }}>{colors.label}</span>
            </div>
          </div>

          {/* Body */}
          <div style={{ flex: 1, display: 'flex', padding: isSmall ? '8px 10px' : '12px 14px', gap: '10px', position: 'relative', zIndex: 1 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: isSmall ? '18px' : '26px', fontWeight: 800, lineHeight: 1.1, color: textColor }}>{firstName}</div>
              {lastName && <div style={{ fontSize: isSmall ? '11px' : '14px', fontWeight: 400, color: subTextColor, marginTop: '2px' }}>{lastName}</div>}
              <div style={{ fontSize: isSmall ? '8px' : '10px', color: colors.accent, marginTop: isSmall ? '4px' : '8px', textTransform: 'uppercase', letterSpacing: '0.8px', fontWeight: 600 }}>{title}</div>
              {person.department && <div style={{ fontSize: '9px', color: kioskMode ? '#999' : '#888', marginTop: '2px' }}>{person.department}</div>}
              {/* Parent info for child badges */}
              {type === 'child' && (person.parents || []).length > 0 && (person.parents || []).slice(0, 2).map((p, i) => (
                <div key={i} style={{ fontSize: '8px', color: kioskMode ? '#666' : '#aaa', marginTop: i === 0 ? '4px' : '1px' }}>{p.name}{p.phone ? ` (${p.phone})` : ''}</div>
              ))}
              {/* Campus info for child badges */}
              {type === 'child' && person.location_name && <div style={{ fontSize: '8px', color: kioskMode ? '#777' : '#999', marginTop: '2px' }}>{person.location_name}{person.campus_phone ? ` | ${person.campus_phone}` : ''}</div>}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <QRCodeSVG value={qrData} size={isSmall ? 50 : 72} bgColor="transparent" fgColor={qrFg} level="M" />
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
