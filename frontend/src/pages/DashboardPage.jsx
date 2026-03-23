import React from 'react';
import { Link } from 'react-router-dom';
import { Users, Calendar, CheckSquare, UserCheck, TrendingUp, ArrowRight, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { MOCK_STATS, MOCK_ACTIVITY, MOCK_EVENTS, MOCK_TASKS } from '../mock';

const StatCard = ({ title, value, sub, icon: Icon, color }) => (
  <Card className="shadow-soft rounded-xl">
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">{title}</p>
          <p className="text-2xl font-bold font-heading">{value}</p>
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

export default function DashboardPage() {
  const upcomingEvents = MOCK_EVENTS.filter(e => e.status === 'upcoming').slice(0, 4);
  const urgentTasks = MOCK_TASKS.filter(t => t.status !== 'done' && t.priority === 'high').slice(0, 4);

  const today = new Date();
  const greeting = today.getHours() < 12 ? 'Good morning' : today.getHours() < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold font-heading">{greeting}!</h1>
        <p className="text-muted-foreground text-sm mt-1">Here's what's happening at 58:12 Global today.</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Members" value={MOCK_STATS.totalMembers.toLocaleString()} sub={`${MOCK_STATS.activeMembers} active`} icon={Users} color="bg-primary" />
        <StatCard title="Events This Month" value={MOCK_STATS.eventsThisMonth} sub={`${MOCK_STATS.upcomingEvents} upcoming`} icon={Calendar} color="bg-blue-500" />
        <StatCard title="Check-ins Today" value={MOCK_STATS.checkInsToday} sub="Across all venues" icon={UserCheck} color="bg-green-500" />
        <StatCard title="Tasks Overdue" value={MOCK_STATS.tasksOverdue} sub={`${MOCK_STATS.newMembersThisMonth} new members`} icon={CheckSquare} color="bg-amber-500" />
      </div>

      {/* Secondary stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="shadow-soft rounded-xl col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-3">
              <TrendingUp size={16} className="text-primary" />
              <span className="text-sm font-medium">Growth This Month</span>
            </div>
            <div className="flex items-center gap-6">
              <div>
                <p className="text-2xl font-bold">+{MOCK_STATS.newMembersThisMonth}</p>
                <p className="text-xs text-muted-foreground">New members</p>
              </div>
              <div>
                <p className="text-2xl font-bold">{MOCK_STATS.volunteerHours}</p>
                <p className="text-xs text-muted-foreground">Volunteer hours</p>
              </div>
              <div>
                <p className="text-2xl font-bold">{MOCK_STATS.eventsThisMonth}</p>
                <p className="text-xs text-muted-foreground">Events held</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-soft rounded-xl col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-3">
              <AlertCircle size={16} className="text-amber-500" />
              <span className="text-sm font-medium">Quick Actions</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" asChild><Link to="/members">Add Member</Link></Button>
              <Button size="sm" variant="outline" asChild><Link to="/events">Create Event</Link></Button>
              <Button size="sm" variant="outline" asChild><Link to="/kiosk">Open Kiosk</Link></Button>
              <Button size="sm" variant="outline" asChild><Link to="/check-ins">View Check-ins</Link></Button>
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
            <div className="space-y-3">
              {upcomingEvents.map(event => (
                <div key={event.id} className="flex items-center gap-4 p-3 rounded-lg border border-border hover:bg-accent/40 transition-colors">
                  <div className="text-center min-w-[44px]">
                    <p className="text-lg font-bold text-primary leading-none">{new Date(event.date).getDate()}</p>
                    <p className="text-xs text-muted-foreground">{new Date(event.date).toLocaleDateString('en-US', { month: 'short' })}</p>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{event.title}</p>
                    <p className="text-xs text-muted-foreground">{event.location} • {event.time}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-medium">{event.registered}/{event.capacity}</p>
                    <p className="text-xs text-muted-foreground">registered</p>
                  </div>
                  <Badge variant={event.isPublic ? 'outline' : 'secondary'} className="text-xs shrink-0">
                    {event.isPublic ? 'Public' : 'Private'}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Activity feed */}
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
            <CardTitle className="text-base font-semibold">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div className="space-y-4">
              {MOCK_ACTIVITY.map(item => (
                <div key={item.id} className="flex items-start gap-3">
                  <div className="mt-0.5 p-1.5 rounded-full bg-secondary">
                    {activityIcons[item.type]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm leading-snug">{item.message}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{item.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Urgent Tasks */}
      {urgentTasks.length > 0 && (
        <Card className="shadow-soft rounded-xl">
          <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
            <CardTitle className="text-base font-semibold">High Priority Tasks</CardTitle>
            <Button variant="ghost" size="sm" className="text-primary text-xs gap-1" asChild>
              <Link to="/tasks">View all <ArrowRight size={13} /></Link>
            </Button>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {urgentTasks.map(task => (
                <div key={task.id} className="p-3 rounded-lg border border-border space-y-2">
                  <div className="flex items-center justify-between">
                    <Badge variant="destructive" className="text-xs">High</Badge>
                    <Badge variant={task.status === 'in-progress' ? 'outline' : 'secondary'} className="text-xs capitalize">
                      {task.status}
                    </Badge>
                  </div>
                  <p className="text-sm font-medium leading-snug">{task.title}</p>
                  <p className="text-xs text-muted-foreground">{task.assignee}</p>
                  <p className="text-xs text-muted-foreground">Due: {task.dueDate}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
