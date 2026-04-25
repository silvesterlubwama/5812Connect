import React, { useState, useEffect } from 'react';
import { Users, Calendar, CheckSquare, UserCheck, TrendingUp, TrendingDown, ArrowRight, AlertCircle, RefreshCw, DollarSign, ShoppingCart, Banknote, Baby, Heart, Zap, Building2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { dashboardApi, eventsApi, tasksApi, financialApi, familiesApi, childrenApi, parentApi, productsApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const StatCard = ({ title, value, sub, icon: Icon, color, loading, onClick }) => (
  <Card className={`shadow-soft rounded-xl ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}`} onClick={onClick}>
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted-foreground mb-1">{title}</p>
          {loading ? <div className="h-7 w-16 bg-muted animate-pulse rounded mt-1" /> : (
            <p className="text-2xl font-bold font-heading">{value ?? '—'}</p>
          )}
          {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}><Icon size={18} className="text-white" /></div>
      </div>
    </CardContent>
  </Card>
);

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isParent = user?.role === 'parent';
  const isSystemAdmin = ['admin', 'system_admin', 'Director', 'Adviser', 'Executive Director'].includes(user?.role);
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [financial, setFinancial] = useState(null);
  const [familyCount, setFamilyCount] = useState(0);
  const [childrenCount, setChildrenCount] = useState(0);
  const [lowStockProducts, setLowStockProducts] = useState([]);
  const [parentData, setParentData] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [deptData, setDeptData] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [selectedCampus, setSelectedCampus] = useState('all');
  const [actionItems, setActionItems] = useState(null);

  useEffect(() => {
    if (isSystemAdmin) {
      locationsApi.list().then(res => setCampuses(res.data || [])).catch(() => {});
    }
  }, [isSystemAdmin]);

  const fetchAll = async () => {
    setLoadingStats(true);
    try {
      const campusParam = selectedCampus !== 'all' ? { campus_id: selectedCampus } : {};
      if (isParent) {
        const [dashRes, evRes] = await Promise.all([parentApi.dashboard(), eventsApi.list({ status: 'upcoming' })]);
        setParentData(dashRes.data);
        setEvents(evRes.data.slice(0, 5));
      } else {
        const [statsRes, eventsRes, tasksRes, finRes, famRes, chdRes, prodRes, actionsRes] = await Promise.all([
          dashboardApi.stats(campusParam),
          eventsApi.list({ status: 'upcoming' }),
          tasksApi.list(),
          financialApi.summary(campusParam),
          familiesApi.list(),
          childrenApi.list(),
          productsApi.list(),
          dashboardApi.actionItems(campusParam).catch(() => ({ data: null })),
        ]);
        setStats(statsRes.data);
        setEvents(eventsRes.data.slice(0, 4));
        setTasks(tasksRes.data.filter(t => t.status !== 'done' && t.priority === 'high').slice(0, 4));
        setFinancial(finRes.data);
        setFamilyCount(Array.isArray(famRes.data) ? famRes.data.length : 0);
        setChildrenCount(Array.isArray(chdRes.data) ? chdRes.data.length : 0);
        const prods = Array.isArray(prodRes.data) ? prodRes.data : [];
        setLowStockProducts(prods.filter(p => p.stock <= (p.reorder_level || 5)));
        setActionItems(actionsRes.data);
        if (statsRes.data?.group_breakdown) {
          setDeptData(Object.entries(statsRes.data.group_breakdown).map(([name, count]) => ({ name, count })));
        }
      }
    } catch (err) {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => { fetchAll(); }, [isParent, selectedCampus]);

  // ---- PARENT VIEW ----
  if (isParent) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold font-heading">Welcome, {user?.name?.split(' ')[0]}</h1>
            <p className="text-sm text-muted-foreground mt-0.5 flex items-center gap-2">
              <Badge variant="outline" className="text-xs capitalize">{user?.role}</Badge>
              <span>58:12 Global Connect</span>
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={fetchAll}><RefreshCw size={14} /></Button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <StatCard title="My Children" value={parentData?.children_count ?? 0} sub="Registered" icon={Baby} color="bg-green-500" loading={loadingStats} />
          <StatCard title="Checked In" value={parentData?.checked_in_count ?? 0} sub="Currently present" icon={UserCheck} color="bg-blue-500" loading={loadingStats} />
        </div>

        {parentData?.children?.length > 0 && (
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="pb-3 pt-4 px-5"><CardTitle className="text-base font-semibold flex items-center gap-2"><Baby size={15} /> My Children</CardTitle></CardHeader>
            <CardContent className="px-5 pb-5">
              <div className="space-y-3">
                {parentData.children.map(child => (
                  <div key={child.id} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/30 transition-colors">
                    <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <Baby size={16} className="text-primary" />
                    </div>
                    <div className="flex-1">
                      <p className="font-medium text-sm">{child.name}</p>
                      <p className="text-xs text-muted-foreground">{child.class_group || 'No class assigned'}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge variant="outline" className="text-xs border-slate-300 text-slate-500">Not checked in</Badge>
                      {child.medical_notes && (
                        <span className="text-xs text-amber-600 flex items-center gap-1"><AlertCircle size={10} /> Medical alert</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        <Card className="shadow-soft rounded-xl">
          <CardHeader className="pb-3 pt-4 px-5"><CardTitle className="text-base font-semibold">Upcoming Events</CardTitle></CardHeader>
          <CardContent className="px-5 pb-5">
            {events.length === 0 ? <p className="text-sm text-muted-foreground text-center py-4">No upcoming events.</p> : (
              <div className="space-y-2">
                {events.map(ev => (
                  <div key={ev.id} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/30 transition-colors">
                    <div className="p-2 rounded-lg bg-primary/10"><Calendar size={14} className="text-primary" /></div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{ev.title}</p>
                      <p className="text-xs text-muted-foreground">{ev.date} {ev.time && `at ${ev.time}`}</p>
                    </div>
                    <ArrowRight size={14} className="text-muted-foreground" />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- ADMIN/STAFF VIEW ----
  const campusName = selectedCampus === 'all' ? 'All Campuses' : (campuses.find(c => c.id === selectedCampus)?.name || '');

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold font-heading">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Welcome back, {user?.name?.split(' ')[0]}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchAll} data-testid="dashboard-refresh"><RefreshCw size={14} /></Button>
        </div>
      </div>

      {/* Primary stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatCard title="Total Members" value={stats?.total_members?.toLocaleString()} sub={`${stats?.active_members ?? 0} active`} icon={Users} color="bg-primary" loading={loadingStats} onClick={() => navigate('/people')} />
        <StatCard title="Families" value={familyCount} sub={`${childrenCount} children`} icon={Heart} color="bg-pink-500" loading={loadingStats} onClick={() => navigate('/people')} />
        <StatCard title="Check-ins Today" value={stats?.checkins_today} sub="Across all venues" icon={UserCheck} color="bg-green-500" loading={loadingStats} onClick={() => navigate('/check-ins')} />
        <StatCard title="Events This Month" value={stats?.events_this_month} sub={`${stats?.upcoming_events ?? 0} upcoming`} icon={Calendar} color="bg-blue-500" loading={loadingStats} onClick={() => navigate('/events')} />
      </div>

      {/* Financial summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <Card className="shadow-soft rounded-xl cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate('/financial')}>
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
        <Card className="shadow-soft rounded-xl cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate('/financial')}>
          <CardContent className="p-5 flex items-center gap-4">
            <div className="p-2.5 rounded-lg bg-red-500"><TrendingDown size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Monthly Expenses</p>
              {loadingStats ? <div className="h-5 w-24 bg-muted animate-pulse rounded mt-1" /> : (
                <p className="text-lg font-bold">UGX {(financial?.monthly_expenses || 0).toLocaleString()}</p>
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate('/financial')}>
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

      {/* Alerts Row */}
      {!loadingStats && lowStockProducts.length > 0 && (
        <Card className="shadow-soft rounded-xl border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertCircle size={16} className="text-amber-600 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-400">Low Stock Alert</p>
              <p className="text-xs text-amber-600 dark:text-amber-500">{lowStockProducts.length} product{lowStockProducts.length > 1 ? 's' : ''} at or below reorder threshold: {lowStockProducts.map(p => p.name).join(', ')}</p>
            </div>
            <Button size="sm" variant="outline" className="border-amber-300 text-amber-700 hover:bg-amber-100 shrink-0" onClick={() => navigate('/sales')}>
              View Products
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Action Items */}
      {!loadingStats && actionItems && (actionItems.overdue_tasks > 0 || actionItems.pending_approvals > 0 || actionItems.expiring_passes > 0 || actionItems.unassigned_tasks > 0) && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {actionItems.overdue_tasks > 0 && (
            <Card className="shadow-soft rounded-xl border-red-200 bg-red-50/50 dark:bg-red-950/20 dark:border-red-800 cursor-pointer hover:shadow-md" onClick={() => navigate('/tasks')} data-testid="action-overdue-tasks">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1"><AlertCircle size={14} className="text-red-600" /><p className="text-xs font-semibold text-red-700 dark:text-red-400">Overdue Tasks</p></div>
                <p className="text-2xl font-bold text-red-600">{actionItems.overdue_tasks}</p>
                <p className="text-[10px] text-red-500 mt-0.5">Past due date, needs attention</p>
              </CardContent>
            </Card>
          )}
          {actionItems.pending_approvals > 0 && (
            <Card className="shadow-soft rounded-xl border-amber-200 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-800 cursor-pointer hover:shadow-md" onClick={() => navigate('/members')} data-testid="action-pending-approvals">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1"><Users size={14} className="text-amber-600" /><p className="text-xs font-semibold text-amber-700 dark:text-amber-400">Pending Approvals</p></div>
                <p className="text-2xl font-bold text-amber-600">{actionItems.pending_approvals}</p>
                <p className="text-[10px] text-amber-500 mt-0.5">Members awaiting approval</p>
              </CardContent>
            </Card>
          )}
          {actionItems.expiring_passes > 0 && (
            <Card className="shadow-soft rounded-xl border-orange-200 bg-orange-50/50 dark:bg-orange-950/20 dark:border-orange-800 cursor-pointer hover:shadow-md" onClick={() => navigate('/access')} data-testid="action-expiring-passes">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1"><AlertCircle size={14} className="text-orange-600" /><p className="text-xs font-semibold text-orange-700 dark:text-orange-400">Expiring Passes</p></div>
                <p className="text-2xl font-bold text-orange-600">{actionItems.expiring_passes}</p>
                <p className="text-[10px] text-orange-500 mt-0.5">Guest passes expiring in 7 days</p>
              </CardContent>
            </Card>
          )}
          {actionItems.unassigned_tasks > 0 && (
            <Card className="shadow-soft rounded-xl border-blue-200 bg-blue-50/50 dark:bg-blue-950/20 dark:border-blue-800 cursor-pointer hover:shadow-md" onClick={() => navigate('/tasks')} data-testid="action-unassigned-tasks">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1"><CheckSquare size={14} className="text-blue-600" /><p className="text-xs font-semibold text-blue-700 dark:text-blue-400">Unassigned Tasks</p></div>
                <p className="text-2xl font-bold text-blue-600">{actionItems.unassigned_tasks}</p>
                <p className="text-[10px] text-blue-500 mt-0.5">Tasks without assignees</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-4 sm:gap-5">
        {/* Upcoming Events */}
        <div className="lg:col-span-2 space-y-4">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3 pt-4 px-5">
              <CardTitle className="text-base font-semibold">Upcoming Events</CardTitle>
              <Button variant="ghost" size="sm" className="text-xs gap-1 text-muted-foreground" onClick={() => navigate('/events')}>View all <ArrowRight size={12} /></Button>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              {loadingStats ? <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}</div> :
                events.length > 0 ? (
                  <div className="space-y-2">
                    {events.map(ev => (
                      <div key={ev.id} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/30 transition-colors cursor-pointer" onClick={() => navigate('/events')}>
                        <div className="p-2 rounded-lg bg-primary/10"><Calendar size={14} className="text-primary" /></div>
                        <div className="flex-1">
                          <p className="text-sm font-medium">{ev.title}</p>
                          <p className="text-xs text-muted-foreground">{ev.date} {ev.time && `at ${ev.time}`} {ev.location && `· ${ev.location}`}</p>
                        </div>
                        <Badge variant="outline" className="text-xs capitalize">{ev.type || 'event'}</Badge>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-sm text-muted-foreground text-center py-4">No upcoming events.</p>}
            </CardContent>
          </Card>

          {/* Overdue Tasks */}
          {tasks.length > 0 && (
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="flex flex-row items-center justify-between pb-3 pt-4 px-5">
                <CardTitle className="text-base font-semibold">High Priority Tasks</CardTitle>
                <Button variant="ghost" size="sm" className="text-xs gap-1 text-muted-foreground" onClick={() => navigate('/tasks')}>View all <ArrowRight size={12} /></Button>
              </CardHeader>
              <CardContent className="px-5 pb-5">
                <div className="space-y-2">
                  {tasks.map(task => (
                    <div key={task.id} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:bg-secondary/30 transition-colors cursor-pointer" onClick={() => navigate('/tasks')}>
                      <div className="p-2 rounded-lg bg-amber-100"><CheckSquare size={14} className="text-amber-600" /></div>
                      <div className="flex-1">
                        <p className="text-sm font-medium">{task.title}</p>
                        <p className="text-xs text-muted-foreground">{task.due_date && `Due: ${task.due_date}`}</p>
                      </div>
                      <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200 capitalize">{task.status}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Quick Actions + Group Chart */}
        <div className="space-y-4">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="pb-3 pt-4 px-5"><CardTitle className="text-base font-semibold flex items-center gap-2"><Zap size={14} className="text-primary" /> Quick Actions</CardTitle></CardHeader>
            <CardContent className="px-5 pb-5 space-y-2">
              {[
                { label: 'Check-in Member', path: '/check-ins', icon: UserCheck, color: 'text-green-600' },
                { label: 'Add Member', path: '/members', icon: Users, color: 'text-blue-600' },
                { label: 'New Event', path: '/events', icon: Calendar, color: 'text-purple-600' },
                { label: 'Open POS', path: '/sales', icon: ShoppingCart, color: 'text-amber-600' },
              ].map(action => (
                <button key={action.path} onClick={() => navigate(action.path)}
                  className="w-full flex items-center gap-3 p-2.5 rounded-lg border border-border hover:bg-secondary/40 transition-colors text-left">
                  <action.icon size={15} className={action.color} />
                  <span className="text-sm font-medium">{action.label}</span>
                  <ArrowRight size={12} className="ml-auto text-muted-foreground" />
                </button>
              ))}
            </CardContent>
          </Card>

          {deptData.length > 0 && (
            <Card className="shadow-soft rounded-xl">
              <CardHeader className="pb-2 pt-4 px-5"><CardTitle className="text-sm font-semibold">Members by Group</CardTitle></CardHeader>
              <CardContent className="px-5 pb-4">
                <ResponsiveContainer width="100%" height={140}>
                  <BarChart data={deptData} layout="vertical" margin={{ top: 0, right: 10, left: 10, bottom: 0 }}>
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={55} />
                    <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
