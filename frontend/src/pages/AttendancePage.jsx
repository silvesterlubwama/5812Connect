import React, { useState, useEffect } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { UserCheck, TrendingUp, Calendar, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { analyticsApi } from '../services/api';
import { toast } from 'sonner';

const StatCard = ({ title, value, icon: Icon, color }) => (
  <Card className="shadow-soft rounded-xl">
    <CardContent className="p-5 flex items-center gap-4">
      <div className={`p-2.5 rounded-lg ${color}`}><Icon size={18} className="text-white" /></div>
      <div>
        <p className="text-xs text-muted-foreground">{title}</p>
        <p className="text-xl font-bold font-heading">{value}</p>
      </div>
    </CardContent>
  </Card>
);

export default function AttendancePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analyticsApi.attendance()
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load attendance data'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold font-heading">Attendance Analytics</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Check-in trends and attendance overview</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Today" value={loading ? '…' : data?.total_today ?? 0} icon={UserCheck} color="bg-green-500" />
        <StatCard title="This Week" value={loading ? '…' : data?.total_week ?? 0} icon={Calendar} color="bg-blue-500" />
        <StatCard title="This Month" value={loading ? '…' : data?.total_month ?? 0} icon={TrendingUp} color="bg-primary" />
        <StatCard title="Avg Weekly" value={loading ? '…' : data?.weekly_data ? Math.round(data.weekly_data.reduce((a, b) => a + b.checkins, 0) / Math.max(data.weekly_data.length, 1)) : 0} icon={Clock} color="bg-amber-500" />
      </div>

      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-2"><CardTitle className="text-base font-semibold">Check-ins — Last 12 Weeks</CardTitle></CardHeader>
        <CardContent className="pt-0 pb-5 px-5">
          {loading ? <div className="h-56 bg-muted animate-pulse rounded" /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data?.weekly_data || []} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                <Bar dataKey="checkins" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-2"><CardTitle className="text-base font-semibold">Recent Check-ins</CardTitle></CardHeader>
        <CardContent className="px-5 pb-5">
          {loading ? <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-10 bg-muted animate-pulse rounded" />)}</div> : (
            (data?.recent || []).length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left">
                    <th className="pb-2 font-medium text-muted-foreground">Member</th>
                    <th className="pb-2 font-medium text-muted-foreground">Event</th>
                    <th className="pb-2 font-medium text-muted-foreground">Time</th>
                    <th className="pb-2 font-medium text-muted-foreground">Method</th>
                  </tr></thead>
                  <tbody className="divide-y divide-border">
                    {data.recent.map(ci => (
                      <tr key={ci.id} className="hover:bg-accent/30">
                        <td className="py-2.5 font-medium">{ci.member_name || '—'}</td>
                        <td className="py-2.5 text-muted-foreground">{ci.event_name || 'General'}</td>
                        <td className="py-2.5 text-muted-foreground text-xs">{ci.check_in_time?.slice(0, 16).replace('T', ' ')}</td>
                        <td className="py-2.5"><span className="text-xs px-2 py-0.5 rounded-full bg-secondary capitalize">{ci.method}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-sm text-muted-foreground text-center py-8">No check-in data yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
