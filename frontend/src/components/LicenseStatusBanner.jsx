/**
 * LicenseStatusBanner — shown globally when this install is blocked / expired.
 *
 * Reads /api/license/self. If the persisted license_status is 'blocked' or
 * 'expired', renders a dismissible banner above the app shell so admins notice
 * + take action. NEVER blocks usage — partner orgs are not paying customers.
 */
import React, { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import api from '../services/api';

export default function LicenseStatusBanner() {
  const [self, setSelf] = useState(null);
  const [dismissed, setDismissed] = useState(() => {
    try { return sessionStorage.getItem('5812_license_banner_dismissed') === '1'; } catch { return false; }
  });

  useEffect(() => {
    let cancel = false;
    api.get('/license/self').then(r => { if (!cancel) setSelf(r.data); }).catch(() => {});
    return () => { cancel = true; };
  }, []);

  const status = self?.license_status;
  const shouldShow = !dismissed && self?.configured && (status === 'blocked' || status === 'expired' || status === 'invalid');
  if (!shouldShow) return null;

  const messages = {
    blocked: { tone: 'rose', title: 'License blocked', body: self?.license_message || 'This deployment\'s license has been revoked. Please contact HQ.' },
    expired: { tone: 'amber', title: 'License expired', body: `Expired ${self?.license_expires_at ? `on ${String(self.license_expires_at).slice(0, 10)}` : ''}. The app keeps working — please renew with HQ.` },
    invalid: { tone: 'rose', title: 'License key not recognised', body: 'HQ does not recognise this key. Update it in /admin → License & Telemetry.' },
  };
  const m = messages[status];
  const colorMap = {
    rose: 'bg-rose-50 border-rose-200 text-rose-900',
    amber: 'bg-amber-50 border-amber-200 text-amber-900',
  };

  return (
    <div className={`flex items-center gap-2 px-4 py-2 border-b text-xs ${colorMap[m.tone]}`} data-testid="license-status-banner">
      <AlertTriangle size={14} className="shrink-0" />
      <p className="flex-1"><span className="font-semibold">{m.title}.</span> {m.body}</p>
      <button onClick={() => { setDismissed(true); try { sessionStorage.setItem('5812_license_banner_dismissed', '1'); } catch {/* ignore */} }} className="opacity-60 hover:opacity-100">
        <X size={14} />
      </button>
    </div>
  );
}
