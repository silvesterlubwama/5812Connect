import React, { useRef, useState } from 'react';
import { Printer, Bluetooth, Monitor } from 'lucide-react';
import { Button } from '../ui/button';
import { toast } from 'sonner';
import DOMPurify from 'dompurify';

export function BadgePrintView({ user, onClose }) {
  const badgeRef = useRef(null);
  const [btStatus, setBtStatus] = useState('idle');
  const [btDevice, setBtDevice] = useState(null);
  const [showZpl, setShowZpl] = useState(false);

  const initials = user.name ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() : 'XX';
  const memberId = user.id?.slice(-8).toUpperCase() || 'N/A';

  const printBadge = () => {
    const printContents = badgeRef.current?.innerHTML;
    const win = window.open('', '_blank', 'width=400,height=300');
    if (!win) return;
    const doc = win.document;
    doc.open();
    doc.write('<!DOCTYPE html>');
    doc.close();
    doc.head.innerHTML = DOMPurify.sanitize(`<title>Badge - ${user.name}</title><style>* { margin: 0; padding: 0; box-sizing: border-box; } body { font-family: Arial, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; background: #fff; } @media print { body { height: auto; } }</style>`, { FORCE_BODY: true });
    const container = doc.createElement('div');
    container.innerHTML = DOMPurify.sanitize(printContents);
    doc.body.appendChild(container);
    setTimeout(() => { win.focus(); win.print(); win.close(); }, 300);
  };

  const generateZpl = () => {
    const nameLines = (user.name || '').split(' ');
    const firstName = nameLines[0] || '';
    const lastName = nameLines.slice(1).join(' ') || '';
    return `^XA
^FO20,20^A0N,28,28^FD58:12 Global Connect^FS
^FO20,55^A0N,18,18^FDCENTRAL SYSTEM^FS
^FO20,90^A0N,36,36^FD${firstName}^FS
^FO20,130^A0N,36,36^FD${lastName}^FS
^FO20,175^A0N,22,22^FD${(user.role || '').toUpperCase()}^FS
^FO20,205^A0N,18,18^FDID: ${memberId}^FS
^FO400,80^BQN,2,4^FDQA,${user.id || 'N/A'}^FS
^FO20,230^GB570,2,2^FS
^FO20,238^A0N,16,16^FD58:12 Global - ${new Date().getFullYear()}^FS
^XZ`;
  };

  const connectBluetooth = async () => {
    if (!navigator.bluetooth) {
      toast.error('Web Bluetooth is not supported in this browser. Use Chrome or Edge on desktop.');
      return;
    }
    setBtStatus('connecting');
    try {
      const device = await navigator.bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices: ['000018f0-0000-1000-8000-00805f9b34fb', '49535343-fe7d-4ae5-8fa9-9fafd205e455', '6e400001-b5a3-f393-e0a9-e50e24dcca9e'],
      });
      setBtDevice(device);
      setBtStatus('connected');
      toast.success(`Connected: ${device.name || 'Bluetooth Printer'}.`);
    } catch (err) {
      if (err.name !== 'NotFoundError') {
        setBtStatus('error');
        toast.error(`Bluetooth error: ${err.message}`);
      } else {
        setBtStatus('idle');
      }
    }
  };

  const zpl = generateZpl();

  return (
    <div className="space-y-4">
      <div ref={badgeRef}>
        <div style={{ width: '324px', height: '204px', border: '2px solid #1a1a2e', borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#fff', boxShadow: '0 2px 8px rgba(0,0,0,0.15)', margin: '0 auto' }}>
          <div style={{ background: '#1a1a2e', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global"
              style={{ height: '18px', filter: 'brightness(0) invert(1)' }} />
            <span style={{ color: '#fbbf24', fontSize: '8px', fontWeight: 700, letterSpacing: '1px', marginLeft: 'auto' }}>STAFF</span>
          </div>
          <div style={{ flex: 1, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
              <div style={{ width: '46px', height: '46px', borderRadius: '50%', background: '#e8e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px', fontWeight: 700, color: '#1a1a2e', border: '2px solid #1a1a2e' }}>{initials}</div>
              <svg id="qr-staff" style={{ width: '48px', height: '48px' }} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: '#1a1a2e', lineHeight: 1.2 }}>{user.name}</div>
              <div style={{ fontSize: '10px', color: '#555', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.8px' }}>{user.role}</div>
              {user.department && <div style={{ fontSize: '9px', color: '#888', marginTop: '2px' }}>{user.department}</div>}
              <div style={{ fontSize: '9px', color: '#aaa', marginTop: '4px' }}>ID: {memberId}</div>
            </div>
          </div>
          <div style={{ background: '#f0f0f0', padding: '4px 12px', textAlign: 'center', fontSize: '7px', color: '#777', borderTop: '1px solid #ddd' }}>
            58:12 Global Connect - {user.location_name || 'Headquarters'} - {new Date().getFullYear()}
          </div>
        </div>
      </div>
      <p className="text-xs text-muted-foreground text-center">Badge preview (3.375" x 2.125" - CR80 card size)</p>
      <div className="grid grid-cols-3 gap-2">
        <Button className="gap-1.5 text-xs" onClick={printBadge} data-testid="print-badge-btn">
          <Printer size={13} /> Browser Print
        </Button>
        <Button variant="outline" className="gap-1.5 text-xs" onClick={connectBluetooth} disabled={btStatus === 'connecting'}>
          <Bluetooth size={13} className={btStatus === 'connected' ? 'text-blue-500' : ''} />
          {btStatus === 'connecting' ? 'Connecting...' : btStatus === 'connected' ? `${btDevice?.name?.slice(0,10) || 'Connected'}` : 'Bluetooth'}
        </Button>
        <Button variant="outline" className="gap-1.5 text-xs" onClick={() => setShowZpl(!showZpl)}>
          <Monitor size={13} /> ZPL Code
        </Button>
      </div>
      {showZpl && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium">ZPL for Zebra Printers</p>
            <Button size="sm" variant="ghost" className="h-6 text-xs gap-1" onClick={() => { navigator.clipboard.writeText(zpl); toast.success('ZPL copied to clipboard'); }}>Copy</Button>
          </div>
          <pre className="text-[10px] bg-muted p-3 rounded-lg overflow-x-auto text-muted-foreground font-mono leading-relaxed">{zpl}</pre>
          <p className="text-xs text-muted-foreground">Send this ZPL code to your networked Zebra printer.</p>
        </div>
      )}
      <Button variant="ghost" className="w-full text-sm" onClick={onClose}>Close</Button>
    </div>
  );
}
