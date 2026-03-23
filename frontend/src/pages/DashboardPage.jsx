import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Users, Calendar, CheckSquare, UserCheck, TrendingUp, ArrowRight, AlertCircle, RefreshCw, DollarSign, ShoppingCart, Banknote } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { dashboardApi, eventsApi, tasksApi, financialApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const StatCard = ({ title, value, sub, icon: Icon, color, loading }) => (
  <Card className="shadow-soft rounded-xl">
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">{title}</p>
          {loading ? (
            <div className="h-7 w-16 bg-muted animate-pulse rounded mt-1" />
          ) : (
            <p className="text-2xl font-bold font-heading">{value}</p>
          )}
          {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}>
          <Icon size={18} className="text-white" />
        </div>
      </div>
    </CardContent>
  </Card>
);

const activityIcons = {
  checkin: <UserCheck size={15} className="text-green-600" />,
  event: <Calendar size={15} className="text-blue-600" />,
  member: <Users size={15} className="text-purple-600" />,
  task: <CheckSquare size={15} className="text-amber-600" />,
};

function timeAgo(isoStr) {
  if (!isoStr) return '';
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [financial, setFinancial] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);

  const fetchAll = async () => {
    setLoadingStats(true);
    try {
      const [statsRes, eventsRes, tasksRes, finRes] = await Promise.all([
        dashboardApi.stats(),
        eventsApi.list({ status: 'upcoming' }),
        tasksApi.list(),
        financialApi.summary(),
      ]);
      setStats(statsRes.data);
      setEvents(eventsRes.data.slice(0, 4));
      setTasks(tasksRes.data.filter(t => t.status !== 'done' && t.priority === 'high').slice(0, 4));
      setFinancial(finRes.data);
    } catch (err) {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const today = new Date();
  const greeting = today.getHours() < 12 ? 'Good morning' : today.getHours() < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">{greeting}, {user?.name?.split(' ')[0]}!</h1>
          <p className="text-muted-foreground text-sm mt-1">Here's what's happening at 58:12 Global today.</p>
        </div>
        <Button variant="ghost" size="sm" onClick={fetchAll} className="gap-2 text-muted-foreground">
          <RefreshCw size={15} /> Refresh
        </Button>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Members" value={stats?.total_members?.toLocaleString() ?? '—'} sub={`${stats?.active_members ?? 0} active`} icon={Users} color="bg-primary" loading={loadingStats} />
        <StatCard title="Events This Month" value={stats?.events_this_month ?? '—'} sub={`${stats?.upcoming_events ?? 0} upcoming`} icon={Calendar} color="bg-blue-500" loading={loadingStats} />
        <StatCard title="Check-ins Today" value={stats?.checkins_today ?? '—'} sub="Across all venues" icon={UserCheck} color="bg-green-500" loading={loadingStats} />
        <StatCard title="Tasks Overdue" value={stats?.tasks_overdue ?? '—'} sub={`${stats?.new_members_this_month ?? 0} new members`} icon={CheckSquare} color="bg-amber-500" loading={loadingStats} />
      </div>

      {/* Financial Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5 flex items-center gap-4">
            <div className="p-2.5 rounded-lg bg-green-500"><DollarSign size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Monthly Donations</p>
              {loadingStats ? <div className="h-5 w-24 bg-muted animate-pulse rounded mt-1" /> : (
                <p className="text-lg font-bold">UGX {(financial?.monthly_donations || 0).toLocaleString()}</p>
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5 flex items-center gap-4">
            <div className="p-2.5 rounded-lg bg-red-500"><Banknote size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Monthly Expenses</p>
              {loadingStats ? <div className="h-5 w-24 bg-muted animate-pulse rounded mt-1" /> : (
                <p className="text-lg font-bold">UGX {(financial?.monthly_expenses || 0).toLocaleString()}</p>
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5 flex items-center gap-4">
            <div className={`p-2.5 rounded-lg ${(financial?.net_balance || 0) >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`}><TrendingUp size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Net Balance</p>
              {loadingStats ? <div className="h-5 w-24 bg-muted animate-pulse rounded mt-1" /> : (
                <p className="text-lg font-bold">UGX {(financial?.net_balance || 0).toLocaleString()}</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Growth & Quick Actions */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-4">
              <TrendingUp size={16} className="text-primary" />
              <span className="text-sm font-medium">Growth This Month</span>
            </div>
            <div className="flex items-center gap-6">
              <div>
                <p className="text-2xl font-bold">+{stats?.new_members_this_month ?? 0}</p>
                <p className="text-xs text-muted-foreground">New members</p>
              </div>
              <div>
                <p className="text-2xl font-bold">{stats?.events_this_month ?? 0}</p>
                <p className="text-xs text-muted-foreground">Events held</p>
              </div>
              <div>
                <p className="text-2xl font-bold">{stats?.upcoming_events ?? 0}</p>
                <p className="text-xs text-muted-foreground">Upcoming</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-4">
              <AlertCircle size={16} className="text-amber-500" />
              <span className="text-sm font-medium">Quick Actions</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" asChild><Link to="/members">Add Member</Link></Button>
              <Button size="sm" variant="outline" asChild><Link to="/events">Create Event</Link></Button>
              <Button size="sm" variant="outline" asChild><Link to="/kiosk" target="_blank">Open Kiosk</Link></Button>
              <Button size="sm" variant="outline" asChild><Link to="/check-ins">Check-Ins</Link></Button>
              <Button size="sm" variant="outline" asChild><Link to="/tasks">Add Task</Link></Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Upcoming Events */}
        <Card className="shadow-soft rounded-xl lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
            <CardTitle className="text-base font-semibold">Upcoming Events</CardTitle>
            <Button variant="ghost" size="sm" className="text-primary text-xs gap-1" asChild>
              <Link to="/events">View all <ArrowRight size={13} /></Link>
            </Button>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            {loadingStats ? (
              <div className="space-y-3">
                {[1,2,3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />)}
              </div>
            ) : events.length > 0 ? (
              <div className="space-y-3">
                {events.map(event => (
                  <div key={event.id} className="flex items-center gap-4 p-3 rounded-lg border border-border hover:bg-accent/40 transition-colors">
                    <div className="text-center min-w-[44px]">
                      <p className="text-lg font-bold text-primary leading-none">{new Date(event.date).getDate()}</p>
                      <p className="text-xs text-muted-foreground">{new Date(event.date).toLocaleDateString('en-US', { month: 'short' })}</p>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{event.title}</p>
                      <p className="text-xs text-muted-foreground">{event.location} · {event.time}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs font-medium">{event.registered}/{event.capacity}</p>
                      <p className="text-xs text-muted-foreground">registered</p>
                    </div>
                    <Badge variant={event.is_public ? 'outline' : 'secondary'} className="text-xs shrink-0">
                      {event.is_public ? 'Public' : 'Private'}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">No upcoming events</p>
            )}
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="py-4 px-5">
            <CardTitle className="text-base font-semibold">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            {loadingStats ? (
              <div className="space-y-4">
                {[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}
              </div>
            ) : (stats?.recent_activity ?? []).length > 0 ? (
              <div className="space-y-4">
                {stats.recent_activity.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-3">
                    <div className="mt-0.5 p-1.5 rounded-full bg-secondary">
                      {activityIcons[item.type] ?? <UserCheck size={15} className="text-primary" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm leading-snug">{item.message}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{timeAgo(item.time)}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">No recent activity</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* High Priority Tasks */}
      {tasks.length > 0 && (
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
            <CardTitle className="text-base font-semibold">High Priority Tasks</CardTitle>
            <Button variant="ghost" size="sm" className="text-primary text-xs gap-1" asChild>
              <Link to="/tasks">View all <ArrowRight size={13} /></Link>
            </Button>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {tasks.map(task => (
                <div key={task.id} className="p-3 rounded-lg border border-border space-y-2">
                  <div className="flex items-center justify-between">
                    <Badge variant="destructive" className="text-xs">High</Badge>
                    <Badge variant={task.status === 'in-progress' ? 'outline' : 'secondary'} className="text-xs capitalize">
                      {task.status === 'in-progress' ? 'In Progress' : task.status}
                    </Badge>
                  </div>
                  <p className="text-sm font-medium leading-snug">{task.title}</p>
                  {task.assignee && <p className="text-xs text-muted-foreground">{task.assignee}</p>}
                  {task.due_date && <p className="text-xs text-muted-foreground">Due: {task.due_date}</p>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
