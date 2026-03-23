import React, { useState, useEffect } from 'react';
import { Building2, Plus, Trash2, Calendar, Clock, Edit2, X } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { resourcesApi } from '../services/api';
import { toast } from 'sonner';

const fmt = (n) => n ? `UGX ${(n).toLocaleString()}/hr` : 'Free';

const typeIcon = { auditorium: '🎭', conference: '📋', hall: '🏛️', equipment: '🎙️', classroom: '📚', vehicle: '🚌' };

const emptyResource = { name: '', type: 'room', capacity: '', description: '', hourly_rate: '' };
const emptyBooking = { resource_id: '', title: '', booked_by: '', date: new Date().toISOString().split('T')[0], start_time: '09:00', end_time: '11:00', notes: '' };

export default function ResourcesPage() {
  const [resources, setResources] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showResource, setShowResource] = useState(false);
  const [showBooking, setShowBooking] = useState(false);
  const [selectedResource, setSelectedResource] = useState(null);
  const [saving, setSaving] = useState(false);
  const [resForm, setResForm] = useState(emptyResource);
  const [bookingForm, setBookingForm] = useState(emptyBooking);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [resRes, bkRes] = await Promise.all([resourcesApi.list(), resourcesApi.bookings()]);
      setResources(resRes.data);
      setBookings(bkRes.data);
    } catch { toast.error('Failed to load resources'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const getResourceBookings = (resId) => bookings.filter(b => b.resource_id === resId);

  const handleAddResource = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await resourcesApi.create({ ...resForm, capacity: resForm.capacity ? parseInt(resForm.capacity) : null, hourly_rate: resForm.hourly_rate ? parseFloat(resForm.hourly_rate) : null });
      setResources(prev => [...prev, res.data]);
      setShowResource(false);
      setResForm(emptyResource);
      toast.success('Resource added!');
    } catch { toast.error('Failed to add resource'); }
    finally { setSaving(false); }
  };

  const handleBookResource = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await resourcesApi.createBooking(bookingForm);
      setBookings(prev => [...prev, res.data]);
      setShowBooking(false);
      setBookingForm(emptyBooking);
      toast.success('Resource booked!');
    } catch { toast.error('Failed to create booking'); }
    finally { setSaving(false); }
  };

  const deleteResource = async (id) => {
    if (!window.confirm('Delete this resource?')) return;
    await resourcesApi.delete(id);
    setResources(prev => prev.filter(r => r.id !== id));
    toast.success('Deleted');
  };

  const deleteBooking = async (id) => {
    await resourcesApi.deleteBooking(id);
    setBookings(prev => prev.filter(b => b.id !== id));
    toast.success('Booking cancelled');
  };

  const openBooking = (res) => {
    setBookingForm({ ...emptyBooking, resource_id: res.id });
    setShowBooking(true);
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Resources</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{resources.length} resources · {bookings.length} bookings</p>
        </div>
        <Button className="gap-2" onClick={() => setShowResource(true)} data-testid="add-resource-btn"><Plus size={16} /> Add Resource</Button>
      </div>

      <Tabs defaultValue="resources">
        <TabsList>
          <TabsTrigger value="resources">Resources ({resources.length})</TabsTrigger>
          <TabsTrigger value="bookings">All Bookings ({bookings.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="resources" className="mt-4">
          {loading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[1,2,3,4].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />)}</div>
          ) : resources.length > 0 ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {resources.map(res => {
                const resBks = getResourceBookings(res.id);
                return (
                  <Card key={res.id} className="shadow-soft rounded-xl hover:shadow-soft-lg transition-shadow" data-testid="resource-card">
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-xl">{typeIcon[res.type] || '🏢'}</span>
                          <div>
                            <p className="font-semibold text-sm">{res.name}</p>
                            <p className="text-xs text-muted-foreground capitalize">{res.type}{res.capacity ? ` · ${res.capacity} cap.` : ''}</p>
                          </div>
                        </div>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteResource(res.id)}><Trash2 size={12} /></Button>
                      </div>
                      {res.description && <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{res.description}</p>}
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold text-primary">{fmt(res.hourly_rate)}</p>
                        <p className="text-xs text-muted-foreground">{resBks.length} booking{resBks.length !== 1 ? 's' : ''}</p>
                      </div>
                      <Button size="sm" className="w-full mt-3 gap-1.5" variant="outline" onClick={() => openBooking(res)} data-testid="book-resource-btn">
                        <Calendar size={12} /> Book
                      </Button>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          ) : <p className="text-center text-sm text-muted-foreground py-16">No resources added yet.</p>}
        </TabsContent>

        <TabsContent value="bookings" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-5">
              {loading ? <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div> :
                bookings.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="border-b border-border text-left">
                        <th className="pb-2 font-medium text-muted-foreground">Resource</th>
                        <th className="pb-2 font-medium text-muted-foreground">Title</th>
                        <th className="pb-2 font-medium text-muted-foreground">Date</th>
                        <th className="pb-2 font-medium text-muted-foreground">Time</th>
                        <th className="pb-2 font-medium text-muted-foreground">Booked By</th>
                        <th className="pb-2"></th>
                      </tr></thead>
                      <tbody className="divide-y divide-border">
                        {bookings.map(bk => {
                          const res = resources.find(r => r.id === bk.resource_id);
                          return (
                            <tr key={bk.id} className="hover:bg-accent/30" data-testid="booking-row">
                              <td className="py-2.5 font-medium">{res?.name || bk.resource_id}</td>
                              <td className="py-2.5">{bk.title}</td>
                              <td className="py-2.5 text-muted-foreground">{bk.date}</td>
                              <td className="py-2.5 text-muted-foreground">{bk.start_time} – {bk.end_time}</td>
                              <td className="py-2.5 text-muted-foreground">{bk.booked_by}</td>
                              <td className="py-2.5">
                                <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteBooking(bk.id)}><X size={12} /></Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="text-sm text-muted-foreground text-center py-10">No bookings yet.</p>}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Add Resource Dialog */}
      <Dialog open={showResource} onOpenChange={setShowResource}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Resource</DialogTitle></DialogHeader>
          <form onSubmit={handleAddResource} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Name *</Label><Input placeholder="e.g. Main Auditorium" value={resForm.name} onChange={e => setResForm({...resForm, name: e.target.value})} required data-testid="resource-name-input" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Type</Label>
                <Select value={resForm.type} onValueChange={v => setResForm({...resForm, type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auditorium">Auditorium</SelectItem>
                    <SelectItem value="conference">Conference</SelectItem>
                    <SelectItem value="hall">Hall</SelectItem>
                    <SelectItem value="classroom">Classroom</SelectItem>
                    <SelectItem value="equipment">Equipment</SelectItem>
                    <SelectItem value="vehicle">Vehicle</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Capacity</Label><Input type="number" placeholder="100" value={resForm.capacity} onChange={e => setResForm({...resForm, capacity: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Description</Label><Input placeholder="Brief description" value={resForm.description} onChange={e => setResForm({...resForm, description: e.target.value})} /></div>
            <div className="space-y-2"><Label>Hourly Rate (UGX, leave blank if free)</Label><Input type="number" placeholder="20000" value={resForm.hourly_rate} onChange={e => setResForm({...resForm, hourly_rate: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowResource(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-resource-btn">{saving ? 'Adding...' : 'Add Resource'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Book Resource Dialog */}
      <Dialog open={showBooking} onOpenChange={setShowBooking}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Book Resource</DialogTitle></DialogHeader>
          <form onSubmit={handleBookResource} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Resource *</Label>
              <Select value={bookingForm.resource_id} onValueChange={v => setBookingForm({...bookingForm, resource_id: v})}>
                <SelectTrigger><SelectValue placeholder="Select resource" /></SelectTrigger>
                <SelectContent>{resources.map(r => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label>Booking Title *</Label><Input placeholder="e.g. Board Meeting" value={bookingForm.title} onChange={e => setBookingForm({...bookingForm, title: e.target.value})} required /></div>
            <div className="space-y-2"><Label>Booked By</Label><Input placeholder="Your name" value={bookingForm.booked_by} onChange={e => setBookingForm({...bookingForm, booked_by: e.target.value})} /></div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2 col-span-3 sm:col-span-1"><Label>Date</Label><Input type="date" value={bookingForm.date} onChange={e => setBookingForm({...bookingForm, date: e.target.value})} /></div>
              <div className="space-y-2"><Label>Start</Label><Input type="time" value={bookingForm.start_time} onChange={e => setBookingForm({...bookingForm, start_time: e.target.value})} /></div>
              <div className="space-y-2"><Label>End</Label><Input type="time" value={bookingForm.end_time} onChange={e => setBookingForm({...bookingForm, end_time: e.target.value})} /></div>
            </div>
            <div className="space-y-2"><Label>Notes</Label><Input placeholder="Any special requirements?" value={bookingForm.notes} onChange={e => setBookingForm({...bookingForm, notes: e.target.value})} /></div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowBooking(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving || !bookingForm.resource_id} data-testid="confirm-booking-btn">{saving ? 'Booking...' : 'Confirm Booking'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
