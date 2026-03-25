import React, { useRef } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Button } from './ui/button';
import { Printer } from 'lucide-react';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';
const ORG = '58:12 Global Connect';

function printElement(ref, title) {
  const html = ref.current?.innerHTML;
  if (!html) return;
  const win = window.open('', '_blank', 'width=500,height=400');
  win.document.write(`<html><head><title>${title}</title><style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff}
    @media print{body{min-height:auto}}
  </style></head><body>${html}</body></html>`);
  win.document.close();
  setTimeout(() => { win.focus(); win.print(); win.close(); }, 300);
}

export function StaffBadge({ user, onPrint }) {
  const ref = useRef(null);
  const initials = (user.name || '').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  const memberId = user.id?.slice(-8).toUpperCase() || 'N/A';

  return (
    <div className="space-y-3">
      <div ref={ref}>
        <div style={{ width: '324px', height: '204px', border: '2px solid #1a1a2e', borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#fff', margin: '0 auto' }}>
          <div style={{ background: '#1a1a2e', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <img src={LOGO_URL} alt={ORG} style={{ height: '18px', filter: 'brightness(0) invert(1)' }} />
            <span style={{ color: '#fbbf24', fontSize: '8px', fontWeight: 700, letterSpacing: '1px', marginLeft: 'auto' }}>STAFF</span>
          </div>
          <div style={{ flex: 1, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
              <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: '#e8e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px', fontWeight: 700, color: '#1a1a2e', border: '2px solid #1a1a2e' }}>{initials}</div>
              <QRCodeSVG value={user.id || 'N/A'} size={48} level="L" />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: '#1a1a2e' }}>{user.name}</div>
              <div style={{ fontSize: '10px', color: '#555', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.8px' }}>{user.role}</div>
              {user.department && <div style={{ fontSize: '9px', color: '#888', marginTop: '1px' }}>{user.department}</div>}
              <div style={{ fontSize: '9px', color: '#aaa', marginTop: '4px' }}>ID: {memberId}</div>
            </div>
          </div>
          <div style={{ background: '#f0f0f0', padding: '4px 12px', textAlign: 'center', fontSize: '7px', color: '#777', borderTop: '1px solid #ddd' }}>
            {ORG} · {new Date().getFullYear()}
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-center">
        <Button size="sm" className="gap-1.5 text-xs" onClick={() => printElement(ref, `Staff Badge - ${user.name}`)} data-testid="print-staff-badge"><Printer size={12} /> Print Badge</Button>
      </div>
    </div>
  );
}

export function ParentBadge({ parent, children: childList }) {
  const ref = useRef(null);
  const phone4 = (parent.phone || '').slice(-4);

  return (
    <div className="space-y-3">
      <div ref={ref}>
        <div style={{ width: '324px', height: '204px', border: '2px solid #1a1a2e', borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#fff', margin: '0 auto' }}>
          <div style={{ background: '#1a1a2e', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <img src={LOGO_URL} alt={ORG} style={{ height: '18px', filter: 'brightness(0) invert(1)' }} />
            <span style={{ color: '#34d399', fontSize: '8px', fontWeight: 700, letterSpacing: '1px', marginLeft: 'auto' }}>PARENT</span>
          </div>
          <div style={{ flex: 1, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <QRCodeSVG value={parent.id || parent.phone || 'N/A'} size={72} level="L" />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: '#1a1a2e' }}>{parent.name}</div>
              {parent.phone && <div style={{ fontSize: '10px', color: '#555', marginTop: '2px' }}>{parent.phone}</div>}
              <div style={{ fontSize: '9px', color: '#888', marginTop: '4px' }}>
                Children: {(childList || []).map(c => c.name?.split(' ')[0]).join(', ') || 'None'}
              </div>
              <div style={{ fontSize: '8px', color: '#aaa', marginTop: '3px' }}>Scan QR to check in children</div>
            </div>
          </div>
          <div style={{ background: '#f0f0f0', padding: '4px 12px', textAlign: 'center', fontSize: '7px', color: '#777', borderTop: '1px solid #ddd' }}>
            {ORG} · {new Date().getFullYear()}
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-center">
        <Button size="sm" className="gap-1.5 text-xs" onClick={() => printElement(ref, `Parent Badge - ${parent.name}`)} data-testid="print-parent-badge"><Printer size={12} /> Print Badge</Button>
      </div>
    </div>
  );
}

export function ChildTag({ child, parentPhone, eventName }) {
  const ref = useRef(null);
  const firstName = (child.name || '').split(' ')[0];
  const phone4 = (parentPhone || '').slice(-4);

  return (
    <div className="space-y-3">
      <div ref={ref}>
        <div style={{ width: '280px', height: '160px', border: '2px solid #1a1a2e', borderRadius: '10px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#fff', margin: '0 auto' }}>
          <div style={{ background: '#1a1a2e', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <img src={LOGO_URL} alt={ORG} style={{ height: '14px', filter: 'brightness(0) invert(1)' }} />
            <span style={{ color: '#a78bfa', fontSize: '7px', fontWeight: 700, letterSpacing: '1px', marginLeft: 'auto' }}>CHILD TAG</span>
          </div>
          <div style={{ flex: 1, padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <QRCodeSVG value={child.id || 'N/A'} size={56} level="L" />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '18px', fontWeight: 800, color: '#1a1a2e', lineHeight: 1.1 }}>{firstName}</div>
              {child.class_group && <div style={{ fontSize: '11px', color: '#555', marginTop: '2px', fontWeight: 600 }}>{child.class_group}</div>}
              {eventName && <div style={{ fontSize: '9px', color: '#6366f1', marginTop: '1px' }}>{eventName}</div>}
              {phone4 && <div style={{ fontSize: '9px', color: '#888', marginTop: '3px' }}>Parent: ****{phone4}</div>}
            </div>
          </div>
          <div style={{ background: '#f0f0f0', padding: '3px 10px', textAlign: 'center', fontSize: '7px', color: '#777', borderTop: '1px solid #ddd' }}>
            {ORG} · {new Date().toLocaleDateString()}
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-center">
        <Button size="sm" className="gap-1.5 text-xs" onClick={() => printElement(ref, `Child Tag - ${child.name}`)} data-testid="print-child-tag"><Printer size={12} /> Print Tag</Button>
      </div>
    </div>
  );
}
