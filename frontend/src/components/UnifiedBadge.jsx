import React, { useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Download, Printer, Smartphone } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import DOMPurify from 'dompurify';
import { toast } from 'sonner';

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

export function UnifiedBadge({ person, size = 'normal', showActions = true }) {
  const badgeRef = useRef(null);
  const [downloading, setDownloading] = useState(false);
  const type = getBadgeType(person);
  const colors = BADGE_COLORS[type] || BADGE_COLORS.member;
  const firstName = (person.name || '').split(' ')[0] || '';
  const lastName = (person.name || '').split(' ').slice(1).join(' ') || '';
  const title = person.title || person.role || type;
  const qrData = person.id || person.name || '';
  const badgeId = (person.id || '').slice(-8).toUpperCase();

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
      // Use canvas to convert badge to PNG
      const canvas = document.createElement('canvas');
      const scale = 3;
      canvas.width = 340 * scale;
      canvas.height = 216 * scale;
      const ctx = canvas.getContext('2d');
      ctx.scale(scale, scale);
      // Draw background
      ctx.fillStyle = colors.bg;
      ctx.roundRect(0, 0, 340, 216, 12);
      ctx.fill();
      // Draw header
      ctx.fillStyle = colors.accent;
      ctx.font = 'bold 10px Arial';
      ctx.fillText(colors.label, 16, 24);
      // Draw name
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 28px Arial';
      ctx.fillText(firstName, 16, 100);
      ctx.font = '16px Arial';
      ctx.fillText(lastName, 16, 122);
      ctx.font = '12px Arial';
      ctx.fillStyle = colors.accent;
      ctx.fillText(title.toUpperCase(), 16, 145);
      ctx.fillStyle = '#999';
      ctx.font = '10px Arial';
      ctx.fillText(`ID: ${badgeId}`, 16, 195);
      ctx.fillText('58:12 Global Connect', 16, 208);
      // Download
      canvas.toBlob(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `badge-${firstName.toLowerCase()}-${type}.png`;
        a.click();
        URL.revokeObjectURL(url);
        toast.success('Badge downloaded!');
      }, 'image/png');
    } catch (e) { toast.error('Download failed'); }
    finally { setDownloading(false); }
  };

  const addToWallet = () => {
    // Generate a .pkpass-like deep link for Apple/Google Wallet
    // For Apple Wallet: would need a server-side .pkpass generator
    // For now: download as image that can be added manually
    toast.info('Download the badge image, then add to your Wallet app manually.');
    downloadBadge();
  };

  const isSmall = size === 'small';

  return (
    <div className="space-y-3">
      {/* Badge Visual */}
      <div ref={badgeRef}>
        <div style={{
          width: isSmall ? '240px' : '340px', height: isSmall ? '152px' : '216px',
          borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column',
          background: colors.bg, color: '#fff', fontFamily: 'Arial, sans-serif',
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)', margin: '0 auto',
        }}>
          {/* Header with logo + badge type */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: isSmall ? '6px 10px' : '8px 14px', borderBottom: `2px solid ${colors.accent}` }}>
            <img src={LOGO_URL} alt="58:12" style={{ height: isSmall ? '14px' : '18px', filter: 'brightness(0) invert(1)' }} />
            <span style={{ color: colors.accent, fontSize: isSmall ? '8px' : '10px', fontWeight: 700, letterSpacing: '1.5px', textTransform: 'uppercase' }}>{colors.label}</span>
          </div>
          {/* Body */}
          <div style={{ flex: 1, display: 'flex', padding: isSmall ? '8px 10px' : '12px 14px', gap: '10px' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: isSmall ? '18px' : '26px', fontWeight: 800, lineHeight: 1.1, color: '#fff' }}>{firstName}</div>
              {lastName && <div style={{ fontSize: isSmall ? '11px' : '14px', fontWeight: 400, color: '#ccc', marginTop: '2px' }}>{lastName}</div>}
              <div style={{ fontSize: isSmall ? '8px' : '10px', color: colors.accent, marginTop: isSmall ? '4px' : '8px', textTransform: 'uppercase', letterSpacing: '0.8px', fontWeight: 600 }}>{title}</div>
              {person.department && <div style={{ fontSize: '9px', color: '#888', marginTop: '2px' }}>{person.department}</div>}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <QRCodeSVG value={qrData} size={isSmall ? 50 : 72} bgColor="transparent" fgColor="#ffffff" level="M" />
            </div>
          </div>
          {/* Footer */}
          <div style={{ background: 'rgba(255,255,255,0.05)', padding: isSmall ? '3px 10px' : '4px 14px', display: 'flex', justifyContent: 'space-between', fontSize: isSmall ? '7px' : '8px', color: '#666' }}>
            <span>ID: {badgeId}</span>
            <span>58:12 Global Connect - {new Date().getFullYear()}</span>
          </div>
        </div>
      </div>

      {/* Actions */}
      {showActions && (
        <div className="flex justify-center gap-2">
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={printBadge} data-testid="print-badge">
            <Printer size={12} /> Print
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={downloadBadge} disabled={downloading} data-testid="download-badge">
            <Download size={12} /> {downloading ? 'Saving...' : 'Download'}
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={addToWallet} data-testid="wallet-badge">
            <Smartphone size={12} /> Add to Wallet
          </Button>
        </div>
      )}
    </div>
  );
}

export function BadgePreview({ person }) {
  return <UnifiedBadge person={person} size="small" showActions={false} />;
}
