import React, { useState, useEffect } from 'react';
import { MapPin, Users, UserCheck, Calendar, TrendingUp } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { analyticsApi } from '../services/api';
import { toast } from 'sonner';

const typeColors = {
  main: 'bg-primary/10 text-primary border-primary/20',
  branch: 'bg-blue-50 text-blue-700 border-blue-200',
  'sub-location': 'bg-slate-50 text-slate-600 border-slate-200',
};

export default function LocationAnalyticsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analyticsApi.locations()
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load location analytics'))
      .finally(() => setLoading(false));
  }, []);

  const chartData = data?.locations?.map(l => ({
    name: l.code || l.name.split(' ')[0],
    Members: l.member_count,
    'Check-ins': l.checkin_count,
    Events: l.event_count,
  })) || [];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold font-heading">Location Analytics</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Compare performance across all locations</p>
      </div>

      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-2"><CardTitle className="text-base font-semibold">Location Comparison</CardTitle></CardHeader>
        <CardContent className="px-5 pb-5">
          {loading ? <div className="h-52 bg-muted animate-pulse rounded" /> : (
            chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="Members" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Check-ins" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Events" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-muted-foreground text-center py-12">No location data yet.</p>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-soft rounded-xl">
        <CardContent className="p-5">
          {loading ? (
            <div className="space-y-3">{[1,2,3,4].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border text-left">
                  <th className="pb-2 font-medium text-muted-foreground">Location</th>
                  <th className="pb-2 font-medium text-muted-foreground">Type</th>
                  <th className="pb-2 font-medium text-muted-foreground text-center">Members</th>
                  <th className="pb-2 font-medium text-muted-foreground text-center">Check-ins</th>
                  <th className="pb-2 font-medium text-muted-foreground text-center">Events</th>
                  <th className="pb-2 font-medium text-muted-foreground">Contact</th>
                </tr></thead>
                <tbody className="divide-y divide-border">
                  {(data?.locations || []).map(loc => (
                    <tr key={loc.id} className="hover:bg-accent/30">
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <MapPin size={13} className="text-muted-foreground" />
                          <span className="font-medium">{loc.name}</span>
                        </div>
                      </td>
                      <td className="py-3">
                        <Badge variant="outline" className={`text-xs capitalize border ${typeColors[loc.type] || ''}`}>{loc.type}</Badge>
                      </td>
                      <td className="py-3 text-center font-semibold">{loc.member_count}</td>
                      <td className="py-3 text-center">{loc.checkin_count}</td>
                      <td className="py-3 text-center">{loc.event_count}</td>
                      <td className="py-3 text-muted-foreground text-xs">{loc.contact_name || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
