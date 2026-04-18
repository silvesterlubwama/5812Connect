import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Ticket, Building, Search, Calendar, Clock, Users, MapPin, CreditCard, ChevronDown, ExternalLink, Globe, Shield, Lock, ChevronRight, ShoppingCart } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { publicApi } from '../services/api';
import { toast } from 'sonner';

const formatDate = (d) => new Date(d).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
const typeLabels = { service: 'Services', conference: 'Conferences', meeting: 'Meetings', community: 'Community', outreach: 'Outreach', workshop: 'Workshops', training: 'Training', social: 'Social' };
const typeColors = { service: 'bg-purple-500', conference: 'bg-amber-500', meeting: 'bg-slate-500', community: 'bg-teal-500', outreach: 'bg-pink-500', workshop: 'bg-violet-500', training: 'bg-cyan-500', social: 'bg-orange-500' };
const COUNTRIES = [
  { code: 'US', label: 'United States (Ohio)', tz: 'America' },
  { code: 'UG', label: 'Uganda', tz: 'Africa/Kampala' },
  { code: 'KE', label: 'Kenya', tz: 'Africa/Nairobi' },
  { code: 'TH', label: 'Thailand', tz: 'Asia/Bangkok' },
  { code: 'HT', label: 'Haiti', tz: 'America/Port-au-Prince' },
  { code: 'ALL', label: 'All Locations', tz: '' },
];
const PAYMENT_METHODS = [
  { id: 'card', label: 'Credit/Debit Card', icon: CreditCard },
  { id: 'mobile_money_mtn', label: 'MTN Mobile Money' },
  { id: 'mobile_money_airtel', label: 'Airtel Money' },
  { id: 'venmo', label: 'Venmo' },
  { id: 'cash', label: 'Cash (in-person)' },
];

export default function PublicBookingsPage() {
  const [events, setEvents] = useState([]);
  const [venues, setVenues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [selectedVenue, setSelectedVenue] = useState(null);
  const [regData, setRegData] = useState({ name: '', email: '', phone: '', num_tickets: 1, payment_method: 'card', agreed_to_terms: false });
  const [spaceData, setSpaceData] = useState({ name: '', email: '', phone: '', booking_date: '', start_time: '', end_time: '', purpose: '' });
  const [statusQuery, setStatusQuery] = useState({ booking_id: '', email: '', phone: '' });
  const [statusResults, setStatusResults] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [searchStatus, setSearchStatus] = useState(false);
  const [countryFilter, setCountryFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [showMore, setShowMore] = useState(false);
  const [showPolicies, setShowPolicies] = useState(false);
  const [policies, setPolicies] = useState(null);
  const [shopProducts, setShopProducts] = useState([]);
  const [shopCart, setShopCart] = useState([]);
  const [shopOrder, setShopOrder] = useState({ name: '', email: '', phone: '', payment_method: 'card' });

  // Auto-detect country
  useEffect(() => {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
      if (tz.includes('America')) setCountryFilter('US');
      else if (tz.includes('Kampala')) setCountryFilter('UG');
      else if (tz.includes('Nairobi')) setCountryFilter('KE');
      else if (tz.includes('Bangkok')) setCountryFilter('TH');
      else if (tz.includes('Port-au-Prince')) setCountryFilter('HT');
    } catch (e) { console.warn(e.message || e); }
    // Ask for location permission
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(() => {}, () => {}, { timeout: 5000 });
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([publicApi.events({ country: countryFilter !== 'ALL' ? countryFilter : undefined }), publicApi.venues(), publicApi.products()])
      .then(([evRes, venRes, prodRes]) => { setEvents(evRes.data); setVenues(venRes.data); setShopProducts(prodRes.data || []); })
      .catch(() => toast.error('Failed to load data'))
      .finally(() => setLoading(false));
  }, [countryFilter]);

  // Load policies
  useEffect(() => {
    if (showPolicies && !policies) {
      fetch(`${process.env.REACT_APP_BACKEND_URL}/api/public/policies`)
        .then(r => r.json()).then(setPolicies).catch(() => {});
    }
  }, [showPolicies, policies]);

  // Filter events by search, type, date range, country
  const filteredEvents = events.filter(ev => {
    // Text search (name)
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchesName = ev.title?.toLowerCase().includes(q);
      const matchesType = ev.type?.toLowerCase().includes(q);
      const matchesLocation = ev.location?.toLowerCase().includes(q);
      if (!matchesName && !matchesType && !matchesLocation) return false;
    }
    // Type filter
    if (typeFilter !== 'all' && ev.type !== typeFilter) return false;
    // Date range
    if (dateFrom && ev.date < dateFrom) return false;
    if (dateTo && ev.date > dateTo) return false;
    // Country filtering is done server-side via API param
    return true;
  }).sort((a, b) => a.date?.localeCompare(b.date));
  const displayEvents = showMore ? filteredEvents : filteredEvents.slice(0, 12);

  // Get unique event types for filter dropdown
  const eventTypes = [...new Set(events.map(e => e.type).filter(Boolean))];

  // Group events by type
  const eventsByType = {};
  displayEvents.forEach(ev => {
    const t = ev.type || 'other';
    if (!eventsByType[t]) eventsByType[t] = [];
    eventsByType[t].push(ev);
  });

  const getDaysUntil = (dateStr) => {
    try { return Math.ceil((new Date(dateStr) - new Date()) / (1000 * 60 * 60 * 24)); } catch { return 999; }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (selectedEvent && !selectedEvent.is_free && selectedEvent.price > 0 && !regData.agreed_to_terms) {
      toast.error('Please agree to the payment terms'); return;
    }
    setSubmitting(true);
    try {
      const res = await publicApi.bookEvent({ ...regData, event_id: selectedEvent.id });
      const msg = res.data.is_free ? `Registered! Ticket: ${res.data.ticket_ids?.join(', ')}` :
        `Booking confirmed! Total: ${res.data.total}. ${res.data.payment_status === 'pending' ? 'Payment pending.' : ''}`;
      toast.success(msg);
      setSelectedEvent(null);
      setRegData({ name: '', email: '', phone: '', num_tickets: 1, payment_method: 'card', agreed_to_terms: false });
      setEvents(prev => prev.map(ev => ev.id === selectedEvent.id ? { ...ev, registered: (ev.registered || 0) + regData.num_tickets } : ev));
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to register'); }
    finally { setSubmitting(false); }
  };

  const handleSpaceBooking = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await publicApi.bookSpace({ ...spaceData, venue_id: selectedVenue.id });
      toast.success(`Space booking submitted! ID: ${res.data.id}`);
      setSelectedVenue(null);
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to book'); }
    finally { setSubmitting(false); }
  };

  const handleStatusLookup = async (e) => {
    e.preventDefault();
    setSearchStatus(true);
    try {
      const params = {};
      if (statusQuery.booking_id) params.booking_id = statusQuery.booking_id;
      else if (statusQuery.email) params.email = statusQuery.email;
      else if (statusQuery.phone) params.phone = statusQuery.phone;
      const res = await publicApi.checkStatus(params);
      setStatusResults(res.data);
      if (res.data.length === 0) toast.info('No bookings found');
    } catch { toast.error('Lookup failed'); }
    finally { setSearchStatus(false); }
  };

  const isPaid = (ev) => !ev.is_free && ev.price > 0;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-4 py-3 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global" className="h-8 w-auto" />
          <div className="flex items-center gap-3">
            {/* Country selector */}
            <Select value={countryFilter} onValueChange={setCountryFilter}>
              <SelectTrigger className="w-[180px] h-8 text-xs" data-testid="country-selector">
                <div className="flex items-center gap-1.5"><Globe size={12} /><SelectValue /></div>
              </SelectTrigger>
              <SelectContent>
                {COUNTRIES.map(c => <SelectItem key={c.code} value={c.code}>{c.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <Link to="/portal"><Button size="sm" variant="outline" className="gap-1.5 text-xs h-8" data-testid="portal-login-btn"><ExternalLink size={12} /> My Portal</Button></Link>
          </div>
        </div>
      </header>

      {/* Hero with 58:12 info */}
      <section className="bg-[#1a1a2e] text-white py-12 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-3xl sm:text-4xl font-bold font-heading mb-3">Bringing Hope & Healing to the Most Vulnerable</h1>
          <p className="text-slate-300 text-sm sm:text-base max-w-2xl mx-auto mb-4">58:12 Global is a Christ-centered nonprofit that exists to bring hope and healing. We serve in the USA (Ohio), Uganda, Kenya, Thailand, and Haiti.</p>
          <p className="text-slate-400 text-xs italic">"Your people will rebuild the ancient ruins and will raise up the age-old foundations; you will be called Repairer of Broken Walls, Restorer of Streets with Dwellings." — Isaiah 58:12</p>
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        {/* Search & Filter Bar */}
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
            {/* Search input */}
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-9 h-10" placeholder="Search by event name, type, or location..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} data-testid="event-search" />
            </div>
            {/* Type filter */}
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="w-full sm:w-[160px] h-10 text-xs" data-testid="type-filter">
                <SelectValue placeholder="All Types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                {eventTypes.map(t => (
                  <SelectItem key={t} value={t}>
                    <div className="flex items-center gap-2"><span className={`w-2 h-2 rounded-full ${typeColors[t] || 'bg-slate-400'}`} />{typeLabels[t] || t.charAt(0).toUpperCase() + t.slice(1)}</div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* Country filter (duplicate in header for mobile) */}
            <Select value={countryFilter} onValueChange={setCountryFilter}>
              <SelectTrigger className="w-full sm:w-[170px] h-10 text-xs sm:hidden" data-testid="country-filter-mobile">
                <div className="flex items-center gap-1.5"><Globe size={12} /><SelectValue /></div>
              </SelectTrigger>
              <SelectContent>
                {COUNTRIES.map(c => <SelectItem key={c.code} value={c.code}>{c.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {/* Date range row */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
            <div className="flex items-center gap-2 flex-1">
              <Label className="text-xs text-muted-foreground whitespace-nowrap">From</Label>
              <Input type="date" className="h-9 text-xs flex-1" value={dateFrom} onChange={e => setDateFrom(e.target.value)} data-testid="date-from" />
              <Label className="text-xs text-muted-foreground whitespace-nowrap">To</Label>
              <Input type="date" className="h-9 text-xs flex-1" value={dateTo} onChange={e => setDateTo(e.target.value)} data-testid="date-to" />
              {(dateFrom || dateTo || typeFilter !== 'all' || searchQuery) && (
                <Button size="sm" variant="ghost" className="text-xs h-9 shrink-0" onClick={() => { setSearchQuery(''); setTypeFilter('all'); setDateFrom(''); setDateTo(''); }} data-testid="clear-filters">Clear</Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground shrink-0">{filteredEvents.length} event{filteredEvents.length !== 1 ? 's' : ''} found</p>
          </div>
        </div>

        <Tabs defaultValue="events" className="space-y-6">
          <TabsList className="grid w-full max-w-2xl mx-auto grid-cols-4">
            <TabsTrigger value="events" className="gap-2"><Ticket size={15} />Events</TabsTrigger>
            <TabsTrigger value="shop" className="gap-2"><ShoppingCart size={15} />Shop</TabsTrigger>
            <TabsTrigger value="venues" className="gap-2"><Building size={15} />Book Space</TabsTrigger>
            <TabsTrigger value="status" className="gap-2"><Search size={15} />My Orders</TabsTrigger>
          </TabsList>

          {/* EVENTS TAB - organized by type in columns */}
          <TabsContent value="events">
            {loading ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">{[1,2,3].map(i => <div key={i} className="h-48 bg-card border rounded-xl animate-pulse" />)}</div>
            ) : Object.keys(eventsByType).length === 0 ? (
              <p className="text-center py-12 text-muted-foreground">No events available for this location</p>
            ) : (
              <div className="space-y-8">
                {Object.entries(eventsByType).map(([type, typeEvents]) => (
                  <div key={type}>
                    <div className="flex items-center gap-2 mb-3">
                      <div className={`w-3 h-3 rounded-full ${typeColors[type] || 'bg-slate-400'}`} />
                      <h3 className="text-base font-semibold capitalize">{typeLabels[type] || type}</h3>
                      <Badge variant="outline" className="text-[10px]">{typeEvents.length}</Badge>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {typeEvents.map(event => (
                        <Card key={event.id} className="rounded-xl hover:shadow-md transition-shadow cursor-pointer" onClick={() => setSelectedEvent(event)} data-testid={`event-card-${event.id}`}>
                          <CardContent className="p-4">
                            <div className="flex items-start justify-between mb-2">
                              <h4 className="font-semibold text-sm line-clamp-2">{event.title}</h4>
                              {isPaid(event) ? <Badge className="bg-amber-100 text-amber-800 text-[10px] shrink-0">{event.price?.toLocaleString()} {event.currency || 'UGX'}</Badge> : <Badge variant="outline" className="text-[10px] text-green-600 shrink-0">Free</Badge>}
                            </div>
                            <div className="space-y-1 text-xs text-muted-foreground">
                              <p className="flex items-center gap-1.5"><Calendar size={11} />{formatDate(event.date)}</p>
                              {event.time && <p className="flex items-center gap-1.5"><Clock size={11} />{event.time}{event.end_time ? ` - ${event.end_time}` : ''}</p>}
                              {event.location && <p className="flex items-center gap-1.5"><MapPin size={11} />{event.location}</p>}
                            </div>
                            <div className="flex items-center justify-between mt-3">
                              <span className="text-xs text-muted-foreground">{event.registered || 0}/{event.capacity} registered</span>
                              <Button size="sm" className="h-7 text-xs">Register</Button>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                ))}
                {filteredEvents.length > 12 && !showMore && (
                  <div className="text-center"><Button variant="outline" onClick={() => setShowMore(true)}>View More Events</Button></div>
                )}
              </div>
            )}
          </TabsContent>

          {/* SHOP TAB */}
          <TabsContent value="shop">
            {loading ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">{[1,2,3].map(i => <div key={i} className="h-48 bg-card border rounded-xl animate-pulse" />)}</div>
            ) : shopProducts.length === 0 ? (
              <p className="text-center py-12 text-muted-foreground">No products available</p>
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                {shopProducts.map(p => (
                  <Card key={p.id} className="rounded-xl hover:shadow-md transition-shadow">
                    <CardContent className="p-4">
                      <h4 className="font-semibold text-sm mb-1">{p.name}</h4>
                      {p.description && <p className="text-xs text-muted-foreground mb-2 line-clamp-2">{p.description}</p>}
                      <div className="flex items-center justify-between mt-2">
                        <span className="font-bold text-primary">{p.currency || 'UGX'} {(p.price || 0).toLocaleString()}</span>
                        <Badge variant={p.stock > 5 ? 'outline' : 'destructive'} className="text-[10px]">{p.stock > 0 ? `${p.stock} left` : 'Sold out'}</Badge>
                      </div>
                      <Button size="sm" className="w-full mt-3 text-xs" disabled={p.stock <= 0}
                        onClick={() => { const existing = shopCart.find(c => c.product_id === p.id); if (existing) setShopCart(prev => prev.map(c => c.product_id === p.id ? {...c, quantity: c.quantity + 1} : c)); else setShopCart(prev => [...prev, { product_id: p.id, name: p.name, price: p.price, quantity: 1 }]); toast.success(`${p.name} added to cart`); }}>
                        Add to Cart
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
            {shopCart.length > 0 && (
              <Card className="rounded-xl mt-6 max-w-md mx-auto">
                <CardContent className="p-4">
                  <h3 className="font-semibold mb-3">Cart ({shopCart.reduce((s, c) => s + c.quantity, 0)} items)</h3>
                  {shopCart.map(c => (
                    <div key={c.product_id} className="flex justify-between text-sm py-1.5 border-b last:border-0">
                      <span>{c.name} x{c.quantity}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{(c.price * c.quantity).toLocaleString()}</span>
                        <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-destructive" onClick={() => setShopCart(prev => prev.filter(x => x.product_id !== c.product_id))}>x</Button>
                      </div>
                    </div>
                  ))}
                  <div className="flex justify-between font-bold mt-2 pt-2 border-t"><span>Total</span><span>{shopCart.reduce((s, c) => s + c.price * c.quantity, 0).toLocaleString()}</span></div>
                  <div className="space-y-2 mt-3">
                    <Input placeholder="Your name" value={shopOrder.name} onChange={e => setShopOrder({...shopOrder, name: e.target.value})} />
                    <Input placeholder="Email" value={shopOrder.email} onChange={e => setShopOrder({...shopOrder, email: e.target.value})} />
                    <Button className="w-full" onClick={async () => {
                      if (!shopOrder.name || !shopOrder.email) { toast.error('Name and email required'); return; }
                      try { const r = await publicApi.createOrder({ ...shopOrder, items: shopCart }); toast.success(`Order placed! ID: ${r.data.id}`); setShopCart([]); }
                      catch { toast.error('Order failed'); }
                    }}>Place Order</Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* VENUES TAB */}
          <TabsContent value="venues">
            {loading ? <div className="h-48 bg-card border rounded-xl animate-pulse" /> : venues.length === 0 ? (
              <p className="text-center py-12 text-muted-foreground">No bookable spaces available</p>
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {venues.map(venue => (
                  <Card key={venue.id} className="rounded-xl hover:shadow-md transition-shadow cursor-pointer" onClick={() => setSelectedVenue(venue)}>
                    <CardContent className="p-4">
                      <h4 className="font-semibold text-sm mb-1">{venue.name}</h4>
                      <p className="text-xs text-muted-foreground mb-2">{venue.description}</p>
                      <div className="flex gap-2 text-xs">
                        <Badge variant="outline"><Users size={10} className="mr-1" />{venue.capacity}</Badge>
                        {venue.hourly_rate && <Badge variant="outline">{venue.hourly_rate?.toLocaleString()}/hr</Badge>}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* STATUS TAB */}
          <TabsContent value="status">
            <Card className="max-w-md mx-auto rounded-xl">
              <CardContent className="p-6">
                <h3 className="font-semibold mb-4">Check Booking Status</h3>
                <form onSubmit={handleStatusLookup} className="space-y-3">
                  <div className="space-y-1.5"><Label className="text-xs">Booking ID</Label><Input placeholder="book_..." value={statusQuery.booking_id} onChange={e => setStatusQuery({...statusQuery, booking_id: e.target.value})} /></div>
                  <p className="text-xs text-muted-foreground text-center">- or -</p>
                  <div className="space-y-1.5"><Label className="text-xs">Email</Label><Input type="email" value={statusQuery.email} onChange={e => setStatusQuery({...statusQuery, email: e.target.value})} /></div>
                  <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={statusQuery.phone} onChange={e => setStatusQuery({...statusQuery, phone: e.target.value})} /></div>
                  <Button type="submit" className="w-full" disabled={searchStatus}>{searchStatus ? 'Searching...' : 'Look Up'}</Button>
                </form>
                {statusResults && (
                  <div className="mt-4 space-y-2">
                    {statusResults.length === 0 ? <p className="text-sm text-muted-foreground">No bookings found</p> :
                      statusResults.map(b => (
                        <div key={b.id} className="p-3 rounded-lg border text-sm">
                          <p className="font-medium">{b.event_title || b.type || 'Booking'}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <Badge variant={b.status === 'confirmed' ? 'default' : 'secondary'} className="text-xs">{b.status}</Badge>
                            {b.payment_status && <Badge variant={b.payment_status === 'paid' ? 'default' : 'destructive'} className="text-xs">{b.payment_status}</Badge>}
                            {b.ticket_ids && <span className="text-xs text-muted-foreground">{b.ticket_ids.join(', ')}</span>}
                          </div>
                        </div>
                      ))
                    }
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      {/* Event Registration Dialog with Payment */}
      <Dialog open={!!selectedEvent} onOpenChange={(open) => !open && setSelectedEvent(null)}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{selectedEvent?.title}</DialogTitle>
            <DialogDescription>{formatDate(selectedEvent?.date || '')} {selectedEvent?.time ? `at ${selectedEvent.time}` : ''}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleRegister} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 space-y-1.5"><Label className="text-xs">Full Name *</Label><Input value={regData.name} onChange={e => setRegData({...regData, name: e.target.value})} required data-testid="reg-name" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Email *</Label><Input type="email" value={regData.email} onChange={e => setRegData({...regData, email: e.target.value})} required /></div>
              <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={regData.phone} onChange={e => setRegData({...regData, phone: e.target.value})} /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Number of Tickets</Label><Input type="number" min={1} max={10} value={regData.num_tickets} onChange={e => setRegData({...regData, num_tickets: parseInt(e.target.value) || 1})} /></div>

            {/* Payment section for paid events */}
            {selectedEvent && isPaid(selectedEvent) && (
              <div className="space-y-3 p-3 bg-amber-50 dark:bg-amber-950 rounded-lg border border-amber-200 dark:border-amber-800">
                <p className="text-sm font-medium">Payment: {(selectedEvent.price * (regData.num_tickets || 1)).toLocaleString()} {selectedEvent.currency || 'UGX'}</p>
                <div className="space-y-1.5"><Label className="text-xs">Payment Method</Label>
                  <Select value={regData.payment_method} onValueChange={v => setRegData({...regData, payment_method: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PAYMENT_METHODS.map(pm => {
                        const daysUntil = getDaysUntil(selectedEvent.date);
                        if (pm.id === 'cash' && daysUntil <= 3) return null;
                        return <SelectItem key={pm.id} value={pm.id}>{pm.label}</SelectItem>;
                      })}
                    </SelectContent>
                  </Select>
                </div>
                {regData.payment_method === 'cash' && (
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    {getDaysUntil(selectedEvent.date) <= 7 ? 'Cash payment must be received within 2 days.' : 'Cash payment must be received within 7 days of booking.'}
                  </p>
                )}
                {regData.payment_method === 'venmo' && (
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    {getDaysUntil(selectedEvent.date) <= 7 ? 'Venmo payment must be sent within 2 days.' : 'Venmo payment must be sent within 7 days of booking.'}
                  </p>
                )}
                <label className="flex items-start gap-2 cursor-pointer text-xs">
                  <input type="checkbox" className="mt-0.5 accent-primary" checked={regData.agreed_to_terms} onChange={e => setRegData({...regData, agreed_to_terms: e.target.checked})} />
                  <span>I agree to complete payment by the deadline. I understand unpaid bookings will be automatically cancelled.</span>
                </label>
              </div>
            )}
            <Button type="submit" className="w-full" disabled={submitting}>{submitting ? 'Registering...' : selectedEvent?.is_free ? 'Register (Free)' : `Pay & Register`}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Venue Booking Dialog */}
      <Dialog open={!!selectedVenue} onOpenChange={(open) => !open && setSelectedVenue(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Book: {selectedVenue?.name}</DialogTitle><DialogDescription>Capacity: {selectedVenue?.capacity} {selectedVenue?.hourly_rate ? `| Rate: ${selectedVenue.hourly_rate}/hr` : ''}</DialogDescription></DialogHeader>
          <form onSubmit={handleSpaceBooking} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 space-y-1.5"><Label className="text-xs">Name *</Label><Input value={spaceData.name} onChange={e => setSpaceData({...spaceData, name: e.target.value})} required /></div>
              <div className="space-y-1.5"><Label className="text-xs">Email *</Label><Input type="email" value={spaceData.email} onChange={e => setSpaceData({...spaceData, email: e.target.value})} required /></div>
              <div className="space-y-1.5"><Label className="text-xs">Phone</Label><Input value={spaceData.phone} onChange={e => setSpaceData({...spaceData, phone: e.target.value})} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5"><Label className="text-xs">Date *</Label><Input type="date" value={spaceData.booking_date} onChange={e => setSpaceData({...spaceData, booking_date: e.target.value})} required /></div>
              <div className="space-y-1.5"><Label className="text-xs">Start *</Label><Input type="time" value={spaceData.start_time} onChange={e => setSpaceData({...spaceData, start_time: e.target.value})} required /></div>
              <div className="space-y-1.5"><Label className="text-xs">End *</Label><Input type="time" value={spaceData.end_time} onChange={e => setSpaceData({...spaceData, end_time: e.target.value})} required /></div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs">Purpose</Label><Input value={spaceData.purpose} onChange={e => setSpaceData({...spaceData, purpose: e.target.value})} /></div>
            <Button type="submit" className="w-full" disabled={submitting}>{submitting ? 'Submitting...' : 'Request Booking'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Policies Dialog */}
      <Dialog open={showPolicies} onOpenChange={setShowPolicies}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>58:12 Global Policies</DialogTitle></DialogHeader>
          {policies ? (
            <div className="space-y-6 mt-2">
              {Object.values(policies).map((p, i) => (
                <div key={p.title || i} className="space-y-1.5">
                  <h3 className="font-semibold text-sm flex items-center gap-2"><Shield size={14} className="text-primary" />{p.title}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">{p.content}</p>
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-muted-foreground py-4">Loading policies...</p>}
        </DialogContent>
      </Dialog>

      {/* Footer */}
      <footer className="bg-[#1a1a2e] text-slate-400 py-8 px-4 mt-12">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-6 mb-6">
            <div>
              <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" alt="58:12 Global" className="h-6 brightness-0 invert mb-3" />
              <p className="text-xs">Bringing hope and healing to the most vulnerable in our world.</p>
              <p className="text-xs mt-2">Office: 330-521-1948</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-300 uppercase mb-2">Where We Serve</p>
              <p className="text-xs">Holmes County (Ohio) | Thailand | Haiti | Kenya | Uganda</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-300 uppercase mb-2">Links</p>
              <div className="space-y-1">
                <a href="https://5812-global.org" target="_blank" rel="noopener noreferrer" className="text-xs hover:text-white flex items-center gap-1"><ExternalLink size={10} /> 5812-Global.org</a>
                <button onClick={() => setShowPolicies(true)} className="text-xs hover:text-white flex items-center gap-1"><Lock size={10} /> Privacy Policy & Terms</button>
                <Link to="/login" className="text-xs hover:text-white flex items-center gap-1"><Shield size={10} /> Staff Login</Link>
              </div>
            </div>
          </div>
          <div className="border-t border-slate-700 pt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[10px]">&copy; {new Date().getFullYear()} 58:12 Global. All rights reserved.</p>
            <div className="flex gap-3">
              <button onClick={() => setShowPolicies(true)} className="text-[10px] hover:text-white">Privacy Policy</button>
              <button onClick={() => setShowPolicies(true)} className="text-[10px] hover:text-white">Terms of Service</button>
              <button onClick={() => setShowPolicies(true)} className="text-[10px] hover:text-white">Refund Policy</button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
