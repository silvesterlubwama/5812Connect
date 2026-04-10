import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Phone, Video, Settings, ExternalLink, Plus, Trash2, Edit2, Save, Globe, RefreshCw, Users, PhoneCall, AlertCircle, X, Monitor, MessageSquare, Voicemail, Download } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { waveApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function WavePage() {
  const { user } = useAuth();
  const [waveConfig, setWaveConfig] = useState(null);
  const [servers, setServers] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdmin, setShowAdmin] = useState(false);
  const [serverForm, setServerForm] = useState({ name: '', url: '', campus_id: '', campus_name: '', is_default: false });
  const [editServer, setEditServer] = useState(null);
  const [waveWindow, setWaveWindow] = useState(null);
  const [waveConnected, setWaveConnected] = useState(false);
  const isAdmin = ['admin', 'system_admin'].includes(user?.role);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [configRes, serversRes, locsRes] = await Promise.all([
          waveApi.getMyConfig(),
          waveApi.listServers().catch(() => ({ data: [] })),
          locationsApi.list().catch(() => ({ data: [] })),
        ]);
        setWaveConfig(configRes.data);
        setServers(serversRes.data || []);
        setLocations(locsRes.data || []);
      } catch (e) { console.warn(e.message || e); }
      finally { setLoading(false); }
    };
    load();
  }, []);

  // Check if Wave popup is still open
  useEffect(() => {
    const check = setInterval(() => {
      if (waveWindow && waveWindow.closed) {
        setWaveWindow(null);
        setWaveConnected(false);
      }
    }, 1000);
    return () => clearInterval(check);
  }, [waveWindow]);

  const getWaveUrl = (server) => (server?.url || '').replace(/\/$/, '');

  const openWave = (server) => {
    const url = getWaveUrl(server || waveConfig?.server);
    if (!url) { toast.error('No Wave server configured'); return; }
    // Open in popup window (iframe is blocked by Grandstream's X-Frame-Options)
    const w = window.open(url, 'wave_window', 'width=1200,height=800,menubar=no,toolbar=no,location=no,status=no');
    if (w) {
      setWaveWindow(w);
      setWaveConnected(true);
      toast.success('Wave opened — sign in with your extension');
    } else {
      toast.error('Popup blocked! Allow popups for this site.');
    }
  };

  const focusWave = () => {
    if (waveWindow && !waveWindow.closed) waveWindow.focus();
    else openWave();
  };

  // Server CRUD
  const saveServer = async () => {
    if (!serverForm.name || !serverForm.url) { toast.error('Name and URL required'); return; }
    try {
      const payload = { ...serverForm, url: serverForm.url.replace(/\/$/, '') };
      if (editServer) { await waveApi.updateServer(editServer.id, payload); toast.success('Updated'); }
      else { await waveApi.addServer(payload); toast.success('Server added'); }
      const res = await waveApi.listServers();
      setServers(res.data || []);
      setEditServer(null);
      setServerForm({ name: '', url: '', campus_id: '', campus_name: '', is_default: false });
    } catch { toast.error('Failed'); }
  };
  const deleteServer = async (id) => {
    if (!window.confirm('Remove?')) return;
    try { await waveApi.deleteServer(id); setServers(prev => prev.filter(s => s.id !== id)); toast.success('Deleted'); } catch { toast.error('Failed'); }
  };

  if (loading) return <div className="p-6"><div className="h-64 animate-pulse bg-muted rounded-xl" /></div>;

  const hasServer = !!waveConfig?.server?.url;
  const hasCredentials = !!waveConfig?.extension;

  return (
    <div className="p-6 space-y-6" data-testid="wave-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2"><Phone size={22} className="text-blue-600" /> Wave</h1>
          <p className="text-sm text-muted-foreground">Grandstream CloudUCM — Calls, Video, Chat & Meetings</p>
        </div>
        <div className="flex items-center gap-2">
          {waveConfig?.server && <Badge variant="outline" className="text-xs gap-1.5"><Globe size={10} /> {waveConfig.server.name}</Badge>}
          {hasCredentials && <Badge className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">Ext {waveConfig.extension}</Badge>}
          {waveConnected && <Badge className="text-xs bg-green-100 text-green-700 gap-1"><span className="w-1.5 h-1.5 rounded-full bg-green-500" /> Connected</Badge>}
          {isAdmin && <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8" onClick={() => setShowAdmin(true)}><Settings size={12} /> Servers</Button>}
        </div>
      </div>

      {/* Main Action Area */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Launch Wave Card */}
        <Card className="lg:col-span-2 rounded-xl">
          <CardContent className="p-6">
            <div className="flex items-start gap-4">
              <div className="h-14 w-14 rounded-xl bg-blue-100 dark:bg-blue-900 flex items-center justify-center shrink-0">
                <Phone size={28} className="text-blue-600" />
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-semibold mb-1">{waveConnected ? 'Wave is Running' : 'Launch Wave'}</h2>
                <p className="text-sm text-muted-foreground mb-4">
                  {waveConnected ? 'Wave is open in a separate window. Click below to bring it to focus.' : 'Open Grandstream Wave in a dedicated window for calling, video meetings, and cross-campus chat.'}
                </p>
                {hasServer ? (
                  <div className="flex flex-wrap gap-3">
                    <Button className="gap-2" onClick={() => waveConnected ? focusWave() : openWave()} data-testid="launch-wave-btn">
                      <Phone size={16} /> {waveConnected ? 'Focus Wave Window' : 'Open Wave'}
                    </Button>
                    {!waveConnected && servers.length > 1 && servers.map(s => (
                      <Button key={s.id} variant="outline" className="gap-1.5 text-xs" onClick={() => openWave(s)}>
                        <Globe size={12} /> {s.name}
                      </Button>
                    ))}
                  </div>
                ) : (
                  <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-200">
                    <p className="text-sm text-amber-700 dark:text-amber-300 flex items-center gap-1.5"><AlertCircle size={14} /> No Wave server configured.</p>
                    {isAdmin && <Button size="sm" className="mt-2 gap-1.5" onClick={() => setShowAdmin(true)}><Settings size={12} /> Configure</Button>}
                  </div>
                )}
              </div>
            </div>

            {/* Login info */}
            {hasCredentials && hasServer && (
              <div className="mt-4 p-3 rounded-lg bg-secondary/50 border border-border">
                <p className="text-xs font-medium text-muted-foreground mb-2">Your Wave Login</p>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div><p className="text-xs text-muted-foreground">Server</p><p className="font-mono text-xs truncate">{getWaveUrl(waveConfig.server)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Extension</p><p className="font-semibold">{waveConfig.extension}</p></div>
                  <div><p className="text-xs text-muted-foreground">Password</p><p className="font-mono text-xs">{'*'.repeat(8)}</p></div>
                </div>
              </div>
            )}
            {!hasCredentials && hasServer && (
              <div className="mt-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-200">
                <p className="text-xs text-amber-700"><AlertCircle size={12} className="inline mr-1" /> No Wave extension assigned. Ask your admin to set your extension in Staff Management → Edit Profile → Account → Wave/PBX section.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Info Card */}
        <Card className="rounded-xl">
          <CardContent className="p-6 space-y-4">
            <h3 className="font-semibold text-sm">Wave Features</h3>
            <div className="space-y-3">
              <div className="flex items-center gap-3"><Phone size={14} className="text-green-500 shrink-0" /><div><p className="text-sm font-medium">HD Audio Calls</p><p className="text-xs text-muted-foreground">Internal & external calling</p></div></div>
              <div className="flex items-center gap-3"><Video size={14} className="text-blue-500 shrink-0" /><div><p className="text-sm font-medium">Video Meetings</p><p className="text-xs text-muted-foreground">1-click meetings, screen share</p></div></div>
              <div className="flex items-center gap-3"><MessageSquare size={14} className="text-purple-500 shrink-0" /><div><p className="text-sm font-medium">Cross-Campus Chat</p><p className="text-xs text-muted-foreground">Message across all locations</p></div></div>
              <div className="flex items-center gap-3"><Users size={14} className="text-teal-500 shrink-0" /><div><p className="text-sm font-medium">Enterprise Contacts</p><p className="text-xs text-muted-foreground">Directory with presence status</p></div></div>
              <div className="flex items-center gap-3"><Voicemail size={14} className="text-amber-500 shrink-0" /><div><p className="text-sm font-medium">Voicemail</p><p className="text-xs text-muted-foreground">Listen & manage voicemail</p></div></div>
              <div className="flex items-center gap-3"><Monitor size={14} className="text-slate-500 shrink-0" /><div><p className="text-sm font-medium">Call Controls</p><p className="text-xs text-muted-foreground">Transfer, hold, record, flip</p></div></div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Connected Servers */}
      {servers.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-3">Wave Servers</h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {servers.map(s => (
              <Card key={s.id} className="rounded-xl cursor-pointer hover:shadow-md transition-shadow" onClick={() => openWave(s)} data-testid={`wave-server-${s.id}`}>
                <CardContent className="p-4 flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-blue-100 dark:bg-blue-900 flex items-center justify-center shrink-0"><Globe size={18} className="text-blue-600" /></div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm">{s.name} {s.is_default && <Badge className="text-[10px] ml-1">Default</Badge>}</p>
                    <p className="text-xs text-muted-foreground truncate">{s.url} {s.campus_name ? `· ${s.campus_name}` : ''}</p>
                  </div>
                  <ExternalLink size={14} className="text-muted-foreground shrink-0" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Wave Add-in Integration */}
      <Card className="rounded-xl border-blue-200 dark:border-blue-800">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shrink-0">
              <Monitor size={22} className="text-white" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold mb-1">Wave Desktop Add-in</h3>
              <p className="text-sm text-muted-foreground mb-3">Install the 58:12 Connect add-in in your Wave Desktop app for click-to-dial, meetings, contacts, and CRM access directly from Wave.</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" className="gap-1.5 text-xs" onClick={async () => {
                  try {
                    const JSZip = (await import('jszip')).default;
                    const zip = new JSZip();
                    const folder = zip.folder('5812connect');
                    const files = ['index.html', 'plugin.json', 'wave-add-in-kit.js', 'logo.png'];
                    for (const file of files) {
                      const res = await fetch(`/wave-addin/${file}`);
                      const blob = await res.blob();
                      folder.file(file, blob);
                    }
                    const content = await zip.generateAsync({ type: 'blob' });
                    const url = URL.createObjectURL(content);
                    const a = document.createElement('a'); a.href = url; a.download = '5812connect-wave-addin.zip';
                    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
                    toast.success('Add-in downloaded! See installation steps below.');
                  } catch (e) { toast.error('Download failed: ' + e.message); }
                }} data-testid="download-addin-btn"><Download size={12} /> Download Add-in (.zip)</Button>
                <a href="/wave-addin/index.html" target="_blank" rel="noopener noreferrer">
                  <Button size="sm" variant="outline" className="gap-1.5 text-xs"><ExternalLink size={12} /> Preview</Button>
                </a>
              </div>
              {isAdmin && (
                <div className="mt-3 p-3 rounded-lg bg-secondary/50 text-xs space-y-1">
                  <p className="font-medium">Installation Steps:</p>
                  <p>1. Download Wave Desktop from <a href="https://www.grandstream.com/products/ucm6300-ecosystem/product/wave" target="_blank" className="text-primary underline">grandstream.com</a></p>
                  <p>2. Copy the <code className="bg-muted px-1 rounded">wave-addin</code> folder to:</p>
                  <p className="pl-3">Mac: <code className="bg-muted px-1 rounded text-[10px]">~/Library/Application Support/Wave/extensions/5812connect/</code></p>
                  <p className="pl-3">Win: <code className="bg-muted px-1 rounded text-[10px]">C:\Users\YOU\AppData\Roaming\Wave\extensions\5812connect\</code></p>
                  <p>3. Restart Wave — the add-in appears in the app module</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
      <Dialog open={showAdmin} onOpenChange={setShowAdmin}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Wave Servers</DialogTitle><DialogDescription>Grandstream CloudUCM servers. URL: https://yourserver.a.gdms.cloud</DialogDescription></DialogHeader>
          <div className="space-y-4 mt-2">
            {servers.map(s => (
              <div key={s.id} className="flex items-center gap-3 p-3 rounded-lg border">
                <Globe size={14} className="text-blue-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{s.name} {s.is_default && <Badge className="text-[10px] ml-1">Default</Badge>}</p>
                  <p className="text-xs text-muted-foreground truncate">{s.url}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => { setServerForm({ name: s.name, url: s.url, campus_id: s.campus_id || '', campus_name: s.campus_name || '', is_default: s.is_default || false }); setEditServer(s); }}><Edit2 size={12} /></Button>
                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => deleteServer(s.id)}><Trash2 size={12} /></Button>
              </div>
            ))}
            <div className="p-4 rounded-lg border border-dashed space-y-3">
              <p className="text-sm font-medium">{editServer ? 'Edit' : 'Add'} Server</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={serverForm.name} onChange={e => setServerForm({...serverForm, name: e.target.value})} placeholder="58:12 Uganda" data-testid="wave-server-name" /></div>
                <div className="space-y-1.5"><Label className="text-xs">Campus</Label>
                  <Select value={serverForm.campus_id || '_none'} onValueChange={v => { const loc = locations.find(l => l.id === v); setServerForm({...serverForm, campus_id: v === '_none' ? '' : v, campus_name: loc?.name || ''}); }}>
                    <SelectTrigger><SelectValue placeholder="All" /></SelectTrigger>
                    <SelectContent><SelectItem value="_none">Global</SelectItem>{locations.filter(l => l.type !== 'sub-location').map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Server URL *</Label><Input value={serverForm.url} onChange={e => setServerForm({...serverForm, url: e.target.value})} placeholder="https://5812Uganda.a.gdms.cloud" data-testid="wave-server-url" /></div>
              <div className="flex items-center justify-between p-2 border rounded-lg"><Label className="text-xs">Default</Label><Switch checked={serverForm.is_default} onCheckedChange={v => setServerForm({...serverForm, is_default: v})} /></div>
              <div className="flex gap-3">
                {editServer && <Button variant="ghost" size="sm" onClick={() => { setEditServer(null); setServerForm({ name: '', url: '', campus_id: '', campus_name: '', is_default: false }); }}>Cancel</Button>}
                <Button size="sm" className="gap-1 ml-auto" onClick={saveServer} data-testid="save-wave-server"><Save size={12} /> {editServer ? 'Update' : 'Add'}</Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
