import React, { useState, useEffect } from 'react';
import { Phone, Video, Settings, ExternalLink, Plus, Trash2, Edit2, Save, Globe, Monitor, RefreshCw, X, Users } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { waveApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

export default function WavePage() {
  const { user } = useAuth();
  const [waveConfig, setWaveConfig] = useState(null);
  const [servers, setServers] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);
  const [serverForm, setServerForm] = useState({ name: '', url: '', campus_id: '', campus_name: '', is_default: false });
  const [editServer, setEditServer] = useState(null);
  const [waveUrl, setWaveUrl] = useState('');
  const [waveLoaded, setWaveLoaded] = useState(false);

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
          setWaveUrl(configRes.data.server.url);
        }
      } catch {}
      finally { setLoading(false); }
    };
    load();
  }, []);

  const saveServer = async () => {
    if (!serverForm.name || !serverForm.url) { toast.error('Name and URL required'); return; }
    try {
      if (editServer) {
        await waveApi.updateServer(editServer.id, serverForm);
        toast.success('Updated');
      } else {
        await waveApi.addServer(serverForm);
        toast.success('Wave server added');
      }
      const res = await waveApi.listServers();
      setServers(res.data || []);
      setEditServer(null);
      setServerForm({ name: '', url: '', campus_id: '', campus_name: '', is_default: false });
    } catch { toast.error('Failed to save'); }
  };

  const deleteServer = async (id) => {
    if (!window.confirm('Remove this Wave server?')) return;
    try { await waveApi.deleteServer(id); setServers(prev => prev.filter(s => s.id !== id)); toast.success('Deleted'); }
    catch { toast.error('Failed'); }
  };

  const openWave = (url) => {
    setWaveUrl(url);
    setWaveLoaded(false);
  };

  const openInNewTab = () => {
    if (waveUrl) window.open(waveUrl, '_blank');
  };

  if (loading) return <div className="p-6"><div className="h-64 animate-pulse bg-muted rounded-xl" /></div>;

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border shrink-0 bg-card">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
            <Phone size={18} className="text-blue-600" />
          </div>
          <div>
            <h1 className="text-lg font-semibold font-heading">Wave</h1>
            <p className="text-xs text-muted-foreground">Grandstream CloudUCM — Calls, Video, Chat & Meetings</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {waveConfig?.server && (
            <Badge variant="outline" className="text-xs gap-1.5">
              <Globe size={10} /> {waveConfig.server.name || waveConfig.server.url}
            </Badge>
          )}
          {/* Server selector for multi-campus */}
          {servers.length > 1 && (
            <Select value={waveUrl} onValueChange={url => openWave(url)}>
              <SelectTrigger className="w-[180px] h-8 text-xs"><SelectValue placeholder="Switch server..." /></SelectTrigger>
              <SelectContent>
                {servers.map(s => <SelectItem key={s.id} value={s.url}>{s.name} {s.campus_name ? `(${s.campus_name})` : ''}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
          <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => { setWaveLoaded(false); setTimeout(() => setWaveLoaded(false), 100); }} title="Reload"><RefreshCw size={14} /></Button>
          <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={openInNewTab} title="Open in new tab"><ExternalLink size={14} /></Button>
          {isAdmin && <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8" onClick={() => setShowAdmin(true)}><Settings size={12} /> Servers</Button>}
        </div>
      </div>

      {/* Main content */}
      {waveUrl ? (
        <div className="flex-1 relative">
          <iframe
            src={waveUrl}
            className="w-full h-full border-0"
            allow="camera; microphone; display-capture; autoplay; clipboard-write; fullscreen"
            sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals allow-downloads allow-popups-to-escape-sandbox"
            title="Grandstream Wave"
            onLoad={() => setWaveLoaded(true)}
            data-testid="wave-iframe"
          />
          {!waveLoaded && (
            <div className="absolute inset-0 bg-card flex items-center justify-center">
              <div className="text-center">
                <div className="h-10 w-10 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">Loading Wave...</p>
                <p className="text-xs text-muted-foreground mt-1">{waveUrl}</p>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* No server configured — show setup */
        <div className="flex-1 flex items-center justify-center p-6">
          <Card className="max-w-lg w-full rounded-xl">
            <CardContent className="p-8 text-center">
              <div className="h-16 w-16 rounded-2xl bg-blue-100 dark:bg-blue-900 flex items-center justify-center mx-auto mb-4">
                <Phone size={32} className="text-blue-600" />
              </div>
              <h2 className="text-xl font-semibold mb-2">Connect Grandstream Wave</h2>
              <p className="text-sm text-muted-foreground mb-6">Wave provides enterprise calling, video meetings, instant messaging, and cross-PBX communication via Grandstream CloudUCM.</p>
              <div className="space-y-4 text-left">
                <div className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                  <Phone size={16} className="text-green-500 mt-0.5 shrink-0" />
                  <div><p className="text-sm font-medium">Audio & Video Calls</p><p className="text-xs text-muted-foreground">HD calling with call transfer, hold, recording</p></div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                  <Video size={16} className="text-blue-500 mt-0.5 shrink-0" />
                  <div><p className="text-sm font-medium">Video Meetings</p><p className="text-xs text-muted-foreground">One-click meetings with screen sharing</p></div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                  <Users size={16} className="text-purple-500 mt-0.5 shrink-0" />
                  <div><p className="text-sm font-medium">Cross-Campus Chat</p><p className="text-xs text-muted-foreground">Chat between Uganda, USA, and all locations</p></div>
                </div>
              </div>
              {isAdmin ? (
                <Button className="w-full mt-6 gap-2" onClick={() => setShowAdmin(true)} data-testid="setup-wave-btn">
                  <Settings size={14} /> Configure Wave Server
                </Button>
              ) : (
                <p className="text-xs text-muted-foreground mt-6">Ask your admin to configure the Wave server for your campus.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Admin Server Management Dialog */}
      <Dialog open={showAdmin} onOpenChange={setShowAdmin}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Wave Server Configuration</DialogTitle>
            <DialogDescription>Configure Grandstream CloudUCM Wave servers per campus</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            {/* Existing servers */}
            {servers.length > 0 && (
              <div className="space-y-2">
                {servers.map(s => (
                  <div key={s.id} className="flex items-center gap-3 p-3 rounded-lg border border-border">
                    <Globe size={16} className="text-blue-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">{s.name} {s.is_default && <Badge className="text-[10px] ml-1">Default</Badge>}</p>
                      <p className="text-xs text-muted-foreground truncate">{s.url} {s.campus_name ? `| ${s.campus_name}` : ''}</p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => {
                      setServerForm({ name: s.name, url: s.url, campus_id: s.campus_id || '', campus_name: s.campus_name || '', is_default: s.is_default || false });
                      setEditServer(s);
                    }}><Edit2 size={12} /></Button>
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => deleteServer(s.id)}><Trash2 size={12} /></Button>
                  </div>
                ))}
              </div>
            )}

            {/* Add/Edit form */}
            <div className="p-4 rounded-lg border border-dashed border-border space-y-3">
              <p className="text-sm font-medium">{editServer ? 'Edit Server' : 'Add Wave Server'}</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label className="text-xs">Server Name *</Label>
                  <Input value={serverForm.name} onChange={e => setServerForm({...serverForm, name: e.target.value})} placeholder="58:12 Uganda" data-testid="wave-server-name" /></div>
                <div className="space-y-1.5"><Label className="text-xs">Campus</Label>
                  <Select value={serverForm.campus_id || '_none'} onValueChange={v => {
                    const loc = locations.find(l => l.id === v);
                    setServerForm({...serverForm, campus_id: v === '_none' ? '' : v, campus_name: loc?.name || ''});
                  }}>
                    <SelectTrigger><SelectValue placeholder="Select campus..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none">All / Global</SelectItem>
                      {locations.filter(l => l.type !== 'sub-location').map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Wave Server URL *</Label>
                <Input value={serverForm.url} onChange={e => setServerForm({...serverForm, url: e.target.value})} placeholder="https://5812Uganda.a.gdms.cloud" data-testid="wave-server-url" />
                <p className="text-[10px] text-muted-foreground">The full URL of your Grandstream Wave / CloudUCM web client</p>
              </div>
              <div className="flex items-center justify-between p-2 border rounded-lg">
                <Label className="text-xs">Default Server</Label>
                <Switch checked={serverForm.is_default} onCheckedChange={v => setServerForm({...serverForm, is_default: v})} />
              </div>
              <div className="flex gap-3">
                {editServer && <Button variant="ghost" size="sm" onClick={() => { setEditServer(null); setServerForm({ name: '', url: '', campus_id: '', campus_name: '', is_default: false }); }}>Cancel Edit</Button>}
                <Button size="sm" className="gap-1.5 ml-auto" onClick={saveServer} data-testid="save-wave-server">
                  <Save size={12} /> {editServer ? 'Update' : 'Add Server'}
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
