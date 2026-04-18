import React, { useState, useEffect } from 'react';
import {
  Phone, Plus, Trash2, Edit2, Save, Server, Shield,
  CheckCircle, XCircle, RefreshCw, Settings, Wifi, Users,
  PhoneForwarded, Voicemail, List, ArrowRightLeft, Lock
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { callingApi, adminApi } from '../services/api';
import { useCall } from '../context/CallContext';
import { toast } from 'sonner';

const PBX_PROVIDERS = [
  { value: 'freepbx', label: 'FreePBX / Asterisk' },
  { value: '3cx', label: '3CX' },
  { value: 'asterisk', label: 'Asterisk (Direct)' },
  { value: 'generic_sip', label: 'Generic SIP Gateway' },
];

export default function PbxSettingsPage() {
  const [configs, setConfigs] = useState([]);
  const [extensions, setExtensions] = useState([]);
  const [users, setUsers] = useState([]);
  const [queues, setQueues] = useState([]);
  const [autoAttendant, setAutoAttendant] = useState(null);
  const [outgoingRules, setOutgoingRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showPbxForm, setShowPbxForm] = useState(false);
  const [editPbx, setEditPbx] = useState(null);
  const [showExtForm, setShowExtForm] = useState(false);
  const [editExt, setEditExt] = useState(null);
  const [showQueueForm, setShowQueueForm] = useState(false);
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [testing, setTesting] = useState(null);

  const [pbxForm, setPbxForm] = useState({ name: '', provider: 'freepbx', host: '', port: 5060, username: '', password: '', sip_username: '', sip_password: '', sip_domain: '', api_key: '', api_url: '', websocket_url: '', stun_servers: 'stun:stun.l.google.com:19302', turn_servers: [], is_active: true, is_default: false, sip_only: false });
  const [extForm, setExtForm] = useState({ user_id: '', extension: '', display_name: '', voicemail_enabled: true, voicemail_pin: '', dnd_enabled: false, forward_to: '' });
  const [queueForm, setQueueForm] = useState({ name: '', strategy: 'ring_all', timeout: 30, max_wait: 300, members: '', announce_position: true });
  const [ruleForm, setRuleForm] = useState({ name: '', pattern: '', action: 'allow', prefix: '', priority: 10, enabled: true });

  useEffect(() => { fetchAll(); }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [pbxRes, extRes, usersRes, qRes, aaRes, rulesRes] = await Promise.all([
        callingApi.listPbxConfigs(),
        callingApi.listExtensions(),
        adminApi.users({ limit: 500 }).catch(() => ({ data: [] })),
        callingApi.listQueues().catch(() => ({ data: [] })),
        callingApi.getAutoAttendant().catch(() => ({ data: null })),
        callingApi.listOutgoingRules().catch(() => ({ data: [] })),
      ]);
      setConfigs(pbxRes.data || []);
      setExtensions(extRes.data || []);
      setUsers(usersRes.data || []);
      setQueues(qRes.data || []);
      setAutoAttendant(aaRes.data);
      setOutgoingRules(rulesRes.data || []);
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  };

  // PBX CRUD
  const savePbx = async () => {
    if (!pbxForm.name || !pbxForm.host) { toast.error('Name and host required'); return; }
    const payload = { ...pbxForm, stun_servers: typeof pbxForm.stun_servers === 'string' ? pbxForm.stun_servers.split('\n').filter(Boolean) : pbxForm.stun_servers };
    try {
      if (editPbx) { await callingApi.updatePbxConfig(editPbx.id, payload); toast.success('Updated'); }
      else { await callingApi.createPbxConfig(payload); toast.success('PBX added'); }
      setShowPbxForm(false); setEditPbx(null); fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
  };
  const deletePbx = async (id) => { if (!window.confirm('Delete?')) return; try { await callingApi.deletePbxConfig(id); fetchAll(); toast.success('Deleted'); } catch { toast.error('Failed'); } };
  const testPbx = async (id) => { setTesting(id); try { const r = await callingApi.testPbxConnection(id); toast[r.data?.success ? 'success' : 'error'](r.data?.message || 'Test done'); } catch { toast.error('Test failed'); } finally { setTesting(null); } };

  // Extension CRUD
  const saveExt = async () => {
    if (!extForm.user_id || !extForm.extension) { toast.error('User and extension required'); return; }
    try {
      if (editExt) { await callingApi.updateExtension(editExt.extension, extForm); toast.success('Updated'); }
      else { await callingApi.createExtension(extForm); toast.success('Extension assigned'); }
      setShowExtForm(false); setEditExt(null); fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
  };
  const deleteExt = async (ext) => { if (!window.confirm(`Remove ext ${ext}?`)) return; try { await callingApi.deleteExtension(ext); fetchAll(); toast.success('Removed'); } catch { toast.error('Failed'); } };
  const getNextExt = () => { const nums = extensions.map(e => parseInt(e.extension)).filter(n => !isNaN(n)); return nums.length === 0 ? '1001' : String(Math.max(...nums) + 1); };

  // Queue CRUD
  const saveQueue = async () => {
    if (!queueForm.name) { toast.error('Name required'); return; }
    const payload = { ...queueForm, members: typeof queueForm.members === 'string' ? queueForm.members.split(',').map(s => s.trim()).filter(Boolean) : queueForm.members };
    try { await callingApi.createQueue(payload); toast.success('Queue created'); setShowQueueForm(false); fetchAll(); }
    catch { toast.error('Failed'); }
  };
  const deleteQueue = async (id) => { try { await callingApi.deleteQueue(id); fetchAll(); toast.success('Deleted'); } catch { toast.error('Failed'); } };

  // Auto-attendant save
  const saveAA = async () => {
    try { await callingApi.updateAutoAttendant(autoAttendant); toast.success('Auto-attendant saved'); } catch { toast.error('Failed'); }
  };

  // Outgoing rule CRUD
  const saveRule = async () => {
    if (!ruleForm.name) { toast.error('Name required'); return; }
    try { await callingApi.createOutgoingRule(ruleForm); toast.success('Rule added'); setShowRuleForm(false); fetchAll(); }
    catch { toast.error('Failed'); }
  };
  const deleteRule = async (id) => { try { await callingApi.deleteOutgoingRule(id); fetchAll(); toast.success('Deleted'); } catch { toast.error('Failed'); } };

  const usersWithoutExt = users.filter(u => !extensions.some(e => e.user_id === u.id));

  let sipStatus = { registered: false, error: null };
  try { const c = useCall(); sipStatus = { registered: c.sipRegistered, error: c.sipError }; } catch (e) { console.warn(e.message || e); }

  if (loading) return <div className="p-6"><div className="h-64 animate-pulse bg-muted rounded-xl" /></div>;

  return (
    <div className="p-6 space-y-6" data-testid="pbx-settings-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">PBX Integration</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Connect a local PBX (FreePBX/Asterisk/FreeSWITCH) for external calling, extensions, queues & routing</p>
        </div>
        <div className="flex items-center gap-2">
          {sipStatus.registered ? (
            <Badge className="gap-1.5 bg-green-100 text-green-700" data-testid="sip-status-badge"><CheckCircle size={12} /> SIP Registered</Badge>
          ) : sipStatus.error ? (
            <Badge variant="destructive" className="gap-1.5 text-xs" data-testid="sip-status-badge" title={sipStatus.error}><XCircle size={12} /> Not Connected</Badge>
          ) : configs.length > 0 ? (
            <Badge variant="outline" className="gap-1.5 text-xs" data-testid="sip-status-badge"><Wifi size={12} /> Checking...</Badge>
          ) : (
            <Badge variant="outline" className="gap-1.5 text-xs"><Server size={12} /> No PBX</Badge>
          )}
        </div>
      </div>

      {/* Info banner when no PBX */}
      {configs.length === 0 && (
        <Card className="rounded-xl border-blue-200 bg-blue-50 dark:bg-blue-950/20">
          <CardContent className="p-4">
            <p className="text-sm font-medium text-blue-800 dark:text-blue-300">Internal calling works without a PBX</p>
            <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">Audio calls, video calls, screen sharing, and group calls are available now via WebRTC. Connect a PBX only if you need external phone numbers, SIP trunking, or traditional telephony features.</p>
            <p className="text-xs text-muted-foreground mt-2">Supported: FreePBX/Asterisk, FreeSWITCH/FusionPBX, 3CX, or any SIP server with WebSocket support.</p>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="extensions" className="space-y-4">
        <TabsList className="grid grid-cols-5 w-full max-w-2xl">
          <TabsTrigger value="extensions" data-testid="tab-extensions"><Phone size={13} className="mr-1" /> Extensions</TabsTrigger>
          <TabsTrigger value="pbx" data-testid="tab-pbx"><Server size={13} className="mr-1" /> PBX</TabsTrigger>
          <TabsTrigger value="queues" data-testid="tab-queues"><Users size={13} className="mr-1" /> Queues</TabsTrigger>
          <TabsTrigger value="aa" data-testid="tab-aa"><List size={13} className="mr-1" /> Auto-Attendant</TabsTrigger>
          <TabsTrigger value="rules" data-testid="tab-rules"><ArrowRightLeft size={13} className="mr-1" /> Rules</TabsTrigger>
        </TabsList>

        {/* ===== EXTENSIONS TAB ===== */}
        <TabsContent value="extensions" className="space-y-4">
          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">{extensions.length} extensions assigned</p>
            <Button size="sm" className="gap-1.5" onClick={() => { setExtForm({ user_id: '', extension: getNextExt(), display_name: '', voicemail_enabled: true, voicemail_pin: '', dnd_enabled: false, forward_to: '' }); setEditExt(null); setShowExtForm(true); }} data-testid="add-extension-btn"><Plus size={14} /> Assign Extension</Button>
          </div>
          <div className="space-y-2">
            {extensions.map(ext => (
              <Card key={ext.extension} className="rounded-xl">
                <CardContent className="p-4 flex items-center gap-4">
                  <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center font-bold text-primary text-sm">{ext.extension}</div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm">{ext.display_name || ext.user_name || 'Unassigned'}</p>
                    <p className="text-xs text-muted-foreground">{ext.user_email} {ext.forward_to ? `| Fwd: ${ext.forward_to}` : ''}</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {ext.voicemail_enabled && <Badge variant="outline" className="text-[10px]"><Voicemail size={10} className="mr-0.5" /> VM</Badge>}
                    {ext.dnd_enabled && <Badge variant="destructive" className="text-[10px]">DND</Badge>}
                    <Button size="sm" variant="ghost" onClick={() => { setExtForm({ user_id: ext.user_id, extension: ext.extension, display_name: ext.display_name || '', voicemail_enabled: ext.voicemail_enabled !== false, voicemail_pin: '', dnd_enabled: ext.dnd_enabled || false, forward_to: ext.forward_to || '' }); setEditExt(ext); setShowExtForm(true); }}><Edit2 size={13} /></Button>
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => deleteExt(ext.extension)}><Trash2 size={13} /></Button>
                  </div>
                </CardContent>
              </Card>
            ))}
            {extensions.length === 0 && <p className="text-center py-8 text-muted-foreground text-sm">No extensions assigned yet</p>}
          </div>
        </TabsContent>

        {/* ===== PBX TAB ===== */}
        <TabsContent value="pbx" className="space-y-4">
          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">{configs.length} PBX connections</p>
            <Button size="sm" className="gap-1.5" onClick={() => { setPbxForm({ name: '', provider: 'freepbx', host: '', port: 5060, username: '', password: '', sip_username: '', sip_password: '', sip_domain: '', api_key: '', api_url: '', websocket_url: '', stun_servers: 'stun:stun.l.google.com:19302', turn_servers: [], is_active: true, is_default: false }); setEditPbx(null); setShowPbxForm(true); }} data-testid="add-pbx-btn"><Plus size={14} /> Add PBX</Button>
          </div>
          {configs.map(c => (
            <Card key={c.id} className="rounded-xl">
              <CardContent className="p-4 flex items-center gap-4">
                <Server size={20} className="text-primary shrink-0" />
                <div className="flex-1">
                  <div className="font-medium text-sm flex items-center gap-1">{c.name} <Badge variant="outline" className="text-[10px]">{c.provider}</Badge></div>
                  <p className="text-xs text-muted-foreground">{c.host}:{c.port} {c.sip_domain ? `| SIP: ${c.sip_domain}` : ''}</p>
                </div>
                <div className="flex gap-1.5">
                  {c.is_default && <Badge className="text-[10px]">Default</Badge>}
                  <Badge className={`text-[10px] ${c.is_active ? 'bg-green-100 text-green-700' : 'bg-slate-100'}`}>{c.is_active ? 'Active' : 'Off'}</Badge>
                  <Button size="sm" variant="outline" onClick={() => testPbx(c.id)} disabled={testing === c.id}>{testing === c.id ? <RefreshCw size={12} className="animate-spin" /> : <Wifi size={12} />}</Button>
                  <Button size="sm" variant="ghost" onClick={() => { setPbxForm({ name: c.name, provider: c.provider, host: c.host, port: c.port || 5060, username: c.username || '', password: '', sip_username: c.sip_username || '', sip_password: '', sip_domain: c.sip_domain || '', api_key: '', api_url: c.api_url || '', websocket_url: c.websocket_url || '', stun_servers: (c.stun_servers || []).join('\n'), is_active: c.is_active !== false, is_default: c.is_default || false }); setEditPbx(c); setShowPbxForm(true); }}><Edit2 size={12} /></Button>
                  <Button size="sm" variant="ghost" className="text-destructive" onClick={() => deletePbx(c.id)}><Trash2 size={12} /></Button>
                </div>
              </CardContent>
            </Card>
          ))}
          {configs.length === 0 && <p className="text-center py-8 text-muted-foreground text-sm">No PBX configured. WebRTC works standalone for internal calls.</p>}
        </TabsContent>

        {/* ===== QUEUES TAB ===== */}
        <TabsContent value="queues" className="space-y-4">
          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">{queues.length} call queues</p>
            <Button size="sm" className="gap-1.5" onClick={() => { setQueueForm({ name: '', strategy: 'ring_all', timeout: 30, max_wait: 300, members: '', announce_position: true }); setShowQueueForm(true); }}><Plus size={14} /> New Queue</Button>
          </div>
          {queues.map(q => (
            <Card key={q.id} className="rounded-xl">
              <CardContent className="p-4 flex items-center gap-4">
                <Users size={18} className="text-blue-500 shrink-0" />
                <div className="flex-1">
                  <p className="font-medium text-sm">{q.name}</p>
                  <p className="text-xs text-muted-foreground">Strategy: {q.strategy} | Timeout: {q.timeout}s | Members: {(q.members || []).length}</p>
                </div>
                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => deleteQueue(q.id)}><Trash2 size={13} /></Button>
              </CardContent>
            </Card>
          ))}
          {queues.length === 0 && <p className="text-center py-8 text-muted-foreground text-sm">No call queues configured</p>}
        </TabsContent>

        {/* ===== AUTO-ATTENDANT TAB ===== */}
        <TabsContent value="aa" className="space-y-4">
          {autoAttendant && (
            <Card className="rounded-xl">
              <CardHeader><CardTitle className="text-base">Auto-Attendant Configuration</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-lg border">
                  <Label>Enabled</Label>
                  <Switch checked={autoAttendant.enabled} onCheckedChange={v => setAutoAttendant({...autoAttendant, enabled: v})} />
                </div>
                <div className="space-y-2"><Label>Greeting Message</Label>
                  <Textarea rows={2} value={autoAttendant.greeting || ''} onChange={e => setAutoAttendant({...autoAttendant, greeting: e.target.value})} />
                </div>
                <div className="space-y-2"><Label>After-Hours Greeting</Label>
                  <Textarea rows={2} value={autoAttendant.after_hours_greeting || ''} onChange={e => setAutoAttendant({...autoAttendant, after_hours_greeting: e.target.value})} />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1.5"><Label className="text-xs">Business Start</Label><Input type="time" value={autoAttendant.business_hours?.start || '08:00'} onChange={e => setAutoAttendant({...autoAttendant, business_hours: {...(autoAttendant.business_hours||{}), start: e.target.value}})} /></div>
                  <div className="space-y-1.5"><Label className="text-xs">Business End</Label><Input type="time" value={autoAttendant.business_hours?.end || '17:00'} onChange={e => setAutoAttendant({...autoAttendant, business_hours: {...(autoAttendant.business_hours||{}), end: e.target.value}})} /></div>
                  <div className="space-y-1.5"><Label className="text-xs">After-Hours Action</Label>
                    <Select value={autoAttendant.after_hours_action || 'voicemail'} onValueChange={v => setAutoAttendant({...autoAttendant, after_hours_action: v})}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="voicemail">Voicemail</SelectItem><SelectItem value="forward">Forward</SelectItem><SelectItem value="hangup">Hang Up</SelectItem></SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-2"><Label>Menu Options</Label>
                  {(autoAttendant.menu_options || []).map((opt, i) => (
                    <div key={opt.key || i} className="flex items-center gap-2 text-sm">
                      <Input className="w-12 h-8 text-center text-xs" value={opt.key} onChange={e => { const mo = [...autoAttendant.menu_options]; mo[i] = {...mo[i], key: e.target.value}; setAutoAttendant({...autoAttendant, menu_options: mo}); }} />
                      <Input className="flex-1 h-8 text-xs" value={opt.label} onChange={e => { const mo = [...autoAttendant.menu_options]; mo[i] = {...mo[i], label: e.target.value}; setAutoAttendant({...autoAttendant, menu_options: mo}); }} />
                      <Select value={opt.action} onValueChange={v => { const mo = [...autoAttendant.menu_options]; mo[i] = {...mo[i], action: v}; setAutoAttendant({...autoAttendant, menu_options: mo}); }}>
                        <SelectTrigger className="w-28 h-8 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent><SelectItem value="transfer">Transfer</SelectItem><SelectItem value="directory">Directory</SelectItem><SelectItem value="operator">Operator</SelectItem><SelectItem value="voicemail">Voicemail</SelectItem><SelectItem value="queue">Queue</SelectItem></SelectContent>
                      </Select>
                      <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-destructive" onClick={() => { const mo = autoAttendant.menu_options.filter((_,j) => j !== i); setAutoAttendant({...autoAttendant, menu_options: mo}); }}><Trash2 size={12} /></Button>
                    </div>
                  ))}
                  <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => setAutoAttendant({...autoAttendant, menu_options: [...(autoAttendant.menu_options||[]), {key: String((autoAttendant.menu_options||[]).length+1), action: 'transfer', target: '', label: 'New Option'}]})}><Plus size={12} /> Add Option</Button>
                </div>
                <Button className="w-full" onClick={saveAA} data-testid="save-aa-btn"><Save size={14} className="mr-1.5" /> Save Auto-Attendant</Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ===== RULES TAB ===== */}
        <TabsContent value="rules" className="space-y-4">
          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">{outgoingRules.length} outgoing rules</p>
            <Button size="sm" className="gap-1.5" onClick={() => { setRuleForm({ name: '', pattern: '', action: 'allow', prefix: '', priority: 10, enabled: true }); setShowRuleForm(true); }}><Plus size={14} /> Add Rule</Button>
          </div>
          {outgoingRules.map(r => (
            <Card key={r.id} className="rounded-xl">
              <CardContent className="p-4 flex items-center gap-4">
                <ArrowRightLeft size={16} className="text-muted-foreground shrink-0" />
                <div className="flex-1">
                  <p className="font-medium text-sm">{r.name} <Badge variant={r.action === 'block' ? 'destructive' : 'outline'} className="text-[10px] ml-1">{r.action}</Badge></p>
                  <p className="text-xs text-muted-foreground font-mono">Pattern: {r.pattern || '*'} {r.prefix ? `| Prefix: ${r.prefix}` : ''} | Priority: {r.priority}</p>
                </div>
                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => deleteRule(r.id)}><Trash2 size={13} /></Button>
              </CardContent>
            </Card>
          ))}
          {outgoingRules.length === 0 && <p className="text-center py-8 text-muted-foreground text-sm">No outgoing rules. All calls allowed by default.</p>}
        </TabsContent>
      </Tabs>

      {/* ===== PBX FORM DIALOG ===== */}
      <Dialog open={showPbxForm} onOpenChange={() => { setShowPbxForm(false); setEditPbx(null); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editPbx ? 'Edit PBX' : 'Add PBX Connection'}</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={pbxForm.name} onChange={e => setPbxForm({...pbxForm, name: e.target.value})} data-testid="pbx-name-input" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Provider</Label>
                <Select value={pbxForm.provider} onValueChange={v => setPbxForm({...pbxForm, provider: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{PBX_PROVIDERS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2 space-y-1.5"><Label className="text-xs">Host / IP *</Label><Input value={pbxForm.host} onChange={e => setPbxForm({...pbxForm, host: e.target.value})} placeholder="pbx.company.com" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Port</Label><Input type="number" value={pbxForm.port} onChange={e => setPbxForm({...pbxForm, port: parseInt(e.target.value)||5060})} /></div>
            </div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">SIP Registration</p>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">SIP Username</Label><Input value={pbxForm.sip_username} onChange={e => setPbxForm({...pbxForm, sip_username: e.target.value})} placeholder="sip_user" data-testid="sip-username" /></div>
              <div className="space-y-1.5"><Label className="text-xs">SIP Password</Label><Input type="password" value={pbxForm.sip_password} onChange={e => setPbxForm({...pbxForm, sip_password: e.target.value})} placeholder="sip_pass" data-testid="sip-password" /></div>
              <div className="space-y-1.5"><Label className="text-xs">SIP Domain</Label><Input value={pbxForm.sip_domain} onChange={e => setPbxForm({...pbxForm, sip_domain: e.target.value})} placeholder="sip.company.com" data-testid="sip-domain" /></div>
            </div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">API Access</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Admin Username</Label><Input value={pbxForm.username} onChange={e => setPbxForm({...pbxForm, username: e.target.value})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Admin Password</Label><Input type="password" value={pbxForm.password} onChange={e => setPbxForm({...pbxForm, password: e.target.value})} /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">API URL</Label><Input value={pbxForm.api_url} onChange={e => setPbxForm({...pbxForm, api_url: e.target.value})} placeholder="https://pbx.company.com/api" /></div>
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold text-primary">WebSocket URL (REQUIRED for browser calling)</Label>
              <Input value={pbxForm.websocket_url} onChange={e => setPbxForm({...pbxForm, websocket_url: e.target.value})} placeholder="wss://pbx.company.com:8089/ws" data-testid="pbx-ws-url" />
              <p className="text-[10px] text-muted-foreground">SIP.js connects via WebSocket. Common ports: 8089 (FreePBX), 7443 (3CX), 443. Ask your PBX provider for the WSS URL. If empty, will auto-try wss://host:8089/ws</p>
            </div>
            {pbxForm.provider === '3cx' && <div className="space-y-1.5"><Label className="text-xs">API Key</Label><Input type="password" value={pbxForm.api_key} onChange={e => setPbxForm({...pbxForm, api_key: e.target.value})} /></div>}
            <div className="space-y-1.5"><Label className="text-xs">STUN Servers (one per line)</Label><Textarea rows={2} value={pbxForm.stun_servers} onChange={e => setPbxForm({...pbxForm, stun_servers: e.target.value})} /></div>
            <div className="flex items-center justify-between p-2 border rounded-lg"><Label className="text-xs">Active</Label><Switch checked={pbxForm.is_active} onCheckedChange={v => setPbxForm({...pbxForm, is_active: v})} /></div>
            <div className="flex items-center justify-between p-2 border rounded-lg"><Label className="text-xs">Default PBX</Label><Switch checked={pbxForm.is_default} onCheckedChange={v => setPbxForm({...pbxForm, is_default: v})} /></div>
            <div className="flex items-center justify-between p-2 border rounded-lg"><Label className="text-xs">SIP Only (no ICE/STUN)</Label><Switch checked={pbxForm.sip_only || false} onCheckedChange={v => setPbxForm({...pbxForm, sip_only: v})} /></div>
            <p className="text-[10px] text-muted-foreground">Enable "SIP Only" when your PBX handles media routing directly without WebRTC ICE negotiation.</p>
            <div className="flex gap-3"><Button variant="outline" className="flex-1" onClick={() => { setShowPbxForm(false); setEditPbx(null); }}>Cancel</Button><Button className="flex-1" onClick={savePbx} data-testid="save-pbx-btn"><Save size={14} className="mr-1" /> {editPbx ? 'Update' : 'Add'}</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ===== EXTENSION FORM DIALOG ===== */}
      <Dialog open={showExtForm} onOpenChange={() => { setShowExtForm(false); setEditExt(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>{editExt ? 'Edit Extension' : 'Assign Extension'}</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Staff Member *</Label>
              <Select value={extForm.user_id} onValueChange={v => { const u = users.find(x => x.id === v); setExtForm({...extForm, user_id: v, display_name: u?.name || ''}); }}>
                <SelectTrigger><SelectValue placeholder="Select staff..." /></SelectTrigger>
                <SelectContent>{(editExt ? users : usersWithoutExt).map(u => <SelectItem key={u.id} value={u.id}>{u.name} ({u.role})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Extension # *</Label><Input value={extForm.extension} onChange={e => setExtForm({...extForm, extension: e.target.value})} maxLength={6} data-testid="ext-number-input" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Display Name</Label><Input value={extForm.display_name} onChange={e => setExtForm({...extForm, display_name: e.target.value})} /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Voicemail PIN</Label><Input value={extForm.voicemail_pin} onChange={e => setExtForm({...extForm, voicemail_pin: e.target.value})} placeholder="4-6 digits" maxLength={6} /></div>
            <div className="space-y-1.5"><Label className="text-xs">Forward To (phone number)</Label><Input value={extForm.forward_to} onChange={e => setExtForm({...extForm, forward_to: e.target.value})} placeholder="+256..." /></div>
            <div className="flex items-center justify-between p-2 border rounded-lg"><Label className="text-xs">Voicemail</Label><Switch checked={extForm.voicemail_enabled} onCheckedChange={v => setExtForm({...extForm, voicemail_enabled: v})} /></div>
            <div className="flex items-center justify-between p-2 border rounded-lg"><Label className="text-xs">Do Not Disturb</Label><Switch checked={extForm.dnd_enabled} onCheckedChange={v => setExtForm({...extForm, dnd_enabled: v})} /></div>
            <div className="flex gap-3"><Button variant="outline" className="flex-1" onClick={() => { setShowExtForm(false); setEditExt(null); }}>Cancel</Button><Button className="flex-1" onClick={saveExt}><Save size={14} className="mr-1" /> {editExt ? 'Update' : 'Assign'}</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ===== QUEUE FORM DIALOG ===== */}
      <Dialog open={showQueueForm} onOpenChange={setShowQueueForm}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Create Call Queue</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Queue Name *</Label><Input value={queueForm.name} onChange={e => setQueueForm({...queueForm, name: e.target.value})} /></div>
            <div className="space-y-1.5"><Label className="text-xs">Ring Strategy</Label>
              <Select value={queueForm.strategy} onValueChange={v => setQueueForm({...queueForm, strategy: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="ring_all">Ring All</SelectItem><SelectItem value="round_robin">Round Robin</SelectItem><SelectItem value="least_recent">Least Recent</SelectItem><SelectItem value="random">Random</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Ring Timeout (s)</Label><Input type="number" value={queueForm.timeout} onChange={e => setQueueForm({...queueForm, timeout: parseInt(e.target.value)||30})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Max Wait (s)</Label><Input type="number" value={queueForm.max_wait} onChange={e => setQueueForm({...queueForm, max_wait: parseInt(e.target.value)||300})} /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Members (ext numbers, comma-separated)</Label><Input value={queueForm.members} onChange={e => setQueueForm({...queueForm, members: e.target.value})} placeholder="1001, 1002, 1003" /></div>
            <div className="flex gap-3"><Button variant="outline" className="flex-1" onClick={() => setShowQueueForm(false)}>Cancel</Button><Button className="flex-1" onClick={saveQueue}><Save size={14} className="mr-1" /> Create</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ===== RULE FORM DIALOG ===== */}
      <Dialog open={showRuleForm} onOpenChange={setShowRuleForm}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Add Outgoing Rule</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Rule Name *</Label><Input value={ruleForm.name} onChange={e => setRuleForm({...ruleForm, name: e.target.value})} /></div>
            <div className="space-y-1.5"><Label className="text-xs">Number Pattern (regex)</Label><Input value={ruleForm.pattern} onChange={e => setRuleForm({...ruleForm, pattern: e.target.value})} placeholder="^\\+1.*" className="font-mono text-xs" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Action</Label>
                <Select value={ruleForm.action} onValueChange={v => setRuleForm({...ruleForm, action: v})}><SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="allow">Allow</SelectItem><SelectItem value="block">Block</SelectItem><SelectItem value="prefix">Add Prefix</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs">Priority</Label><Input type="number" value={ruleForm.priority} onChange={e => setRuleForm({...ruleForm, priority: parseInt(e.target.value)||10})} /></div>
            </div>
            {ruleForm.action === 'prefix' && <div className="space-y-1.5"><Label className="text-xs">Prefix to Add</Label><Input value={ruleForm.prefix} onChange={e => setRuleForm({...ruleForm, prefix: e.target.value})} placeholder="9" /></div>}
            <div className="flex gap-3"><Button variant="outline" className="flex-1" onClick={() => setShowRuleForm(false)}>Cancel</Button><Button className="flex-1" onClick={saveRule}><Save size={14} className="mr-1" /> Add Rule</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
