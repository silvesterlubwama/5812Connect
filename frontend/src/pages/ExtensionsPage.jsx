import React, { useState, useEffect } from 'react';
import { 
  Phone, Plus, Trash2, Edit2, Save, X, Search, 
  UserPlus, Shield, PhoneForwarded, VoicemailIcon, Bell, BellOff
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { callingApi, adminApi } from '../services/api';
import { toast } from 'sonner';

const statusColors = {
  available: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400',
  busy: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400',
  dnd: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400',
  offline: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400',
  on_call: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400',
};

export default function ExtensionsPage() {
  const [extensions, setExtensions] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  const [form, setForm] = useState({
    user_id: '',
    extension: '',
    display_name: '',
    voicemail_enabled: true,
    voicemail_pin: '',
    dnd_enabled: false,
    forward_to: '',
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [extRes, usersRes] = await Promise.all([
        callingApi.listExtensions(),
        adminApi.userDirectory(),
      ]);
      setExtensions(extRes.data || []);
      setUsers(usersRes.data || []);
    } catch (err) {
      toast.error('Failed to load extensions');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.user_id || !form.extension) {
      toast.error('Please select a user and enter an extension number');
      return;
    }
    if (!/^\d{3,6}$/.test(form.extension)) {
      toast.error('Extension must be 3-6 digits');
      return;
    }
    try {
      const res = await callingApi.createExtension(form);
      setExtensions(prev => [...prev, res.data]);
      setShowCreate(false);
      resetForm();
      toast.success('Extension assigned');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create extension');
    }
  };

  const handleUpdate = async () => {
    if (!showEdit) return;
    try {
      await callingApi.updateExtension(showEdit.extension, {
        extension: form.extension,
        display_name: form.display_name,
        voicemail_enabled: form.voicemail_enabled,
        voicemail_pin: form.voicemail_pin || undefined,
        dnd_enabled: form.dnd_enabled,
        forward_to: form.forward_to || undefined,
      });
      setExtensions(prev => prev.map(e => 
        e.extension === showEdit.extension ? { ...e, ...form } : e
      ));
      setShowEdit(null);
      resetForm();
      toast.success('Extension updated');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update');
    }
  };

  const handleDelete = async (extension) => {
    if (!window.confirm(`Remove extension ${extension}?`)) return;
    try {
      await callingApi.deleteExtension(extension);
      setExtensions(prev => prev.filter(e => e.extension !== extension));
      toast.success('Extension removed');
    } catch {
      toast.error('Failed to remove');
    }
  };

  const resetForm = () => {
    setForm({
      user_id: '',
      extension: '',
      display_name: '',
      voicemail_enabled: true,
      voicemail_pin: '',
      dnd_enabled: false,
      forward_to: '',
    });
  };

  const openEdit = (ext) => {
    setForm({
      user_id: ext.user_id,
      extension: ext.extension,
      display_name: ext.display_name || '',
      voicemail_enabled: ext.voicemail_enabled !== false,
      voicemail_pin: '',
      dnd_enabled: ext.dnd_enabled || false,
      forward_to: ext.forward_to || '',
    });
    setShowEdit(ext);
  };

  const getNextExtension = () => {
    const existingExts = extensions.map(e => parseInt(e.extension)).filter(n => !isNaN(n));
    if (existingExts.length === 0) return '1001';
    const maxExt = Math.max(...existingExts);
    return String(maxExt + 1);
  };

  const usersWithoutExtension = users.filter(
    u => !extensions.some(e => e.user_id === u.id)
  );

  const filteredExtensions = extensions.filter(ext => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      ext.extension.includes(term) ||
      (ext.display_name || '').toLowerCase().includes(term) ||
      (ext.user_name || '').toLowerCase().includes(term) ||
      (ext.user_email || '').toLowerCase().includes(term)
    );
  });

  return (
    <div className="p-6 space-y-6" data-testid="extensions-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Extension Management</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Assign and manage phone extensions for staff</p>
        </div>
        <Button className="gap-2" onClick={() => { resetForm(); setForm(f => ({ ...f, extension: getNextExtension() })); setShowCreate(true); }} data-testid="add-extension-btn">
          <Plus size={16} /> Assign Extension
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search extensions, names..."
          className="pl-9"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Extensions List */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <div key={i} className="h-40 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : filteredExtensions.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <Phone size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground mb-4">No extensions assigned yet</p>
            <Button onClick={() => setShowCreate(true)} className="gap-2">
              <Plus size={14} /> Assign First Extension
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredExtensions.map(ext => (
            <Card key={ext.extension} className="shadow-soft rounded-xl" data-testid={`extension-card-${ext.extension}`}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                      <span className="text-lg font-bold text-primary">{ext.extension}</span>
                    </div>
                    <div>
                      <p className="font-semibold">{ext.display_name || ext.user_name || 'Unknown'}</p>
                      <p className="text-xs text-muted-foreground">{ext.user_email || ext.user_id}</p>
                    </div>
                  </div>
                  <Badge className={`text-xs ${statusColors[ext.status] || statusColors.offline}`}>
                    {ext.status || 'offline'}
                  </Badge>
                </div>

                <div className="space-y-2 mb-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground flex items-center gap-1.5">
                      <VoicemailIcon size={12} /> Voicemail
                    </span>
                    <span>{ext.voicemail_enabled ? 'Enabled' : 'Disabled'}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground flex items-center gap-1.5">
                      {ext.dnd_enabled ? <BellOff size={12} /> : <Bell size={12} />} DND
                    </span>
                    <span>{ext.dnd_enabled ? 'On' : 'Off'}</span>
                  </div>
                  {ext.forward_to && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground flex items-center gap-1.5">
                        <PhoneForwarded size={12} /> Forward
                      </span>
                      <span>{ext.forward_to}</span>
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="flex-1" onClick={() => openEdit(ext)}>
                    <Edit2 size={12} className="mr-1" /> Edit
                  </Button>
                  <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => handleDelete(ext.extension)}>
                    <Trash2 size={12} />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate || !!showEdit} onOpenChange={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{showEdit ? 'Edit Extension' : 'Assign Extension'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            {!showEdit && (
              <div className="space-y-2">
                <Label>Select User *</Label>
                <Select value={form.user_id || '_none'} onValueChange={v => {
                  const selectedUser = users.find(u => u.id === v);
                  setForm({ 
                    ...form, 
                    user_id: v === '_none' ? '' : v,
                    display_name: selectedUser?.name || ''
                  });
                }}>
                  <SelectTrigger data-testid="user-select"><SelectValue placeholder="Select user..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">Select user...</SelectItem>
                    {usersWithoutExtension.map(u => (
                      <SelectItem key={u.id} value={u.id}>
                        {u.name} ({u.email})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Extension Number *</Label>
                <Input
                  placeholder="1001"
                  value={form.extension}
                  onChange={e => setForm({ ...form, extension: e.target.value.replace(/\D/g, '').slice(0, 6) })}
                  data-testid="extension-number-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Display Name</Label>
                <Input
                  placeholder="John Smith"
                  value={form.display_name}
                  onChange={e => setForm({ ...form, display_name: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Call Forwarding (optional)</Label>
              <Input
                placeholder="Extension or phone number"
                value={form.forward_to}
                onChange={e => setForm({ ...form, forward_to: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">Forward calls when unavailable</p>
            </div>

            <div className="space-y-2">
              <Label>Voicemail PIN</Label>
              <Input
                type="password"
                placeholder="4-6 digits (default: extension number)"
                value={form.voicemail_pin}
                onChange={e => setForm({ ...form, voicemail_pin: e.target.value.replace(/\D/g, '').slice(0, 6) })}
              />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Voicemail</p>
                <p className="text-xs text-muted-foreground">Enable voicemail for missed calls</p>
              </div>
              <Switch checked={form.voicemail_enabled} onCheckedChange={v => setForm({ ...form, voicemail_enabled: v })} />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Do Not Disturb</p>
                <p className="text-xs text-muted-foreground">Block all incoming calls</p>
              </div>
              <Switch checked={form.dnd_enabled} onCheckedChange={v => setForm({ ...form, dnd_enabled: v })} />
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>
                Cancel
              </Button>
              <Button className="flex-1 gap-2" onClick={showEdit ? handleUpdate : handleCreate} data-testid="save-extension-btn">
                <Save size={14} /> {showEdit ? 'Update' : 'Assign'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
