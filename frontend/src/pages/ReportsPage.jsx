import React, { useState, useEffect } from 'react';
import { FileText, Download, BarChart3, Users, DollarSign, Calendar } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { reportsApi, locationsApi } from '../services/api';
import { toast } from 'sonner';

export default function ReportsPage() {
  const [locations, setLocations] = useState([]);
  const [locationId, setLocationId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => { locationsApi.list().then(r => setLocations(r.data)).catch(() => {}); }, []);

  const fetchReport = async () => {
    setLoading(true);
    try {
      const params = {};
      if (locationId) params.location_id = locationId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await reportsApi.summary(params);
      setReport(res.data);
    } catch { toast.error('Failed to generate report'); }
    finally { setLoading(false); }
  };

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const params = {};
      if (locationId) params.location_id = locationId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await reportsApi.pdf(params);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a'); a.href = url; a.download = `5812_report_${new Date().toISOString().split('T')[0]}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success('PDF downloaded');
    } catch { toast.error('PDF download failed'); }
    finally { setDownloading(false); }
  };

  const statCards = report ? [
    { label: 'Total Income', value: (report.total_income || 0).toLocaleString(), icon: DollarSign, color: 'text-green-600 bg-green-50' },
    { label: 'Total Expenses', value: (report.total_expenses || 0).toLocaleString(), icon: DollarSign, color: 'text-red-600 bg-red-50' },
    { label: 'Net Balance', value: (report.net || 0).toLocaleString(), icon: BarChart3, color: (report.net || 0) >= 0 ? 'text-green-600 bg-green-50' : 'text-red-600 bg-red-50' },
    { label: 'Members', value: report.members_count || 0, icon: Users, color: 'text-blue-600 bg-blue-50' },
    { label: 'Children', value: report.children_count || 0, icon: Users, color: 'text-purple-600 bg-purple-50' },
    { label: 'Events', value: report.events_count || 0, icon: Calendar, color: 'text-amber-600 bg-amber-50' },
  ] : [];

  return (
    <div className="p-6 space-y-5" data-testid="reports-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="reports-page-title">Reports</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Generate and export comprehensive reports</p>
        </div>
        <Button className="gap-2" onClick={downloadPdf} disabled={downloading || !report} data-testid="download-pdf-btn">
          <Download size={16} /> {downloading ? 'Generating...' : 'Export PDF'}
        </Button>
      </div>

      <Card className="shadow-soft rounded-xl">
        <CardContent className="p-4">
          <div className="flex items-end gap-3 flex-wrap">
            <div className="space-y-1.5 w-48">
              <Label className="text-xs">Location</Label>
              <Select value={locationId || '__all__'} onValueChange={v => setLocationId(v === '__all__' ? '' : v)}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="__all__">All Locations</SelectItem>{locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">From</Label><Input type="date" className="h-9 w-40" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></div>
            <div className="space-y-1.5"><Label className="text-xs">To</Label><Input type="date" className="h-9 w-40" value={dateTo} onChange={e => setDateTo(e.target.value)} /></div>
            <Button variant="outline" onClick={fetchReport} disabled={loading} data-testid="generate-report-btn">
              {loading ? 'Loading...' : 'Generate Report'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {report && (
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

          <div className="grid lg:grid-cols-2 gap-4">
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Income Breakdown</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(report.income_breakdown || []).map((d, i) => (
                    <div key={i} className="flex justify-between text-sm"><span className="text-muted-foreground capitalize">{d._id || 'Other'}</span><span className="font-medium text-green-600">{(d.total || 0).toLocaleString()} <span className="text-xs text-muted-foreground">({d.count})</span></span></div>
                  ))}
                  {(report.income_breakdown || []).length === 0 && <p className="text-xs text-muted-foreground">No income in period</p>}
                </div>
              </CardContent>
            </Card>
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Expense Breakdown</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(report.expense_breakdown || []).map((d, i) => (
                    <div key={i} className="flex justify-between text-sm"><span className="text-muted-foreground capitalize">{d._id || 'Other'}</span><span className="font-medium text-red-600">{(d.total || 0).toLocaleString()} <span className="text-xs text-muted-foreground">({d.count})</span></span></div>
                  ))}
                  {(report.expense_breakdown || []).length === 0 && <p className="text-xs text-muted-foreground">No expenses in period</p>}
                </div>
              </CardContent>
            </Card>
          </div>

          <p className="text-xs text-muted-foreground text-center">Report generated: {new Date().toLocaleDateString()} {locationId ? `| Location: ${locations.find(l => l.id === locationId)?.name || locationId}` : '| All locations'} {dateFrom ? `| From: ${dateFrom}` : ''} {dateTo ? `| To: ${dateTo}` : ''}</p>
        </>
      )}

      {!report && !loading && (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <FileText size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground">Click "Generate Report" to view statistics</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
