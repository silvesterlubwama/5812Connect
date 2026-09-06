import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Receipt, Send, DollarSign } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { portalApi } from '../services/api';
import { toast } from 'sonner';

const statusColors = {
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
};

export default function PortalExpenses() {
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showExpense, setShowExpense] = useState(false);
  const [showCashReq, setShowCashReq] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: '', amount: '', category: 'general', notes: '', currency: 'UGX' });
  const [cashForm, setCashForm] = useState({ amount: '', reason: '', currency: 'UGX' });
  const [searchParams, setSearchParams] = useSearchParams();
  const [highlightId, setHighlightId] = useState(null);
  const rowRefs = useRef({});

  // iter313 — deep-link support: `/portal/expenses?expense=<id>` (from an
  // approve/reject bell notification) scrolls the specific expense into
  // view and briefly ring-highlights it so the user can see what changed.
  useEffect(() => {
    const wanted = searchParams.get('expense');
    if (!wanted || !expenses.length) return;
    const row = rowRefs.current[wanted];
    if (row?.scrollIntoView) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setHighlightId(wanted);
    const t = setTimeout(() => setHighlightId(null), 3500);
    const next = new URLSearchParams(searchParams);
    next.delete('expense');
    setSearchParams(next, { replace: true });
    return () => clearTimeout(t);
  }, [expenses, searchParams, setSearchParams]);

  const fetchExpenses = async () => {
    setLoading(true);
    try {
      const res = await portalApi.expenses();
      setExpenses(res.data);
    } catch { toast.error('Failed to load expenses'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchExpenses(); }, []);

  const handleSubmitExpense = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await portalApi.createExpense({ ...form, amount: parseFloat(form.amount) });
      toast.success('Expense submitted');
      setShowExpense(false);
      setForm({ title: '', amount: '', category: 'general', notes: '', currency: 'UGX' });
      fetchExpenses();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleCashRequest = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await portalApi.cashRequest({ ...cashForm, amount: parseFloat(cashForm.amount) });
      toast.success('Cash request submitted and admins notified');
      setShowCashReq(false);
      setCashForm({ amount: '', reason: '', currency: 'UGX' });
      fetchExpenses();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const totalAmount = expenses.reduce((s, e) => s + (e.amount || 0), 0);
  const pendingCount = expenses.filter(e => e.status === 'pending').length;

  return (
    <div className="space-y-6 max-w-4xl" data-testid="portal-expenses">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading">My Expenses</h1>
          <p className="text-sm text-muted-foreground mt-1">{expenses.length} expenses, {pendingCount} pending</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-1.5" onClick={() => setShowCashReq(true)} data-testid="portal-cash-request-btn">
            <Send size={14} /> Cash Request
          </Button>
          <Button className="gap-1.5" onClick={() => setShowExpense(true)} data-testid="portal-add-expense-btn">
            <Plus size={14} /> Add Expense
          </Button>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5 flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-amber-500"><DollarSign size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Total Submitted</p>
              <p className="text-lg font-bold">{totalAmount.toLocaleString()} UGX</p>
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5 flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-blue-500"><Receipt size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Pending Approval</p>
              <p className="text-lg font-bold">{pendingCount}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Expense List */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Expense History</CardTitle>
        </CardHeader>
        <CardContent>
          {expenses.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">No expenses submitted yet</p>
          ) : (
            <div className="divide-y">
              {expenses.map(exp => (
                <div
                  key={exp.id}
                  ref={el => { if (el) rowRefs.current[exp.id] = el; }}
                  className={
                    'flex items-center justify-between py-3 rounded-md px-2 -mx-2 transition-shadow ' +
                    (highlightId === exp.id ? 'ring-2 ring-amber-400 bg-amber-50/50' : '')
                  }
                  data-testid={`expense-${exp.id}`}
                >
                  <div>
                    <p className="text-sm font-medium">{exp.title}</p>
                    <p className="text-xs text-muted-foreground">{exp.date} — {exp.category}{exp.is_cash_request && ' (Cash Request)'}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold">{(exp.amount || 0).toLocaleString()} {exp.currency || 'UGX'}</span>
                    <Badge className={`text-xs ${statusColors[exp.status] || statusColors.pending}`}>
                      {exp.status || 'pending'}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add Expense Dialog */}
      <Dialog open={showExpense} onOpenChange={setShowExpense}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Submit Expense</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmitExpense} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Title</Label>
              <Input placeholder="e.g. Transport to Entebbe" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} required data-testid="expense-title-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Amount</Label>
                <Input type="number" placeholder="0" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} required data-testid="expense-amount-input" />
              </div>
              <div className="space-y-2">
                <Label>Currency</Label>
                <Select value={form.currency} onValueChange={v => setForm({ ...form, currency: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="UGX">UGX</SelectItem>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="THB">THB</SelectItem>
                    <SelectItem value="HTG">HTG</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={form.category} onValueChange={v => setForm({ ...form, category: v })}>
                <SelectTrigger data-testid="expense-category-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="general">General</SelectItem>
                  <SelectItem value="transport">Transport</SelectItem>
                  <SelectItem value="supplies">Supplies</SelectItem>
                  <SelectItem value="food">Food</SelectItem>
                  <SelectItem value="utilities">Utilities</SelectItem>
                  <SelectItem value="programs">Programs</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Notes</Label>
              <Textarea placeholder="Optional details..." value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} />
            </div>
            <div className="flex gap-3">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowExpense(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Submitting...' : 'Submit Expense'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Cash Request Dialog */}
      <Dialog open={showCashReq} onOpenChange={setShowCashReq}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Cash Request</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Submit a cash request. Admins will be notified via chat.</p>
          <form onSubmit={handleCashRequest} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Amount</Label>
                <Input type="number" placeholder="0" value={cashForm.amount} onChange={e => setCashForm({ ...cashForm, amount: e.target.value })} required data-testid="cash-request-amount" />
              </div>
              <div className="space-y-2">
                <Label>Currency</Label>
                <Select value={cashForm.currency} onValueChange={v => setCashForm({ ...cashForm, currency: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="UGX">UGX</SelectItem>
                    <SelectItem value="USD">USD</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Reason</Label>
              <Textarea placeholder="Describe why you need this cash..." value={cashForm.reason} onChange={e => setCashForm({ ...cashForm, reason: e.target.value })} rows={3} required data-testid="cash-request-reason" />
            </div>
            <div className="flex gap-3">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowCashReq(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Sending...' : 'Send Request'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
