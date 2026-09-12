import React, { useRef, useState, useEffect } from 'react';
import { Download, Printer, Smartphone, Wifi, ZoomIn } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import DOMPurify from 'dompurify';
import { toast } from 'sonner';
import { QRCodeSVG } from 'qrcode.react';

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
  // Contracted security personnel — neutral slate with red accent so they
  // read as clearly distinct from staff at a glance.
  security: { bg: '#1e293b', accent: '#ef4444', label: 'SECURITY' },
};

// Badge type icons (inline SVG) — replace text labels
function BadgeTypeIcon({ type, size = 14, color }) {
  const s = size;
  switch (type) {
    case 'staff': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>;
    case 'director':
      // iter313 — was a crown / coronet (m2 4 3 12h14…) which read as
      // "king" on admin badges. Users found it intimidating for a role
      // that's really "team lead / oversight". Swapped for a friendly
      // 5-point Star (matches lucide's Star) — universal shorthand for
      // "senior / trusted" without the monarchic overtones.
      return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>;
    case 'volunteer': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>;
    case 'child': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 1 0-16 0"/></svg>;
    case 'parent': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>;
    case 'guest': case 'visitor': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 20a6 6 0 0 0-12 0"/><circle cx="12" cy="10" r="4"/><circle cx="12" cy="12" r="10"/></svg>;
    case 'security': return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>;
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
  if (role === 'security contractor' || role === 'security_contractor') return 'security';
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
  // iter311 — fill the whole canvas as a rect (not a circle) so the
  // initials still look right when the image is placed into a portrait
  // photo slot with `object-fit: cover`. The old arc-based fill left
  // transparent corners and turned into a stretched oval inside a
  // taller-than-wide container.
  const initials = (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = bgColor;
  ctx.fillRect(0, 0, size, size);
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
  const [zoomUrl, setZoomUrl] = useState(null);
  const [zooming, setZooming] = useState(false);
  const [nfcWriting, setNfcWriting] = useState(false);
  const type = getBadgeType(person);
  const colors = BADGE_COLORS[type] || BADGE_COLORS.member;
  const isSmall = size === 'small';
  const firstName = (person.name || '').split(' ')[0] || '';
  const lastName = (person.name || '').split(' ').slice(1).join(' ') || '';
  // Business-card-style auto-fit: shrink the first-name font a step for
  // longer names so triple-barrelled / hyphenated names don't get chopped
  // by the ellipsis. Buckets keep the cascade readable rather than fluidly
  // scaling to unreadable extremes.
  const nameLen = firstName.length;
  const firstNameSize = isSmall
    ? (nameLen > 12 ? '11px' : nameLen > 9 ? '13px' : '15px')
    : (nameLen > 14 ? '15px' : nameLen > 11 ? '17px' : '20px');
  const lastNameLen = lastName.length;
  const lastNameSize = isSmall
    ? (lastNameLen > 20 ? '9px' : '11px')
    : (lastNameLen > 22 ? '11px' : '13px');
  const title = person.title || person.role || type;
  const qrData = person.id || person.name || '';
  // Prefer a human-friendly ID (admin-assigned badge_id or social-worker-issued
  // social_id) over the raw internal UUID slice — those are the numbers
  // security personnel actually verify against their register.
  const badgeId = person.badge_id || person.social_id || (person.id || '').slice(-8).toUpperCase();
  const country = person.country || person.location_country || '';
  const countryCode = person.country_code || person.location_country_code || '';
  const isStaffType = STAFF_TYPES.has(type);

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

  // iter311 — preload the (possibly cross-origin) profile photo into a
  // base64 data URL. html2canvas + `window.print()` both need the pixel
  // bytes to be available on the same origin as the render context;
  // without this the photo shows on-screen but comes out blank in the
  // Save-as-PNG / Print outputs. Falls back to the generated initials
  // image if the fetch fails (or is blocked by CORS).
  const [photoDataUrl, setPhotoDataUrl] = useState(null);
  useEffect(() => {
    let cancelled = false;
    // Photos land on different fields depending on where they came from:
    // an upload writes photo_url, Google SSO writes picture.
    const src = person.photo_url || person.picture || person.avatar_url;
    if (!src) { setPhotoDataUrl(null); return; }
    fetch(src, { mode: 'cors', credentials: 'omit' })
      .then(r => r.ok ? r.blob() : Promise.reject(r.status))
      .then(blob => new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = () => rej(fr.error);
        fr.readAsDataURL(blob);
      }))
      .then(url => { if (!cancelled) setPhotoDataUrl(url); })
      .catch(() => { if (!cancelled) setPhotoDataUrl(null); });
    return () => { cancelled = true; };
  }, [person.photo_url, person.picture, person.avatar_url]);
  const photoSrc = photoDataUrl || generateInitialsImage(person.name, colors.accent, '#1a1a2e', 220);

  // Rendering the badge to PNG relies on html-to-image so the QR canvas
  // and the (possibly cross-origin) profile photo are baked into a single
  // raster before we print or download. Previously downloadBadge was a
  // hand-rolled canvas that drew text only — QR + photo were silently
  // dropped, and print's innerHTML copy also lost QR canvas pixels once
  // it hit a new window context.
  const renderBadgePng = async () => {
    const { toPng } = await import('html-to-image');
    const el = badgeRef.current;
    if (!el) throw new Error('badge not mounted');
    return toPng(el, {
      pixelRatio: 3,
      cacheBust: true,
      // Google Fonts CSS is cross-origin — inlining it throws a SecurityError
      // and spams the console. The badge uses Arial fallbacks anyway.
      skipFonts: true,
      // Fetch cross-origin images (photos, company logos) as data URLs
      // otherwise the canvas render leaves them blank.
      fetchRequestInit: { mode: 'cors' },
      style: { transform: 'none' },
    });
  };

  const printBadge = async () => {
    try {
      const dataUrl = await renderBadgePng();
      const win = window.open('', '_blank', 'width=420,height=320');
      if (!win) { toast.error('Popup blocked — enable popups to print'); return; }      const doc = win.document;
      doc.open(); doc.write('<!DOCTYPE html>'); doc.close();
      doc.head.innerHTML = DOMPurify.sanitize(
        '<title>Badge</title><style>*{margin:0;padding:0;box-sizing:border-box}body{display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff;font-family:Arial,sans-serif}img{max-width:100%;height:auto}@media print{body{min-height:auto}@page{margin:0}}</style>',
        { FORCE_BODY: true }
      );
      const img = doc.createElement('img');
      img.src = dataUrl;
      img.onload = () => { win.focus(); win.print(); setTimeout(() => win.close(), 500); };
      doc.body.appendChild(img);
    } catch (e) {
      console.error(e);
      toast.error('Could not print — try Download instead');
    }
  };

  const openZoom = async () => {
    setZooming(true);
    try {
      // Uses the exact same raster the printer gets, blown up 2× — what you
      // check here is literally what comes out of the badge printer.
      setZoomUrl(await renderBadgePng());
    } catch (e) {
      console.error(e);
      toast.error('Could not build the preview');
    } finally { setZooming(false); }
  };

  const downloadBadge = async () => {
    setDownloading(true);
    try {
      const dataUrl = await renderBadgePng();
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = `badge-${firstName.toLowerCase()}-${type}.png`;
      a.click();
      toast.success('Badge downloaded!');
    } catch (e) {
      console.error(e);
      toast.error('Download failed — check console');
    }
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
          width: isSmall ? '240px' : '340px',
          // iter345 — was a hard height with overflow:hidden, which cropped the
          // footer (ID / site / year) on the larger badge. minHeight keeps the
          // card size while letting it grow rather than hide information.
          minHeight: isSmall ? '152px' : '216px',
          borderRadius: '12px', display: 'flex', flexDirection: 'column',
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

          {/* Header — logo(s) | status symbols + badge type icon
              For contracted security personnel we render the client (58:12)
              logo AND the contractor's company logo side-by-side so the
              badge clearly conveys "who this person works for". */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: isSmall ? '6px 10px' : '8px 14px',
            borderBottom: headerBorder,
            background: headerBg,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: isSmall ? '6px' : '8px' }}>
              <img src={LOGO_URL} alt="58:12" style={{ height: isSmall ? '14px' : '18px', filter: logoFilter }} crossOrigin="anonymous" />
              {type === 'security' && person.security_company_logo_url && (
                <>
                  <span style={{ color: subTextColor, fontSize: isSmall ? '10px' : '12px', opacity: 0.5 }}>|</span>
                  <img
                    src={person.security_company_logo_url}
                    alt={person.security_company_name || 'Security'}
                    style={{ height: isSmall ? '14px' : '18px', maxWidth: isSmall ? '52px' : '70px', objectFit: 'contain' }}
                    crossOrigin="anonymous"
                    onError={(e) => { e.currentTarget.style.display = 'none'; }}
                  />
                </>
              )}
              {type === 'security' && !person.security_company_logo_url && person.security_company_name && (
                <>
                  <span style={{ color: subTextColor, fontSize: isSmall ? '10px' : '12px', opacity: 0.5 }}>|</span>
                  <span style={{ color: colors.accent, fontSize: isSmall ? '9px' : '11px', fontWeight: 700, letterSpacing: '0.5px' }}>
                    {person.security_company_name}
                  </span>
                </>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              {(isStaffType || type === 'child') && <NfcSymbol size={isSmall ? 9 : 11} color={colors.accent} />}
              {person.is_medical && <MedicalIcon size={isSmall ? 9 : 11} color="#ef4444" />}
              {person.is_resident && <ResidentIcon size={isSmall ? 9 : 11} color="#3b82f6" />}
              {person.is_sponsored && <SponsorIcon size={isSmall ? 9 : 11} color="#8b5cf6" />}
              <BadgeTypeIcon type={type} size={isSmall ? 11 : 13} color={colors.accent} />
            </div>
          </div>

          {/* Body — Iter 291 layout:
               Two columns. Left column has a FIXED height equal to the photo
               height, so `justify-content: space-between` puts the info block
               top-aligned with the photo top AND the QR bottom-aligned with
               the photo bottom. Any leftover space at the bottom of the badge
               (footer area) is untouched — the QR never dips into it. */}
          <div style={{ flex: 1, display: 'flex', padding: isSmall ? '8px 10px 8px 10px' : '10px 14px 12px 14px', gap: isSmall ? '8px' : '12px', position: 'relative', zIndex: 1, alignItems: 'flex-start' }}>
            {/* Left column — info fills the full fixed height.
                iter308 — the QR moved into the right column and now
                embeds the photo as its centre logo (via react-qrcode-logo).
                That kills the previous "tiny QR + separate photo" split
                where the QR was unreadable and neither survived some
                html2canvas exports cleanly. */}
            <div style={{ flex: 1, minWidth: 0, height: isSmall ? '108px' : '148px', display: 'flex', flexDirection: 'column', justifyContent: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: firstNameSize, fontWeight: 800, lineHeight: 1.1, color: textColor, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{firstName}</div>
                {lastName && <div style={{ fontSize: lastNameSize, fontWeight: 500, color: subTextColor, marginTop: '1px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{lastName}</div>}
                {type === 'security' && person.security_rank ? (
                  <div style={{ fontSize: isSmall ? '9px' : '11px', color: colors.accent, marginTop: isSmall ? '4px' : '6px', textTransform: 'uppercase', letterSpacing: '0.9px', fontWeight: 800, background: `${colors.accent}22`, display: 'inline-block', padding: '2px 7px', borderRadius: '4px' }}>
                    {person.security_rank}
                  </div>
                ) : (
                  <div style={{
                    fontSize: isSmall ? '8px' : '9px',
                    color: colors.accent,
                    marginTop: isSmall ? '3px' : '5px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.6px',
                    fontWeight: 700,
                    lineHeight: 1.25,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                    wordBreak: 'break-word',
                  }}>{title}</div>
                )}
                {type === 'security' && person.security_company_name && (
                  <div style={{ fontSize: isSmall ? '8px' : '10px', color: subTextColor, marginTop: '2px', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {person.security_company_name}
                  </div>
                )}
                {type !== 'security' && person.department && <div style={{ fontSize: isSmall ? '8px' : '9px', color: kioskMode ? '#999' : '#a3a3a3', marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{person.department}</div>}
                {type === 'child' && (person.parents || []).length > 0 && (person.parents || []).slice(0, 2).map((p, i) => (
                  <div key={i} style={{ fontSize: '7px', color: kioskMode ? '#666' : '#aaa', marginTop: i === 0 ? '3px' : '0px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}{p.phone ? ` (${p.phone})` : ''}</div>
                ))}
                {type === 'child' && person.location_name && <div style={{ fontSize: '7px', color: kioskMode ? '#777' : '#999', marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{person.location_name}{person.campus_phone ? ` | ${person.campus_phone}` : ''}</div>}
              </div>
            </div>
            {/* Right column — iter313: [QR | Photo]. Photo right-most,
                QR to its left. Both centered vertically in the column so
                the QR doesn't ride high against the top edge. QR sits
                directly on the badge background (no white card / no
                border / no shadow) with white pixels on the dark badge
                bg — looks like part of the card, not a sticker. */}
            <div style={{
              flexShrink: 0,
              display: 'flex',
              // iter314 — was center; nudged to `flex-end` so the QR (which is
              // shorter than the photo) drops toward the bottom of the column
              // and gives the left-column name more breathing room.
              alignItems: 'flex-end',
              gap: isSmall ? '6px' : '10px',
              height: isSmall ? '108px' : '148px',
            }}>
              <div style={{
                // iter314 — shrunk one step (108 → 92 large / 78 → 68 small) so
                // long first names ("Silvester", "Emmanuel") no longer get
                // ellipsised on the left column.
                width: isSmall ? '68px' : '92px',
                height: isSmall ? '68px' : '92px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                // Small bottom margin so the QR sits flush with the photo's
                // bottom edge rather than the column's absolute bottom.
                marginBottom: isSmall ? '4px' : '6px',
              }}>
                {/* iter345 — SVG (not canvas) QR. A <canvas> QR is silently
                    dropped when the badge is cloned for print / PNG export /
                    wallet, which is why saved badges came out with no code.
                    SVG survives every export path. */}
                <QRCodeSVG
                  value={qrData || 'N/A'}
                  size={isSmall ? 68 : 92}
                  bgColor="#ffffff"
                  fgColor="#000000"
                  level="M"
                  includeMargin={false}
                  style={{ display: 'block', width: isSmall ? '68px' : '92px', height: isSmall ? '68px' : '92px' }}
                />
              </div>
              {/* Photo — right-most, larger, `contain` so faces are
                  never cropped. Accent-tinted background fills any
                  aspect-ratio gap when the source photo isn't the
                  same portrait as the container. */}
              <div style={{
                // iter 341 — photo shrunk another ~2mm (108→100 wide, 148→140 tall
                // large; 76→68 wide, 108→100 tall small) so the QR next to it
                // reads cleanly without visual pressure on the face.
                width: isSmall ? '68px' : '100px',
                height: isSmall ? '100px' : '140px',
                borderRadius: '10px',
                overflow: 'hidden',
                background: `${colors.accent}22`,
                border: `2px solid ${colors.accent}`,
                boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}>
                <img
                  src={photoSrc}
                  alt={person.name || 'photo'}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                  onError={(e) => { e.currentTarget.src = generateInitialsImage(person.name, colors.accent, '#1a1a2e', 220); }}
                />
              </div>
            </div>
          </div>

          {/* Footer */}
          <div style={{
            background: footerBg, padding: isSmall ? '3px 10px' : '4px 14px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            fontSize: isSmall ? '7px' : '8px', color: footerColor,
            marginTop: 'auto', flexShrink: 0, gap: '6px',
            borderBottomLeftRadius: '12px', borderBottomRightRadius: '12px',
          }}>
            <span>ID: {badgeId}</span>
            <span style={{ fontWeight: 600 }}>www.5812-Global.org</span>
            <span>58:12 GLOBAL - {new Date().getFullYear()}</span>
          </div>
        </div>
      </div>

      {showActions && (
        <div className="flex justify-center gap-2 flex-wrap">
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={openZoom} disabled={zooming} data-testid="zoom-badge">
            <ZoomIn size={12} /> {zooming ? 'Building…' : 'Preview 200%'}
          </Button>
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

      {/* 200% print check — inspect the actual raster before wasting badge stock */}
      <BadgeZoomDialog
        url={zoomUrl}
        onClose={() => setZoomUrl(null)}
        onPrint={printBadge}
        width={(isSmall ? 280 : 360) * 2}
      />
    </div>
  );
}

export function BadgePreview({ person }) {
  return <UnifiedBadge person={person} size="small" showActions={false} />;
}

/**
 * 200% print check — shows the exact raster that goes to the printer so
 * staff can spot a soft QR or a cropped photo before burning badge stock.
 */
export function BadgeZoomDialog({ url, onClose, onPrint, width = 720 }) {
  return (
    <Dialog open={!!url} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-[860px]" data-testid="badge-zoom-dialog">
        <DialogHeader>
          <DialogTitle className="text-base">Print preview · 200%</DialogTitle>
        </DialogHeader>
        <div className="overflow-auto max-h-[65vh] rounded-lg bg-[repeating-conic-gradient(#f1f5f9_0%_25%,#ffffff_0%_50%)] bg-[length:16px_16px] p-4">
          {url && (
            <img src={url} alt="Badge at 200%" data-testid="badge-zoom-image"
                 style={{ width: `${width}px`, display: 'block', margin: '0 auto' }} />
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          This is the exact image sent to the printer. Check the QR squares are crisp and the photo isn't cropped before printing.
        </p>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={onClose} data-testid="badge-zoom-close">Close</Button>
          {onPrint && (
            <Button size="sm" onClick={() => { onClose(); onPrint(); }} data-testid="badge-zoom-print">
              <Printer size={12} className="mr-1.5" /> Print it
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
