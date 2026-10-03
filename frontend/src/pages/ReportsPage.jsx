import React, { useState, useEffect, useMemo } from 'react';
import { FileText, Download, BarChart3, Users, DollarSign, Calendar } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { reportsApi, locationsApi } from '../services/api';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';

// iter 291 — the Reports page can now flip between the five finance ledger
// reports, honour a user-supplied FX rate for export, and download either a
// PDF (iter374: letterheaded with the organisation's OWN logo + name, the
// period, the campus and a prepared-by / printed-on line) or a CSV. Restricted users no longer see "All Locations" — they're pinned to
// their assigned campus/sublocation set.
const REPORT_TYPES = [
  { value: 'summary', label: 'Summary (revenue · expenses · people)' },
  { value: 'trial-balance', label: 'Trial Balance' },
  { value: 'pnl', label: 'Profit & Loss' },
  { value: 'balance-sheet', label: 'Balance Sheet' },
  { value: 'cashflow', label: 'Cash Flow' },
  { value: 'expenditure', label: 'Expenditure Detail (what · why · who)' },
];

export default function ReportsPage() {
  const { user } = useAuth();
  const isAdmin = ['admin', 'system_admin', 'director', 'Executive Director'].includes(user?.role || '');

  const [locations, setLocations] = useState([]);
  const [reportType, setReportType] = useState('summary');
  const [locationId, setLocationId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // iter375 — rates saved in Settings → Exchange rates, so nobody retypes one
  const [savedFx, setSavedFx] = useState({ base: '', rates: {} });
  useEffect(() => {
    (async () => {
      try {
        const api = (await import('../services/api')).default;
        const r = await api.get('/finance/fx/rates');
        setSavedFx({ base: r.data.base || '', rates: r.data.rates || {} });
      } catch { /* staff without finance access simply type a rate */ }
    })();
  }, []);

  // iter374 — click a P&L expense total to see the payments behind it
  const [drill, setDrill] = useState(null);   // { code, name, loading, data }

  // FX conversion (optional at export time)
  const [fxTarget, setFxTarget] = useState('');
  const [fxRate, setFxRate] = useState('');

  useEffect(() => {
    locationsApi.list().then(r => {
      const rows = r.data || [];
      setLocations(rows);
      // Restricted users get pinned to their first assigned location so the
      // dropdown never surfaces "All Locations" or a campus they can't see.
      if (!isAdmin && !locationId) {
        const mine = user?.active_campus_id || user?.location_id || (user?.location_ids || [])[0];
        if (mine) setLocationId(mine);
      }
    }).catch(() => {});
    // We intentionally re-run on role change (login → landing on page).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  // A report of one shape must never render under another type's table.
  useEffect(() => { setReport(null); }, [reportType]);

  const fetchReport = async () => {
    setLoading(true);
    setReport(null);
    try {
      const params = {};
      if (locationId) params.location_id = locationId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const api = (await import('../services/api')).default;
      const res = reportType === 'summary'
        ? await reportsApi.summary(params)
        : reportType === 'expenditure'
          ? await api.get('/finance/reports/expenditure', { params })
          : await api.get(`/finance/reports/${reportType}`, { params });
      setReport(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to generate report');
    } finally {
      setLoading(false);
    }
  };

  const openDrill = async (row) => {
    setDrill({ code: row.code, name: row.name, loading: true, data: null });
    try {
      const api = (await import('../services/api')).default;
      const params = { account_code: row.code };
      if (locationId) params.location_id = locationId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await api.get('/finance/reports/expenditure', { params });
      setDrill(d => ({ ...d, loading: false, data: res.data }));
    } catch {
      toast.error('Could not load the payments behind that total');
      setDrill(null);
    }
  };

  const applyFx = (n) => {
    const rate = Number(fxRate);
    if (!fxTarget || !rate || rate <= 0) return n;
    return Number(n || 0) * rate;
  };

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const params = {};
      if (locationId) params.location_id = locationId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (fxTarget && Number(fxRate) > 0) { params.fx_target = fxTarget; params.fx_rate = fxRate; }
      // Each report type has its own PDF now — the button used to hand you the
      // summary PDF no matter what was on screen (iter375).
      const FINANCE_PDFS = {
        expenditure: 'expenditure',
        'trial-balance': 'trial-balance',
        pnl: 'pnl',
        'balance-sheet': 'balance-sheet',
        cashflow: 'cashflow',
      };
      let res;
      if (FINANCE_PDFS[reportType]) {
        const api = (await import('../services/api')).default;
        res = await api.get(`/finance/reports/${FINANCE_PDFS[reportType]}.pdf`, { params, responseType: 'blob' });
      } else {
        res = await reportsApi.pdf(params);
      }
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${reportType}_${new Date().toISOString().split('T')[0]}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success('PDF downloaded');
    } catch { toast.error('PDF download failed'); }
    finally { setDownloading(false); }
  };

  // Client-side CSV export — turns whatever the current report shape is into
  // a flat table. Falls back to a "no rows" file for reports with no natural
  // rows (Cash Flow) so the download button never dead-ends.
  const downloadCsv = () => {
    if (!report) { toast.error('Run the report first'); return; }
    const fxSuffix = fxTarget && Number(fxRate) > 0 ? ` (in ${fxTarget} @ ${fxRate})` : '';
    let headers = [];
    let rows = [];
    if (reportType === 'summary') {
      headers = ['Metric', `Value${fxSuffix}`];
      rows = [
        ['Total Income', applyFx(report.total_income)],
        ['Total Expenses', applyFx(report.total_expenses)],
        ['Net Balance', applyFx(report.net)],
        ['Members', report.members_count],
        ['Children', report.children_count],
        ['Events', report.events_count],
      ];
    } else if (reportType === 'trial-balance') {
      headers = ['Code', 'Account', 'Type', `Debit${fxSuffix}`, `Credit${fxSuffix}`, `Balance${fxSuffix}`];
      rows = (report.rows || []).map(r => [r.code, r.name, r.type, applyFx(r.debit), applyFx(r.credit), applyFx(r.balance)]);
      rows.push(['', 'TOTAL', '', applyFx(report.total_debit), applyFx(report.total_credit), '']);
    } else if (reportType === 'pnl') {
      headers = ['Section', 'Code', 'Account', `Amount${fxSuffix}`];
      (report.revenue || []).forEach(r => rows.push(['Revenue', r.code, r.name, applyFx(r.amount)]));
      rows.push(['', '', 'Total Revenue', applyFx(report.total_revenue)]);
      (report.expenses || []).forEach(r => rows.push(['Expense', r.code, r.name, applyFx(r.amount)]));
      rows.push(['', '', 'Total Expenses', applyFx(report.total_expenses)]);
      rows.push(['', '', 'Net Income', applyFx(report.net_income)]);
    } else if (reportType === 'balance-sheet') {
      headers = ['Section', 'Code', 'Account', `Amount${fxSuffix}`];
      (report.assets || []).forEach(r => rows.push(['Asset', r.code, r.name, applyFx(r.amount)]));
      rows.push(['', '', 'Total Assets', applyFx(report.total_assets)]);
      (report.liabilities || []).forEach(r => rows.push(['Liability', r.code, r.name, applyFx(r.amount)]));
      rows.push(['', '', 'Total Liabilities', applyFx(report.total_liabilities)]);
      (report.equity || []).forEach(r => rows.push(['Equity', r.code, r.name, applyFx(r.amount)]));
      rows.push(['', '', 'Total Equity', applyFx(report.total_equity)]);
    } else if (reportType === 'expenditure') {
      headers = ['Date', 'Paid to', 'Description', 'Category', 'Campus', 'Paid by', 'Recorded by', 'Ref / receipt', `Amount${fxSuffix}`, 'Status'];
      rows = (report.rows || []).map(r => [r.date, r.payee, r.description, r.category, r.location_name, r.paid_by, r.recorded_by, r.reference, applyFx(r.amount), r.status]);
      rows.push([]);
      rows.push(['SUBTOTALS BY CATEGORY, THEN CAMPUS']);
      (report.by_category || []).forEach(c => {
        rows.push([c.category, '', '', '', '', '', '', `${c.count} payments`, applyFx(c.total), '']);
        (c.campuses || []).forEach(camp => rows.push(['', camp.location_name, '', '', '', '', '', `${camp.count} payments`, applyFx(camp.total), '']));
      });
      rows.push(['TOTAL', '', '', '', '', '', '', `${report.count} payments`, applyFx(report.total), '']);
    } else if (reportType === 'cashflow') {
      headers = ['Date', 'Description', `Amount${fxSuffix}`];
      rows = (report.lines || []).map(l => [l.date, l.description, applyFx(l.amount)]);
      rows.push(['', 'Net Change', applyFx(report.net_change)]);
    }
    const escape = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const csv = [headers.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${reportType}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success('CSV downloaded');
  };

  const statCards = report && reportType === 'summary' ? [
    { label: 'Total Income', value: applyFx(report.total_income || 0).toLocaleString(), icon: DollarSign, color: 'text-green-600 bg-green-50' },
    { label: 'Total Expenses', value: applyFx(report.total_expenses || 0).toLocaleString(), icon: DollarSign, color: 'text-red-600 bg-red-50' },
    { label: 'Net Balance', value: applyFx(report.net || 0).toLocaleString(), icon: BarChart3, color: (report.net || 0) >= 0 ? 'text-green-600 bg-green-50' : 'text-red-600 bg-red-50' },
    { label: 'Members', value: report.members_count || 0, icon: Users, color: 'text-blue-600 bg-blue-50' },
    { label: 'Children', value: report.children_count || 0, icon: Users, color: 'text-purple-600 bg-purple-50' },
    { label: 'Events', value: report.events_count || 0, icon: Calendar, color: 'text-amber-600 bg-amber-50' },
  ] : [];

  const showAllLocations = isAdmin;
  const fxSuffix = fxTarget && Number(fxRate) > 0 ? ` (in ${fxTarget} @ ${fxRate})` : '';

  return (
    <div className="p-6 space-y-5" data-testid="reports-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="reports-page-title">Reports</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Generate and export comprehensive reports</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" onClick={downloadCsv} disabled={!report} data-testid="download-csv-btn">
            <Download size={16} /> CSV
          </Button>
          <Button className="gap-2" onClick={downloadPdf} disabled={downloading || !report} data-testid="download-pdf-btn">
            <Download size={16} /> {downloading ? 'Generating...' : 'PDF'}
          </Button>
        </div>
      </div>

      <Card className="shadow-soft rounded-xl">
        <CardContent className="p-4">
          <div className="flex items-end gap-3 flex-wrap">
            <div className="space-y-1.5 w-52">
              <Label className="text-xs">Report</Label>
              <Select value={reportType} onValueChange={setReportType}>
                <SelectTrigger className="h-9" data-testid="report-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{REPORT_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5 w-48">
              <Label className="text-xs">Location</Label>
              <Select value={locationId || '__all__'} onValueChange={v => setLocationId(v === '__all__' ? '' : v)}>
                <SelectTrigger className="h-9" data-testid="report-location-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {showAllLocations && <SelectItem value="__all__">All Locations</SelectItem>}
                  {locations.length === 0 && <div className="px-3 py-2 text-xs text-muted-foreground">No locations found</div>}
                  {/* iter 293 — visually nest sublocations under their parent. Sort so
                      each parent is followed by its children; children get a leading
                      "└" glyph + left padding so the hierarchy is obvious at a glance. */}
                  {[...locations]
                    .sort((a, b) => {
                      const pa = a.parent_id || a.id;
                      const pb = b.parent_id || b.id;
                      if (pa !== pb) return String(pa).localeCompare(String(pb));
                      // Parent (no parent_id) sorts before children of the same group
                      if (!a.parent_id && b.parent_id) return -1;
                      if (a.parent_id && !b.parent_id) return 1;
                      return String(a.name || '').localeCompare(String(b.name || ''));
                    })
                    .map(l => (
                      <SelectItem key={l.id} value={l.id} data-testid={`report-location-option-${l.id}`}>
                        {l.parent_id ? <span className="pl-4 text-muted-foreground">└ {l.name}</span> : l.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">From</Label><Input type="date" className="h-9 w-40" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></div>
            <div className="space-y-1.5"><Label className="text-xs">To</Label><Input type="date" className="h-9 w-40" value={dateTo} onChange={e => setDateTo(e.target.value)} /></div>
            <Button variant="outline" onClick={fetchReport} disabled={loading} data-testid="generate-report-btn">
              {loading ? 'Loading...' : 'Generate Report'}
            </Button>
          </div>
          {/* FX conversion — picks up the rates saved in Settings. */}
          <div className="flex flex-wrap items-end gap-3 mt-3 pt-3 border-t">
            <div className="space-y-1.5 w-44">
              <Label className="text-xs">Show in currency</Label>
              <Select value={fxTarget || '__base__'} onValueChange={v => {
                if (v === '__base__') { setFxTarget(''); setFxRate(''); return; }
                setFxTarget(v);
                setFxRate(String(savedFx.rates[v] ?? ''));
              }}>
                <SelectTrigger className="h-9" data-testid="fx-target"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__base__">{savedFx.base || 'Base'} (no conversion)</SelectItem>
                  {Object.keys(savedFx.rates).map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5 w-40">
              <Label className="text-xs">Rate (1 {savedFx.base || 'base'} = ?)</Label>
              <Input type="number" step="0.000001" placeholder="e.g. 0.00027" className="h-9" value={fxRate} onChange={e => setFxRate(e.target.value)} data-testid="fx-rate" />
            </div>
            <p className="text-xs text-muted-foreground pb-2">
              {Object.keys(savedFx.rates).length === 0
                ? 'No saved rates yet — '
                : 'Picked up from settings. Change the rate here to override it for this export only. '}
              <a href="/app-settings" className="underline" data-testid="fx-manage-link">Manage exchange rates</a>
            </p>
          </div>
        </CardContent>
      </Card>

      {report && reportType === 'summary' && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            {statCards.map((card, i) => (
              <Card key={card.label} className="shadow-soft rounded-xl" data-testid={`report-stat-${i}`}>
                <CardContent className="p-4 flex items-start gap-3">
                  <div className={`h-10 w-10 rounded-lg flex items-center justify-center shrink-0 ${card.color}`}><card.icon size={20} /></div>
                  <div><p className="text-xs text-muted-foreground">{card.label}</p><p className="text-xl font-semibold mt-0.5">{card.value}</p></div>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="text-xs text-muted-foreground text-center">Report{fxSuffix} generated: {new Date().toLocaleDateString()} {locationId ? `| Location: ${locations.find(l => l.id === locationId)?.name || locationId}` : '| All locations'} {dateFrom ? `| From: ${dateFrom}` : ''} {dateTo ? `| To: ${dateTo}` : ''}</p>
        </>
      )}

      {report && reportType !== 'summary' && (
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm">{REPORT_TYPES.find(t => t.value === reportType)?.label}{fxSuffix}</CardTitle>
            {dateFrom || dateTo ? <span className="text-xs text-muted-foreground">{dateFrom || '…'} → {dateTo || 'today'}</span> : null}
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <ReportTable reportType={reportType} report={report} applyFx={applyFx} onDrill={openDrill} />
          </CardContent>
        </Card>
      )}

      <Dialog open={!!drill} onOpenChange={o => { if (!o) setDrill(null); }}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" data-testid="pnl-drill-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">{drill?.code} {drill?.name}</DialogTitle>
            <DialogDescription>
              Every payment behind this total{dateFrom || dateTo ? ` · ${dateFrom || '…'} → ${dateTo || 'today'}` : ''}
            </DialogDescription>
          </DialogHeader>
          {drill?.loading && <p className="text-sm text-muted-foreground py-6 text-center">Loading…</p>}
          {drill?.data && (
            <>
              <p className="text-xs text-muted-foreground">
                {drill.data.count} payments · total <strong className="font-mono">{Number(drill.data.total || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
              </p>
              <table className="w-full text-sm border-collapse mt-2">
                <thead><tr className="bg-muted/40 text-xs uppercase text-muted-foreground">
                  <th className="text-left px-2 py-2 font-medium">Date</th>
                  <th className="text-left px-2 py-2 font-medium">Paid to</th>
                  <th className="text-left px-2 py-2 font-medium">Description</th>
                  <th className="text-left px-2 py-2 font-medium">Campus</th>
                  <th className="text-left px-2 py-2 font-medium">Paid by</th>
                  <th className="text-left px-2 py-2 font-medium">Ref</th>
                  <th className="text-right px-2 py-2 font-medium">Amount</th>
                </tr></thead>
                <tbody>
                  {drill.data.rows.length === 0 && <tr><td colSpan={7} className="text-center text-muted-foreground py-6 text-xs">No payments in this period</td></tr>}
                  {drill.data.rows.map((r, i) => (
                    <tr key={`${r.id}-${i}`} className="border-t" data-testid={`drill-row-${i}`}>
                      <td className="px-2 py-1.5 font-mono text-xs whitespace-nowrap">{r.date}</td>
                      <td className="px-2 py-1.5">{r.payee || '—'}</td>
                      <td className="px-2 py-1.5">{r.description || '—'}</td>
                      <td className="px-2 py-1.5 text-xs">{r.location_name}</td>
                      <td className="px-2 py-1.5 text-xs">{r.paid_by || '—'}</td>
                      <td className="px-2 py-1.5 font-mono text-xs">{r.reference || '—'}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{Number(r.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </DialogContent>
      </Dialog>

      {!report && !loading && (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <FileText size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground">Pick a report type and click "Generate Report"</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── REPORT TABLE ────────────────────────────────────────────
// Turns the four finance-reports shapes (trial-balance / pnl / balance-sheet
// / cashflow) into on-screen tables so users can actually read the numbers
// without opening the CSV/PDF export. Currency conversion (`applyFx`) is
// applied at render time so the same table doubles as the print preview
// when a target currency + rate has been entered.
function ReportTable({ reportType, report, applyFx, onDrill }) {
  const fmt = (n) => Number(applyFx(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (!report) return null;

  if (reportType === 'trial-balance') {
    const rows = report.rows || [];
    return (
      <table className="w-full text-sm border-collapse" data-testid="report-table-trial-balance">
        <thead>
          <tr className="bg-muted/40 text-xs uppercase text-muted-foreground">
            <th className="text-left px-3 py-2 font-medium">Code</th>
            <th className="text-left px-3 py-2 font-medium">Account</th>
            <th className="text-left px-3 py-2 font-medium">Type</th>
            <th className="text-right px-3 py-2 font-medium">Debit</th>
            <th className="text-right px-3 py-2 font-medium">Credit</th>
            <th className="text-right px-3 py-2 font-medium">Balance</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={6} className="text-center text-muted-foreground py-6 text-xs">No entries in this period</td></tr>}
          {rows.map((r, i) => (
            <tr key={r.account_id || i} className="border-t hover:bg-muted/20">
              <td className="px-3 py-1.5 font-mono text-xs">{r.code}</td>
              <td className="px-3 py-1.5">{r.name}</td>
              <td className="px-3 py-1.5 text-xs text-muted-foreground capitalize">{r.type}</td>
              <td className="px-3 py-1.5 text-right font-mono">{fmt(r.debit)}</td>
              <td className="px-3 py-1.5 text-right font-mono">{fmt(r.credit)}</td>
              <td className={`px-3 py-1.5 text-right font-mono font-medium ${Number(r.balance) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>{fmt(r.balance)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 font-semibold bg-muted/20">
            <td colSpan={3} className="px-3 py-2 text-right">TOTAL</td>
            <td className="px-3 py-2 text-right font-mono">{fmt(report.total_debit)}</td>
            <td className="px-3 py-2 text-right font-mono">{fmt(report.total_credit)}</td>
            <td className={`px-3 py-2 text-right font-mono ${report.balanced ? 'text-emerald-700' : 'text-rose-700'}`}>{report.balanced ? '✓ balanced' : '✗ off'}</td>
          </tr>
        </tfoot>
      </table>
    );
  }

  if (reportType === 'pnl') {
    return (
      <table className="w-full text-sm border-collapse" data-testid="report-table-pnl">
        <tbody>
          <tr className="bg-muted/40 text-xs uppercase font-medium"><td colSpan={3} className="px-3 py-2">Revenue</td></tr>
          {(report.revenue || []).map((r, i) => (
            <tr key={`rev-${i}`} className="border-t"><td className="px-3 py-1.5 font-mono text-xs w-16">{r.code}</td><td className="px-3 py-1.5">{r.name}</td><td className="px-3 py-1.5 text-right font-mono">{fmt(r.amount)}</td></tr>
          ))}
          <tr className="border-t bg-emerald-50 font-medium"><td colSpan={2} className="px-3 py-2">Total Revenue</td><td className="px-3 py-2 text-right font-mono">{fmt(report.total_revenue)}</td></tr>
          <tr className="bg-muted/40 text-xs uppercase font-medium"><td colSpan={3} className="px-3 py-2 pt-4">Expenses</td></tr>
          {(report.expenses || []).map((r, i) => (
            <tr key={`exp-${i}`} className="border-t hover:bg-amber-50/60 cursor-pointer" onClick={() => onDrill?.(r)}
              title="See every payment behind this total" data-testid={`pnl-drill-${r.code}`}>
              <td className="px-3 py-1.5 font-mono text-xs w-16">{r.code}</td>
              <td className="px-3 py-1.5">{r.name} <span className="text-[10px] text-muted-foreground">· see the payments</span></td>
              <td className="px-3 py-1.5 text-right font-mono">{fmt(r.amount)}</td>
            </tr>
          ))}
          <tr className="border-t bg-rose-50 font-medium"><td colSpan={2} className="px-3 py-2">Total Expenses</td><td className="px-3 py-2 text-right font-mono">{fmt(report.total_expenses)}</td></tr>
          <tr className={`border-t-2 font-bold text-base ${Number(report.net_income) >= 0 ? 'bg-emerald-100' : 'bg-rose-100'}`}><td colSpan={2} className="px-3 py-2">Net Income</td><td className="px-3 py-2 text-right font-mono">{fmt(report.net_income)}</td></tr>
        </tbody>
      </table>
    );
  }

  if (reportType === 'expenditure') {
    const rows = report.rows || [];
    return (
      <div className="space-y-6">
        <div className="flex flex-wrap gap-4 text-xs">
          <span><span className="text-muted-foreground">Posted to the ledger: </span><strong className="font-mono">{fmt(report.total_posted)}</strong></span>
          <span><span className="text-muted-foreground">Awaiting approval: </span><strong className="font-mono text-amber-700">{fmt(report.total_pending)}</strong></span>
          <span><span className="text-muted-foreground">Total: </span><strong className="font-mono">{fmt(report.total)}</strong> over {report.count} payments</span>
        </div>

        <table className="w-full text-sm border-collapse" data-testid="report-table-expenditure">
          <thead>
            <tr className="bg-muted/40 text-xs uppercase text-muted-foreground">
              <th className="text-left px-2 py-2 font-medium">Date</th>
              <th className="text-left px-2 py-2 font-medium">Paid to</th>
              <th className="text-left px-2 py-2 font-medium">Description</th>
              <th className="text-left px-2 py-2 font-medium">Category</th>
              <th className="text-left px-2 py-2 font-medium">Campus</th>
              <th className="text-left px-2 py-2 font-medium">Paid by</th>
              <th className="text-left px-2 py-2 font-medium">Recorded by</th>
              <th className="text-left px-2 py-2 font-medium">Ref</th>
              <th className="text-right px-2 py-2 font-medium">Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={9} className="text-center text-muted-foreground py-6 text-xs">No expenditure in this period</td></tr>}
            {rows.map((r, i) => (
              <tr key={`${r.id}-${i}`} className="border-t hover:bg-muted/20" data-testid={`expenditure-row-${i}`}>
                <td className="px-2 py-1.5 whitespace-nowrap font-mono text-xs">{r.date}</td>
                <td className="px-2 py-1.5">{r.payee || <span className="text-muted-foreground">—</span>}</td>
                <td className="px-2 py-1.5 max-w-[260px]">{r.description || <span className="text-muted-foreground">—</span>}</td>
                <td className="px-2 py-1.5 text-xs">{r.category}</td>
                <td className="px-2 py-1.5 text-xs">{r.location_name}</td>
                <td className="px-2 py-1.5 text-xs">{r.paid_by || <span className="text-muted-foreground">—</span>}</td>
                <td className="px-2 py-1.5 text-xs">{r.recorded_by || <span className="text-muted-foreground">—</span>}</td>
                <td className="px-2 py-1.5 font-mono text-xs">{r.reference || '—'}</td>
                <td className="px-2 py-1.5 text-right font-mono">
                  {fmt(r.amount)}
                  {r.status !== 'posted' && <span className="ml-1 text-[10px] text-amber-700">{r.status}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-2">Subtotals — by category, then campus</p>
          <table className="w-full text-sm border-collapse" data-testid="expenditure-subtotals">
            <tbody>
              {(report.by_category || []).map((c, i) => (
                <React.Fragment key={c.category + i}>
                  <tr className="bg-muted/40 border-t font-medium">
                    <td className="px-3 py-1.5">{c.category}</td>
                    <td className="px-3 py-1.5 text-right text-xs text-muted-foreground">{c.count} payments</td>
                    <td className="px-3 py-1.5 text-right font-mono">{fmt(c.total)}</td>
                  </tr>
                  {(c.campuses || []).map((camp, j) => (
                    <tr key={`${c.category}-${j}`} className="border-t">
                      <td className="px-3 py-1 pl-8 text-xs text-muted-foreground">{camp.location_name}</td>
                      <td className="px-3 py-1 text-right text-xs text-muted-foreground">{camp.count}</td>
                      <td className="px-3 py-1 text-right font-mono text-xs">{fmt(camp.total)}</td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (reportType === 'balance-sheet') {
    const section = (label, rows, total, tone) => (
      <>
        <tr className="bg-muted/40 text-xs uppercase font-medium"><td colSpan={3} className="px-3 py-2">{label}</td></tr>
        {(rows || []).map((r, i) => (
          <tr key={`${label}-${i}`} className="border-t"><td className="px-3 py-1.5 font-mono text-xs w-16">{r.code}</td><td className="px-3 py-1.5">{r.name}</td><td className="px-3 py-1.5 text-right font-mono">{fmt(r.amount)}</td></tr>
        ))}
        <tr className={`border-t font-medium bg-${tone}-50`}><td colSpan={2} className="px-3 py-2">Total {label}</td><td className="px-3 py-2 text-right font-mono">{fmt(total)}</td></tr>
      </>
    );
    return (
      <table className="w-full text-sm border-collapse" data-testid="report-table-balance-sheet">
        <tbody>
          {section('Assets', report.assets, report.total_assets, 'sky')}
          {section('Liabilities', report.liabilities, report.total_liabilities, 'amber')}
          {section('Equity', report.equity, report.total_equity, 'emerald')}
        </tbody>
      </table>
    );
  }

  if (reportType === 'cashflow') {
    const lines = report.lines || [];
    return (
      <table className="w-full text-sm border-collapse" data-testid="report-table-cashflow">
        <thead>
          <tr className="bg-muted/40 text-xs uppercase text-muted-foreground">
            <th className="text-left px-3 py-2 font-medium">Date</th>
            <th className="text-left px-3 py-2 font-medium">Description</th>
            <th className="text-right px-3 py-2 font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {lines.length === 0 && <tr><td colSpan={3} className="text-center text-muted-foreground py-6 text-xs">{report.note || 'No cash movement in this period'}</td></tr>}
          {lines.map((l, i) => (
            <tr key={i} className="border-t">
              <td className="px-3 py-1.5 font-mono text-xs">{l.date}</td>
              <td className="px-3 py-1.5">{l.description}</td>
              <td className={`px-3 py-1.5 text-right font-mono ${Number(l.amount) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>{fmt(l.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 font-semibold bg-muted/20"><td colSpan={2} className="px-3 py-2 text-right">Net Change</td><td className={`px-3 py-2 text-right font-mono ${Number(report.net_change) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>{fmt(report.net_change)}</td></tr>
        </tfoot>
      </table>
    );
  }

  return <pre className="text-xs bg-muted p-3 rounded overflow-auto">{JSON.stringify(report, null, 2)}</pre>;
}
