import React, { useEffect, useState } from 'react';
import { Clock, LogOut, Calendar, ShoppingBag, Heart, RefreshCw, Ticket } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

// Approval-gated landing shown to any user whose account status is 'pending'.
// Unapproved guests get: (1) contact-admin banner, (2) public events browse
// + purchase, (3) sign out. NO family edit, NO tasks/chat/expenses/sales,
// NO badge issuance until an admin approves the account (iter343).
export default function PendingApprovalScreen() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    // Public events feed — no auth needed, no scope leakage.
    api.get('/public/events').then(r => setEvents(r.data || []))
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  };
  useEffect(() => { refresh(); }, []);

  return (
    <div className="min-h-screen bg-background" data-testid="pending-approval-screen">
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
              <Clock size={20} className="text-amber-600" />
            </div>
            <div>
              <h1 className="text-lg font-semibold font-heading">Hi {user?.name?.split(' ')[0] || 'there'}</h1>
              <p className="text-xs text-muted-foreground">Your account is pending approval</p>
            </div>
          </div>
          <Button variant="ghost" size="sm" className="gap-2 text-destructive" onClick={() => { logout(); navigate('/login'); }} data-testid="pending-logout-btn">
            <LogOut size={14} /> Sign out
          </Button>
        </div>

        <Card className="border-amber-200 bg-amber-50/40 dark:bg-amber-950/20">
          <CardContent className="p-5 space-y-2">
            <Badge className="bg-amber-500 hover:bg-amber-500">Pending admin approval</Badge>
            <p className="text-sm">
              An administrator needs to approve your profile before you can access family details,
              badges, event tickets tied to attendance, or portal features. While you wait, you
              can browse and purchase tickets for our public events below.
            </p>
            <p className="text-xs text-muted-foreground">
              Reach out to your campus admin if this is urgent — they can approve you in the People module.
            </p>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { icon: Heart, label: 'Family editing', locked: 'Unlocks after approval' },
            { icon: ShoppingBag, label: 'My purchases', locked: 'Available now, below' },
            { icon: Calendar, label: 'Public events', locked: 'Available now, below' },
          ].map(({ icon: Icon, label, locked }) => (
            <Card key={label}>
              <CardContent className="p-4 flex items-center gap-3">
                <Icon size={16} className="text-muted-foreground shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-[11px] text-muted-foreground truncate">{locked}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardContent className="p-4 sm:p-5 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">Upcoming public events</p>
              <Button size="sm" variant="ghost" onClick={refresh} data-testid="pending-refresh-events"><RefreshCw size={14} /></Button>
            </div>
            {loading && <div className="animate-pulse h-16 bg-muted rounded" />}
            {!loading && events.length === 0 && <p className="text-xs text-muted-foreground py-4 text-center">No public events scheduled — check back soon.</p>}
            {!loading && events.map(e => {
              const isTicketed = !e.is_free && (e.price || 0) > 0;
              return (
                <div key={e.id} className="flex items-center justify-between border rounded-lg p-3 gap-3 flex-wrap" data-testid={`pending-event-${e.id}`}>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{e.title}</p>
                    <p className="text-[11px] text-muted-foreground">{e.date}{e.time ? ` · ${e.time}` : ''}{e.location ? ` · ${e.location}` : ''}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {isTicketed ? (
                      <Badge variant="secondary" className="text-[10px]">{e.currency || 'UGX'} {(e.price || 0).toLocaleString()}</Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px]">Free</Badge>
                    )}
                    <Button
                      size="sm"
                      variant={isTicketed ? 'default' : 'outline'}
                      className="h-8 gap-1"
                      data-testid={`pending-buy-${e.id}`}
                      onClick={() => navigate(`/marketplace?event=${e.id}`)}
                    >
                      <Ticket size={13} /> {isTicketed ? 'Buy ticket' : 'RSVP'}
                    </Button>
                  </div>
                </div>
              );
            })}
            <p className="text-[11px] text-muted-foreground pt-2 border-t border-border">
              Tickets you buy here stay tied to your account so check-in works the moment the event starts, even before your profile is fully approved.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
