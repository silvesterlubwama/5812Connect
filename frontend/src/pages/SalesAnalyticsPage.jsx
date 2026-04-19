import React, { useState, useEffect } from 'react';
import { BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { ShoppingCart, TrendingUp, Receipt, CreditCard } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { analyticsApi } from '../services/api';
import { toast } from 'sonner';

const fmt = (n) => `UGX ${(n || 0).toLocaleString()}`;
const PIE_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6'];

const StatCard = ({ title, value, sub, icon: Icon, color }) => (
  <Card className="shadow-soft rounded-xl">
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted-foreground mb-1">{title}</p>
          <p className="text-xl font-bold font-heading">{value}</p>
          {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}><Icon size={18} className="text-white" /></div>
      </div>
    </CardContent>
  </Card>
);

export default function SalesAnalyticsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analyticsApi.sales()
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load sales analytics'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold font-heading">Sales Analytics</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Revenue performance and product insights</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Revenue" value={loading ? '…' : fmt(data?.total_revenue)} icon={TrendingUp} color="bg-primary" />
        <StatCard title="Transactions" value={loading ? '…' : (data?.total_transactions ?? 0)} sub="All time" icon={Receipt} color="bg-blue-500" />
        <StatCard title="This Month" value={loading ? '…' : fmt(data?.monthly_data?.[data.monthly_data.length - 1]?.revenue)} icon={ShoppingCart} color="bg-green-500" />
        <StatCard title="Top Method" value={loading ? '…' : (data?.payment_breakdown?.[0]?.name || 'Cash')} sub="By volume" icon={CreditCard} color="bg-amber-500" />
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="pb-2"><CardTitle className="text-base font-semibold">Monthly Revenue</CardTitle></CardHeader>
            <CardContent className="px-5 pb-5">
              {loading ? <div className="h-56 bg-muted animate-pulse rounded" /> : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data?.monthly_data || []} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}K`} />
                    <Tooltip formatter={v => [fmt(v), 'Revenue']} contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                    <Bar dataKey="revenue" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-2"><CardTitle className="text-base font-semibold">Payment Methods</CardTitle></CardHeader>
          <CardContent className="px-5 pb-5">
            {loading ? <div className="h-56 bg-muted animate-pulse rounded" /> : (
              data?.payment_breakdown?.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={160}>
                    <PieChart>
                      <Pie data={data.payment_breakdown} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={65} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false} fontSize={10}>
                        {data.payment_breakdown.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Tooltip formatter={v => [fmt(v)]} contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="space-y-2 mt-2">
                    {data.payment_breakdown.map((item, i) => (
                      <div key={item?.name || item?.label || i} className="flex items-center gap-2 text-xs">
                        <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                        <span className="text-muted-foreground">{item.name}</span>
                        <span className="ml-auto font-semibold">{fmt(item.value)}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : <p className="text-sm text-muted-foreground text-center py-12">No payment data yet.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-2"><CardTitle className="text-base font-semibold">Top Products by Revenue</CardTitle></CardHeader>
        <CardContent className="px-5 pb-5">
          {loading ? <div className="h-48 bg-muted animate-pulse rounded" /> : (
            data?.top_products?.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data.top_products} layout="vertical" margin={{ top: 5, right: 20, left: 60, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}K`} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={80} />
                  <Tooltip formatter={v => [fmt(v), 'Revenue']} contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
                  <Bar dataKey="revenue" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-muted-foreground text-center py-10">No product sales recorded yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
