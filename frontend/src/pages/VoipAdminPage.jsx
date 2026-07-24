/**
 * VoIP admin — tenant-level UCM connection settings + per-user SIP provisioning.
 *
 * Sections:
 *   1. UCM connection            (host, WSS URL, STUN/TURN, HTTPS API creds)
 *   2. Test connection           (challenge/login probe)
 *   3. Extensions per user       (assign extension + SIP password to each staff)
 *
 * All writes go through the admin-scoped /api/voip endpoints. SIP passwords
 * are Fernet-encrypted server-side; this UI never displays existing passwords.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { toast } from 'sonner';
import { Save, Zap, User, Key, Trash2, Search, Phone } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import api from '../services/api';

export default function VoipAdminPage() {
  const [cfg, setCfg] = useState(null);
  const [rotatePw, setRotatePw] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [users, setUsers] = useState([]);
  const [filter, setFilter] = useState('');
  const [editingUser, setEditingUser] = useState(null);
  const [editExt, setEditExt] = useState('');
  const [editPw, setEditPw] = useState('');
  const [editDisplay, setEditDisplay] = useState('');

  const load = useCallback(async () => {
    try {
      const [c, u] = await Promise.all([api.get('/voip/tenant/config'), api.get('/voip/users')]);
      setCfg(c.data);
      setUsers(u.data || []);
    } catch (e) {
      toast.error('Could not load VoIP settings');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!cfg) return <div className="p-6 text-sm text-slate-500">Loading VoIP settings…</div>;

  const saveConfig = async () => {
    setSaving(true);
    try {
      const payload = {
        ucm_host: cfg.ucm_host, sip_domain: cfg.sip_domain, ws_url: cfg.ws_url,
        stun_urls: cfg.stun_urls, turn_urls: cfg.turn_urls,
        turn_username: cfg.turn_username, turn_password: cfg.turn_password,
        ucm_api_url: cfg.ucm_api_url, ucm_api_username: cfg.ucm_api_username,
        ucm_verify_tls: cfg.ucm_verify_tls,
      };
      if (rotatePw) payload.ucm_api_password = rotatePw;
      const r = await api.put('/voip/tenant/config', payload);
      setCfg(r.data);
      setRotatePw('');
      toast.success('VoIP settings saved');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    try {
      await api.post('/voip/tenant/test');
      toast.success('UCM connection OK — challenge/login succeeded.');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'UCM connection failed');
    } finally {
      setTesting(false);
    }
  };

  const openEdit = (u) => {
    setEditingUser(u);
    setEditExt(u.extension || '');
    setEditPw('');
    setEditDisplay(u.display_name || u.name || '');
  };

  const closeEdit = () => { setEditingUser(null); setEditExt(''); setEditPw(''); setEditDisplay(''); };

  const saveUserSip = async () => {
    if (!editExt || (!editPw && !editingUser.has_password)) {
      toast.error('Extension and password are both required'); return;
    }
    try {
      const payload = { extension: editExt.trim(), display_name: editDisplay.trim() };
      if (editPw) payload.sip_password = editPw;
      else payload.sip_password = 'unchanged__will_never_be_used__see_note';
      // If no new password was entered, do a two-step: keep existing by not sending
      // If a new password was entered, the backend replaces it.
      // For simplicity we require a password when editing; the UI prompts for one.
      if (!editPw) { toast.error('Enter a SIP password (one is required to update). Copy it from UCM → Extension → SIP Password.'); return; }
      await api.put(`/voip/users/${editingUser.id}/sip`, payload);
      toast.success('SIP credentials saved');
      closeEdit();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    }
  };

  const clearUserSip = async (u) => {
    if (!window.confirm(`Remove SIP extension from ${u.name || u.email}?`)) return;
    try {
      await api.delete(`/voip/users/${u.id}/sip`);
      toast.success('SIP cleared');
      load();
    } catch (e) {
      toast.error('Could not clear SIP');
    }
  };

  const filtered = users.filter(u => {
    if (!filter.trim()) return true;
    const q = filter.toLowerCase();
    return (u.name || '').toLowerCase().includes(q)
      || (u.email || '').toLowerCase().includes(q)
      || (u.extension || '').includes(q);
  });

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8" data-testid="voip-admin-page">
      <div>
        <h1 className="text-2xl font-semibold">VoIP / Softphone</h1>
        <p className="text-sm text-slate-500 mt-1">
          Configure your Grandstream UCM connection and assign SIP extensions to staff. Each staff
          member's browser will register as an additional endpoint on their extension — the UCM
          continues to own trunks, outbound routing, IVRs, and voicemail.
        </p>
      </div>

      {/* ── UCM connection ────────────────────────────────── */}
      <section className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">UCM connection</h2>
          <Button size="sm" variant="outline" onClick={testConnection} disabled={testing || !cfg.ucm_api_configured}
                  data-testid="test-ucm-btn">
            <Zap size={13} className="mr-1" /> {testing ? 'Testing…' : 'Test connection'}
          </Button>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <Label>UCM host / IP</Label>
            <Input value={cfg.ucm_host} onChange={e => setCfg({ ...cfg, ucm_host: e.target.value })}
                   placeholder="pbx.example.org  (no https://)" data-testid="ucm-host-input" />
            <div className="text-[10px] text-slate-500 mt-1">
              Hostname only — do <b>not</b> paste <code>https://</code> or a trailing slash. Auto-cleaned on save.
            </div>
          </div>
          <div>
            <Label>SIP realm (optional)</Label>
            <Input value={cfg.sip_domain} onChange={e => setCfg({ ...cfg, sip_domain: e.target.value })}
                   placeholder="Defaults to UCM host" data-testid="sip-domain-input" />
            <div className="text-[10px] text-slate-500 mt-1">
              Set only if your UCM's SIP realm differs from its DNS name
              (<span className="font-mono">PBX Settings → SIP Settings → Realm</span>).
            </div>
          </div>
          <div className="md:col-span-2">
            <Label>Browser WebSocket URL (WSS)</Label>
            <Input value={cfg.ws_url} onChange={e => setCfg({ ...cfg, ws_url: e.target.value })}
                   placeholder="wss://pbx.example.org:8089/ws" data-testid="ws-url-input" />
            <div className="text-[11px] text-slate-500 mt-1">
              Enable "Sip Settings → WSS" on the UCM. The cert must be trusted (Let's Encrypt or an
              internal CA). Self-signed certs will silently fail in browsers.
            </div>
          </div>
          <div className="md:col-span-2">
            <Label>STUN servers (comma-separated)</Label>
            <Input value={(cfg.stun_urls || []).join(', ')}
                   onChange={e => setCfg({ ...cfg, stun_urls: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                   placeholder="stun:stun.l.google.com:19302" data-testid="stun-urls-input" />
          </div>
          <div className="md:col-span-2">
            <Label>TURN servers (comma-separated, for staff outside LAN)</Label>
            <Input value={(cfg.turn_urls || []).join(', ')}
                   onChange={e => setCfg({ ...cfg, turn_urls: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                   placeholder="turn:pbx.example.org:3478" data-testid="turn-urls-input" />
          </div>
          <div>
            <Label>TURN username</Label>
            <Input value={cfg.turn_username} onChange={e => setCfg({ ...cfg, turn_username: e.target.value })}
                   data-testid="turn-user-input" />
          </div>
          <div>
            <Label>TURN password</Label>
            <Input type="password" value={cfg.turn_password} onChange={e => setCfg({ ...cfg, turn_password: e.target.value })}
                   data-testid="turn-pw-input" />
          </div>
        </div>

        <div className="pt-4 border-t border-slate-100 space-y-4">
          <div className="text-sm font-medium">Voicemail / call history — UCM HTTPS API</div>
          <div className="text-[11px] text-slate-500 -mt-2">
            Grandstream UCM 63xx exposes an admin HTTPS API for voicemail + CDR. Enter a UCM
            Super Admin (or a dedicated API user) here. The password is Fernet-encrypted at rest
            and never returned to the browser.
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <Label>UCM API base URL</Label>
              <Input value={cfg.ucm_api_url} onChange={e => setCfg({ ...cfg, ucm_api_url: e.target.value })}
                     placeholder="https://pbx.example.org:8089" data-testid="ucm-api-url-input" />
            </div>
            <div>
              <Label>UCM API username</Label>
              <Input value={cfg.ucm_api_username} onChange={e => setCfg({ ...cfg, ucm_api_username: e.target.value })}
                     placeholder="cdrapi or apiuser" data-testid="ucm-api-user-input" />
            </div>
            <div>
              <Label>UCM API password {cfg.ucm_api_configured && <span className="text-[10px] text-emerald-600">(saved — leave blank to keep)</span>}</Label>
              <Input type="password" value={rotatePw} onChange={e => setRotatePw(e.target.value)}
                     placeholder={cfg.ucm_api_configured ? 'Enter to rotate' : 'Set password'}
                     data-testid="ucm-api-pw-input" />
            </div>
            <div className="flex items-center gap-2 mt-6">
              <Switch checked={!!cfg.ucm_verify_tls} onCheckedChange={v => setCfg({ ...cfg, ucm_verify_tls: v })}
                      data-testid="ucm-verify-tls-switch" />
              <Label className="mb-0">Verify TLS certificate</Label>
            </div>
          </div>
        </div>

        <div className="pt-2">
          <Button onClick={saveConfig} disabled={saving} data-testid="save-voip-config-btn">
            <Save size={14} className="mr-1" /> {saving ? 'Saving…' : 'Save VoIP settings'}
          </Button>
        </div>
      </section>

      {/* ── User provisioning ──────────────────────────────── */}
      <section className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-medium">Staff extensions</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">
              One SIP extension per user. Paste the extension number + SIP password from
              <span className="font-mono"> UCM → Extension/Trunk → Extensions → &lt;ext&gt; → Edit</span>.
            </p>
          </div>
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
            <Input value={filter} onChange={e => setFilter(e.target.value)} className="pl-8 h-9 w-56"
                   placeholder="Search staff…" data-testid="user-filter-input" />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50">
              <tr>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Role</th>
                <th className="text-left px-3 py-2">Extension</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map(u => (
                <tr key={u.id} data-testid={`voip-user-row-${u.id}`}>
                  <td className="px-3 py-2">
                    <div className="font-medium">{u.name || '(no name)'}</div>
                    <div className="text-[11px] text-slate-500">{u.email}</div>
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-600">{u.role}</td>
                  <td className="px-3 py-2 font-mono">{u.extension || '—'}</td>
                  <td className="px-3 py-2">
                    {u.has_password
                      ? <span className="inline-flex items-center gap-1 text-emerald-600 text-xs"><Phone size={11} /> Configured</span>
                      : <span className="text-xs text-slate-400">Not set</span>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="outline" className="mr-1" onClick={() => openEdit(u)}
                            data-testid={`edit-voip-user-btn-${u.id}`}>
                      <Key size={12} className="mr-1" /> {u.has_password ? 'Update' : 'Assign'}
                    </Button>
                    {u.has_password && (
                      <Button size="sm" variant="ghost" onClick={() => clearUserSip(u)}
                              className="text-red-600 hover:text-red-700 hover:bg-red-50"
                              data-testid={`clear-voip-user-btn-${u.id}`}>
                        <Trash2 size={12} />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  No matching staff.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── edit modal ─────────────────────────────────────── */}
      {editingUser && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
             onClick={closeEdit} data-testid="voip-edit-modal">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-4">
              <User size={16} className="text-slate-600" />
              <h3 className="font-medium">{editingUser.name}</h3>
            </div>
            <div className="space-y-4">
              <div>
                <Label>Extension number</Label>
                <Input value={editExt} onChange={e => setEditExt(e.target.value)}
                       placeholder="e.g. 1042" data-testid="edit-ext-input" />
              </div>
              <div>
                <Label>SIP password</Label>
                <Input type="password" value={editPw} onChange={e => setEditPw(e.target.value)}
                       placeholder="From UCM → Extension → SIP Password" data-testid="edit-pw-input" />
                <div className="text-[10px] text-slate-500 mt-1">Stored encrypted. You must re-enter it on every update.</div>
              </div>
              <div>
                <Label>Display name (optional)</Label>
                <Input value={editDisplay} onChange={e => setEditDisplay(e.target.value)}
                       placeholder="Shows as Caller ID name" data-testid="edit-display-input" />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <Button variant="outline" onClick={closeEdit} data-testid="cancel-edit-voip-btn">Cancel</Button>
              <Button onClick={saveUserSip} data-testid="save-edit-voip-btn">Save</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
