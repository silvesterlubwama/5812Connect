import React, { useState, useEffect } from 'react';
import { FileText, Download, BarChart3, Users, DollarSign, Calendar, MapPin, Building2 } from 'lucide-react';
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

  useEffect(() => {
    locationsApi.list().then(r => setLocations(r.data)).catch(() => {});
  }, []);

  const fetchReport = async () => {
    setLoading(true);
    try {
      const params = {};
      if (locationId) params.location_id = locationId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await reportsApi.summary(params);
      setReport(res.data);
    } catch { toast.error('Failed to load report'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchReport(); }, []);

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const params = {};
      if (locationId) params.location_id = locationId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await reportsApi.pdf(params);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `5812_report_${new Date().toISOString().split('T')[0]}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success('PDF downloaded');
    } catch { toast.error('PDF download failed'); }
    finally { setDownloading(false); }
  };

  const statCards = report ? [
    { label: 'Total Members', value: report.members?.total || 0, icon: Users, color: 'text-blue-600 bg-blue-50' },
    { label: 'Active Members', value: report.members?.active || 0, icon: Users, color: 'text-green-600 bg-green-50' },
    { label: 'Total Donations', value: `${(report.financial?.total_donations || 0).toLocaleString()}`, icon: DollarSign, color: 'text-emerald-600 bg-emerald-50' },
    { label: 'Total Expenses', value: `${(report.financial?.total_expenses || 0).toLocaleString()}`, icon: DollarSign, color: 'text-red-600 bg-red-50' },
    { label: 'Net Balance', value: `${(report.financial?.net || 0).toLocaleString()}`, icon: BarChart3, color: (report.financial?.net || 0) >= 0 ? 'text-green-600 bg-green-50' : 'text-red-600 bg-red-50' },
    { label: 'Total Events', value: report.events?.total || 0, icon: Calendar, color: 'text-purple-600 bg-purple-50' },
    { label: 'Total Check-ins', value: report.events?.checkins || 0, icon: Building2, color: 'text-amber-600 bg-amber-50' },
    { label: 'Locations', value: report.locations?.total || 0, icon: MapPin, color: 'text-indigo-600 bg-indigo-50' },
  ] : [];

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading" data-testid="reports-page-title">Reports</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Generate and export comprehensive reports</p>
        </div>
        <Button className="gap-2" onClick={downloadPdf} disabled={downloading} data-testid="download-pdf-btn">
          <Download size={16} /> {downloading ? 'Generating...' : 'Export PDF'}
        </Button>
      </div>

      {/* Filters */}
      <Card className="shadow-soft rounded-xl">
        <CardContent className="p-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Location</Label>
              <Select value={locationId || '_all'} onValueChange={v => setLocationId(v === '_all' ? '' : v)}>
                <SelectTrigger className="w-52" data-testid="report-location-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Locations</SelectItem>
                  {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">From</Label>
              <Input type="date" className="w-40" value={dateFrom} onChange={e => setDateFrom(e.target.value)} data-testid="report-date-from" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">To</Label>
              <Input type="date" className="w-40" value={dateTo} onChange={e => setDateTo(e.target.value)} data-testid="report-date-to" />
            </div>
            <Button variant="outline" onClick={fetchReport} disabled={loading} data-testid="generate-report-btn">
              {loading ? 'Loading...' : 'Generate Report'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Report Stats Grid */}
      {report && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {statCards.map((card, i) => (
              <Card key={s?.label || i} className="shadow-soft rounded-xl" data-testid={`report-stat-${i}`}>
                <CardContent className="p-4 flex items-start gap-3">
                  <div className={`h-10 w-10 rounded-lg flex items-center justify-center shrink-0 ${card.color}`}>
                    <card.icon size={20} />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">{card.label}</p>
                    <p className="text-xl font-semibold mt-0.5">{card.value}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Summary Details */}
          <div className="grid lg:grid-cols-2 gap-4">
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Members Overview</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total Members</span><span className="font-medium">{report.members?.total}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Active Members</span><span className="font-medium text-green-600">{report.members?.active}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Inactive</span><span className="font-medium text-amber-600">{(report.members?.total || 0) - (report.members?.active || 0)}</span></div>
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Financial Overview</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total Donations</span><span className="font-medium text-green-600">{(report.financial?.total_donations || 0).toLocaleString()}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total Expenses</span><span className="font-medium text-red-600">{(report.financial?.total_expenses || 0).toLocaleString()}</span></div>
                  <div className="flex justify-between text-sm border-t border-border pt-2"><span className="font-semibold">Net Balance</span><span className={`font-semibold ${(report.financial?.net || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>{(report.financial?.net || 0).toLocaleString()}</span></div>
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Events & Attendance</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total Events</span><span className="font-medium">{report.events?.total}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total Check-ins</span><span className="font-medium">{report.events?.checkins}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total Bookings</span><span className="font-medium">{report.bookings?.total || 0}</span></div>
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Report Info</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Generated</span><span className="font-medium">{new Date(report.generated_at).toLocaleString()}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Location</span><span className="font-medium">{locationId ? locations.find(l => l.id === locationId)?.name : 'All'}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Period</span><span className="font-medium">{dateFrom || 'Start'} — {dateTo || 'Now'}</span></div>
                </div>
              </CardContent>
            </Card>
          </div>
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
