import React, { useState, useEffect, useRef } from 'react';
import { ShoppingCart, Plus, Trash2, Edit2, Package, Receipt, RefreshCw, Minus, X, Search } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { productsApi, salesApi } from '../services/api';
import { toast } from 'sonner';

const fmt = (n) => `UGX ${(n || 0).toLocaleString()}`;

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

const emptyProduct = { name: '', price: '', currency: 'UGX', stock: '', category: '', sku: '', reorder_level: '5' };

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [sales, setSales] = useState([]);
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

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [prodRes, salesRes] = await Promise.all([productsApi.list(), salesApi.list({ limit: 50 })]);
      setProducts(prodRes.data);
      setSales(salesRes.data);
    } catch { toast.error('Failed to load data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  // ---- Cart operations ----
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
    setCart(prev => {
      const updated = prev.map(i => i.product_id === productId ? { ...i, qty: Math.max(0, i.qty + delta) } : i);
      return updated.filter(i => i.qty > 0);
    });
  };

  const removeFromCart = (productId) => setCart(prev => prev.filter(i => i.product_id !== productId));

  const cartTotal = cart.reduce((sum, i) => sum + i.unit_price * i.qty, 0);

  const handleCheckout = async () => {
    if (cart.length === 0) { toast.error('Cart is empty'); return; }
    setCheckoutLoading(true);
    try {
      const res = await salesApi.create({ items: cart, customer_name: customerName, payment_method: paymentMethod, total: cartTotal });
      setLastReceipt(res.data);
      setShowReceipt(true);
      setCart([]);
      setCustomerName('Walk-in Customer');
      toast.success(`Sale recorded! Invoice: ${res.data.id}`);
      fetchAll();
    } catch { toast.error('Checkout failed'); }
    finally { setCheckoutLoading(false); }
  };

  // ---- Product CRUD ----
  const openAddProduct = () => { setEditingProduct(null); setProductForm(emptyProduct); setShowProductModal(true); };
  const openEditProduct = (p) => {
    setEditingProduct(p);
    setProductForm({ name: p.name, price: String(p.price), currency: p.currency || 'UGX', stock: String(p.stock), category: p.category || '', sku: p.sku || '', reorder_level: String(p.reorder_level || 5) });
    setShowProductModal(true);
  };

  const handleSaveProduct = async (e) => {
    e.preventDefault();
    setSaving(true);
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

  const filteredProducts = products.filter(p => p.name?.toLowerCase().includes(productSearch.toLowerCase()));

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Sales & Products</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{products.length} products · {sales.length} sales recorded</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAll} data-testid="sales-refresh"><RefreshCw size={14} /></Button>
      </div>

      <Tabs defaultValue="pos">
        <TabsList>
          <TabsTrigger value="pos" data-testid="tab-pos">Point of Sale</TabsTrigger>
          <TabsTrigger value="products" data-testid="tab-products">Products</TabsTrigger>
          <TabsTrigger value="history" data-testid="tab-history">Sales History</TabsTrigger>
        </TabsList>

        {/* ---- POS TAB ---- */}
        <TabsContent value="pos" className="mt-4">
          <div className="grid lg:grid-cols-3 gap-5 h-[calc(100vh-280px)] min-h-[500px]">
            {/* Product grid */}
            <div className="lg:col-span-2 flex flex-col gap-4">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input className="pl-9" placeholder="Search products..." value={productSearch} onChange={e => setProductSearch(e.target.value)} data-testid="pos-search" />
              </div>
              <div className="overflow-y-auto flex-1">
                {loading ? (
                  <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                    {[1,2,3,4,5,6].map(i => <div key={i} className="h-32 bg-muted animate-pulse rounded-xl" />)}
                  </div>
                ) : (
                  <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                    {filteredProducts.map(p => (
                      <button
                        key={p.id}
                        data-testid={`product-card-${p.id}`}
                        onClick={() => addToCart(p)}
                        disabled={p.stock === 0}
                        className={`text-left p-4 rounded-xl border-2 transition-all hover:shadow-soft-lg active:scale-[0.98] ${p.stock === 0 ? 'opacity-50 cursor-not-allowed border-border bg-secondary/30' : 'cursor-pointer border-border hover:border-primary bg-card hover:bg-primary/5'}`}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="p-2 rounded-lg bg-secondary">
                            <Package size={16} className="text-muted-foreground" />
                          </div>
                          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${stockColor(p.stock, p.reorder_level)}`}>
                            {stockLabel(p.stock, p.reorder_level)}
                          </span>
                        </div>
                        <p className="font-semibold text-sm leading-tight">{p.name}</p>
                        {p.category && <p className="text-xs text-muted-foreground mt-0.5">{p.category}</p>}
                        <p className="text-primary font-bold mt-2 text-sm">{fmt(p.price)}</p>
                      </button>
                    ))}
                    {filteredProducts.length === 0 && (
                      <div className="col-span-3 text-center py-12 text-sm text-muted-foreground">No products found.</div>
                    )}
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

              {/* Cart items */}
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {cart.length === 0 ? (
                  <div className="text-center py-8 text-xs text-muted-foreground">
                    <ShoppingCart size={24} className="mx-auto mb-2 opacity-30" />
                    Tap products to add them
                  </div>
                ) : cart.map(item => (
                  <div key={item.product_id} className="flex items-center gap-2 p-2.5 rounded-lg bg-secondary/40 hover:bg-secondary/60 transition-colors">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{item.name}</p>
                      <p className="text-xs text-muted-foreground">{fmt(item.unit_price)} each</p>
                    </div>
                    <div className="flex items-center gap-1">
                      <button className="h-5 w-5 rounded bg-secondary flex items-center justify-center hover:bg-border transition-colors" onClick={() => updateQty(item.product_id, -1)}>
                        <Minus size={10} />
                      </button>
                      <span className="text-xs font-semibold w-5 text-center">{item.qty}</span>
                      <button className="h-5 w-5 rounded bg-secondary flex items-center justify-center hover:bg-border transition-colors" onClick={() => updateQty(item.product_id, 1)}>
                        <Plus size={10} />
                      </button>
                    </div>
                    <span className="text-xs font-bold text-primary min-w-[60px] text-right">{fmt(item.unit_price * item.qty)}</span>
                    <button className="text-muted-foreground hover:text-destructive" onClick={() => removeFromCart(item.product_id)}><X size={12} /></button>
                  </div>
                ))}
              </div>

              {/* Cart footer */}
              <div className="p-4 border-t border-border space-y-3 bg-card">
                <div className="space-y-2">
                  <Input
                    placeholder="Customer name"
                    value={customerName}
                    onChange={e => setCustomerName(e.target.value)}
                    className="text-sm h-8"
                    data-testid="customer-name-input"
                  />
                  <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                    <SelectTrigger className="h-8 text-sm" data-testid="payment-method-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cash">Cash</SelectItem>
                      <SelectItem value="mobile_money">Mobile Money</SelectItem>
                      <SelectItem value="card">Card</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-bold text-lg text-primary">{fmt(cartTotal)}</span>
                </div>
                <Button
                  className="w-full gap-2"
                  disabled={cart.length === 0 || checkoutLoading}
                  onClick={handleCheckout}
                  data-testid="checkout-btn"
                >
                  <Receipt size={15} />
                  {checkoutLoading ? 'Processing...' : 'Complete Sale'}
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* ---- PRODUCTS TAB ---- */}
        <TabsContent value="products" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="gap-2" onClick={openAddProduct} data-testid="add-product-btn">
              <Plus size={14} /> Add Product
            </Button>
          </div>
          {loading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1,2,3].map(i => <div key={i} className="h-32 bg-muted animate-pulse rounded-xl" />)}
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {products.map(p => (
                <Card key={p.id} className="shadow-soft rounded-xl" data-testid="product-item">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <p className="font-semibold text-sm leading-tight flex-1">{p.name}</p>
                      <div className="flex gap-1 ml-2">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => openEditProduct(p)} data-testid="edit-product-btn"><Edit2 size={11} /></Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={() => deleteProduct(p.id)} data-testid="delete-product-btn"><Trash2 size={11} /></Button>
                      </div>
                    </div>
                    {p.category && <p className="text-xs text-muted-foreground mb-2">{p.category}</p>}
                    <p className="text-primary font-bold text-sm">{fmt(p.price)}</p>
                    <div className="mt-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${stockColor(p.stock, p.reorder_level)}`}>
                        {stockLabel(p.stock, p.reorder_level)}
                      </span>
                    </div>
                    {p.sku && <p className="text-xs text-muted-foreground mt-1.5 font-mono">SKU: {p.sku}</p>}
                  </CardContent>
                </Card>
              ))}
              {products.length === 0 && (
                <div className="col-span-4 text-center py-16 text-sm text-muted-foreground">No products added yet.</div>
              )}
            </div>
          )}
        </TabsContent>

        {/* ---- HISTORY TAB ---- */}
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
                      <th className="pb-2 font-medium text-muted-foreground">Date</th>
                      <th className="pb-2 font-medium text-muted-foreground">Cashier</th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {sales.map(sale => (
                        <tr key={sale.id} className="hover:bg-accent/30 transition-colors" data-testid="sale-row">
                          <td className="py-3 font-mono text-xs text-primary font-semibold">{sale.id}</td>
                          <td className="py-3">{sale.customer_name || '—'}</td>
                          <td className="py-3 text-muted-foreground">{(sale.items || []).length} items</td>
                          <td className="py-3 font-bold text-primary">{fmt(sale.total)}</td>
                          <td className="py-3">
                            <Badge variant="outline" className="text-xs capitalize">{sale.payment_method}</Badge>
                          </td>
                          <td className="py-3 text-muted-foreground text-xs">{sale.created_at?.slice(0, 16).replace('T', ' ')}</td>
                          <td className="py-3 text-muted-foreground">{sale.cashier || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-12">No sales recorded yet.</p>
              )}
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
              <div className="space-y-2"><Label>Price (UGX) *</Label>
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
                  <div key={i} className="flex justify-between text-xs">
                    <span>{item.name} x{item.qty}</span>
                    <span>{fmt(item.unit_price * item.qty)}</span>
                  </div>
                ))}
              </div>
              <div className="border-t border-border pt-3 flex justify-between font-bold">
                <span>TOTAL</span>
                <span className="text-primary">{fmt(lastReceipt.total)}</span>
              </div>
              <div className="text-xs text-muted-foreground flex justify-between">
                <span>Customer: {lastReceipt.customer_name}</span>
                <span className="capitalize">{lastReceipt.payment_method}</span>
              </div>
              <div className="text-center text-xs text-muted-foreground border-t border-border pt-3">
                Thank you for your purchase!
              </div>
              <Button className="w-full" onClick={() => { setShowReceipt(false); window.print(); }}>
                Print Receipt
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
