import React, { useState, useEffect } from 'react';
import { Building2, Download, TrendingUp, Users, Heart, Baby, DollarSign, Calendar, UserCheck, ChevronRight, FileText, Mail, ArrowLeft } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { reportsApi, locationsApi, emailApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, Legend, PieChart, Pie, Cell } from 'recharts';

const COLORS = ['#e97316', '#3b82f6', '#22c55e', '#a855f7', '#ef4444', '#06b6d4', '#f59e0b', '#ec4899', '#14b8a6', '#6366f1'];

export default function CampusReportsPage() {
  const { user } = useAuth();
  const isSystemAdmin = ['admin', 'system_admin', 'Director', 'Adviser', 'Executive Director'].includes(user?.role);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [detailCampus, setDetailCampus] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const fetchComparison = async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await reportsApi.campusComparison(params);
      setComparison(res.data);
    } catch (err) {
      toast.error('Failed to load campus report');
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (locId) => {
    setLoadingDetail(true);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await reportsApi.campusDetail(locId, params);
      setDetailData(res.data);
      setDetailCampus(locId);
    } catch (err) {
      toast.error('Failed to load campus detail');
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => { fetchComparison(); }, []);

  const downloadPdf = async () => {
    try {
      const res = await reportsApi.pdf({ date_from: dateFrom, date_to: dateTo });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url; a.download = `5812_report_${new Date().toISOString().slice(0,10)}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      toast.success('PDF downloaded');
    } catch { toast.error('PDF export failed'); }
  };

  const emailReport = async () => {
    if (!user?.email) return toast.error('No email on your profile');
    try {
      const t = comparison?.totals || {};
      const body = `<p>Campus Comparison Report</p>
        <ul>
          <li>Total Members: ${t.members || 0}</li>
          <li>Total Children: ${t.children || 0}</li>
          <li>Total Donations: UGX ${(t.donations || 0).toLocaleString()}</li>
          <li>Total Expenses: UGX ${(t.expenses || 0).toLocaleString()}</li>
          <li>Net Balance: UGX ${(t.net || 0).toLocaleString()}</li>
        </ul>
        <p>Campuses: ${(comparison?.campuses || []).map(c => c.location_name).join(', ')}</p>`;
      await emailApi.send({ to: [user.email], subject: '58:12 Campus Comparison Report', template: 'report', context: { title: 'Campus Comparison', body } });
      toast.success('Report emailed to ' + user.email);
    } catch { toast.error('Email failed'); }
  };

  // Detail view
  if (detailCampus && detailData) {
    return (
      <div className="p-4 sm:p-6 space-y-4 sm:space-y-6" data-testid="campus-detail-report">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => { setDetailCampus(null); setDetailData(null); }} className="gap-1.5 w-fit">
            <ArrowLeft size={14} /> Back to Comparison
          </Button>
        </div>
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold font-heading">{detailData.campus?.name}</h1>
          <p className="text-sm text-muted-foreground">Detailed campus report · {detailData.campus?.type}</p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{detailData.member_count}</p><p className="text-xs text-muted-foreground">Members</p></CardContent></Card>
          <Card><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{detailData.children_count}</p><p className="text-xs text-muted-foreground">Children</p></CardContent></Card>
          <Card><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{Object.keys(detailData.group_breakdown || {}).length}</p><p className="text-xs text-muted-foreground">Groups</p></CardContent></Card>
          <Card><CardContent className="p-4 text-center"><p className="text-2xl font-bold">{(detailData.monthly_trends || []).reduce((s,m) => s + m.checkins, 0)}</p><p className="text-xs text-muted-foreground">Total Check-ins</p></CardContent></Card>
        </div>

        {/* Group Breakdown */}
        {Object.keys(detailData.group_breakdown || {}).length > 0 && (
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Member Groups</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={Object.entries(detailData.group_breakdown).map(([name, value]) => ({ name, value }))} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({name, value}) => `${name}: ${value}`}>
                    {Object.keys(detailData.group_breakdown).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Monthly Trends */}
        {(detailData.monthly_trends || []).length > 0 && (
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">6-Month Financial Trends</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={detailData.monthly_trends}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }} />
                  <Legend />
                  <Line type="monotone" dataKey="donations" stroke="#22c55e" strokeWidth={2} name="Donations" />
                  <Line type="monotone" dataKey="expenses" stroke="#ef4444" strokeWidth={2} name="Expenses" />
                  <Line type="monotone" dataKey="checkins" stroke="#3b82f6" strokeWidth={2} name="Check-ins" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  // Comparison view
  const campuses = comparison?.campuses || [];
  const totals = comparison?.totals || {};

  const chartData = campuses.map(c => ({
    name: c.location_name?.replace('58:12 ', '').slice(0, 12),
    Members: c.members,
    Children: c.children,
    Donations: c.donations,
    Expenses: c.expenses,
  }));

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6" data-testid="campus-reports-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold font-heading">Campus Reports</h1>
          <p className="text-sm text-muted-foreground">Compare performance across campuses</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={downloadPdf} data-testid="download-pdf-btn"><Download size={13} /> PDF</Button>
          <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={emailReport} data-testid="email-report-btn"><Mail size={13} /> Email</Button>
        </div>
      </div>

      {/* Date Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row items-end gap-3">
            <div className="flex-1 w-full sm:w-auto space-y-1"><Label className="text-xs">From</Label><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="h-9" /></div>
            <div className="flex-1 w-full sm:w-auto space-y-1"><Label className="text-xs">To</Label><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="h-9" /></div>
            <Button size="sm" onClick={fetchComparison} className="w-full sm:w-auto">Apply</Button>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">{[1,2,3,4].map(i => <Card key={i}><CardContent className="p-4"><div className="h-12 bg-muted animate-pulse rounded" /></CardContent></Card>)}</div>
      ) : (
        <>
          {/* Totals Row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Card><CardContent className="p-4"><div className="flex items-center gap-2 mb-1"><Users size={14} className="text-primary" /><span className="text-xs text-muted-foreground">Total Members</span></div><p className="text-2xl font-bold">{totals.members?.toLocaleString()}</p></CardContent></Card>
            <Card><CardContent className="p-4"><div className="flex items-center gap-2 mb-1"><Baby size={14} className="text-pink-500" /><span className="text-xs text-muted-foreground">Total Children</span></div><p className="text-2xl font-bold">{totals.children?.toLocaleString()}</p></CardContent></Card>
            <Card><CardContent className="p-4"><div className="flex items-center gap-2 mb-1"><DollarSign size={14} className="text-green-500" /><span className="text-xs text-muted-foreground">Donations</span></div><p className="text-2xl font-bold">UGX {(totals.donations || 0).toLocaleString()}</p></CardContent></Card>
            <Card><CardContent className="p-4"><div className="flex items-center gap-2 mb-1"><TrendingUp size={14} className={(totals.net || 0) >= 0 ? 'text-green-500' : 'text-red-500'} /><span className="text-xs text-muted-foreground">Net Balance</span></div><p className="text-2xl font-bold">UGX {(totals.net || 0).toLocaleString()}</p></CardContent></Card>
          </div>

          {/* Bar Chart */}
          {chartData.length > 0 && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base">Campus Comparison</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto -mx-4 sm:mx-0">
                  <div className="min-w-[500px] px-4 sm:px-0">
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Bar dataKey="Members" fill="#3b82f6" radius={[4,4,0,0]} />
                        <Bar dataKey="Children" fill="#ec4899" radius={[4,4,0,0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Campus Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {campuses.map((c, i) => (
              <Card key={c.location_id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => fetchDetail(c.location_id)} data-testid={`campus-card-${c.location_id}`}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-semibold text-sm">{c.location_name}</h3>
                      <Badge variant="outline" className="text-[10px] mt-1 capitalize">{c.location_type}</Badge>
                    </div>
                    <ChevronRight size={16} className="text-muted-foreground mt-0.5" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div><span className="text-muted-foreground">Members:</span> <strong>{c.members}</strong></div>
                    <div><span className="text-muted-foreground">Children:</span> <strong>{c.children}</strong></div>
                    <div><span className="text-muted-foreground">Donations:</span> <strong>{(c.donations || 0).toLocaleString()}</strong></div>
                    <div><span className="text-muted-foreground">Expenses:</span> <strong>{(c.expenses || 0).toLocaleString()}</strong></div>
                    <div><span className="text-muted-foreground">Events:</span> <strong>{c.events}</strong></div>
                    <div><span className="text-muted-foreground">Check-ins:</span> <strong>{c.checkins}</strong></div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
