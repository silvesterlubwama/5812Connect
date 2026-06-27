/**
 * PBX Admin — Phase 1.
 *
 * One page, six tabs. Each tab is a CRUD list for a PBX entity. The Config
 * tab renders the live Asterisk config files (pjsip / extensions / voicemail)
 * so admins can audit what the appliance will pull on the next reload.
 *
 * All endpoints under /api/pbx/* require admin role — non-admins should not
 * see the sidebar entry that links here.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Textarea } from '../components/ui/textarea';
import { Phone, Server, ArrowDownToLine, ArrowUpFromLine, Users, ListTree, FileCode, Plus, Trash2, Pencil, Copy, RefreshCw, Check, X, BarChart3, Mic, Headphones } from 'lucide-react';
import api from '../services/api';
import { toast } from 'sonner';
import EmptyState from '../components/EmptyState';
import PBXAnalytics from '../components/PBXAnalytics';

const TRANSPORTS = [
  { value: 'transport-udp', label: 'UDP (most hardphones)' },
  { value: 'transport-tcp', label: 'TCP' },
  { value: 'transport-wss', label: 'WebRTC / WSS (browser softphone)' },
];

const CODECS = ['ulaw', 'alaw', 'opus', 'gsm', 'g722', 'g729'];

export default function PBXAdminPage() {
  const [tab, setTab] = useState('extensions');
  // Lists
  const [extensions, setExtensions] = useState([]);
  const [trunks, setTrunks] = useState([]);
  const [inbound, setInbound] = useState([]);
  const [outbound, setOutbound] = useState([]);
  const [huntGroups, setHuntGroups] = useState([]);
  const [ivrs, setIvrs] = useState([]);
  const [queues, setQueues] = useState([]);
  const [recSettings, setRecSettings] = useState({ retention_days: 30, format: 'wav', stereo: true, announce_recording: false, storage_path: '/var/spool/asterisk/monitor' });
  const [configBundle, setConfigBundle] = useState(null);
  const [loading, setLoading] = useState(true);
  // Dialogs
  const [editingExt, setEditingExt] = useState(null);
  const [editingTrunk, setEditingTrunk] = useState(null);
  const [editingInb, setEditingInb] = useState(null);
  const [editingOut, setEditingOut] = useState(null);
  const [editingHg, setEditingHg] = useState(null);
  const [editingIvr, setEditingIvr] = useState(null);
  const [editingQ, setEditingQ] = useState(null);
  const [showConfig, setShowConfig] = useState({ open: false, fname: 'pjsip.conf' });

  const fetchAll = async () => {
    setLoading(true);
    const calls = [
      ['extensions', '/pbx/extensions'],
      ['trunks', '/pbx/trunks'],
      ['inbound', '/pbx/inbound-routes'],
      ['outbound', '/pbx/outbound-routes'],
      ['hunt_groups', '/pbx/hunt-groups'],
      ['ivrs', '/pbx/ivrs'],
      ['queues', '/pbx/queues'],
      ['rec', '/pbx/recording-settings'],
    ];
    const results = await Promise.allSettled(calls.map(([_, url]) => api.get(url)));
    results.forEach((r, idx) => {
      const [name] = calls[idx];
      const data = r.status === 'fulfilled' ? (r.value.data ?? (Array.isArray(r.value.data) ? [] : {})) : [];
      if (name === 'extensions') setExtensions(data || []);
      if (name === 'trunks') setTrunks(data || []);
      if (name === 'inbound') setInbound(data || []);
      if (name === 'outbound') setOutbound(data || []);
      if (name === 'hunt_groups') setHuntGroups(data || []);
      if (name === 'ivrs') setIvrs(data || []);
      if (name === 'queues') setQueues(data || []);
      if (name === 'rec' && data && !Array.isArray(data)) setRecSettings(data);
    });
    setLoading(false);
  };
  useEffect(() => { fetchAll(); }, []);

  const trunksById = useMemo(() => Object.fromEntries(trunks.map(t => [t.id, t])), [trunks]);
  const extsById = useMemo(() => Object.fromEntries(extensions.map(e => [e.id, e])), [extensions]);
  const hgsById = useMemo(() => Object.fromEntries(huntGroups.map(h => [h.id, h])), [huntGroups]);
  const ivrsById = useMemo(() => Object.fromEntries(ivrs.map(v => [v.id, v])), [ivrs]);
  const queuesById = useMemo(() => Object.fromEntries(queues.map(q => [q.id, q])), [queues]);
  const allSkills = useMemo(() => {
    const s = new Set();
    extensions.forEach(e => (e.skills || []).forEach(sk => s.add(sk)));
    queues.forEach(q => (q.required_skills || []).forEach(sk => s.add(sk)));
    return Array.from(s).sort();
  }, [extensions, queues]);

  const refreshConfig = async () => {
    try {
      const r = await api.get('/pbx/config-bundle');
      setConfigBundle(r.data);
    } catch { toast.error('Failed to render config'); }
  };

  // ── generic save/delete helpers ────────────────────────────────
  const save = async (entity, url, body, setter, listRef) => {
    try {
      if (body.id) {
        await api.put(`${url}/${body.id}`, body);
        toast.success(`${entity} updated`);
      } else {
        await api.post(url, body);
        toast.success(`${entity} created`);
      }
      setter(null);
      const r = await api.get(url);
      listRef(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
  };
  const remove = async (entity, url, id, listRef) => {
    if (!window.confirm(`Delete this ${entity}?`)) return;
    try {
      await api.delete(`${url}/${id}`);
      toast.success(`${entity} deleted`);
      const r = await api.get(url);
      listRef(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || 'Delete failed'); }
  };

  return (
    <div className="space-y-4" data-testid="pbx-admin-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Phone size={22} /> PBX Admin</h1>
          <p className="text-sm text-muted-foreground">Manage extensions, SIP trunks, and call routing for your in-app phone system.</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={fetchAll} disabled={loading} data-testid="pbx-refresh">
            <RefreshCw size={12} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
          <Button size="sm" onClick={() => { refreshConfig(); setShowConfig({ open: true, fname: 'pjsip.conf' }); }} data-testid="pbx-view-config">
            <FileCode size={12} className="mr-1" /> Preview Asterisk config
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="extensions" data-testid="pbx-tab-extensions"><Phone size={11} className="mr-1" /> Extensions ({extensions.length})</TabsTrigger>
          <TabsTrigger value="trunks" data-testid="pbx-tab-trunks"><Server size={11} className="mr-1" /> SIP Trunks ({trunks.length})</TabsTrigger>
          <TabsTrigger value="inbound" data-testid="pbx-tab-inbound"><ArrowDownToLine size={11} className="mr-1" /> Inbound ({inbound.length})</TabsTrigger>
          <TabsTrigger value="outbound" data-testid="pbx-tab-outbound"><ArrowUpFromLine size={11} className="mr-1" /> Outbound ({outbound.length})</TabsTrigger>
          <TabsTrigger value="hunt" data-testid="pbx-tab-hunt"><Users size={11} className="mr-1" /> Hunt groups ({huntGroups.length})</TabsTrigger>
          <TabsTrigger value="queues" data-testid="pbx-tab-queues"><Headphones size={11} className="mr-1" /> Queues ({queues.length})</TabsTrigger>
          <TabsTrigger value="ivr" data-testid="pbx-tab-ivr"><ListTree size={11} className="mr-1" /> IVRs ({ivrs.length})</TabsTrigger>
          <TabsTrigger value="recording" data-testid="pbx-tab-recording"><Mic size={11} className="mr-1" /> Recording</TabsTrigger>
          <TabsTrigger value="analytics" data-testid="pbx-tab-analytics"><BarChart3 size={11} className="mr-1" /> Analytics</TabsTrigger>
        </TabsList>

        {/* ─── Extensions ──────────────────────────────────────────── */}
        <TabsContent value="extensions">
          <Card><CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-xs text-muted-foreground">Each extension = one phone (softphone, hardphone, or browser). The secret is the SIP password to register.</p>
              <Button size="sm" onClick={() => setEditingExt({ transport: 'transport-udp', allowed_codecs: ['ulaw', 'alaw', 'opus'], max_contacts: 3, voicemail_enabled: true, is_enabled: true })} data-testid="pbx-add-extension"><Plus size={11} className="mr-1" /> Extension</Button>
            </div>
            {extensions.length === 0 && !loading && <EmptyState title="No extensions yet" description="Create one to register a softphone or desk phone." />}
            <div className="grid gap-2">
              {extensions.map(e => (
                <div key={e.id} className="border rounded-lg p-2 flex items-center gap-3" data-testid={`pbx-ext-${e.id}`}>
                  <Badge className="text-sm font-mono">{e.number}</Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{e.display_name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {e.transport.replace('transport-', '')} · {(e.allowed_codecs || []).join('/')} · {e.voicemail_enabled ? `VM PIN ${e.voicemail_pin}` : 'No VM'}
                    </p>
                  </div>
                  {!e.is_enabled && <Badge variant="outline" className="text-[10px]">disabled</Badge>}
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => navigator.clipboard.writeText(e.secret).then(() => toast.success('SIP secret copied'))} title="Copy SIP secret" data-testid={`pbx-ext-copy-secret-${e.id}`}><Copy size={11} /></Button>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingExt(e)} data-testid={`pbx-ext-edit-${e.id}`}><Pencil size={11} /></Button>
                  <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => remove('extension', '/pbx/extensions', e.id, setExtensions)} data-testid={`pbx-ext-del-${e.id}`}><Trash2 size={11} /></Button>
                </div>
              ))}
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── Trunks ──────────────────────────────────────────────── */}
        <TabsContent value="trunks">
          <Card><CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-xs text-muted-foreground">SIP trunks connect your PBX to a carrier (your VoIP provider) so calls can leave & enter the building.</p>
              <Button size="sm" onClick={() => setEditingTrunk({ port: 5060, transport: 'transport-udp', register: true, allowed_codecs: ['ulaw', 'alaw'], is_enabled: true, did_numbers: [] })} data-testid="pbx-add-trunk"><Plus size={11} className="mr-1" /> Trunk</Button>
            </div>
            {trunks.length === 0 && !loading && <EmptyState title="No trunks yet" description="Add your VoIP provider's SIP credentials." />}
            <div className="grid gap-2">
              {trunks.map(t => (
                <div key={t.id} className="border rounded-lg p-2 flex items-center gap-3" data-testid={`pbx-trunk-${t.id}`}>
                  <Server size={14} className="text-primary shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{t.name}</p>
                    <p className="text-[10px] text-muted-foreground">{t.host}:{t.port} · {t.transport.replace('transport-', '')} · user {t.username || '—'} · {t.register ? 'register' : 'no register'}</p>
                    {(t.did_numbers || []).length > 0 && <p className="text-[10px] text-muted-foreground">DIDs: {t.did_numbers.join(', ')}</p>}
                  </div>
                  {!t.is_enabled && <Badge variant="outline" className="text-[10px]">disabled</Badge>}
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingTrunk(t)} data-testid={`pbx-trunk-edit-${t.id}`}><Pencil size={11} /></Button>
                  <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => remove('trunk', '/pbx/trunks', t.id, setTrunks)} data-testid={`pbx-trunk-del-${t.id}`}><Trash2 size={11} /></Button>
                </div>
              ))}
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── Inbound Routes ──────────────────────────────────────── */}
        <TabsContent value="inbound">
          <Card><CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-xs text-muted-foreground">When a call comes in from a trunk, where should it ring? Match by DID pattern.</p>
              <Button size="sm" onClick={() => setEditingInb({ destination_type: 'extension', fallback_type: 'voicemail' })} data-testid="pbx-add-inbound"><Plus size={11} className="mr-1" /> Inbound route</Button>
            </div>
            {inbound.length === 0 && !loading && <EmptyState title="No inbound routes" />}
            <div className="grid gap-2">
              {inbound.map(r => (
                <div key={r.id} className="border rounded-lg p-2 flex items-center gap-3" data-testid={`pbx-inb-${r.id}`}>
                  <Badge className="font-mono text-[11px]">{r.did_pattern}</Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{r.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      → {r.destination_type} {r.destination_type === 'extension' && extsById[r.destination_id] ? `(${extsById[r.destination_id].number})` : ''}
                      {r.destination_type === 'hunt_group' && hgsById[r.destination_id] ? `(${hgsById[r.destination_id].name})` : ''}
                      {r.destination_type === 'ivr' && ivrsById[r.destination_id] ? `(${ivrsById[r.destination_id].name})` : ''}
                      {r.trunk_id ? ` · via ${trunksById[r.trunk_id]?.name || r.trunk_id}` : ''}
                    </p>
                  </div>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingInb(r)} data-testid={`pbx-inb-edit-${r.id}`}><Pencil size={11} /></Button>
                  <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => remove('inbound route', '/pbx/inbound-routes', r.id, setInbound)} data-testid={`pbx-inb-del-${r.id}`}><Trash2 size={11} /></Button>
                </div>
              ))}
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── Outbound Routes ─────────────────────────────────────── */}
        <TabsContent value="outbound">
          <Card><CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-xs text-muted-foreground">When a user dials a number, which trunk should carry it? Routes are evaluated in priority order (lowest first).</p>
              <Button size="sm" onClick={() => setEditingOut({ priority: 100, strip: 0, prepend: '' })} data-testid="pbx-add-outbound"><Plus size={11} className="mr-1" /> Outbound route</Button>
            </div>
            {outbound.length === 0 && !loading && <EmptyState title="No outbound routes" />}
            <div className="grid gap-2">
              {outbound.map(r => (
                <div key={r.id} className="border rounded-lg p-2 flex items-center gap-3" data-testid={`pbx-out-${r.id}`}>
                  <Badge variant="outline" className="font-mono text-[11px]">#{r.priority}</Badge>
                  <Badge className="font-mono text-[11px]">{r.pattern}</Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{r.name}</p>
                    <p className="text-[10px] text-muted-foreground">→ trunk {trunksById[r.trunk_id]?.name || '?'}{r.strip ? ` · strip ${r.strip}` : ''}{r.prepend ? ` · prepend "${r.prepend}"` : ''}</p>
                  </div>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingOut(r)} data-testid={`pbx-out-edit-${r.id}`}><Pencil size={11} /></Button>
                  <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => remove('outbound route', '/pbx/outbound-routes', r.id, setOutbound)}><Trash2 size={11} /></Button>
                </div>
              ))}
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── Hunt groups ─────────────────────────────────────────── */}
        <TabsContent value="hunt">
          <Card><CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-xs text-muted-foreground">Ring multiple extensions at once (sales team, reception, etc.).</p>
              <Button size="sm" onClick={() => setEditingHg({ strategy: 'ringall', member_extension_ids: [], ring_timeout: 20, fallback_type: 'voicemail' })} data-testid="pbx-add-hg"><Plus size={11} className="mr-1" /> Hunt group</Button>
            </div>
            {huntGroups.length === 0 && !loading && <EmptyState title="No hunt groups" />}
            <div className="grid gap-2">
              {huntGroups.map(h => (
                <div key={h.id} className="border rounded-lg p-2 flex items-center gap-3" data-testid={`pbx-hg-${h.id}`}>
                  <Users size={14} className="text-primary" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{h.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {h.strategy} · {(h.member_extension_ids || []).length} members · {h.ring_timeout}s
                    </p>
                  </div>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingHg(h)} data-testid={`pbx-hg-edit-${h.id}`}><Pencil size={11} /></Button>
                  <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => remove('hunt group', '/pbx/hunt-groups', h.id, setHuntGroups)}><Trash2 size={11} /></Button>
                </div>
              ))}
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── Queues ──────────────────────────────────────────────── */}
        <TabsContent value="queues">
          <Card><CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-xs text-muted-foreground">Skill-based call queues. Add agents (extensions) and optional required skills — only agents carrying ALL required skill tags will be rung.</p>
              <Button size="sm" onClick={() => setEditingQ({ strategy: 'ringall', agent_extension_ids: [], required_skills: [], ring_timeout: 20, wrapup_time: 5, max_wait: 120, moh_class: 'default', is_enabled: true })} data-testid="pbx-add-queue"><Plus size={11} className="mr-1" /> Queue</Button>
            </div>
            {queues.length === 0 && !loading && <EmptyState title="No queues yet" description="Create one to route inbound calls by agent skill." />}
            <div className="grid gap-2">
              {queues.map(q => {
                const required = q.required_skills || [];
                const eligibleAgents = (q.agent_extension_ids || []).filter(id => {
                  const e = extsById[id];
                  if (!e) return false;
                  const skills = new Set(e.skills || []);
                  return required.every(s => skills.has(s));
                });
                return (
                  <div key={q.id} className="border rounded-lg p-2 flex items-center gap-3" data-testid={`pbx-queue-${q.id}`}>
                    <Headphones size={14} className="text-primary" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">{q.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {q.strategy} · {eligibleAgents.length}/{(q.agent_extension_ids || []).length} eligible agents · wait≤{q.max_wait}s
                        {required.length > 0 && ` · skills: ${required.join(', ')}`}
                      </p>
                    </div>
                    {!q.is_enabled && <Badge variant="outline" className="text-[10px]">disabled</Badge>}
                    <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingQ(q)} data-testid={`pbx-queue-edit-${q.id}`}><Pencil size={11} /></Button>
                    <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => remove('queue', '/pbx/queues', q.id, setQueues)} data-testid={`pbx-queue-del-${q.id}`}><Trash2 size={11} /></Button>
                  </div>
                );
              })}
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── IVRs ────────────────────────────────────────────────── */}
        <TabsContent value="ivr">
          <Card><CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-xs text-muted-foreground">Auto-attendant menus. "Press 1 for sales, 2 for support…"</p>
              <Button size="sm" onClick={() => setEditingIvr({ name: '', options: {}, timeout_sec: 10, max_retries: 2, timeout_type: 'hangup', invalid_type: 'hangup' })} data-testid="pbx-add-ivr"><Plus size={11} className="mr-1" /> IVR</Button>
            </div>
            {ivrs.length === 0 && !loading && <EmptyState title="No IVRs" />}
            <div className="grid gap-2">
              {ivrs.map(v => (
                <div key={v.id} className="border rounded-lg p-2 flex items-center gap-3" data-testid={`pbx-ivr-${v.id}`}>
                  <ListTree size={14} className="text-primary" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{v.name}</p>
                    <p className="text-[10px] text-muted-foreground">{Object.keys(v.options || {}).length} options · timeout {v.timeout_sec}s</p>
                  </div>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingIvr(v)} data-testid={`pbx-ivr-edit-${v.id}`}><Pencil size={11} /></Button>
                  <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => remove('IVR', '/pbx/ivrs', v.id, setIvrs)}><Trash2 size={11} /></Button>
                </div>
              ))}
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── Recording settings ─────────────────────────────────── */}
        <TabsContent value="recording">
          <Card><CardContent className="p-3 space-y-3" data-testid="pbx-recording-panel">
            <p className="text-xs text-muted-foreground">Global call recording policy. Per-extension recording is toggled on each extension. Files older than the retention window are auto-unlinked from the analytics dashboard (run the purge manually below).</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Retention (days)</Label>
                <Input type="number" min={1} max={3650} value={recSettings.retention_days}
                       onChange={e => setRecSettings({ ...recSettings, retention_days: parseInt(e.target.value) || 1 })}
                       data-testid="rec-retention-days" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">File format</Label>
                <Select value={recSettings.format} onValueChange={v => setRecSettings({ ...recSettings, format: v })}>
                  <SelectTrigger data-testid="rec-format"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="wav">wav</SelectItem>
                    <SelectItem value="wav49">wav49 (smaller)</SelectItem>
                    <SelectItem value="gsm">gsm</SelectItem>
                    <SelectItem value="g722">g722 (HD)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1 col-span-2">
                <Label className="text-xs">Asterisk storage path (on the appliance)</Label>
                <Input value={recSettings.storage_path || ''}
                       onChange={e => setRecSettings({ ...recSettings, storage_path: e.target.value })}
                       placeholder="/var/spool/asterisk/monitor"
                       data-testid="rec-storage-path" />
              </div>
              <label className="flex items-center gap-2 text-xs col-span-2">
                <input type="checkbox" checked={!!recSettings.stereo} onChange={e => setRecSettings({ ...recSettings, stereo: e.target.checked })} data-testid="rec-stereo" />
                Stereo (separate channels — caller / agent)
              </label>
              <label className="flex items-center gap-2 text-xs col-span-2">
                <input type="checkbox" checked={!!recSettings.announce_recording} onChange={e => setRecSettings({ ...recSettings, announce_recording: e.target.checked })} data-testid="rec-announce" />
                Play a beep before each recorded call (compliance)
              </label>
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={async () => {
                try { await api.put('/pbx/recording-settings', recSettings); toast.success('Recording settings saved'); }
                catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
              }} data-testid="rec-save">Save settings</Button>
              <Button size="sm" variant="outline" onClick={async () => {
                if (!window.confirm(`Unlink recordings older than ${recSettings.retention_days} day(s)?`)) return;
                try {
                  const r = await api.post('/pbx/recording-retention/purge');
                  toast.success(`Purged ${r.data.purged} recording(s)`);
                } catch (e) { toast.error(e.response?.data?.detail || 'Purge failed'); }
              }} data-testid="rec-purge">Run retention purge now</Button>
            </div>
            <div className="border-t pt-2 text-[11px] text-muted-foreground">
              <p>Recording is currently enabled on <strong>{extensions.filter(e => e.recording_enabled).length}</strong> of {extensions.length} extension(s).</p>
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* ─── Analytics ──────────────────────────────────────────── */}
        <TabsContent value="analytics">
          <PBXAnalytics />
        </TabsContent>
      </Tabs>

      {/* ─── Extension dialog ────────────────────────────────────── */}
      <Dialog open={!!editingExt} onOpenChange={(o) => { if (!o) setEditingExt(null); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="pbx-ext-dialog">
          <DialogHeader>
            <DialogTitle>{editingExt?.id ? `Edit extension ${editingExt?.number}` : 'New extension'}</DialogTitle>
            <DialogDescription className="text-xs">A phone identity. Hand the SIP secret to the user so they can configure their softphone or desk phone.</DialogDescription>
          </DialogHeader>
          {editingExt && (
            <div className="space-y-2 mt-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Extension number *</Label>
                  <Input value={editingExt.number || ''} onChange={e => setEditingExt({ ...editingExt, number: e.target.value })} placeholder="e.g. 101" data-testid="pbx-ext-number" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Transport</Label>
                  <Select value={editingExt.transport} onValueChange={v => setEditingExt({ ...editingExt, transport: v })}>
                    <SelectTrigger data-testid="pbx-ext-transport"><SelectValue /></SelectTrigger>
                    <SelectContent>{TRANSPORTS.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Display name</Label>
                <Input value={editingExt.display_name || ''} onChange={e => setEditingExt({ ...editingExt, display_name: e.target.value })} placeholder="Reception desk" data-testid="pbx-ext-name" />
              </div>
              <div className="grid grid-cols-3 gap-1">
                {CODECS.map(c => (
                  <label key={c} className="flex items-center gap-1 text-[11px]">
                    <input type="checkbox" checked={(editingExt.allowed_codecs || []).includes(c)} onChange={e => setEditingExt({
                      ...editingExt,
                      allowed_codecs: e.target.checked
                        ? [...(editingExt.allowed_codecs || []), c]
                        : (editingExt.allowed_codecs || []).filter(x => x !== c),
                    })} />
                    {c}
                  </label>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Max contacts</Label>
                  <Input type="number" value={editingExt.max_contacts || 1} onChange={e => setEditingExt({ ...editingExt, max_contacts: parseInt(e.target.value) || 1 })} />
                </div>
                <label className="flex items-center gap-2 text-xs pt-5">
                  <input type="checkbox" checked={!!editingExt.voicemail_enabled} onChange={e => setEditingExt({ ...editingExt, voicemail_enabled: e.target.checked })} />
                  Voicemail
                </label>
              </div>
              {editingExt.voicemail_enabled && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1"><Label className="text-xs">VM PIN (4 digits)</Label>
                    <Input value={editingExt.voicemail_pin || ''} onChange={e => setEditingExt({ ...editingExt, voicemail_pin: e.target.value })} maxLength={6} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">VM → email</Label>
                    <Input type="email" value={editingExt.voicemail_email || ''} onChange={e => setEditingExt({ ...editingExt, voicemail_email: e.target.value })} placeholder="optional" />
                  </div>
                </div>
              )}
              <div className="space-y-1"><Label className="text-xs">Outbound caller ID (optional)</Label>
                <Input value={editingExt.outbound_caller_id || ''} onChange={e => setEditingExt({ ...editingExt, outbound_caller_id: e.target.value })} placeholder="+1 555 010 0000" />
              </div>
              <div className="space-y-1 border-t pt-2">
                <Label className="text-xs flex items-center gap-1"><Mic size={11} /> Call recording</Label>
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={!!editingExt.recording_enabled}
                         onChange={e => setEditingExt({ ...editingExt, recording_enabled: e.target.checked })}
                         data-testid="pbx-ext-recording-enabled" />
                  Record every call placed to / from this extension (Asterisk MixMonitor)
                </label>
                <p className="text-[10px] text-muted-foreground">Retention is configured globally on the Recording tab. Recordings appear next to the CDR row.</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Skills (comma-separated, for queue routing)</Label>
                <Input
                  value={(editingExt.skills || []).join(', ')}
                  onChange={e => setEditingExt({ ...editingExt, skills: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                  placeholder="spanish, tier-2, billing"
                  data-testid="pbx-ext-skills"
                />
                {allSkills.length > 0 && (
                  <p className="text-[10px] text-muted-foreground">Existing skills in use: {allSkills.join(', ')}</p>
                )}
              </div>
              {editingExt.id && editingExt.secret && (
                <div className="rounded-lg bg-muted/30 p-2 text-[11px] space-y-1">
                  <p className="font-semibold">SIP credentials</p>
                  <p>Username: <code>{editingExt.number}</code></p>
                  <p className="flex items-center gap-2 break-all">Secret: <code className="bg-background px-1 rounded">{editingExt.secret}</code>
                    <Button size="sm" variant="ghost" className="h-6 px-1" onClick={() => navigator.clipboard.writeText(editingExt.secret).then(() => toast.success('Copied'))}><Copy size={10} /></Button>
                  </p>
                  <Button size="sm" variant="outline" className="h-6 text-[10px]" onClick={async () => {
                    if (!window.confirm('Rotate secret? The current softphone will deregister.')) return;
                    const r = await api.post(`/pbx/extensions/${editingExt.id}/rotate-secret`);
                    setEditingExt({ ...editingExt, secret: r.data.secret });
                    toast.success('New secret issued');
                  }} data-testid="pbx-ext-rotate-secret">
                    <RefreshCw size={9} className="mr-1" /> Rotate secret
                  </Button>
                </div>
              )}
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={editingExt.is_enabled !== false} onChange={e => setEditingExt({ ...editingExt, is_enabled: e.target.checked })} />
                Enabled
              </label>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingExt(null)}>Cancel</Button>
                <Button className="flex-1" onClick={() => save('Extension', '/pbx/extensions', editingExt, setEditingExt, setExtensions)} data-testid="pbx-ext-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ─── Trunk dialog ────────────────────────────────────────── */}
      <Dialog open={!!editingTrunk} onOpenChange={(o) => { if (!o) setEditingTrunk(null); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="pbx-trunk-dialog">
          <DialogHeader>
            <DialogTitle>{editingTrunk?.id ? `Edit ${editingTrunk?.name}` : 'New SIP trunk'}</DialogTitle>
            <DialogDescription className="text-xs">Your VoIP provider's connection details. They give these to you when you sign up.</DialogDescription>
          </DialogHeader>
          {editingTrunk && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Trunk name *</Label>
                <Input value={editingTrunk.name || ''} onChange={e => setEditingTrunk({ ...editingTrunk, name: e.target.value })} placeholder="MainStreet Voice" data-testid="pbx-trunk-name" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1 col-span-2"><Label className="text-xs">SIP host *</Label>
                  <Input value={editingTrunk.host || ''} onChange={e => setEditingTrunk({ ...editingTrunk, host: e.target.value })} placeholder="sip.provider.com" data-testid="pbx-trunk-host" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Port</Label>
                  <Input type="number" value={editingTrunk.port || 5060} onChange={e => setEditingTrunk({ ...editingTrunk, port: parseInt(e.target.value) || 5060 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Transport</Label>
                  <Select value={editingTrunk.transport} onValueChange={v => setEditingTrunk({ ...editingTrunk, transport: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{TRANSPORTS.filter(t => t.value !== 'transport-wss').map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">SIP username *</Label>
                  <Input value={editingTrunk.username || ''} onChange={e => setEditingTrunk({ ...editingTrunk, username: e.target.value })} data-testid="pbx-trunk-username" />
                </div>
                <div className="space-y-1"><Label className="text-xs">SIP secret *</Label>
                  <Input type="password" value={editingTrunk.secret || ''} onChange={e => setEditingTrunk({ ...editingTrunk, secret: e.target.value })} data-testid="pbx-trunk-secret" />
                </div>
              </div>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={!!editingTrunk.register} onChange={e => setEditingTrunk({ ...editingTrunk, register: e.target.checked })} />
                Register with carrier (most carriers need this for inbound calls)
              </label>
              <div className="space-y-1"><Label className="text-xs">DID numbers (one per line)</Label>
                <Textarea rows={2} value={(editingTrunk.did_numbers || []).join('\n')} onChange={e => setEditingTrunk({ ...editingTrunk, did_numbers: e.target.value.split('\n').map(s => s.trim()).filter(Boolean) })} placeholder="+15551234567" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Outbound caller ID (optional)</Label>
                <Input value={editingTrunk.outbound_caller_id || ''} onChange={e => setEditingTrunk({ ...editingTrunk, outbound_caller_id: e.target.value })} placeholder="+15551234567" />
              </div>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={editingTrunk.is_enabled !== false} onChange={e => setEditingTrunk({ ...editingTrunk, is_enabled: e.target.checked })} />
                Enabled
              </label>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingTrunk(null)}>Cancel</Button>
                <Button className="flex-1" onClick={() => save('Trunk', '/pbx/trunks', editingTrunk, setEditingTrunk, setTrunks)} data-testid="pbx-trunk-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ─── Inbound dialog ──────────────────────────────────────── */}
      <Dialog open={!!editingInb} onOpenChange={(o) => { if (!o) setEditingInb(null); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="pbx-inb-dialog">
          <DialogHeader><DialogTitle>{editingInb?.id ? 'Edit inbound route' : 'New inbound route'}</DialogTitle></DialogHeader>
          {editingInb && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Name</Label>
                <Input value={editingInb.name || ''} onChange={e => setEditingInb({ ...editingInb, name: e.target.value })} placeholder="Main line" />
              </div>
              <div className="space-y-1"><Label className="text-xs">DID pattern * <span className="text-muted-foreground font-normal">(Asterisk syntax — e.g. <code>_+15551234567</code> or <code>_+1NXXNXXXXXX</code>)</span></Label>
                <Input value={editingInb.did_pattern || ''} onChange={e => setEditingInb({ ...editingInb, did_pattern: e.target.value })} data-testid="pbx-inb-pattern" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Via trunk (optional)</Label>
                <Select value={editingInb.trunk_id || 'any'} onValueChange={v => setEditingInb({ ...editingInb, trunk_id: v === 'any' ? null : v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">— Any trunk —</SelectItem>
                    {trunks.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Destination</Label>
                  <Select value={editingInb.destination_type} onValueChange={v => setEditingInb({ ...editingInb, destination_type: v, destination_id: null })}>
                    <SelectTrigger data-testid="pbx-inb-dest-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="extension">Extension</SelectItem>
                      <SelectItem value="hunt_group">Hunt group</SelectItem>
                      <SelectItem value="queue">Queue</SelectItem>
                      <SelectItem value="ivr">IVR menu</SelectItem>
                      <SelectItem value="voicemail">Voicemail</SelectItem>
                      <SelectItem value="hangup">Hangup</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {editingInb.destination_type !== 'hangup' && (
                  <div className="space-y-1"><Label className="text-xs">Target</Label>
                    <Select value={editingInb.destination_id || ''} onValueChange={v => setEditingInb({ ...editingInb, destination_id: v })}>
                      <SelectTrigger><SelectValue placeholder="Pick…" /></SelectTrigger>
                      <SelectContent>
                        {editingInb.destination_type === 'extension' && extensions.map(e => <SelectItem key={e.id} value={e.id}>{e.number} · {e.display_name}</SelectItem>)}
                        {editingInb.destination_type === 'hunt_group' && huntGroups.map(h => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                        {editingInb.destination_type === 'queue' && queues.map(q => <SelectItem key={q.id} value={q.id}>{q.name}</SelectItem>)}
                        {editingInb.destination_type === 'ivr' && ivrs.map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}
                        {editingInb.destination_type === 'voicemail' && extensions.filter(e => e.voicemail_enabled).map(e => <SelectItem key={e.id} value={e.id}>{e.number} · {e.display_name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>

              {/* ── Time-of-day routing ─────────────────────────────── */}
              <div className="space-y-1 pt-2 border-t">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-semibold">Time-of-day overrides</Label>
                  <Button size="sm" variant="outline" className="h-7 text-[10px]" onClick={() => setEditingInb({
                    ...editingInb,
                    time_conditions: [...(editingInb.time_conditions || []), {
                      days: [1, 2, 3, 4, 5], start: '09:00', end: '17:00',
                      destination_type: 'extension', destination_id: null,
                    }],
                  })} data-testid="pbx-inb-add-tc"><Plus size={10} className="mr-1" /> Add window</Button>
                </div>
                <p className="text-[10px] text-muted-foreground">First matching window wins; outside all windows, the default destination above is used.</p>
                {(editingInb.time_conditions || []).map((tc, idx) => (
                  <div key={idx} className="border rounded p-2 space-y-2 bg-muted/20" data-testid={`pbx-inb-tc-${idx}`}>
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-medium">Window {idx + 1}</span>
                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-rose-600" onClick={() => setEditingInb({
                        ...editingInb,
                        time_conditions: (editingInb.time_conditions || []).filter((_, i) => i !== idx),
                      })} data-testid={`pbx-inb-tc-del-${idx}`}><Trash2 size={10} /></Button>
                    </div>
                    <div className="grid grid-cols-7 gap-1 text-center">
                      {[['Mon', 1], ['Tue', 2], ['Wed', 3], ['Thu', 4], ['Fri', 5], ['Sat', 6], ['Sun', 7]].map(([lbl, d]) => {
                        const checked = (tc.days || []).includes(d);
                        return (
                          <label key={d} className={`text-[10px] py-1 rounded cursor-pointer border ${checked ? 'bg-primary text-primary-foreground border-primary' : 'bg-background'}`}>
                            <input type="checkbox" className="hidden" checked={checked} onChange={e => {
                              const next = e.target.checked ? [...(tc.days || []), d] : (tc.days || []).filter(x => x !== d);
                              const conds = [...(editingInb.time_conditions || [])];
                              conds[idx] = { ...tc, days: next };
                              setEditingInb({ ...editingInb, time_conditions: conds });
                            }} />
                            {lbl}
                          </label>
                        );
                      })}
                    </div>
                    <div className="grid grid-cols-2 gap-1">
                      <Input type="time" value={tc.start || '09:00'} onChange={e => {
                        const conds = [...(editingInb.time_conditions || [])];
                        conds[idx] = { ...tc, start: e.target.value };
                        setEditingInb({ ...editingInb, time_conditions: conds });
                      }} className="h-7 text-[11px]" data-testid={`pbx-inb-tc-start-${idx}`} />
                      <Input type="time" value={tc.end || '17:00'} onChange={e => {
                        const conds = [...(editingInb.time_conditions || [])];
                        conds[idx] = { ...tc, end: e.target.value };
                        setEditingInb({ ...editingInb, time_conditions: conds });
                      }} className="h-7 text-[11px]" data-testid={`pbx-inb-tc-end-${idx}`} />
                    </div>
                    <div className="grid grid-cols-2 gap-1">
                      <Select value={tc.destination_type || 'extension'} onValueChange={v => {
                        const conds = [...(editingInb.time_conditions || [])];
                        conds[idx] = { ...tc, destination_type: v, destination_id: null };
                        setEditingInb({ ...editingInb, time_conditions: conds });
                      }}>
                        <SelectTrigger className="h-7 text-[11px]"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="extension">Extension</SelectItem>
                          <SelectItem value="hunt_group">Hunt group</SelectItem>
                          <SelectItem value="ivr">IVR</SelectItem>
                          <SelectItem value="voicemail">Voicemail</SelectItem>
                          <SelectItem value="hangup">Hangup</SelectItem>
                        </SelectContent>
                      </Select>
                      {tc.destination_type !== 'hangup' && (
                        <Select value={tc.destination_id || ''} onValueChange={v => {
                          const conds = [...(editingInb.time_conditions || [])];
                          conds[idx] = { ...tc, destination_id: v };
                          setEditingInb({ ...editingInb, time_conditions: conds });
                        }}>
                          <SelectTrigger className="h-7 text-[11px]"><SelectValue placeholder="…" /></SelectTrigger>
                          <SelectContent>
                            {tc.destination_type === 'extension' && extensions.map(e => <SelectItem key={e.id} value={e.id}>{e.number}</SelectItem>)}
                            {tc.destination_type === 'hunt_group' && huntGroups.map(h => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                            {tc.destination_type === 'ivr' && ivrs.map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}
                            {tc.destination_type === 'voicemail' && extensions.filter(e => e.voicemail_enabled).map(e => <SelectItem key={e.id} value={e.id}>{e.number}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingInb(null)}>Cancel</Button>
                <Button className="flex-1" onClick={() => save('Inbound route', '/pbx/inbound-routes', editingInb, setEditingInb, setInbound)} data-testid="pbx-inb-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ─── Outbound dialog ─────────────────────────────────────── */}
      <Dialog open={!!editingOut} onOpenChange={(o) => { if (!o) setEditingOut(null); }}>
        <DialogContent className="max-w-md" data-testid="pbx-out-dialog">
          <DialogHeader><DialogTitle>{editingOut?.id ? 'Edit outbound route' : 'New outbound route'}</DialogTitle></DialogHeader>
          {editingOut && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Name</Label>
                <Input value={editingOut.name || ''} onChange={e => setEditingOut({ ...editingOut, name: e.target.value })} placeholder="US national" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Pattern *</Label>
                  <Input value={editingOut.pattern || ''} onChange={e => setEditingOut({ ...editingOut, pattern: e.target.value })} placeholder="_1NXXNXXXXXX" data-testid="pbx-out-pattern" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Priority</Label>
                  <Input type="number" value={editingOut.priority || 100} onChange={e => setEditingOut({ ...editingOut, priority: parseInt(e.target.value) || 100 })} />
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Trunk *</Label>
                <Select value={editingOut.trunk_id || ''} onValueChange={v => setEditingOut({ ...editingOut, trunk_id: v })}>
                  <SelectTrigger data-testid="pbx-out-trunk"><SelectValue placeholder="Pick a trunk…" /></SelectTrigger>
                  <SelectContent>{trunks.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Strip leading digits</Label>
                  <Input type="number" value={editingOut.strip || 0} onChange={e => setEditingOut({ ...editingOut, strip: parseInt(e.target.value) || 0 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Prepend</Label>
                  <Input value={editingOut.prepend || ''} onChange={e => setEditingOut({ ...editingOut, prepend: e.target.value })} placeholder="+1" />
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Caller ID override (optional)</Label>
                <Input value={editingOut.caller_id_override || ''} onChange={e => setEditingOut({ ...editingOut, caller_id_override: e.target.value })} placeholder="+15551234567" />
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingOut(null)}>Cancel</Button>
                <Button className="flex-1" onClick={() => save('Outbound route', '/pbx/outbound-routes', editingOut, setEditingOut, setOutbound)} data-testid="pbx-out-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ─── Hunt group dialog ───────────────────────────────────── */}
      <Dialog open={!!editingHg} onOpenChange={(o) => { if (!o) setEditingHg(null); }}>
        <DialogContent className="max-w-md" data-testid="pbx-hg-dialog">
          <DialogHeader><DialogTitle>{editingHg?.id ? 'Edit hunt group' : 'New hunt group'}</DialogTitle></DialogHeader>
          {editingHg && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Name *</Label>
                <Input value={editingHg.name || ''} onChange={e => setEditingHg({ ...editingHg, name: e.target.value })} placeholder="Sales team" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Strategy</Label>
                <Select value={editingHg.strategy || 'ringall'} onValueChange={v => setEditingHg({ ...editingHg, strategy: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ringall">Ring all at once</SelectItem>
                    <SelectItem value="hunt">Hunt — ring in order</SelectItem>
                    <SelectItem value="random">Random</SelectItem>
                    <SelectItem value="least_recent">Least recently rung</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1"><Label className="text-xs">Members</Label>
                <div className="grid grid-cols-2 gap-1 max-h-44 overflow-y-auto border rounded p-2">
                  {extensions.map(e => (
                    <label key={e.id} className="flex items-center gap-1 text-[11px]">
                      <input type="checkbox" checked={(editingHg.member_extension_ids || []).includes(e.id)} onChange={ev => setEditingHg({
                        ...editingHg,
                        member_extension_ids: ev.target.checked
                          ? [...(editingHg.member_extension_ids || []), e.id]
                          : (editingHg.member_extension_ids || []).filter(x => x !== e.id),
                      })} />
                      {e.number} · {e.display_name}
                    </label>
                  ))}
                </div>
              </div>
              <div className="space-y-1"><Label className="text-xs">Ring timeout (sec)</Label>
                <Input type="number" value={editingHg.ring_timeout || 20} onChange={e => setEditingHg({ ...editingHg, ring_timeout: parseInt(e.target.value) || 20 })} />
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingHg(null)}>Cancel</Button>
                <Button className="flex-1" onClick={() => save('Hunt group', '/pbx/hunt-groups', editingHg, setEditingHg, setHuntGroups)} data-testid="pbx-hg-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ─── Queue dialog ────────────────────────────────────────── */}
      <Dialog open={!!editingQ} onOpenChange={(o) => { if (!o) setEditingQ(null); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="pbx-queue-dialog">
          <DialogHeader>
            <DialogTitle>{editingQ?.id ? 'Edit queue' : 'New queue'}</DialogTitle>
            <DialogDescription className="text-xs">Skill-based call queues route inbound calls to agents tagged with the matching skills.</DialogDescription>
          </DialogHeader>
          {editingQ && (
            <div className="space-y-2 mt-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Name *</Label>
                  <Input value={editingQ.name || ''} onChange={e => setEditingQ({ ...editingQ, name: e.target.value })} placeholder="Sales — Spanish line" data-testid="pbx-queue-name" />
                </div>
                <div className="space-y-1"><Label className="text-xs">Internal extension (optional)</Label>
                  <Input value={editingQ.extension_number || ''} onChange={e => setEditingQ({ ...editingQ, extension_number: e.target.value })} placeholder="e.g. 700" data-testid="pbx-queue-extension" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Strategy</Label>
                  <Select value={editingQ.strategy || 'ringall'} onValueChange={v => setEditingQ({ ...editingQ, strategy: v })}>
                    <SelectTrigger data-testid="pbx-queue-strategy"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ringall">Ring all at once</SelectItem>
                      <SelectItem value="leastrecent">Least recently called</SelectItem>
                      <SelectItem value="fewestcalls">Fewest calls handled</SelectItem>
                      <SelectItem value="random">Random</SelectItem>
                      <SelectItem value="rrmemory">Round robin (with memory)</SelectItem>
                      <SelectItem value="linear">Linear (in order)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">Max wait (sec)</Label>
                  <Input type="number" min={10} max={3600} value={editingQ.max_wait || 120}
                         onChange={e => setEditingQ({ ...editingQ, max_wait: parseInt(e.target.value) || 120 })} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1"><Label className="text-xs">Ring timeout (sec)</Label>
                  <Input type="number" min={5} max={120} value={editingQ.ring_timeout || 20}
                         onChange={e => setEditingQ({ ...editingQ, ring_timeout: parseInt(e.target.value) || 20 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Wrapup (sec)</Label>
                  <Input type="number" min={0} max={300} value={editingQ.wrapup_time || 5}
                         onChange={e => setEditingQ({ ...editingQ, wrapup_time: parseInt(e.target.value) || 0 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">MOH class</Label>
                  <Input value={editingQ.moh_class || 'default'} onChange={e => setEditingQ({ ...editingQ, moh_class: e.target.value })} placeholder="default" />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Required skills (comma-separated)</Label>
                <Input
                  value={(editingQ.required_skills || []).join(', ')}
                  onChange={e => setEditingQ({ ...editingQ, required_skills: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                  placeholder="spanish, billing"
                  data-testid="pbx-queue-skills"
                />
                <p className="text-[10px] text-muted-foreground">Agents must carry ALL listed skills to be eligible. Leave blank for no skill gating.</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Agents</Label>
                <div className="grid grid-cols-2 gap-1 max-h-44 overflow-y-auto border rounded p-2" data-testid="pbx-queue-agents">
                  {extensions.map(e => {
                    const skills = new Set(e.skills || []);
                    const eligible = (editingQ.required_skills || []).every(s => skills.has(s));
                    return (
                      <label key={e.id} className={`flex items-center gap-1 text-[11px] ${!eligible ? 'opacity-50' : ''}`}>
                        <input type="checkbox" checked={(editingQ.agent_extension_ids || []).includes(e.id)} onChange={ev => setEditingQ({
                          ...editingQ,
                          agent_extension_ids: ev.target.checked
                            ? [...(editingQ.agent_extension_ids || []), e.id]
                            : (editingQ.agent_extension_ids || []).filter(x => x !== e.id),
                        })} />
                        {e.number} · {e.display_name}
                        {!eligible && <span className="text-rose-600 text-[9px]">(missing skill)</span>}
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={!!editingQ.announce_position}
                         onChange={e => setEditingQ({ ...editingQ, announce_position: e.target.checked })} />
                  Announce queue position
                </label>
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={!!editingQ.announce_holdtime}
                         onChange={e => setEditingQ({ ...editingQ, announce_holdtime: e.target.checked })} />
                  Announce hold time
                </label>
              </div>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={editingQ.is_enabled !== false} onChange={e => setEditingQ({ ...editingQ, is_enabled: e.target.checked })} />
                Enabled
              </label>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingQ(null)}>Cancel</Button>
                <Button className="flex-1" onClick={() => save('Queue', '/pbx/queues', editingQ, setEditingQ, setQueues)} data-testid="pbx-queue-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ─── IVR dialog ──────────────────────────────────────────── */}
      <Dialog open={!!editingIvr} onOpenChange={(o) => { if (!o) setEditingIvr(null); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="pbx-ivr-dialog">
          <DialogHeader><DialogTitle>{editingIvr?.id ? 'Edit IVR' : 'New IVR'}</DialogTitle></DialogHeader>
          {editingIvr && (
            <div className="space-y-2 mt-2">
              <div className="space-y-1"><Label className="text-xs">Name *</Label>
                <Input value={editingIvr.name || ''} onChange={e => setEditingIvr({ ...editingIvr, name: e.target.value })} placeholder="Main menu" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Prompt text (TTS fallback)</Label>
                <Textarea rows={2} value={editingIvr.prompt_text || ''} onChange={e => setEditingIvr({ ...editingIvr, prompt_text: e.target.value })} placeholder="Press 1 for sales, 2 for support" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Prompt audio URL (optional)</Label>
                <Input value={editingIvr.prompt_audio_url || ''} onChange={e => setEditingIvr({ ...editingIvr, prompt_audio_url: e.target.value })} placeholder="custom/welcome" />
              </div>
              <div className="space-y-1"><Label className="text-xs">Menu options</Label>
                <div className="space-y-1">
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 0].map(k => {
                    const key = String(k);
                    const opt = editingIvr.options?.[key] || { type: '', id: '' };
                    return (
                      <div key={key} className="flex items-center gap-1">
                        <Badge className="font-mono w-7 justify-center">{k}</Badge>
                        <Select value={opt.type || 'none'} onValueChange={v => {
                          const next = { ...(editingIvr.options || {}) };
                          if (v === 'none') delete next[key]; else next[key] = { ...next[key], type: v, id: '' };
                          setEditingIvr({ ...editingIvr, options: next });
                        }}>
                          <SelectTrigger className="flex-1 h-7 text-[11px]"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">— not used —</SelectItem>
                            <SelectItem value="extension">Extension</SelectItem>
                            <SelectItem value="hunt_group">Hunt group</SelectItem>
                            <SelectItem value="ivr">Submenu (IVR)</SelectItem>
                            <SelectItem value="voicemail">Voicemail</SelectItem>
                            <SelectItem value="hangup">Hangup</SelectItem>
                          </SelectContent>
                        </Select>
                        {opt.type && opt.type !== 'hangup' && (
                          <Select value={opt.id || ''} onValueChange={v => {
                            const next = { ...(editingIvr.options || {}) };
                            next[key] = { ...opt, id: v };
                            setEditingIvr({ ...editingIvr, options: next });
                          }}>
                            <SelectTrigger className="flex-1 h-7 text-[11px]"><SelectValue placeholder="…" /></SelectTrigger>
                            <SelectContent>
                              {opt.type === 'extension' && extensions.map(e => <SelectItem key={e.id} value={e.id}>{e.number}</SelectItem>)}
                              {opt.type === 'hunt_group' && huntGroups.map(h => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                              {opt.type === 'ivr' && ivrs.filter(v => v.id !== editingIvr.id).map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}
                              {opt.type === 'voicemail' && extensions.filter(e => e.voicemail_enabled).map(e => <SelectItem key={e.id} value={e.id}>{e.number}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1"><Label className="text-xs">Timeout (sec)</Label>
                  <Input type="number" value={editingIvr.timeout_sec || 10} onChange={e => setEditingIvr({ ...editingIvr, timeout_sec: parseInt(e.target.value) || 10 })} />
                </div>
                <div className="space-y-1"><Label className="text-xs">Max retries</Label>
                  <Input type="number" value={editingIvr.max_retries || 2} onChange={e => setEditingIvr({ ...editingIvr, max_retries: parseInt(e.target.value) || 2 })} />
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="ghost" className="flex-1" onClick={() => setEditingIvr(null)}>Cancel</Button>
                <Button className="flex-1" onClick={() => save('IVR', '/pbx/ivrs', editingIvr, setEditingIvr, setIvrs)} data-testid="pbx-ivr-save">Save</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ─── Config preview dialog ───────────────────────────────── */}
      <Dialog open={showConfig.open} onOpenChange={(o) => setShowConfig(c => ({ ...c, open: o }))}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="pbx-config-dialog">
          <DialogHeader>
            <DialogTitle>Asterisk config preview</DialogTitle>
            <DialogDescription className="text-xs">
              This is what the appliance Asterisk will pull on its next reload.{' '}
              Counts: {configBundle?.counts?.extensions || 0} exts · {configBundle?.counts?.trunks || 0} trunks · {configBundle?.counts?.inbound || 0} inbound · {configBundle?.counts?.outbound || 0} outbound · {configBundle?.counts?.hunt_groups || 0} hunt groups · {configBundle?.counts?.ivrs || 0} IVRs.
            </DialogDescription>
          </DialogHeader>
          <div className="flex gap-2 mb-2">
            {['pjsip.conf', 'extensions.conf', 'voicemail.conf', 'queues.conf'].map(f => (
              <Button key={f} size="sm" variant={showConfig.fname === f ? 'default' : 'outline'} onClick={() => setShowConfig({ open: true, fname: f })} data-testid={`pbx-config-tab-${f.replace('.', '-')}`}>
                {f}
              </Button>
            ))}
          </div>
          <pre className="text-[10px] bg-muted/30 rounded p-2 overflow-auto whitespace-pre" data-testid="pbx-config-preview">
            {configBundle?.[showConfig.fname] || 'Loading…'}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
