import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import { CheckCheck, Plus, Trash2, Check, X, ArrowRight, Inbox, Send, Workflow } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const ROLES = ['Volunteer', 'Staff', 'Coordinator', 'Leader', 'Manager', 'Director', 'Adviser', 'Executive Director'];
const KINDS = ['expense', 'leave', 'sale_discount', 'purchase_order', 'custom'];
const STATUS_COLOR = {
  in_progress: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-700',
};

export default function ApprovalsPage() {
  const { user } = useAuth();
  const [workflows, setWorkflows] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [mine, setMine] = useState([]);
  const [all, setAll] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showWfForm, setShowWfForm] = useState(false);
  const [wfForm, setWfForm] = useState({ name: '', kind: 'custom', steps: [{ name: '', approver_role: 'Manager', min_approvals: 1 }] });
  const [showReqForm, setShowReqForm] = useState(false);
  const [reqForm, setReqForm] = useState({ workflow_id: '', title: '', summary: '', amount: '', currency: 'UGX' });
  const [viewReq, setViewReq] = useState(null);
  const [actNote, setActNote] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [wfRes, inboxRes, mineRes, allRes] = await Promise.all([
        api.get('/approvals/workflows').catch(() => ({ data: [] })),
        api.get('/approvals/requests', { params: { pending_my_action: true } }).catch(() => ({ data: [] })),
        api.get('/approvals/requests', { params: { submitted_by_me: true } }).catch(() => ({ data: [] })),
        api.get('/approvals/requests', { params: { limit: 100 } }).catch(() => ({ data: [] })),
      ]);
      setWorkflows(wfRes.data || []);
      setInbox(inboxRes.data || []);
      setMine(mineRes.data || []);
      setAll(allRes.data || []);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const addWfStep = () => setWfForm(p => ({ ...p, steps: [...p.steps, { _key: `s-${Date.now()}-${Math.random().toString(36).slice(2,8)}`, name: '', approver_role: 'Manager', min_approvals: 1 }] }));
  const updateStep = (i, k, v) => setWfForm(p => { const s = [...p.steps]; s[i] = {...s[i], [k]: v}; return {...p, steps: s}; });
  const removeStep = (i) => setWfForm(p => ({ ...p, steps: p.steps.filter((_, j) => j !== i) }));

  const createWorkflow = async () => {
    try {
      const cleaned = { ...wfForm, steps: wfForm.steps.filter(s => s.name && s.approver_role) };
      if (!cleaned.steps.length) { toast.error('Add at least one step'); return; }
      await api.post('/approvals/workflows', cleaned);
      toast.success('Workflow created');
      setShowWfForm(false);
      setWfForm({ name: '', kind: 'custom', steps: [{ name: '', approver_role: 'Manager', min_approvals: 1 }] });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const deleteWorkflow = async (id) => {
    if (!window.confirm('Delete this workflow?')) return;
    try { await api.delete(`/approvals/workflows/${id}`); toast.success('Deleted'); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const submitRequest = async () => {
    try {
      const payload = { ...reqForm };
      if (payload.amount === '') delete payload.amount;
      else payload.amount = parseFloat(payload.amount);
      await api.post('/approvals/requests', payload);
      toast.success('Request submitted');
      setShowReqForm(false);
      setReqForm({ workflow_id: '', title: '', summary: '', amount: '', currency: 'UGX' });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const actOnRequest = async (req, outcome) => {
    try {
      await api.post(`/approvals/requests/${req.id}/act`, { outcome, note: actNote });
      toast.success(outcome === 'approved' ? 'Approved' : 'Rejected');
      setViewReq(null); setActNote('');
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const cancelRequest = async (id) => {
    if (!window.confirm('Cancel this request?')) return;
    try { await api.post(`/approvals/requests/${id}/cancel`); toast.success('Cancelled'); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  if (loading) return <div className="p-6 space-y-2">{[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded" />)}</div>;

  const RequestCard = ({ r, showActions }) => {
    const stepIdx = r.current_step;
    const currentStep = r.workflow_snapshot?.steps?.[stepIdx];
    return (
      <Card className="rounded-xl cursor-pointer hover:border-primary/40" onClick={() => setViewReq(r)} data-testid={`req-${r.id}`}>
        <CardContent className="p-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm font-medium">{r.title}</p>
              <Badge variant="outline" className="text-[10px] capitalize">{r.subject_kind}</Badge>
              {r.auto_generated && <Badge className="bg-blue-100 text-blue-700 text-[10px]">auto</Badge>}
            </div>
            <p className="text-xs text-muted-foreground">
              by {r.submitted_by_name} · {r.workflow_name}
              {currentStep && r.status === 'in_progress' && <> · current step: <strong>{currentStep.name}</strong></>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {r.amount && <p className="text-sm font-bold">{r.currency} {(r.amount || 0).toLocaleString()}</p>}
            <Badge className={`text-[10px] capitalize ${STATUS_COLOR[r.status] || ''}`}>{r.status.replace('_', ' ')}</Badge>
            {showActions && r.submitted_by === user.id && r.status === 'in_progress' && (
              <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={(e) => { e.stopPropagation(); cancelRequest(r.id); }}>Cancel</Button>
            )}
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="p-6 space-y-5" data-testid="approvals-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading flex items-center gap-2">
            <Workflow size={22} className="text-primary" /> Approvals
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Multi-step approval workflows · routing requests through your org</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" disabled={workflows.length === 0} onClick={() => setShowReqForm(true)} data-testid="apr-new-req-btn"><Send size={14} className="mr-1" />New Request</Button>
          <Button size="sm" variant="outline" onClick={() => setShowWfForm(true)} data-testid="apr-new-wf-btn"><Plus size={14} className="mr-1" />New Workflow</Button>
        </div>
      </div>

      <Tabs defaultValue="inbox" className="space-y-3">
        <TabsList>
          <TabsTrigger value="inbox" data-testid="apr-tab-inbox"><Inbox size={13} className="mr-1" />Inbox ({inbox.length})</TabsTrigger>
          <TabsTrigger value="mine" data-testid="apr-tab-mine"><Send size={13} className="mr-1" />My Requests ({mine.length})</TabsTrigger>
          <TabsTrigger value="all" data-testid="apr-tab-all">All ({all.length})</TabsTrigger>
          <TabsTrigger value="workflows" data-testid="apr-tab-wf">Workflows ({workflows.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="inbox" className="space-y-2">
          {inbox.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">Inbox zero — nothing requires your action right now.</p> :
            inbox.map(r => <RequestCard key={r.id} r={r} />)}
        </TabsContent>

        <TabsContent value="mine" className="space-y-2">
          {mine.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">You haven't submitted any requests.</p> :
            mine.map(r => <RequestCard key={r.id} r={r} showActions />)}
        </TabsContent>

        <TabsContent value="all" className="space-y-2">
          {all.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No requests yet.</p> :
            all.map(r => <RequestCard key={r.id} r={r} />)}
        </TabsContent>

        <TabsContent value="workflows" className="space-y-2">
          {workflows.length === 0 ? <p className="text-sm text-muted-foreground text-center py-12">No workflows defined. Click "New Workflow" to start.</p> : workflows.map(wf => (
            <Card key={wf.id} className="rounded-xl" data-testid={`wf-${wf.id}`}>
              <CardContent className="p-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <p className="text-sm font-medium">{wf.name} <Badge variant="outline" className="text-[10px] ml-1 capitalize">{wf.kind}</Badge></p>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1 flex-wrap">
                      {wf.steps.map((s, i) => (
                        <React.Fragment key={s.id || `${wf.id}-step-${i}`}>
                          {i > 0 && <ArrowRight size={10} />}
                          <span className="px-1.5 py-0.5 rounded bg-muted">{s.name} <span className="opacity-60">({s.approver_role || s.approver_user_id})</span></span>
                        </React.Fragment>
                      ))}
                    </div>
                  </div>
                  <Button size="sm" variant="ghost" className="h-7 text-destructive" onClick={() => deleteWorkflow(wf.id)} data-testid={`wf-del-${wf.id}`}><Trash2 size={12} /></Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>

      {/* New Workflow Dialog */}
      <Dialog open={showWfForm} onOpenChange={setShowWfForm}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Approval Workflow</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Name *</Label><Input value={wfForm.name} onChange={e => setWfForm({...wfForm, name: e.target.value})} placeholder="Expense > $100" data-testid="wf-name" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Kind</Label>
                <Select value={wfForm.kind} onValueChange={v => setWfForm({...wfForm, kind: v})}>
                  <SelectTrigger data-testid="wf-kind"><SelectValue /></SelectTrigger>
                  <SelectContent>{KINDS.map(k => <SelectItem key={k} value={k} className="capitalize">{k.replace('_', ' ')}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Steps</Label>
              {wfForm.steps.map((s, i) => (
                <div key={s._key || `s-${i}`} className="grid grid-cols-12 gap-2 items-end p-2 border rounded" data-testid={`wf-step-${i}`}>
                  <div className="col-span-5 space-y-1"><Label className="text-[10px]">Name</Label><Input className="h-8 text-xs" value={s.name} onChange={e => updateStep(i, 'name', e.target.value)} placeholder="Manager review" /></div>
                  <div className="col-span-4 space-y-1"><Label className="text-[10px]">Approver Role</Label>
                    <Select value={s.approver_role || 'none'} onValueChange={v => updateStep(i, 'approver_role', v === 'none' ? '' : v)}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="none">(specific user)</SelectItem>{ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-2 space-y-1"><Label className="text-[10px]">Min Approvals</Label><Input className="h-8 text-xs" type="number" min={1} value={s.min_approvals || 1} onChange={e => updateStep(i, 'min_approvals', parseInt(e.target.value) || 1)} /></div>
                  <Button type="button" size="sm" variant="ghost" className="col-span-1 h-8 text-destructive" disabled={wfForm.steps.length === 1} onClick={() => removeStep(i)}>×</Button>
                </div>
              ))}
              <Button type="button" size="sm" variant="outline" className="w-full h-8 text-xs" onClick={addWfStep}><Plus size={12} className="mr-1" />Add Step</Button>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowWfForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={createWorkflow} disabled={!wfForm.name} data-testid="wf-submit">Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* New Request Dialog */}
      <Dialog open={showReqForm} onOpenChange={setShowReqForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Approval Request</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5"><Label className="text-xs">Workflow *</Label>
              <Select value={reqForm.workflow_id} onValueChange={v => setReqForm({...reqForm, workflow_id: v})}>
                <SelectTrigger data-testid="req-workflow"><SelectValue placeholder="Pick workflow" /></SelectTrigger>
                <SelectContent>{workflows.map(wf => <SelectItem key={wf.id} value={wf.id}>{wf.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Title *</Label><Input value={reqForm.title} onChange={e => setReqForm({...reqForm, title: e.target.value})} data-testid="req-title" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Summary</Label><Textarea rows={2} value={reqForm.summary} onChange={e => setReqForm({...reqForm, summary: e.target.value})} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Amount</Label><Input type="number" step="0.01" value={reqForm.amount} onChange={e => setReqForm({...reqForm, amount: e.target.value})} /></div>
              <div className="space-y-1.5"><Label className="text-xs">Currency</Label>
                <Select value={reqForm.currency} onValueChange={v => setReqForm({...reqForm, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','EUR','GBP'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowReqForm(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitRequest} disabled={!reqForm.workflow_id || !reqForm.title} data-testid="req-submit">Submit</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* View Request Dialog */}
      <Dialog open={!!viewReq} onOpenChange={(o) => { if (!o) { setViewReq(null); setActNote(''); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{viewReq?.title}</DialogTitle></DialogHeader>
          {viewReq && (
            <div className="space-y-3 mt-2 text-sm">
              <div className="flex items-center gap-2 flex-wrap text-xs">
                <Badge variant="outline" className="capitalize">{viewReq.subject_kind}</Badge>
                <Badge className={`capitalize ${STATUS_COLOR[viewReq.status]}`}>{viewReq.status.replace('_', ' ')}</Badge>
                {viewReq.auto_generated && <Badge className="bg-blue-100 text-blue-700">auto-generated</Badge>}
                <span className="text-muted-foreground">by {viewReq.submitted_by_name} · {viewReq.workflow_name}</span>
              </div>
              {viewReq.summary && <p className="text-xs italic">{viewReq.summary}</p>}
              {viewReq.amount != null && <p className="text-base font-bold">{viewReq.currency} {(viewReq.amount || 0).toLocaleString()}</p>}
              <div className="space-y-1.5">
                <p className="text-xs font-semibold uppercase text-muted-foreground">Approval chain</p>
                {viewReq.workflow_snapshot.steps.map((st, idx) => {
                  const state = viewReq.step_states[idx];
                  const isCurrent = viewReq.status === 'in_progress' && idx === viewReq.current_step;
                  return (
                    <div key={st.id || `step-${idx}`} className={`p-2 rounded border ${isCurrent ? 'border-primary bg-primary/5' : ''}`} data-testid={`req-step-${idx}`}>
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium">{idx + 1}. {st.name} <span className="text-xs text-muted-foreground font-normal">({st.approver_role || 'specific user'})</span></p>
                        <Badge className={`text-[10px] capitalize ${STATUS_COLOR[state.status] || STATUS_COLOR.in_progress}`}>{state.status}</Badge>
                      </div>
                      {state.approvals?.length > 0 && (
                        <div className="mt-1 space-y-0.5">
                          {state.approvals.map((a) => (
                            <p key={`${a.user_id}-${a.at}`} className="text-[11px] text-muted-foreground">
                              {a.outcome === 'approved' ? '✓' : '✗'} {a.user_name} ({a.user_role}) — <em>{a.note || 'no note'}</em>
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              {viewReq.status === 'in_progress' && (
                <div className="space-y-2 pt-2 border-t">
                  <Label className="text-xs">Decision Note (optional)</Label>
                  <Textarea rows={2} value={actNote} onChange={e => setActNote(e.target.value)} data-testid="req-act-note" />
                  <div className="flex gap-2">
                    <Button variant="destructive" className="flex-1" onClick={() => actOnRequest(viewReq, 'rejected')} data-testid="req-reject-btn"><X size={14} className="mr-1" />Reject</Button>
                    <Button className="flex-1" onClick={() => actOnRequest(viewReq, 'approved')} data-testid="req-approve-btn"><Check size={14} className="mr-1" />Approve</Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
