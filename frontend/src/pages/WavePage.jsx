import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Phone, Video, Settings, ExternalLink, Plus, Trash2, Edit2, Save, Globe, RefreshCw, Users, PhoneCall, X, AlertCircle } from 'lucide-react';
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
  const [waveUrl, setWaveUrl] = useState('');
  const [waveLoaded, setWaveLoaded] = useState(false);
  const [waveStatus, setWaveStatus] = useState('loading'); // loading, ready, login_sent, error
  const [dialNumber, setDialNumber] = useState('');
  const iframeRef = useRef(null);
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
        if (configRes.data?.server?.url) {
          setWaveUrl(configRes.data.server.url + '/wave');
        }
      } catch {}
      finally { setLoading(false); }
    };
    load();
  }, []);

  // Listen for messages from Wave iframe
  useEffect(() => {
    const handler = (event) => {
      // Only accept messages from the Wave server origin
      if (!waveUrl) return;
      try {
        const origin = new URL(waveUrl).origin;
        if (event.origin !== origin) return;
      } catch { return; }
      console.log('[Wave] Message from iframe:', event.data);
      if (event.data?.type === 'wave_ready') setWaveStatus('ready');
      if (event.data?.type === 'wave_call_event') toast.info(`Call: ${event.data.status}`);
      if (event.data?.type === 'wave_logged_in') { setWaveStatus('ready'); toast.success('Wave connected'); }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [waveUrl]);

  // Auto-login when iframe loads
  const handleIframeLoad = useCallback(() => {
    setWaveLoaded(true);
    if (!waveConfig?.auto_login || !waveConfig?.extension || !waveConfig?.wave_password) {
      setWaveStatus('ready');
      return;
    }
    // Attempt auto-login via postMessage
    setTimeout(() => {
      try {
        const origin = new URL(waveUrl).origin;
        iframeRef.current?.contentWindow?.postMessage({
          action: 'login',
          extension: waveConfig.extension,
          password: waveConfig.wave_password,
          server: origin,
        }, origin);
        setWaveStatus('login_sent');
        toast.info(`Logging into Wave as ext ${waveConfig.extension}...`);
      } catch (e) {
        console.warn('[Wave] Auto-login failed:', e);
        setWaveStatus('ready');
      }
    }, 2000); // Wait for Wave to initialize
  }, [waveConfig, waveUrl]);

  // Click-to-dial: send dial command to Wave iframe
  const handleDial = useCallback((number) => {
    if (!number || !iframeRef.current || !waveUrl) {
      toast.error('Wave not connected');
      return;
    }
    try {
      const origin = new URL(waveUrl).origin;
      iframeRef.current.contentWindow.postMessage({
        action: 'dial',
        number: number.trim(),
      }, origin);
      toast.success(`Dialing ${number} via Wave...`);
      setDialNumber('');
    } catch { toast.error('Failed to dial'); }
  }, [waveUrl]);

  const openInNewTab = () => { if (waveUrl) window.open(waveUrl, '_blank'); };
  const switchServer = (url) => { setWaveUrl(url + '/wave'); setWaveLoaded(false); setWaveStatus('loading'); };

  // Server CRUD
  const saveServer = async () => {
    if (!serverForm.name || !serverForm.url) { toast.error('Name and URL required'); return; }
    try {
      const payload = { ...serverForm, url: serverForm.url.replace(/\/wave\/?$/, '').replace(/\/$/, '') };
      if (editServer) { await waveApi.updateServer(editServer.id, payload); toast.success('Updated'); }
      else { await waveApi.addServer(payload); toast.success('Wave server added'); }
      const res = await waveApi.listServers();
      setServers(res.data || []);
      setEditServer(null);
      setServerForm({ name: '', url: '', campus_id: '', campus_name: '', is_default: false });
    } catch { toast.error('Failed'); }
  };
  const deleteServer = async (id) => {
    if (!window.confirm('Remove?')) return;
    try { await waveApi.deleteServer(id); setServers(prev => prev.filter(s => s.id !== id)); toast.success('Deleted'); }
    catch { toast.error('Failed'); }
  };

  if (loading) return <div className="p-6"><div className="h-64 animate-pulse bg-muted rounded-xl" /></div>;

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col" data-testid="wave-page">
      {/* Header */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-2.5 border-b border-border shrink-0 bg-card">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
            <Phone size={16} className="text-blue-600" />
          </div>
          <div>
            <h1 className="text-base font-semibold font-heading">Wave</h1>
            <p className="text-[10px] text-muted-foreground">Calls, Video, Chat & Meetings</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Quick dial */}
          <div className="hidden sm:flex items-center gap-1">
            <Input className="w-32 h-8 text-xs" placeholder="Dial number..." value={dialNumber} onChange={e => setDialNumber(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleDial(dialNumber); }} data-testid="wave-dial-input" />
            <Button size="icon" variant="ghost" className="h-8 w-8 text-green-600" onClick={() => handleDial(dialNumber)} disabled={!dialNumber}><PhoneCall size={14} /></Button>
          </div>

          {waveConfig?.server && <Badge variant="outline" className="text-[10px] gap-1 hidden sm:flex"><Globe size={9} /> {waveConfig.server.name}</Badge>}
          {waveConfig?.extension && <Badge className="text-[10px] bg-blue-100 text-blue-700">Ext {waveConfig.extension}</Badge>}

          {/* Status */}
          {waveStatus === 'login_sent' && <Badge className="text-[10px] bg-amber-100 text-amber-700 animate-pulse">Connecting...</Badge>}
          {waveStatus === 'ready' && waveLoaded && <Badge className="text-[10px] bg-green-100 text-green-700">Ready</Badge>}

          {servers.length > 1 && (
            <Select value={waveConfig?.server?.url || ''} onValueChange={switchServer}>
              <SelectTrigger className="w-[140px] h-7 text-[10px]"><SelectValue placeholder="Server..." /></SelectTrigger>
              <SelectContent>{servers.map(s => <SelectItem key={s.id} value={s.url}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setWaveLoaded(false); setWaveStatus('loading'); const el = iframeRef.current; if (el) { el.src = el.src; } }} title="Reload"><RefreshCw size={13} /></Button>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={openInNewTab} title="Open in new tab"><ExternalLink size={13} /></Button>
          {isAdmin && <Button size="sm" variant="outline" className="gap-1 text-[10px] h-7" onClick={() => setShowAdmin(true)}><Settings size={11} /> Servers</Button>}
        </div>
      </div>

      {/* Wave H5 Embedded */}
      {waveUrl ? (
        <div className="flex-1 relative">
          <iframe
            ref={iframeRef}
            src={waveUrl}
            className="w-full h-full border-0"
            allow="camera; microphone; display-capture; autoplay; clipboard-write; fullscreen"
            sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals allow-downloads allow-popups-to-escape-sandbox"
            title="Grandstream Wave H5"
            onLoad={handleIframeLoad}
            data-testid="wave-iframe"
          />
          {!waveLoaded && (
            <div className="absolute inset-0 bg-card flex items-center justify-center">
              <div className="text-center">
                <div className="h-10 w-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm font-medium">Loading Wave...</p>
                <p className="text-xs text-muted-foreground mt-1">{waveUrl}</p>
                {waveConfig?.auto_login && <p className="text-xs text-blue-600 mt-2">Will auto-login as ext {waveConfig.extension}</p>}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center p-6">
          <Card className="max-w-lg w-full rounded-xl">
            <CardContent className="p-8 text-center">
              <div className="h-16 w-16 rounded-2xl bg-blue-100 dark:bg-blue-900 flex items-center justify-center mx-auto mb-4">
                <Phone size={32} className="text-blue-600" />
              </div>
              <h2 className="text-xl font-semibold mb-2">Connect Grandstream Wave</h2>
              <p className="text-sm text-muted-foreground mb-6">Enterprise calling, video meetings, instant messaging, and cross-campus communication via CloudUCM.</p>
              <div className="space-y-3 text-left">
                <div className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                  <Phone size={14} className="text-green-500 mt-0.5 shrink-0" />
                  <div><p className="text-sm font-medium">HD Audio & Video</p><p className="text-xs text-muted-foreground">Call transfer, hold, recording, voicemail</p></div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                  <Video size={14} className="text-blue-500 mt-0.5 shrink-0" />
                  <div><p className="text-sm font-medium">One-Click Meetings</p><p className="text-xs text-muted-foreground">Screen sharing, up to 3000 attendees</p></div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                  <Users size={14} className="text-purple-500 mt-0.5 shrink-0" />
                  <div><p className="text-sm font-medium">Cross-Campus Chat</p><p className="text-xs text-muted-foreground">Message between Uganda, USA, Kenya & more</p></div>
                </div>
              </div>
              {!waveConfig?.extension && (
                <div className="mt-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 text-left">
                  <p className="text-xs text-amber-700 dark:text-amber-300 flex items-center gap-1.5"><AlertCircle size={12} /> No Wave extension assigned to your account. Ask your admin to set your Wave extension and password in Staff Management.</p>
                </div>
              )}
              {isAdmin ? (
                <Button className="w-full mt-6 gap-2" onClick={() => setShowAdmin(true)} data-testid="setup-wave-btn"><Settings size={14} /> Configure Wave Server</Button>
              ) : (
                <p className="text-xs text-muted-foreground mt-6">Ask your admin to configure the Wave server.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Admin Server Management */}
      <Dialog open={showAdmin} onOpenChange={setShowAdmin}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Wave Servers</DialogTitle><DialogDescription>Configure Grandstream CloudUCM servers per campus. URL format: https://yourserver.a.gdms.cloud</DialogDescription></DialogHeader>
          <div className="space-y-4 mt-2">
            {servers.map(s => (
              <div key={s.id} className="flex items-center gap-3 p-3 rounded-lg border">
                <Globe size={14} className="text-blue-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{s.name} {s.is_default && <Badge className="text-[10px] ml-1">Default</Badge>}</p>
                  <p className="text-xs text-muted-foreground truncate">{s.url} {s.campus_name ? `| ${s.campus_name}` : ''}</p>
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
              <div className="space-y-1.5"><Label className="text-xs">Server URL *</Label>
                <Input value={serverForm.url} onChange={e => setServerForm({...serverForm, url: e.target.value})} placeholder="https://5812Uganda.a.gdms.cloud" data-testid="wave-server-url" />
              </div>
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
