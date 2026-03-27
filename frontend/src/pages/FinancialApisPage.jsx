import React, { useState, useEffect } from 'react';
import { CreditCard, Plus, Trash2, Edit2, Save, Shield, RefreshCw, Link2, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { financialApisApi } from '../services/api';
import { toast } from 'sonner';

const API_PROVIDERS = [
  { value: 'stripe', label: 'Stripe', icon: '💳' },
  { value: 'paypal', label: 'PayPal', icon: '🅿️' },
  { value: 'flutterwave', label: 'Flutterwave', icon: '🌊' },
  { value: 'mtn_momo', label: 'MTN Mobile Money', icon: '📱' },
  { value: 'airtel_money', label: 'Airtel Money', icon: '📲' },
  { value: 'quickbooks', label: 'QuickBooks', icon: '📊' },
  { value: 'xero', label: 'Xero', icon: '📈' },
  { value: 'custom', label: 'Custom API', icon: '🔧' },
];

const statusColors = {
  active: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400',
  inactive: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400',
  error: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400',
};

export default function FinancialApisPage() {
  const [apis, setApis] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(null);

  const [form, setForm] = useState({
    name: '',
    provider: 'stripe',
    api_key: '',
    secret_key: '',
    webhook_url: '',
    is_active: true,
    is_sandbox: true,
    config: {},
  });

  useEffect(() => {
    fetchApis();
  }, []);

  const fetchApis = async () => {
    setLoading(true);
    try {
      const res = await financialApisApi.list();
      setApis(res.data || []);
    } catch {
      toast.error('Failed to load financial APIs');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.name || !form.provider) {
      toast.error('Please fill required fields');
      return;
    }
    try {
      const res = await financialApisApi.create(form);
      setApis(prev => [...prev, res.data]);
      setShowCreate(false);
      resetForm();
      toast.success('API connection added');
    } catch {
      toast.error('Failed to add API');
    }
  };

  const handleUpdate = async () => {
    if (!showEdit?.id) return;
    try {
      await financialApisApi.update(showEdit.id, form);
      setApis(prev => prev.map(a => a.id === showEdit.id ? { ...a, ...form } : a));
      setShowEdit(null);
      resetForm();
      toast.success('API updated');
    } catch {
      toast.error('Failed to update API');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Remove this API connection?')) return;
    try {
      await financialApisApi.delete(id);
      setApis(prev => prev.filter(a => a.id !== id));
      toast.success('API removed');
    } catch {
      toast.error('Failed to remove API');
    }
  };

  const resetForm = () => {
    setForm({
      name: '',
      provider: 'stripe',
      api_key: '',
      secret_key: '',
      webhook_url: '',
      is_active: true,
      is_sandbox: true,
      config: {},
    });
  };

  const openEdit = (api) => {
    setForm({
      name: api.name,
      provider: api.provider,
      api_key: api.api_key || '',
      secret_key: '', // Don't populate secret for security
      webhook_url: api.webhook_url || '',
      is_active: api.is_active !== false,
      is_sandbox: api.is_sandbox !== false,
      config: api.config || {},
    });
    setShowEdit(api);
  };

  const getProviderInfo = (provider) => API_PROVIDERS.find(p => p.value === provider) || { icon: '🔧', label: provider };

  const maskKey = (key) => {
    if (!key || key.length < 8) return '••••••••';
    return key.slice(0, 4) + '••••' + key.slice(-4);
  };

  return (
    <div className="p-6 space-y-6" data-testid="financial-apis-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Financial API Connections</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Manage payment gateways and accounting integrations</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchApis}><RefreshCw size={14} /></Button>
          <Button className="gap-2" onClick={() => setShowCreate(true)} data-testid="add-api-btn">
            <Plus size={16} /> Add Connection
          </Button>
        </div>
      </div>

      {/* Warning Banner */}
      <Card className="shadow-soft rounded-xl border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800">
        <CardContent className="p-4 flex items-start gap-3">
          <Shield size={20} className="text-amber-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-400">Security Notice</p>
            <p className="text-xs text-amber-700 dark:text-amber-500 mt-1">
              API keys are encrypted and stored securely. Never share your secret keys. Use sandbox/test mode for development.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* APIs List */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : apis.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <CreditCard size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground mb-4">No financial API connections configured</p>
            <Button onClick={() => setShowCreate(true)} className="gap-2"><Plus size={14} /> Add First Connection</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {apis.map(api => {
            const provider = getProviderInfo(api.provider);
            return (
              <Card key={api.id} className="shadow-soft rounded-xl hover:shadow-md transition-shadow" data-testid={`api-card-${api.id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center text-xl">
                        {provider.icon}
                      </div>
                      <div>
                        <p className="font-semibold text-sm">{api.name}</p>
                        <p className="text-xs text-muted-foreground">{provider.label}</p>
                      </div>
                    </div>
                    <Badge className={`text-xs ${statusColors[api.is_active ? 'active' : 'inactive']}`}>
                      {api.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>

                  <div className="space-y-2 mb-4">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">API Key</span>
                      <code className="font-mono bg-muted px-1.5 py-0.5 rounded">{maskKey(api.api_key)}</code>
                    </div>
                    {api.webhook_url && (
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Webhook</span>
                        <span className="truncate max-w-[140px]">{api.webhook_url}</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">Environment</span>
                      <Badge variant={api.is_sandbox ? 'secondary' : 'default'} className="text-xs">
                        {api.is_sandbox ? 'Sandbox' : 'Live'}
                      </Badge>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1" onClick={() => openEdit(api)}>
                      <Edit2 size={12} className="mr-1.5" /> Edit
                    </Button>
                    <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => handleDelete(api.id)}>
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
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{showEdit ? 'Edit API Connection' : 'Add API Connection'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Connection Name *</Label>
              <Input placeholder="e.g., Main Stripe Account" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="api-name-input" />
            </div>

            <div className="space-y-2">
              <Label>Provider *</Label>
              <Select value={form.provider} onValueChange={v => setForm({ ...form, provider: v })}>
                <SelectTrigger data-testid="api-provider-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {API_PROVIDERS.map(p => (
                    <SelectItem key={p.value} value={p.value}>{p.icon} {p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>API Key / Public Key</Label>
              <Input placeholder="pk_test_..." value={form.api_key} onChange={e => setForm({ ...form, api_key: e.target.value })} data-testid="api-key-input" />
            </div>

            <div className="space-y-2">
              <Label>Secret Key {showEdit && '(leave blank to keep existing)'}</Label>
              <Input type="password" placeholder="sk_test_..." value={form.secret_key} onChange={e => setForm({ ...form, secret_key: e.target.value })} data-testid="api-secret-input" />
            </div>

            <div className="space-y-2">
              <Label>Webhook URL (optional)</Label>
              <Input placeholder="https://..." value={form.webhook_url} onChange={e => setForm({ ...form, webhook_url: e.target.value })} />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Sandbox/Test Mode</p>
                <p className="text-xs text-muted-foreground">Use test credentials</p>
              </div>
              <Switch checked={form.is_sandbox} onCheckedChange={v => setForm({ ...form, is_sandbox: v })} data-testid="sandbox-toggle" />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Active</p>
                <p className="text-xs text-muted-foreground">Enable this connection</p>
              </div>
              <Switch checked={form.is_active} onCheckedChange={v => setForm({ ...form, is_active: v })} data-testid="active-toggle" />
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>Cancel</Button>
              <Button className="flex-1 gap-2" onClick={showEdit ? handleUpdate : handleCreate} data-testid="save-api-btn">
                <Save size={14} /> {showEdit ? 'Update' : 'Add Connection'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
