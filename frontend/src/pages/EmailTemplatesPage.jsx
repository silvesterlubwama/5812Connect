import React, { useState, useEffect } from 'react';
import { Mail, Plus, Edit2, Trash2, Send, Save, Copy, X, Tag, FileText } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { emailTemplatesApi } from '../services/api';
import { toast } from 'sonner';

const CATEGORIES = ['onboarding', 'events', 'financial', 'reminders', 'general'];

const categoryColors = {
  onboarding: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400',
  events: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400',
  financial: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400',
  reminders: 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-400',
  general: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400',
};

export default function EmailTemplatesPage() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(null);
  const [showSend, setShowSend] = useState(null);
  const [sending, setSending] = useState(false);

  const [form, setForm] = useState({
    name: '',
    subject: '',
    body: '',
    category: 'general',
    variables: [],
  });

  const [sendForm, setSendForm] = useState({
    to_email: '',
    variables: {},
  });

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const res = await emailTemplatesApi.list();
      setTemplates(res.data || []);
    } catch {
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.name || !form.subject || !form.body) {
      toast.error('Please fill all required fields');
      return;
    }
    try {
      const res = await emailTemplatesApi.create({
        ...form,
        variables: extractVariables(form.body + form.subject),
      });
      setTemplates(prev => [...prev, res.data]);
      setShowCreate(false);
      resetForm();
      toast.success('Template created');
    } catch {
      toast.error('Failed to create template');
    }
  };

  const handleUpdate = async () => {
    if (!showEdit?.id) return;
    try {
      await emailTemplatesApi.update(showEdit.id, {
        ...form,
        variables: extractVariables(form.body + form.subject),
      });
      setTemplates(prev => prev.map(t => t.id === showEdit.id ? { ...t, ...form, variables: extractVariables(form.body + form.subject) } : t));
      setShowEdit(null);
      resetForm();
      toast.success('Template updated');
    } catch {
      toast.error('Failed to update template');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this template?')) return;
    try {
      await emailTemplatesApi.delete(id);
      setTemplates(prev => prev.filter(t => t.id !== id));
      toast.success('Template deleted');
    } catch {
      toast.error('Failed to delete template');
    }
  };

  const handleSend = async () => {
    if (!sendForm.to_email) {
      toast.error('Please enter recipient email');
      return;
    }
    setSending(true);
    try {
      await emailTemplatesApi.send(showSend.id, sendForm);
      toast.success('Email sent successfully');
      setShowSend(null);
      setSendForm({ to_email: '', variables: {} });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send email');
    } finally {
      setSending(false);
    }
  };

  const extractVariables = (text) => {
    const matches = text.match(/\{\{(\w+)\}\}/g) || [];
    return [...new Set(matches.map(m => m.replace(/[{}]/g, '')))];
  };

  const resetForm = () => {
    setForm({ name: '', subject: '', body: '', category: 'general', variables: [] });
  };

  const openEdit = (template) => {
    setForm({
      name: template.name,
      subject: template.subject,
      body: template.body,
      category: template.category,
      variables: template.variables || [],
    });
    setShowEdit(template);
  };

  const openSend = (template) => {
    const vars = {};
    (template.variables || []).forEach(v => { vars[v] = ''; });
    setSendForm({ to_email: '', variables: vars });
    setShowSend(template);
  };

  const copyVariable = (varName) => {
    navigator.clipboard.writeText(`{{${varName}}}`);
    toast.success(`Copied {{${varName}}}`);
  };

  const previewSubject = () => {
    let preview = showSend?.subject || '';
    Object.entries(sendForm.variables).forEach(([k, v]) => {
      preview = preview.replace(new RegExp(`\\{\\{${k}\\}\\}`, 'g'), v || `[${k}]`);
    });
    return preview;
  };

  const previewBody = () => {
    let preview = showSend?.body || '';
    Object.entries(sendForm.variables).forEach(([k, v]) => {
      preview = preview.replace(new RegExp(`\\{\\{${k}\\}\\}`, 'g'), v || `[${k}]`);
    });
    return preview;
  };

  return (
    <div className="p-6 space-y-6" data-testid="email-templates-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Email Templates</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Create and manage reusable email templates with variables</p>
        </div>
        <Button className="gap-2" onClick={() => setShowCreate(true)} data-testid="create-template-btn">
          <Plus size={16} /> New Template
        </Button>
      </div>

      {/* Templates List */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : templates.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <Mail size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground mb-4">No email templates yet</p>
            <Button onClick={() => setShowCreate(true)} className="gap-2"><Plus size={14} /> Create Template</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map(template => (
            <Card key={template.id} className="shadow-soft rounded-xl hover:shadow-md transition-shadow" data-testid={`template-card-${template.id}`}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Mail size={18} className="text-primary" />
                    <div>
                      <p className="font-semibold text-sm">{template.name}</p>
                      <Badge className={`text-xs mt-1 ${categoryColors[template.category] || categoryColors.general}`}>
                        {template.category}
                      </Badge>
                    </div>
                  </div>
                </div>

                <p className="text-sm font-medium mb-2 truncate">{template.subject}</p>
                <p className="text-xs text-muted-foreground line-clamp-3 mb-3">{template.body}</p>

                {(template.variables || []).length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {template.variables.slice(0, 4).map(v => (
                      <Badge key={v} variant="outline" className="text-xs cursor-pointer hover:bg-muted" onClick={() => copyVariable(v)}>
                        {`{{${v}}}`}
                      </Badge>
                    ))}
                    {template.variables.length > 4 && (
                      <Badge variant="secondary" className="text-xs">+{template.variables.length - 4}</Badge>
                    )}
                  </div>
                )}

                <div className="flex gap-2">
                  <Button size="sm" className="flex-1 gap-1.5" onClick={() => openSend(template)} data-testid={`send-template-${template.id}`}>
                    <Send size={12} /> Send
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => openEdit(template)}><Edit2 size={12} /></Button>
                  <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => handleDelete(template.id)}>
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{showEdit ? 'Edit Template' : 'Create Email Template'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Template Name *</Label>
                <Input placeholder="e.g., Welcome Email" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="template-name-input" />
              </div>
              <div className="space-y-2">
                <Label>Category</Label>
                <Select value={form.category} onValueChange={v => setForm({ ...form, category: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Subject Line *</Label>
              <Input placeholder="Email subject (use {{variable}} for dynamic content)" value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} data-testid="template-subject-input" />
            </div>

            <div className="space-y-2">
              <Label>Email Body *</Label>
              <Textarea rows={8} placeholder="Email content... Use {{name}}, {{date}}, etc. for variables" value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} data-testid="template-body-input" />
            </div>

            <div className="p-3 rounded-lg bg-muted/50">
              <p className="text-xs font-medium text-muted-foreground mb-2">Detected Variables:</p>
              <div className="flex flex-wrap gap-1">
                {extractVariables(form.subject + form.body).map(v => (
                  <Badge key={v} variant="outline" className="text-xs">{`{{${v}}}`}</Badge>
                ))}
                {extractVariables(form.subject + form.body).length === 0 && (
                  <span className="text-xs text-muted-foreground">No variables detected. Use {`{{variable_name}}`} syntax.</span>
                )}
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>Cancel</Button>
              <Button className="flex-1 gap-2" onClick={showEdit ? handleUpdate : handleCreate} data-testid="save-template-btn">
                <Save size={14} /> {showEdit ? 'Update' : 'Create'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Send Dialog */}
      <Dialog open={!!showSend} onOpenChange={() => setShowSend(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Send size={18} /> Send: {showSend?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Recipient Email *</Label>
              <Input type="email" placeholder="recipient@example.com" value={sendForm.to_email} onChange={e => setSendForm({ ...sendForm, to_email: e.target.value })} data-testid="send-to-email" />
            </div>

            {Object.keys(sendForm.variables).length > 0 && (
              <div className="space-y-3">
                <Label className="text-sm font-medium">Fill Variables:</Label>
                {Object.keys(sendForm.variables).map(varName => (
                  <div key={varName} className="space-y-1">
                    <Label className="text-xs text-muted-foreground">{`{{${varName}}}`}</Label>
                    <Input placeholder={varName} value={sendForm.variables[varName]} onChange={e => setSendForm({ ...sendForm, variables: { ...sendForm.variables, [varName]: e.target.value } })} />
                  </div>
                ))}
              </div>
            )}

            <div className="p-3 rounded-lg border border-border space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Preview:</p>
              <p className="text-sm font-semibold">{previewSubject()}</p>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{previewBody()}</p>
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowSend(null)}>Cancel</Button>
              <Button className="flex-1 gap-2" onClick={handleSend} disabled={sending} data-testid="confirm-send-btn">
                <Send size={14} /> {sending ? 'Sending...' : 'Send Email'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
