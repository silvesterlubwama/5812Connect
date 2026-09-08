import React, { useState, useEffect, useCallback } from 'react';
import { ShoppingCart, Plus, Minus, Trash2, Lock, LogOut, Search, Package } from 'lucide-react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import api from '../services/api';
import { toast } from 'sonner';
import { Toaster } from '../components/ui/sonner';

export default function SalesPortalPage() {
  const [authed, setAuthed] = useState(false);
  const [staffName, setStaffName] = useState('');
  const [staffUser, setStaffUser] = useState(null);
  const [loginForm, setLoginForm] = useState({ last_name: '', pin: '' });
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState([]);
  const [search, setSearch] = useState('');
  const [locked, setLocked] = useState(false);
  const [showUnlock, setShowUnlock] = useState(false);
  const [adminPwd, setAdminPwd] = useState('');
  const [processing, setProcessing] = useState(false);
  const [showManage, setShowManage] = useState(false);
  const [productForm, setProductForm] = useState({ name: '', price: '', stock: '', category: '', resource_id: '', event_id: '' });
  const [resourceOptions, setResourceOptions] = useState([]);
  const [eventOptions, setEventOptions] = useState([]);
  const [recentSales, setRecentSales] = useState([]);
  const [customerSearch, setCustomerSearch] = useState('');
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [customers, setCustomers] = useState([]);

  const handleLogin = async () => {
    try {
      const res = await api.post('/auth/sales-portal-login', loginForm);
      setAuthed(true);
      setStaffName(res.data.name);
      setStaffUser(res.data);
      toast.success(`Welcome, ${res.data.name}`);
    } catch (err) { toast.error(err.response?.data?.detail || 'Invalid credentials'); }
  };

  const fetchProducts = useCallback(async () => {
    try {
      const res = await api.get('/products');
      setProducts(res.data || []);
    } catch { /* ignore */ }
  }, []);

  const fetchRecentSales = useCallback(async () => {
    try {
      const res = await api.get('/sales', { params: { limit: 10 } });
      setRecentSales(res.data || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (authed) { fetchProducts(); fetchRecentSales(); } }, [authed, fetchProducts, fetchRecentSales]);

  // Fetch bookable resources + upcoming public events so the product editor
  // can offer them for linkage (marketplace ↔ resource / marketplace ↔ ticket).
  useEffect(() => {
    if (!authed || !showManage) return;
    (async () => {
      try {
        const [rs, ev] = await Promise.all([
          api.get('/resources').catch(() => ({ data: [] })),
          api.get('/events', { params: { is_public: true } }).catch(() => ({ data: [] })),
        ]);
        setResourceOptions((rs.data || []).filter(r => r.is_bookable && !r.is_consumable));
        setEventOptions((ev.data || []).filter(e => e.status !== 'cancelled'));
      } catch { /* ignore */ }
    })();
  }, [authed, showManage]);

  const searchCustomers = async (q) => {
    if (q.length < 2) { setCustomers([]); return; }
    try { const res = await api.get('/customers', { params: { search: q } }); setCustomers(res.data || []); } catch { setCustomers([]); }
  };

  // Auto-lock after 5 minutes of inactivity
  useEffect(() => {
    if (!authed || locked) return;
    let timer;
    const resetTimer = () => { clearTimeout(timer); timer = setTimeout(() => setLocked(true), 5 * 60 * 1000); };
    const events = ['mousedown', 'keydown', 'touchstart', 'scroll'];
    events.forEach(e => document.addEventListener(e, resetTimer));
    resetTimer();
    return () => { clearTimeout(timer); events.forEach(e => document.removeEventListener(e, resetTimer)); };
  }, [authed, locked]);

  // Request fullscreen on first auth
  useEffect(() => {
    if (authed && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  }, [authed]);

  // ESC exits fullscreen — but only when the terminal is NOT locked. When
  // locked, the admin has explicitly pinned the kiosk in place, so we swallow
  // ESC and immediately re-enter fullscreen if the browser dropped it.
  useEffect(() => {
    if (!authed) return;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (locked) {
        e.preventDefault();
        e.stopPropagation();
        if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(() => {});
        }
      } else if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    };
    const onFsChange = () => {
      // If locked and the browser dropped fullscreen (e.g., user pressed F11),
      // re-enter it so the kiosk stays pinned.
      if (locked && !document.fullscreenElement && document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => {});
      }
    };
    // Capture-phase so this runs before shadcn Dialog's own ESC handler.
    window.addEventListener('keydown', onKey, true);
    document.addEventListener('fullscreenchange', onFsChange);
    return () => {
      window.removeEventListener('keydown', onKey, true);
      document.removeEventListener('fullscreenchange', onFsChange);
    };
  }, [authed, locked]);



  const addToCart = (p) => {
    setCart(prev => {
      const existing = prev.find(c => c.product_id === p.id);
      // If this product is linked to a resource, capture a booking slot so
      // the sale can auto-create the booking. Sensible defaults: today, 2pm–3pm.
      const slot = p.resource_id ? {
        booking_date: new Date().toISOString().slice(0, 10),
        booking_start_time: '14:00',
        booking_end_time: '15:00',
      } : {};
      if (existing) return prev.map(c => c.product_id === p.id ? { ...c, qty: c.qty + 1 } : c);
      return [...prev, { product_id: p.id, name: p.name, price: p.price, qty: 1, resource_id: p.resource_id || null, event_id: p.event_id || null, ...slot }];
    });
  };

  const updateQty = (pid, delta) => {
    setCart(prev => prev.map(c => c.product_id === pid ? { ...c, qty: Math.max(1, c.qty + delta) } : c));
  };

  const removeFromCart = (pid) => setCart(prev => prev.filter(c => c.product_id !== pid));

  const total = cart.reduce((s, c) => s + c.price * c.qty, 0);

  const completeSale = async () => {
    if (cart.length === 0) return;
    setProcessing(true);
    try {
      await api.post('/sales', { items: cart, total, payment_method: 'cash', cashier: staffName, customer_id: selectedCustomer?.id, customer_name: selectedCustomer?.name || 'Walk-in Customer' });
      toast.success(`Sale completed — ${total.toLocaleString()}`);
      setCart([]); setSelectedCustomer(null); setCustomerSearch('');
      fetchProducts();
      fetchRecentSales();
    } catch (err) { toast.error(err.response?.data?.detail || 'Sale failed'); }
    finally { setProcessing(false); }
  };

  const handleUnlock = async () => {
    try {
      await api.post('/auth/login', { identifier: 'admin@5812uganda.org', password: adminPwd });
      setLocked(false); setShowUnlock(false); setAdminPwd('');
    } catch { toast.error('Invalid admin password'); }
  };

  const handleAddProduct = async () => {
    try {
      const res = await api.post('/products', { ...productForm, price: parseFloat(productForm.price) || 0, stock: parseInt(productForm.stock) || 0, resource_id: productForm.resource_id || null, event_id: productForm.event_id || null });
      setProductForm({ name: '', price: '', stock: '', category: '', resource_id: '', event_id: '' });
      fetchProducts();
      toast.success('Product added');
    } catch { toast.error('Failed'); }
  };

  const filtered = search ? products.filter(p => p.name?.toLowerCase().includes(search.toLowerCase())) : products;

  // Lock screen
  if (locked) return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center" data-testid="sales-locked">
      <div className="text-center space-y-4">
        <Lock size={48} className="mx-auto text-slate-500" />
        <p className="text-white text-lg font-semibold">Sales Terminal Locked</p>
        <Button onClick={() => setShowUnlock(true)} className="bg-amber-600 hover:bg-amber-700">Unlock</Button>
        <Dialog open={showUnlock} onOpenChange={setShowUnlock}>
          <DialogContent className="max-w-xs">
            <DialogHeader><DialogTitle>Admin Unlock</DialogTitle></DialogHeader>
            <div className="space-y-3 mt-2">
              <Input type="password" placeholder="Admin password" value={adminPwd} onChange={e => setAdminPwd(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') handleUnlock(); }} data-testid="admin-unlock-pwd" />
              <Button className="w-full" onClick={handleUnlock}>Unlock</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
      <Toaster />
    </div>
  );

  // Login screen
  if (!authed) return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-4" data-testid="sales-login">
      <Card className="w-full max-w-sm shadow-2xl rounded-2xl border-0">
        <CardContent className="p-6 space-y-4">
          <div className="text-center">
            <ShoppingCart size={32} className="mx-auto mb-2 text-amber-500" />
            <h1 className="text-xl font-bold">Sales Portal</h1>
            <p className="text-xs text-muted-foreground">58:12 Global Connect</p>
          </div>
          <div className="space-y-2"><Label>Last Name</Label><Input value={loginForm.last_name} onChange={e => setLoginForm({ ...loginForm, last_name: e.target.value })} placeholder="Enter last name" data-testid="sales-last-name" /></div>
          <div className="space-y-2"><Label>PIN</Label><Input type="password" maxLength={6} value={loginForm.pin} onChange={e => setLoginForm({ ...loginForm, pin: e.target.value })} placeholder="Enter PIN" onKeyDown={e => { if (e.key === 'Enter') handleLogin(); }} data-testid="sales-pin" /></div>
          <Button className="w-full" onClick={handleLogin} data-testid="sales-login-btn">Log In</Button>
        </CardContent>
      </Card>
      <Toaster />
    </div>
  );

  // Main POS
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex flex-col" data-testid="sales-portal">
      {/* Header */}
      <div className="bg-white dark:bg-slate-800 border-b px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShoppingCart size={18} className="text-amber-500" />
          <span className="font-semibold text-sm">Sales Portal</span>
          <Badge variant="outline" className="text-xs">{staffName}</Badge>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => setShowManage(true)} data-testid="manage-products-btn"><Package size={12} /> Manage</Button>
          <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => setLocked(true)} data-testid="lock-terminal-btn"><Lock size={12} /> Lock</Button>
        </div>
      </div>

      <div className="flex-1 flex">
        {/* Products */}
        <div className="flex-1 p-4 space-y-3 overflow-auto">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9 h-9" placeholder="Search products..." value={search} onChange={e => setSearch(e.target.value)} data-testid="product-search" />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            {filtered.map(p => (
              <Card key={p.id} className="rounded-xl cursor-pointer hover:shadow-md transition-shadow" onClick={() => addToCart(p)} data-testid={`product-${p.id}`}>
                <CardContent className="p-3 text-center">
                  <p className="text-sm font-medium truncate">{p.name}</p>
                  <p className="text-xs text-amber-600 font-bold">{(p.price || 0).toLocaleString()}</p>
                  <p className="text-[10px] text-muted-foreground">Stock: {p.stock ?? '-'}</p>
                </CardContent>
              </Card>
            ))}
            {filtered.length === 0 && <p className="col-span-full text-center text-sm text-muted-foreground py-8">No products found</p>}
          </div>
        </div>

        {/* Cart */}
        <div className="w-80 border-l bg-white dark:bg-slate-800 flex flex-col">
          <div className="p-3 border-b"><p className="text-sm font-semibold">Cart ({cart.length})</p></div>
          {/* Customer lookup */}
          <div className="p-2 border-b space-y-1">
            <div className="flex gap-1">
              <Input className="h-7 text-xs flex-1" placeholder="Customer name/phone..." value={customerSearch} onChange={e => { setCustomerSearch(e.target.value); searchCustomers(e.target.value); }} />
              {customerSearch.trim() && !selectedCustomer && customers.length === 0 && (
                <Button size="sm" className="h-7 text-[10px] shrink-0" onClick={async () => {
                  try {
                    const res = await api.post('/customers', { name: customerSearch.trim() });
                    setSelectedCustomer(res.data); setCustomers([]); toast.success('Customer created');
                  } catch { toast.error('Failed'); }
                }} data-testid="create-customer-btn">+ New</Button>
              )}
            </div>
            {customers.length > 0 && !selectedCustomer && (
              <div className="max-h-24 overflow-auto border rounded text-xs">
                {customers.map(c => <button key={c.id} className="w-full text-left px-2 py-1 hover:bg-accent/50" onClick={() => { setSelectedCustomer(c); setCustomerSearch(c.name); setCustomers([]); }}>{c.name} {c.phone ? `(${c.phone})` : ''}</button>)}
              </div>
            )}
            {selectedCustomer && <div className="flex items-center justify-between text-xs"><Badge variant="outline" className="text-[10px]">{selectedCustomer.name}</Badge><button className="text-destructive text-[10px]" onClick={() => { setSelectedCustomer(null); setCustomerSearch(''); }}>Clear</button></div>}
          </div>
          <div className="flex-1 overflow-auto p-2 space-y-1">
            {cart.map(c => (
              <div key={c.product_id} className="flex items-center gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-700/50 text-sm">
                <div className="flex-1 min-w-0"><p className="truncate font-medium text-xs">{c.name}</p><p className="text-[10px] text-muted-foreground">{c.price.toLocaleString()} x {c.qty}</p></div>
                <div className="flex items-center gap-1">
                  <button className="w-6 h-6 rounded bg-muted flex items-center justify-center" onClick={() => updateQty(c.product_id, -1)}><Minus size={10} /></button>
                  <span className="text-xs w-5 text-center">{c.qty}</span>
                  <button className="w-6 h-6 rounded bg-muted flex items-center justify-center" onClick={() => updateQty(c.product_id, 1)}><Plus size={10} /></button>
                  <button className="text-destructive" onClick={() => removeFromCart(c.product_id)}><Trash2 size={12} /></button>
                </div>
              </div>
            ))}
            {cart.length === 0 && <p className="text-center text-xs text-muted-foreground py-8">Cart empty</p>}
          </div>
          <div className="border-t p-3 space-y-2">
            <div className="flex justify-between text-sm font-bold"><span>Total</span><span>{total.toLocaleString()}</span></div>
            <Button className="w-full bg-green-600 hover:bg-green-700" disabled={cart.length === 0 || processing} onClick={completeSale} data-testid="complete-sale-btn">
              {processing ? 'Processing...' : 'Complete Sale'}
            </Button>
          </div>
        </div>
      </div>

      {/* Product Management Dialog */}
      <Dialog open={showManage} onOpenChange={setShowManage}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Manage Products</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-2">
              <Input placeholder="Product name" value={productForm.name} onChange={e => setProductForm({...productForm, name: e.target.value})} />
              <Input type="number" placeholder="Price" value={productForm.price} onChange={e => setProductForm({...productForm, price: e.target.value})} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input type="number" placeholder="Stock" value={productForm.stock} onChange={e => setProductForm({...productForm, stock: e.target.value})} />
              <Input placeholder="Category" value={productForm.category} onChange={e => setProductForm({...productForm, category: e.target.value})} />
            </div>
            {/* iter-marketplace-links: pick a bookable resource OR a public
                event so a POS sale auto-creates a booking or ticket. */}
            <div className="grid grid-cols-2 gap-2">
              <select
                className="text-xs h-9 rounded border px-2 bg-background"
                value={productForm.resource_id}
                onChange={e => setProductForm({ ...productForm, resource_id: e.target.value, event_id: e.target.value ? '' : productForm.event_id })}
                data-testid="product-resource-picker"
              >
                <option value="">Link resource (optional)</option>
                {resourceOptions.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <select
                className="text-xs h-9 rounded border px-2 bg-background"
                value={productForm.event_id}
                onChange={e => setProductForm({ ...productForm, event_id: e.target.value, resource_id: e.target.value ? '' : productForm.resource_id })}
                data-testid="product-event-picker"
              >
                <option value="">Link event (optional)</option>
                {eventOptions.map(ev => <option key={ev.id} value={ev.id}>{ev.title}</option>)}
              </select>
            </div>
            {(productForm.resource_id || productForm.event_id) && (
              <p className="text-[10px] text-muted-foreground -mt-1">
                {productForm.resource_id ? '✓ Sales of this product will auto-book the resource (cart must ship a date/start/end).' : '✓ Each sold unit will auto-issue a scannable event ticket.'}
              </p>
            )}
            <Button className="w-full" disabled={!productForm.name} onClick={handleAddProduct} data-testid="add-product-portal-btn">Add Product</Button>
            <div className="border-t pt-3 space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground">All Products ({products.length})</p>
              {products.map(p => (
                <div key={p.id} className="flex items-center justify-between p-2 rounded bg-muted/50 text-xs">
                  <span>{p.name} — {(p.price || 0).toLocaleString()} (stock: {p.stock ?? '-'})</span>
                </div>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>
      <Toaster />
    </div>
  );
}
