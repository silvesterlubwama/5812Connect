import React, { useEffect, useState, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { locationsApi, storeSettingsApi } from '../services/api';
import { QRCode as QRCodeLogo } from 'react-qrcode-logo';
import { Copy, ExternalLink, Search, MapPin, Store } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { Navigate } from 'react-router-dom';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';

/**
 * PosKioskSetupPage — admin-only page that lists every marketplace-enabled location
 * and gives a "Generate kiosk link + QR" for each one. Tap the QR with a tablet's camera
 * and the kiosk auto-binds to that store.
 */
export default function PosKioskSetupPage() {
  const { user } = useAuth();
  const isAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director'].includes(user?.role);

  const [locations, setLocations] = useState([]);
  const [storeNames, setStoreNames] = useState({});
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeQr, setActiveQr] = useState(null);
  const qrCardRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    locationsApi.list()
      .then(async (res) => {
        const eligible = (res.data || []).filter(l => l.marketplace_enabled !== false);
        setLocations(eligible);
        // Load custom store_names for each location
        const settings = await Promise.all(eligible.map(l => storeSettingsApi.get(l.id).catch(() => ({ data: {} }))));
        const names = {};
        eligible.forEach((l, i) => {
          const s = settings[i]?.data;
          if (s?.store_name) names[l.id] = s.store_name;
        });
        setStoreNames(names);
      })
      .catch(() => toast.error('Failed to load locations'))
      .finally(() => setLoading(false));
  }, []);

  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  const filtered = locations.filter(l => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (l.name || '').toLowerCase().includes(s)
      || (l.country || '').toLowerCase().includes(s)
      || (l.code || '').toLowerCase().includes(s)
      || (storeNames[l.id] || '').toLowerCase().includes(s);
  });

  const buildUrl = (locId) => `${window.location.origin}/pos/${encodeURIComponent(locId)}`;

  const copyLink = (locId) => {
    const url = buildUrl(locId);
    navigator.clipboard.writeText(url).then(() => toast.success('Link copied to clipboard'));
  };

  const downloadQr = (locId, locName) => {
    const canvas = qrCardRef.current?.querySelector('canvas');
    if (!canvas) { toast.error('QR not ready'); return; }
    const link = document.createElement('a');
    link.download = `pos-kiosk-${locName.replace(/[^\w]/g, '_')}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

  return (
    <div className="container mx-auto px-4 py-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Store size={22} /> POS Kiosk Setup</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Each marketplace-enabled location gets a unique kiosk URL. Open the URL on a POS tablet → it auto-binds to that store. Use the QR to set up tablets quickly.
        </p>
      </div>

      <div className="relative max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search by name, country, or store..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
          data-testid="pos-setup-search"
        />
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map(i => <div key={i} className="h-44 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="rounded-xl border-dashed">
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            <Store size={28} className="mx-auto mb-2 opacity-40" />
            No marketplace-enabled locations found. Enable marketplace in <span className="font-medium">Admin → Campuses</span> for any location to appear here.
          </CardContent>
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map(loc => {
            const url = buildUrl(loc.id);
            const displayName = storeNames[loc.id] || loc.name;
            return (
              <Card key={loc.id} className="rounded-xl hover:shadow-md transition-shadow" data-testid={`pos-setup-card-${loc.id}`}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <MapPin size={14} className="text-primary" />
                    <span className="truncate">{displayName}</span>
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {loc.type === 'sub-location' ? 'Sub-location' : 'Campus'}
                    {loc.country ? ` · ${loc.country}` : ''}
                    {loc.code ? ` · ${loc.code}` : ''}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="bg-muted/30 rounded-md p-2 flex items-center gap-1.5">
                    <code className="text-[10px] font-mono truncate flex-1" title={url}>{url}</code>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => copyLink(loc.id)} title="Copy link" data-testid={`copy-link-${loc.id}`}>
                      <Copy size={11} />
                    </Button>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => window.open(url, '_blank')} title="Open kiosk" data-testid={`open-kiosk-${loc.id}`}>
                      <ExternalLink size={11} />
                    </Button>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1 h-8 text-xs" onClick={() => setActiveQr(loc)} data-testid={`qr-${loc.id}`}>
                      Show QR
                    </Button>
                    <Badge variant="outline" className="text-[10px]">
                      {loc.id}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* QR overlay */}
      {activeQr && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setActiveQr(null)}>
          <Card className="max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <CardHeader>
              <CardTitle className="text-center">{storeNames[activeQr.id] || activeQr.name}</CardTitle>
              <CardDescription className="text-center text-xs">Scan to bind a tablet to this store</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 flex flex-col items-center" ref={qrCardRef}>
              <div className="bg-white p-3 rounded-lg border">
                <QRCodeLogo
                  value={buildUrl(activeQr.id)}
                  size={260}
                  logoImage={LOGO_URL}
                  logoWidth={48}
                  ecLevel="M"
                  quietZone={6}
                />
              </div>
              <code className="text-[10px] font-mono text-muted-foreground text-center break-all">{buildUrl(activeQr.id)}</code>
              <div className="flex gap-2 w-full pt-2">
                <Button variant="outline" className="flex-1" onClick={() => copyLink(activeQr.id)}>
                  <Copy size={14} className="mr-1.5" /> Copy link
                </Button>
                <Button className="flex-1" onClick={() => downloadQr(activeQr.id, storeNames[activeQr.id] || activeQr.name)} data-testid="download-qr-btn">
                  Download QR
                </Button>
              </div>
              <Button variant="ghost" className="w-full" onClick={() => setActiveQr(null)}>Close</Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
