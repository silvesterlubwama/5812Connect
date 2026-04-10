import React, { useState, useEffect, useRef } from 'react';
import { ShoppingCart, Plus, Trash2, Edit2, Package, Receipt, RefreshCw, Minus, X, Search, MapPin, Settings, Download, Upload } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { productsApi, salesApi, locationsApi, storeSettingsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const fmt = (n, currency = 'UGX') => `${currency} ${(n || 0).toLocaleString()}`;

const stockColor = (stock, reorder) => {
  if (stock === 0) return 'bg-red-100 text-red-700 border-red-200';
  if (stock <= (reorder || 5)) return 'bg-amber-100 text-amber-700 border-amber-200';
  return 'bg-green-100 text-green-700 border-green-200';
};

const stockLabel = (stock, reorder) => {
  if (stock === 0) return 'Out of stock';
  if (stock <= (reorder || 5)) return 'Low stock';
  return `${stock} in stock`;
};

const emptyProduct = { name: '', price: '', currency: 'UGX', stock: '', category: '', sku: '', reorder_level: '5', location_id: '' };

export default function ProductsPage() {
  const { user } = useAuth();
  const [products, setProducts] = useState([]);
  const [sales, setSales] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState([]);
  const [customerName, setCustomerName] = useState('Walk-in Customer');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [showProductModal, setShowProductModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [saving, setSaving] = useState(false);
  const [productForm, setProductForm] = useState(emptyProduct);
  const [productSearch, setProductSearch] = useState('');
  const [lastReceipt, setLastReceipt] = useState(null);
  const [showReceipt, setShowReceipt] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [locationFilter, setLocationFilter] = useState('all');
  // Store settings
  const [showStoreSettings, setShowStoreSettings] = useState(false);
  const [storeSettingsLoc, setStoreSettingsLoc] = useState('');
  const [storeSettings, setStoreSettings] = useState({});
  const [savingStore, setSavingStore] = useState(false);
  // Import/Export
  const [showImportExport, setShowImportExport] = useState(false);
  const [importData, setImportData] = useState('');
  const [importingData, setImportingData] = useState(false);

  const isAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager'].includes(user?.role);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [prodRes, salesRes, locRes] = await Promise.all([productsApi.list(), salesApi.list({ limit: 50 }), locationsApi.list()]);
      setProducts(prodRes.data);
      setSales(salesRes.data);
      setLocations(locRes.data || []);
      const custMap = {};
      salesRes.data.forEach(s => {
        const name = s.customer_name || 'Walk-in Customer';
        if (!custMap[name]) custMap[name] = { name, total_spent: 0, transactions: 0, last_purchase: s.created_at };
        custMap[name].total_spent += s.total || 0;
        custMap[name].transactions += 1;
        if (s.created_at > (custMap[name].last_purchase || '')) custMap[name].last_purchase = s.created_at;
      });
      setCustomers(Object.values(custMap).sort((a, b) => b.total_spent - a.total_spent));
    } catch { toast.error('Failed to load data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const filteredProducts = products.filter(p => {
    const matchSearch = p.name?.toLowerCase().includes(productSearch.toLowerCase());
    const matchLoc = locationFilter === 'all' || p.location_id === locationFilter || !p.location_id;
    return matchSearch && matchLoc;
  });

  const activeCurrency = (() => {
    if (locationFilter && locationFilter !== 'all') {
      const loc = locations.find(l => l.id === locationFilter);
      return loc?.currency || 'UGX';
    }
    return 'UGX';
  })();

  // Cart operations
  const addToCart = (product) => {
    if (product.stock === 0) { toast.error('Product is out of stock'); return; }
    setCart(prev => {
      const existing = prev.find(i => i.product_id === product.id);
      if (existing) {
        if (existing.qty >= product.stock) { toast.error('Not enough stock'); return prev; }
        return prev.map(i => i.product_id === product.id ? { ...i, qty: i.qty + 1 } : i);
      }
      return [...prev, { product_id: product.id, name: product.name, unit_price: product.price, qty: 1 }];
    });
  };

  const updateQty = (productId, delta) => {
    setCart(prev => prev.map(i => i.product_id === productId ? { ...i, qty: Math.max(0, i.qty + delta) } : i).filter(i => i.qty > 0));
  };

  const removeFromCart = (productId) => setCart(prev => prev.filter(i => i.product_id !== productId));
  const cartTotal = cart.reduce((sum, i) => sum + i.unit_price * i.qty, 0);

  const handleCheckout = async () => {
    if (cart.length === 0) { toast.error('Cart is empty'); return; }
    setCheckoutLoading(true);
    try {
      const payload = { items: cart, customer_name: customerName, payment_method: paymentMethod, total: cartTotal };
      if (locationFilter !== 'all') payload.location_id = locationFilter;
      const res = await salesApi.create(payload);
      setLastReceipt(res.data); setShowReceipt(true); setCart([]); setCustomerName('Walk-in Customer');
      toast.success(`Sale recorded! Invoice: ${res.data.id}`); fetchAll();
    } catch { toast.error('Checkout failed'); }
    finally { setCheckoutLoading(false); }
  };

  // Product CRUD
  const openAddProduct = () => { setEditingProduct(null); setProductForm({ ...emptyProduct, location_id: locationFilter !== 'all' ? locationFilter : '' }); setShowProductModal(true); };
  const openEditProduct = (p) => {
    setEditingProduct(p);
    setProductForm({ name: p.name, price: String(p.price), currency: p.currency || 'UGX', stock: String(p.stock), category: p.category || '', sku: p.sku || '', reorder_level: String(p.reorder_level || 5), location_id: p.location_id || '' });
    setShowProductModal(true);
  };

  const handleSaveProduct = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      const data = { ...productForm, price: parseFloat(productForm.price), stock: parseInt(productForm.stock), reorder_level: parseInt(productForm.reorder_level) || 5 };
      if (editingProduct) {
        const res = await productsApi.update(editingProduct.id, data);
        setProducts(prev => prev.map(p => p.id === editingProduct.id ? res.data : p));
        toast.success('Product updated!');
      } else {
        const res = await productsApi.create(data);
        setProducts(prev => [...prev, res.data]);
        toast.success('Product added!');
      }
      setShowProductModal(false);
    } catch { toast.error('Failed to save product'); }
    finally { setSaving(false); }
  };

  const deleteProduct = async (id) => {
    if (!window.confirm('Delete this product?')) return;
    await productsApi.delete(id);
    setProducts(prev => prev.filter(p => p.id !== id));
    toast.success('Product deleted');
  };

  // Store settings
  const openStoreSettings = async (locId) => {
    setStoreSettingsLoc(locId);
    try {
      const res = await storeSettingsApi.get(locId);
      setStoreSettings(res.data || {});
    } catch { setStoreSettings({}); }
    setShowStoreSettings(true);
  };

  const saveStoreSettings = async () => {
    setSavingStore(true);
    try {
      await storeSettingsApi.update(storeSettingsLoc, storeSettings);
      toast.success('Store settings saved');
      setShowStoreSettings(false);
    } catch { toast.error('Failed to save store settings'); }
    finally { setSavingStore(false); }
  };

  // Import/Export
  const handleExport = async () => {
    try {
      const params = {};
      if (locationFilter !== 'all') params.location_id = locationFilter;
      const res = await salesApi.export(params);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `sales_export_${new Date().toISOString().slice(0,10)}.json`; a.click();
      toast.success(`Exported ${res.data.count} sales`);
    } catch { toast.error('Export failed'); }
  };

  const handleImport = async () => {
    if (!importData.trim()) return;
    setImportingData(true);
    try {
      const parsed = JSON.parse(importData);
      const salesArr = Array.isArray(parsed) ? parsed : parsed.sales || [];
      const res = await salesApi.import({ sales: salesArr });
      toast.success(`Imported ${res.data.imported} sales`);
      setShowImportExport(false); setImportData(''); fetchAll();
    } catch (err) { toast.error(err.message || 'Import failed - check JSON format'); }
    finally { setImportingData(false); }
  };

  const locName = (id) => locations.find(l => l.id === id)?.name || '';

  // Available payment methods based on store settings or defaults
  const getPaymentMethods = () => {
    if (locationFilter !== 'all' && storeSettings?.payment_methods?.length) {
      return storeSettings.payment_methods;
    }
    return ['cash', 'mobile_money', 'card'];
  };

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold font-heading" data-testid="sales-page-title">Sales & Products</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{products.length} products &middot; {sales.length} sales recorded</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Select value={locationFilter} onValueChange={v => { setLocationFilter(v); setCart([]); }}>
            <SelectTrigger className="w-[180px] h-8 text-xs" data-testid="sales-location-filter"><SelectValue placeholder="All Locations" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Locations</SelectItem>
              {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {isAdmin && locationFilter !== 'all' && (
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1" onClick={() => openStoreSettings(locationFilter)} data-testid="store-settings-btn">
              <Settings size={12} /> Store
            </Button>
          )}
          <Button variant="outline" size="sm" className="h-8 text-xs gap-1" onClick={() => setShowImportExport(true)} data-testid="import-export-btn">
            <Download size={12} /> Import/Export
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={fetchAll} data-testid="sales-refresh"><RefreshCw size={14} /></Button>
        </div>
      </div>

      <Tabs defaultValue="pos">
        <TabsList>
          <TabsTrigger value="pos" data-testid="tab-pos">Point of Sale</TabsTrigger>
          <TabsTrigger value="products" data-testid="tab-products">Products</TabsTrigger>
          <TabsTrigger value="history" data-testid="tab-history">Sales History</TabsTrigger>
          <TabsTrigger value="customers" data-testid="tab-customers">Customers</TabsTrigger>
        </TabsList>

        {/* POS TAB */}
        <TabsContent value="pos" className="mt-4">
          <div className="grid lg:grid-cols-3 gap-5 h-[calc(100vh-320px)] min-h-[500px]">
            <div className="lg:col-span-2 flex flex-col gap-4">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input className="pl-9" placeholder="Search products..." value={productSearch} onChange={e => setProductSearch(e.target.value)} data-testid="pos-search" />
              </div>
              <div className="overflow-y-auto flex-1">
                {loading ? (
                  <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">{[1,2,3,4,5,6].map(i => <div key={i} className="h-32 bg-muted animate-pulse rounded-xl" />)}</div>
                ) : (
                  <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                    {filteredProducts.map(p => (
                      <button key={p.id} data-testid={`product-card-${p.id}`} onClick={() => addToCart(p)} disabled={p.stock === 0}
                        className={`text-left p-4 rounded-xl border-2 transition-all hover:shadow-soft-lg active:scale-[0.98] ${p.stock === 0 ? 'opacity-50 cursor-not-allowed border-border bg-secondary/30' : 'cursor-pointer border-border hover:border-primary bg-card hover:bg-primary/5'}`}>
                        <div className="flex items-start justify-between mb-2">
                          <div className="p-2 rounded-lg bg-secondary"><Package size={16} className="text-muted-foreground" /></div>
                          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${stockColor(p.stock, p.reorder_level)}`}>{stockLabel(p.stock, p.reorder_level)}</span>
                        </div>
                        <p className="font-semibold text-sm leading-tight">{p.name}</p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {p.category && <span className="text-xs text-muted-foreground">{p.category}</span>}
                          {p.location_id && <span className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground"><MapPin size={8} className="inline mr-0.5" />{locName(p.location_id)}</span>}
                        </div>
                        <p className="text-primary font-bold mt-2 text-sm">{fmt(p.price, p.currency || activeCurrency)}</p>
                      </button>
                    ))}
                    {filteredProducts.length === 0 && <div className="col-span-3 text-center py-12 text-sm text-muted-foreground">No products found.</div>}
                  </div>
                )}
              </div>
            </div>

            {/* Cart */}
            <div className="flex flex-col bg-card border border-border rounded-xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-secondary/30">
                <ShoppingCart size={15} className="text-primary" />
                <span className="font-semibold text-sm">Cart</span>
                <span className="ml-auto text-xs text-muted-foreground">{cart.length} items</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {cart.length === 0 ? (
                  <div className="text-center py-8 text-xs text-muted-foreground"><ShoppingCart size={24} className="mx-auto mb-2 opacity-30" />Tap products to add them</div>
                ) : cart.map(item => (
                  <div key={item.product_id} className="flex items-center gap-2 p-2.5 rounded-lg bg-secondary/40 hover:bg-secondary/60 transition-colors">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{item.name}</p>
                      <p className="text-xs text-muted-foreground">{fmt(item.unit_price, activeCurrency)} each</p>
                    </div>
                    <div className="flex items-center gap-1">
                      <button className="h-5 w-5 rounded bg-secondary flex items-center justify-center hover:bg-border" onClick={() => updateQty(item.product_id, -1)}><Minus size={10} /></button>
                      <span className="text-xs font-semibold w-5 text-center">{item.qty}</span>
                      <button className="h-5 w-5 rounded bg-secondary flex items-center justify-center hover:bg-border" onClick={() => updateQty(item.product_id, 1)}><Plus size={10} /></button>
                    </div>
                    <span className="text-xs font-bold text-primary min-w-[60px] text-right">{fmt(item.unit_price * item.qty, activeCurrency)}</span>
                    <button className="text-muted-foreground hover:text-destructive" onClick={() => removeFromCart(item.product_id)}><X size={12} /></button>
                  </div>
                ))}
              </div>
              <div className="p-4 border-t border-border space-y-3 bg-card">
                <div className="space-y-2">
                  <Input placeholder="Customer name" value={customerName} onChange={e => setCustomerName(e.target.value)} className="text-sm h-8" data-testid="customer-name-input" />
                  <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                    <SelectTrigger className="h-8 text-sm" data-testid="payment-method-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {getPaymentMethods().map(m => <SelectItem key={m} value={m}>{m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-bold text-lg text-primary">{fmt(cartTotal, activeCurrency)}</span>
                </div>
                <Button className="w-full gap-2" disabled={cart.length === 0 || checkoutLoading} onClick={handleCheckout} data-testid="checkout-btn">
                  <Receipt size={15} />{checkoutLoading ? 'Processing...' : 'Complete Sale'}
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* PRODUCTS TAB */}
        <TabsContent value="products" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={openAddProduct} data-testid="add-product-btn"><Plus size={14} /> Add Product</Button>
          </div>
          {loading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[1,2,3].map(i => <div key={i} className="h-32 bg-muted animate-pulse rounded-xl" />)}</div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredProducts.map(p => (
                <Card key={p.id} className="shadow-soft rounded-xl" data-testid="product-item">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <p className="font-semibold text-sm leading-tight flex-1">{p.name}</p>
                      <div className="flex gap-1 ml-2">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => openEditProduct(p)} data-testid="edit-product-btn"><Edit2 size={11} /></Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={() => deleteProduct(p.id)} data-testid="delete-product-btn"><Trash2 size={11} /></Button>
                      </div>
                    </div>
                    {p.category && <p className="text-xs text-muted-foreground mb-1">{p.category}</p>}
                    {p.location_id && <p className="text-[10px] text-muted-foreground mb-1 flex items-center gap-1"><MapPin size={9} />{locName(p.location_id)}</p>}
                    <p className="text-primary font-bold text-sm">{fmt(p.price, p.currency || 'UGX')}</p>
                    <div className="mt-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${stockColor(p.stock, p.reorder_level)}`}>{stockLabel(p.stock, p.reorder_level)}</span>
                    </div>
                    {p.sku && <p className="text-xs text-muted-foreground mt-1.5 font-mono">SKU: {p.sku}</p>}
                  </CardContent>
                </Card>
              ))}
              {filteredProducts.length === 0 && <div className="col-span-4 text-center py-16 text-sm text-muted-foreground">No products added yet.</div>}
            </div>
          )}
        </TabsContent>

        {/* HISTORY TAB */}
        <TabsContent value="history" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardContent className="p-5">
              {loading ? (
                <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
              ) : sales.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 font-medium text-muted-foreground">Invoice</th>
                      <th className="pb-2 font-medium text-muted-foreground">Customer</th>
                      <th className="pb-2 font-medium text-muted-foreground">Items</th>
                      <th className="pb-2 font-medium text-muted-foreground">Total</th>
                      <th className="pb-2 font-medium text-muted-foreground">Payment</th>
                      <th className="pb-2 font-medium text-muted-foreground">Location</th>
                      <th className="pb-2 font-medium text-muted-foreground">Date</th>
                      <th className="pb-2 font-medium text-muted-foreground">Cashier</th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {sales.map(sale => (
                        <tr key={sale.id} className="hover:bg-accent/30 transition-colors" data-testid="sale-row">
                          <td className="py-3 font-mono text-xs text-primary font-semibold">{sale.id}</td>
                          <td className="py-3">{sale.customer_name || '--'}</td>
                          <td className="py-3 text-muted-foreground">{(sale.items || []).length} items</td>
                          <td className="py-3 font-bold text-primary">{fmt(sale.total)}</td>
                          <td className="py-3"><Badge variant="outline" className="text-xs capitalize">{sale.payment_method}</Badge></td>
                          <td className="py-3 text-xs text-muted-foreground">{sale.location_id ? locName(sale.location_id) : '--'}</td>
                          <td className="py-3 text-muted-foreground text-xs">{sale.created_at?.slice(0, 16).replace('T', ' ')}</td>
                          <td className="py-3 text-muted-foreground">{sale.cashier || '--'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="text-sm text-muted-foreground text-center py-12">No sales recorded yet.</p>}
            </CardContent>
          </Card>
        </TabsContent>

        {/* CUSTOMERS TAB */}
        <TabsContent value="customers" className="mt-4">
          <Card className="shadow-soft rounded-xl">
            <CardHeader className="py-4 px-5"><CardTitle className="text-base font-semibold">Customer Directory</CardTitle></CardHeader>
            <CardContent className="px-5 pb-5">
              {loading ? (
                <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-12 bg-muted animate-pulse rounded" />)}</div>
              ) : customers.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left border-b border-border">
                      <th className="pb-2 font-medium text-muted-foreground">Customer</th>
                      <th className="pb-2 font-medium text-muted-foreground">Total Spent</th>
                      <th className="pb-2 font-medium text-muted-foreground">Transactions</th>
                      <th className="pb-2 font-medium text-muted-foreground">Last Purchase</th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {customers.map((c, i) => (
                        <tr key={i} className="hover:bg-accent/30 transition-colors" data-testid="customer-row">
                          <td className="py-3 font-medium">{c.name}</td>
                          <td className="py-3 text-primary font-semibold">{fmt(c.total_spent)}</td>
                          <td className="py-3 text-muted-foreground">{c.transactions}</td>
                          <td className="py-3 text-muted-foreground text-xs">{c.last_purchase?.slice(0, 10)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="text-sm text-muted-foreground text-center py-12">No customer data yet.</p>}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Add/Edit Product Modal */}
      <Dialog open={showProductModal} onOpenChange={setShowProductModal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingProduct ? 'Edit Product' : 'Add Product'}</DialogTitle></DialogHeader>
          <form onSubmit={handleSaveProduct} className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Product Name *</Label>
              <Input placeholder="Product name" value={productForm.name} onChange={e => setProductForm({...productForm, name: e.target.value})} required data-testid="product-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Price *</Label>
                <Input type="number" placeholder="0" value={productForm.price} onChange={e => setProductForm({...productForm, price: e.target.value})} required data-testid="product-price-input" />
              </div>
              <div className="space-y-2"><Label>Stock</Label>
                <Input type="number" placeholder="0" value={productForm.stock} onChange={e => setProductForm({...productForm, stock: e.target.value})} data-testid="product-stock-input" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Category</Label>
                <Input placeholder="e.g. Farm, Merchandise" value={productForm.category} onChange={e => setProductForm({...productForm, category: e.target.value})} />
              </div>
              <div className="space-y-2"><Label>Currency</Label>
                <Select value={productForm.currency || 'UGX'} onValueChange={v => setProductForm({...productForm, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','EUR','GBP'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Location</Label>
                <Select value={productForm.location_id || 'none'} onValueChange={v => setProductForm({...productForm, location_id: v === 'none' ? '' : v})}>
                  <SelectTrigger data-testid="product-location-select"><SelectValue placeholder="Select location" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No Location</SelectItem>
                    {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Reorder Level</Label>
                <Input type="number" placeholder="5" value={productForm.reorder_level} onChange={e => setProductForm({...productForm, reorder_level: e.target.value})} />
              </div>
            </div>
            <div className="space-y-2"><Label>SKU</Label>
              <Input placeholder="Product SKU (optional)" value={productForm.sku} onChange={e => setProductForm({...productForm, sku: e.target.value})} />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowProductModal(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-product-btn">{saving ? 'Saving...' : editingProduct ? 'Update' : 'Add Product'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Receipt Modal */}
      <Dialog open={showReceipt} onOpenChange={setShowReceipt}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Receipt size={16} /> Receipt</DialogTitle></DialogHeader>
          {lastReceipt && (
            <div className="space-y-4 font-mono text-sm">
              <div className="text-center border-b border-border pb-3">
                <p className="font-bold">58:12 Global Connect</p>
                <p className="text-xs text-muted-foreground">Invoice: {lastReceipt.id}</p>
                <p className="text-xs text-muted-foreground">{lastReceipt.created_at?.slice(0, 16).replace('T', ' ')}</p>
              </div>
              <div className="space-y-1.5">
                {(lastReceipt.items || []).map((item, i) => (
                  <div key={i} className="flex justify-between text-xs"><span>{item.name} x{item.qty}</span><span>{fmt(item.unit_price * item.qty)}</span></div>
                ))}
              </div>
              <div className="border-t border-border pt-3 flex justify-between font-bold"><span>TOTAL</span><span className="text-primary">{fmt(lastReceipt.total)}</span></div>
              <div className="text-xs text-muted-foreground flex justify-between">
                <span>Customer: {lastReceipt.customer_name}</span>
                <span className="capitalize">{lastReceipt.payment_method}</span>
              </div>
              <div className="text-center text-xs text-muted-foreground border-t border-border pt-3">Thank you for your purchase!</div>
              <Button className="w-full" onClick={() => { setShowReceipt(false); window.print(); }}>Print Receipt</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Store Settings Modal */}
      <Dialog open={showStoreSettings} onOpenChange={setShowStoreSettings}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Settings size={16} /> Store Settings</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">{locName(storeSettingsLoc)}</p>
          <div className="space-y-4 mt-2">
            <div className="space-y-2"><Label>Store Name</Label>
              <Input placeholder="Store display name" value={storeSettings.store_name || ''} onChange={e => setStoreSettings({...storeSettings, store_name: e.target.value})} data-testid="store-name-input" />
            </div>
            <div className="space-y-2">
              <Label>Payment Methods</Label>
              <div className="flex flex-wrap gap-2">
                {['cash', 'mobile_money', 'card', 'bank_transfer', 'cheque'].map(m => (
                  <label key={m} className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="checkbox" checked={(storeSettings.payment_methods || []).includes(m)}
                      onChange={e => {
                        const methods = storeSettings.payment_methods || [];
                        setStoreSettings({...storeSettings, payment_methods: e.target.checked ? [...methods, m] : methods.filter(x => x !== m)});
                      }} className="rounded border-border" />
                    {m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  </label>
                ))}
              </div>
            </div>
            <div className="space-y-2"><Label>Mobile Money Providers (comma-separated)</Label>
              <Input placeholder="MTN, Airtel, ..." value={(storeSettings.mobile_money_providers || []).join(', ')} onChange={e => setStoreSettings({...storeSettings, mobile_money_providers: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2"><Label>Tax Rate (%)</Label>
                <Input type="number" step="0.01" value={storeSettings.tax_rate || 0} onChange={e => setStoreSettings({...storeSettings, tax_rate: parseFloat(e.target.value) || 0})} />
              </div>
              <div className="space-y-2"><Label>Currency</Label>
                <Select value={storeSettings.currency || 'UGX'} onValueChange={v => setStoreSettings({...storeSettings, currency: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{['UGX','USD','KES','EUR','GBP'].map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2"><Label>Receipt Footer</Label>
              <Input placeholder="Thank you for shopping!" value={storeSettings.receipt_footer || ''} onChange={e => setStoreSettings({...storeSettings, receipt_footer: e.target.value})} />
            </div>
            <div className="space-y-2">
              <Label>API Integrations (JSON)</Label>
              <Textarea rows={3} placeholder='[{"name": "MoMo API", "url": "https://...", "key": "..."}]'
                value={JSON.stringify(storeSettings.api_integrations || [], null, 2)}
                onChange={e => { try { setStoreSettings({...storeSettings, api_integrations: JSON.parse(e.target.value)}); } catch (e) { console.warn(e.message || e); } }}
              />
              <p className="text-xs text-muted-foreground">External payment API configurations for this location</p>
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowStoreSettings(false)}>Cancel</Button>
              <Button className="flex-1" onClick={saveStoreSettings} disabled={savingStore} data-testid="save-store-settings-btn">{savingStore ? 'Saving...' : 'Save Settings'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Import/Export Modal */}
      <Dialog open={showImportExport} onOpenChange={setShowImportExport}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Sales Import / Export</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Button className="w-full gap-2" variant="outline" onClick={handleExport} data-testid="export-sales-btn">
                <Download size={14} /> Export Sales (JSON)
              </Button>
              <p className="text-xs text-muted-foreground">Downloads all sales{locationFilter !== 'all' ? ` for ${locName(locationFilter)}` : ''} as JSON</p>
            </div>
            <div className="border-t border-border pt-4 space-y-2">
              <Label>Import Sales Data (JSON)</Label>
              <Textarea rows={5} placeholder='[{"items": [...], "total": 50000, "customer_name": "John", "payment_method": "cash"}]'
                value={importData} onChange={e => setImportData(e.target.value)} data-testid="import-sales-input" />
              <Button className="w-full gap-2" onClick={handleImport} disabled={importingData || !importData.trim()} data-testid="import-sales-btn">
                <Upload size={14} /> {importingData ? 'Importing...' : 'Import Sales'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
