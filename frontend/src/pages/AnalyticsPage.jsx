import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, Users, Calendar, DollarSign, MapPin, RefreshCw, Globe, Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { analyticsApi } from '../services/api';
import { toast } from 'sonner';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, PieChart, Pie, Cell } from 'recharts';

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

const StatCard = ({ title, value, sub, icon: Icon, color, loading }) => (
  <Card className="shadow-soft rounded-xl">
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted-foreground mb-1">{title}</p>
          {loading ? <div className="h-7 w-20 bg-muted animate-pulse rounded mt-1" /> : (
            <p className="text-2xl font-bold font-heading">{value ?? '—'}</p>
          )}
          {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}><Icon size={18} className="text-white" /></div>
      </div>
    </CardContent>
  </Card>
);

export default function AnalyticsPage() {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState(null);
  const [trends, setTrends] = useState([]);
  const [locationBreakdown, setLocationBreakdown] = useState([]);
  const [memberGrowth, setMemberGrowth] = useState([]);
  const [outreachImpact, setOutreachImpact] = useState(null);
  const [months, setMonths] = useState(6);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const [overviewRes, trendsRes, locRes, growthRes, outreachRes] = await Promise.all([
        analyticsApi.overview(months),
        analyticsApi.trends(months),
        analyticsApi.locationBreakdown(),
        analyticsApi.memberGrowth(12),
        analyticsApi.outreachImpact(),
      ]);
      setOverview(overviewRes.data);
      setTrends(trendsRes.data?.monthly || []);
      setLocationBreakdown(locRes.data || []);
      setMemberGrowth(growthRes.data || []);
      setOutreachImpact(outreachRes.data);
    } catch (err) {
      toast.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [months]);

  const fmt = (n) => (n || 0).toLocaleString();

  return (
    <div className="p-6 space-y-6" data-testid="analytics-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Advanced Analytics</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Deep insights into your organization's performance</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(months)} onValueChange={v => setMonths(parseInt(v))}>
            <SelectTrigger className="w-32 h-9" data-testid="analytics-period-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="3">3 Months</SelectItem>
              <SelectItem value="6">6 Months</SelectItem>
              <SelectItem value="12">12 Months</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={fetchAnalytics} data-testid="analytics-refresh">
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Total Members" 
          value={fmt(overview?.members?.total)} 
          sub={`${fmt(overview?.members?.active)} active`}
          icon={Users} 
          color="bg-primary" 
          loading={loading} 
        />
        <StatCard 
          title="Total Events" 
          value={fmt(overview?.events?.total)} 
          sub={`Last ${months} months`}
          icon={Calendar} 
          color="bg-blue-500" 
          loading={loading} 
        />
        <StatCard 
          title="Check-ins" 
          value={fmt(overview?.checkins?.total)} 
          sub={`Last ${months} months`}
          icon={Activity} 
          color="bg-green-500" 
          loading={loading} 
        />
        <StatCard 
          title="Net Financial" 
          value={`UGX ${fmt(overview?.financial?.net)}`} 
          sub={`Donations: ${fmt(overview?.financial?.donations)}`}
          icon={DollarSign} 
          color={(overview?.financial?.net || 0) >= 0 ? 'bg-emerald-500' : 'bg-red-500'} 
          loading={loading} 
        />
      </div>

      {/* Trends Chart */}
      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <TrendingUp size={16} className="text-primary" /> Monthly Trends
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="h-64 bg-muted animate-pulse rounded" />
            ) : trends.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={trends} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="new_members" name="New Members" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="checkins" name="Check-ins" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-16">No trend data available</p>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <DollarSign size={16} className="text-green-600" /> Financial Trends
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="h-64 bg-muted animate-pulse rounded" />
            ) : trends.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={trends} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}K`} />
                  <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} formatter={v => [`UGX ${v.toLocaleString()}`]} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="donations" name="Donations" fill="#22c55e" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="expenses" name="Expenses" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-16">No financial data available</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Member Growth */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Users size={16} className="text-primary" /> Member Growth Over Time
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="h-48 bg-muted animate-pulse rounded" />
          ) : memberGrowth.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={memberGrowth} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                <Bar dataKey="new" name="New Members" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Line type="monotone" dataKey="cumulative" name="Cumulative" stroke="#f59e0b" strokeWidth={2} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-12">No growth data available</p>
          )}
        </CardContent>
      </Card>

      {/* Location Breakdown & Outreach Impact */}
      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <MapPin size={16} className="text-blue-600" /> By Location
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="h-64 bg-muted animate-pulse rounded" />
            ) : locationBreakdown.length > 0 ? (
              <div className="space-y-3">
                {locationBreakdown.map((loc, i) => (
                  <div key={loc.location_id} className="flex items-center gap-3 p-3 rounded-lg border border-border" data-testid={`location-stat-${loc.location_id}`}>
                    <div className="h-10 w-10 rounded-lg flex items-center justify-center text-white font-bold text-sm" style={{ backgroundColor: COLORS[i % COLORS.length] }}>
                      {loc.name?.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="flex-1">
                      <p className="font-medium text-sm">{loc.name}</p>
                      <div className="flex gap-4 mt-1">
                        <span className="text-xs text-muted-foreground"><Users size={10} className="inline mr-1" />{loc.members}</span>
                        <span className="text-xs text-muted-foreground"><Calendar size={10} className="inline mr-1" />{loc.events}</span>
                        <span className="text-xs text-muted-foreground"><Activity size={10} className="inline mr-1" />{loc.checkins}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-16">No location data</p>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Globe size={16} className="text-purple-600" /> Outreach Impact
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="h-64 bg-muted animate-pulse rounded" />
            ) : outreachImpact ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center p-4 rounded-lg bg-purple-50 dark:bg-purple-950/30">
                    <p className="text-2xl font-bold text-purple-600">{outreachImpact.programs}</p>
                    <p className="text-xs text-muted-foreground mt-1">Programs</p>
                  </div>
                  <div className="text-center p-4 rounded-lg bg-blue-50 dark:bg-blue-950/30">
                    <p className="text-2xl font-bold text-blue-600">{outreachImpact.total_sessions}</p>
                    <p className="text-xs text-muted-foreground mt-1">Sessions</p>
                  </div>
                  <div className="text-center p-4 rounded-lg bg-green-50 dark:bg-green-950/30">
                    <p className="text-2xl font-bold text-green-600">{fmt(outreachImpact.total_reached)}</p>
                    <p className="text-xs text-muted-foreground mt-1">People Reached</p>
                  </div>
                </div>
                {outreachImpact.programs_list?.slice(0, 4).map(prog => (
                  <div key={prog.id} className="flex items-center gap-3 p-2 rounded-lg border border-border">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                      <Globe size={14} className="text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{prog.name}</p>
                      <p className="text-xs text-muted-foreground">{prog.sessions_count || 0} sessions · {prog.total_reached || 0} reached</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-16">No outreach data</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
