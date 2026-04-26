import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ListTodo, MessageSquare, Receipt, Calendar, Clock, ArrowRight, Download, QrCode, User } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { portalApi } from '../services/api';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { UnifiedBadge } from '../components/UnifiedBadge';

const StatCard = ({ title, value, sub, icon: Icon, color, onClick }) => (
  <Card className="shadow-soft rounded-xl cursor-pointer hover:shadow-md transition-shadow" onClick={onClick} data-testid={`portal-stat-${title.toLowerCase().replace(/\s/g, '-')}`}>
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">{title}</p>
          <p className="text-2xl font-bold font-heading mt-1">{value}</p>
          {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}>
          <Icon size={18} className="text-white" />
        </div>
      </div>
    </CardContent>
  </Card>
);

export default function PortalDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    portalApi.dashboard()
      .then(res => setData(res.data))
      .catch(() => toast.error('Failed to load dashboard'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  const d = data || {};
  const tasks = d.tasks || {};
  const expenses = d.expenses || {};

  return (
    <div className="space-y-6 max-w-5xl" data-testid="portal-dashboard">
      <div>
        <h1 className="text-2xl font-bold font-heading">Welcome back, {user?.name?.split(' ')[0]}</h1>
        <p className="text-sm text-muted-foreground mt-1">Here's your overview for today</p>
      </div>

      {/* Quick Actions: Badge + PDF */}
      <div className="grid sm:grid-cols-2 gap-3">
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-4">
            <p className="text-xs font-semibold text-muted-foreground mb-3">My Badge</p>
            <UnifiedBadge person={{ ...user, role: user?.role || 'Member' }} size="small" showActions={true} />
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-4 space-y-3">
            <p className="text-xs font-semibold text-muted-foreground">Profile Actions</p>
            <Button variant="outline" className="w-full gap-2 text-sm" onClick={async () => {
              try { const res = await api.get(`/members/${user?.member_id || user?.id}/profile-pdf`, { responseType: 'blob' }); const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' })); const a = document.createElement('a'); a.href = url; a.download = `profile-${user?.name?.replace(/\s/g, '_')}.pdf`; a.click(); toast.success('PDF downloaded'); }
              catch { toast.error('PDF download failed'); }
            }} data-testid="portal-download-pdf"><Download size={14} /> Download Profile PDF</Button>
            <Button variant="outline" className="w-full gap-2 text-sm" onClick={() => navigate('/portal/profile')} data-testid="portal-edit-profile"><User size={14} /> Edit My Profile</Button>
          </CardContent>
        </Card>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="My Tasks" value={tasks.total || 0} sub={`${tasks.todo || 0} to do, ${tasks.in_progress || 0} in progress`} icon={ListTodo} color="bg-blue-500" onClick={() => navigate('/portal/tasks')} />
        <StatCard title="Expenses" value={expenses.count || 0} sub={`${expenses.pending || 0} pending approval`} icon={Receipt} color="bg-amber-500" onClick={() => navigate('/portal/expenses')} />
        <StatCard title="Events" value={(d.upcoming_events || []).length} sub="upcoming" icon={Calendar} color="bg-green-500" onClick={() => navigate('/portal/events')} />
        <StatCard title="Messages" value={d.unread_messages || 0} sub="unread" icon={MessageSquare} color="bg-purple-500" onClick={() => navigate('/portal/chat')} />
      </div>

      {/* Recent Check-ins */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm">Recent Check-ins</CardTitle>
          <Button variant="ghost" size="sm" className="gap-1 text-xs" onClick={() => navigate('/portal/profile')}>View All <ArrowRight size={12} /></Button>
        </CardHeader>
        <CardContent>
          {(d.recent_checkins || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No recent check-ins</p>
          ) : (
            <div className="space-y-2">
              {(d.recent_checkins || []).map((c, i) => (
                <div key={c.id || i} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div className="flex items-center gap-2">
                    <Clock size={14} className="text-muted-foreground" />
                    <span className="text-sm">{c.event_name || c.type || 'Check-in'}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">{new Date(c.check_in_time || c.timestamp).toLocaleDateString()}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upcoming Events */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm">Upcoming Events</CardTitle>
          <Button variant="ghost" size="sm" className="gap-1 text-xs" onClick={() => navigate('/portal/events')}>View All <ArrowRight size={12} /></Button>
        </CardHeader>
        <CardContent>
          {(d.upcoming_events || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No upcoming events</p>
          ) : (
            <div className="space-y-2">
              {(d.upcoming_events || []).map((e, i) => (
                <div key={e.id || e.title || i} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium">{e.title}</p>
                    <p className="text-xs text-muted-foreground">{e.date} {e.time && `at ${e.time}`} {e.location && `— ${e.location}`}</p>
                  </div>
                  <Badge variant="outline" className="text-xs">{e.type}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
