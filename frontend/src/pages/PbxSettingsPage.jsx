import React, { useState, useEffect } from 'react';
import { 
  Phone, Plus, Trash2, Edit2, Save, Server, Shield, 
  CheckCircle, XCircle, RefreshCw, Link2, Settings, Wifi
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { callingApi } from '../services/api';
import { toast } from 'sonner';

const PBX_PROVIDERS = [
  { value: 'freepbx', label: 'FreePBX / Asterisk', icon: '🌟' },
  { value: '3cx', label: '3CX', icon: '📞' },
  { value: 'asterisk', label: 'Asterisk (Direct)', icon: '⭐' },
  { value: 'generic_sip', label: 'Generic SIP Gateway', icon: '🔗' },
];

export default function PbxSettingsPage() {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(null);
  const [testing, setTesting] = useState(null);

  const [form, setForm] = useState({
    name: '',
    provider: 'freepbx',
    host: '',
    port: 5060,
    username: '',
    password: '',
    api_key: '',
    api_url: '',
    websocket_url: '',
    stun_servers: ['stun:stun.l.google.com:19302'],
    turn_servers: [],
    is_active: true,
    is_default: false,
  });

  useEffect(() => {
    fetchConfigs();
  }, []);

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const res = await callingApi.listPbxConfigs();
      setConfigs(res.data || []);
    } catch {
      toast.error('Failed to load PBX configurations');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.name || !form.host) {
      toast.error('Please fill in required fields');
      return;
    }
    try {
      const res = await callingApi.createPbxConfig({
        ...form,
        stun_servers: typeof form.stun_servers === 'string' 
          ? form.stun_servers.split('\n').filter(s => s.trim())
          : form.stun_servers,
      });
      setConfigs(prev => [...prev, res.data]);
      setShowCreate(false);
      resetForm();
      toast.success('PBX configuration added');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create configuration');
    }
  };

  const handleUpdate = async () => {
    if (!showEdit?.id) return;
    try {
      await callingApi.updatePbxConfig(showEdit.id, {
        ...form,
        stun_servers: typeof form.stun_servers === 'string'
          ? form.stun_servers.split('\n').filter(s => s.trim())
          : form.stun_servers,
      });
      setConfigs(prev => prev.map(c => c.id === showEdit.id ? { ...c, ...form } : c));
      setShowEdit(null);
      resetForm();
      toast.success('Configuration updated');
    } catch {
      toast.error('Failed to update');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this PBX configuration?')) return;
    try {
      await callingApi.deletePbxConfig(id);
      setConfigs(prev => prev.filter(c => c.id !== id));
      toast.success('Configuration deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  const handleTest = async (id) => {
    setTesting(id);
    try {
      const res = await callingApi.testPbxConnection(id);
      if (res.data?.success) {
        toast.success(res.data.message || 'Connection successful');
      } else {
        toast.error(res.data?.message || 'Connection failed');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Connection test failed');
    } finally {
      setTesting(null);
    }
  };

  const resetForm = () => {
    setForm({
      name: '',
      provider: 'freepbx',
      host: '',
      port: 5060,
      username: '',
      password: '',
      api_key: '',
      api_url: '',
      websocket_url: '',
      stun_servers: ['stun:stun.l.google.com:19302'],
      turn_servers: [],
      is_active: true,
      is_default: false,
    });
  };

  const openEdit = (config) => {
    setForm({
      name: config.name,
      provider: config.provider,
      host: config.host,
      port: config.port || 5060,
      username: config.username || '',
      password: '',
      api_key: '',
      api_url: config.api_url || '',
      websocket_url: config.websocket_url || '',
      stun_servers: config.stun_servers || ['stun:stun.l.google.com:19302'],
      turn_servers: config.turn_servers || [],
      is_active: config.is_active !== false,
      is_default: config.is_default || false,
    });
    setShowEdit(config);
  };

  const getProviderInfo = (provider) => PBX_PROVIDERS.find(p => p.value === provider) || { icon: '📞', label: provider };

  return (
    <div className="p-6 space-y-6" data-testid="pbx-settings-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">PBX Configuration</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Connect to external PBX systems for enhanced calling</p>
        </div>
        <Button className="gap-2" onClick={() => { resetForm(); setShowCreate(true); }} data-testid="add-pbx-btn">
          <Plus size={16} /> Add PBX Connection
        </Button>
      </div>

      {/* Info Banner */}
      <Card className="shadow-soft rounded-xl bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800">
        <CardContent className="p-4 flex items-start gap-3">
          <Server size={20} className="text-blue-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-blue-800 dark:text-blue-400">PBX Integration</p>
            <p className="text-xs text-blue-700 dark:text-blue-500 mt-1">
              Connect to your existing phone system (FreePBX, 3CX, Asterisk) to enable external calling, 
              SIP trunks, and advanced telephony features. WebRTC calling works standalone without PBX.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Configs List */}
      {loading ? (
        <div className="grid sm:grid-cols-2 gap-4">
          {[1, 2].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : configs.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <Server size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground mb-2">No PBX systems configured</p>
            <p className="text-xs text-muted-foreground mb-4">WebRTC calling will work standalone for internal calls</p>
            <Button onClick={() => setShowCreate(true)} className="gap-2">
              <Plus size={14} /> Add PBX Connection
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 gap-4">
          {configs.map(config => {
            const provider = getProviderInfo(config.provider);
            return (
              <Card key={config.id} className="shadow-soft rounded-xl" data-testid={`pbx-card-${config.id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center text-2xl">
                        {provider.icon}
                      </div>
                      <div>
                        <p className="font-semibold">{config.name}</p>
                        <p className="text-xs text-muted-foreground">{provider.label}</p>
                      </div>
                    </div>
                    <div className="flex gap-1">
                      {config.is_default && (
                        <Badge variant="default" className="text-xs">Default</Badge>
                      )}
                      <Badge className={`text-xs ${config.is_active ? 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400' : 'bg-slate-100 text-slate-700'}`}>
                        {config.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </div>
                  </div>

                  <div className="space-y-2 mb-4 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Host</span>
                      <code className="text-xs bg-muted px-2 py-0.5 rounded">{config.host}:{config.port}</code>
                    </div>
                    {config.api_url && (
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">API URL</span>
                        <span className="text-xs truncate max-w-[180px]">{config.api_url}</span>
                      </div>
                    )}
                    {config.websocket_url && (
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">WebSocket</span>
                        <span className="text-xs truncate max-w-[180px]">{config.websocket_url}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 gap-1"
                      onClick={() => handleTest(config.id)}
                      disabled={testing === config.id}
                    >
                      {testing === config.id ? (
                        <RefreshCw size={12} className="animate-spin" />
                      ) : (
                        <Wifi size={12} />
                      )}
                      Test
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => openEdit(config)}>
                      <Edit2 size={12} />
                    </Button>
                    <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => handleDelete(config.id)}>
                      <Trash2 size={12} />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate || !!showEdit} onOpenChange={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{showEdit ? 'Edit PBX Configuration' : 'Add PBX Connection'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Connection Name *</Label>
                <Input
                  placeholder="Main Office PBX"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  data-testid="pbx-name-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Provider *</Label>
                <Select value={form.provider} onValueChange={v => setForm({ ...form, provider: v })}>
                  <SelectTrigger data-testid="pbx-provider-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PBX_PROVIDERS.map(p => (
                      <SelectItem key={p.value} value={p.value}>{p.icon} {p.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-2 space-y-2">
                <Label>Host / IP Address *</Label>
                <Input
                  placeholder="pbx.company.com"
                  value={form.host}
                  onChange={e => setForm({ ...form, host: e.target.value })}
                  data-testid="pbx-host-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Port</Label>
                <Input
                  type="number"
                  placeholder="5060"
                  value={form.port}
                  onChange={e => setForm({ ...form, port: parseInt(e.target.value) || 5060 })}
                />
              </div>
            </div>

            {['freepbx', 'asterisk'].includes(form.provider) && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Username</Label>
                  <Input
                    placeholder="admin"
                    value={form.username}
                    onChange={e => setForm({ ...form, username: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Password {showEdit && '(leave blank to keep)'}</Label>
                  <Input
                    type="password"
                    placeholder="••••••••"
                    value={form.password}
                    onChange={e => setForm({ ...form, password: e.target.value })}
                  />
                </div>
              </div>
            )}

            {form.provider === '3cx' && (
              <div className="space-y-2">
                <Label>API Key</Label>
                <Input
                  type="password"
                  placeholder="3CX API Key"
                  value={form.api_key}
                  onChange={e => setForm({ ...form, api_key: e.target.value })}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label>API URL (optional)</Label>
              <Input
                placeholder="https://pbx.company.com/api"
                value={form.api_url}
                onChange={e => setForm({ ...form, api_url: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label>WebSocket URL (for WebRTC)</Label>
              <Input
                placeholder="wss://pbx.company.com:8089/ws"
                value={form.websocket_url}
                onChange={e => setForm({ ...form, websocket_url: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label>STUN Servers (one per line)</Label>
              <Textarea
                rows={2}
                placeholder="stun:stun.l.google.com:19302"
                value={Array.isArray(form.stun_servers) ? form.stun_servers.join('\n') : form.stun_servers}
                onChange={e => setForm({ ...form, stun_servers: e.target.value })}
              />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Active</p>
                <p className="text-xs text-muted-foreground">Enable this PBX connection</p>
              </div>
              <Switch checked={form.is_active} onCheckedChange={v => setForm({ ...form, is_active: v })} />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Set as Default</p>
                <p className="text-xs text-muted-foreground">Use this PBX for external calls</p>
              </div>
              <Switch checked={form.is_default} onCheckedChange={v => setForm({ ...form, is_default: v })} />
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>
                Cancel
              </Button>
              <Button className="flex-1 gap-2" onClick={showEdit ? handleUpdate : handleCreate} data-testid="save-pbx-btn">
                <Save size={14} /> {showEdit ? 'Update' : 'Add Connection'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
