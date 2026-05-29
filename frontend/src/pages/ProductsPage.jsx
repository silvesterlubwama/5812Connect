import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import useConfirm from '../hooks/useConfirm';
import { ShoppingCart, Plus, Trash2, Edit2, Package, Receipt, RefreshCw, Minus, X, Search, MapPin, Settings, Download, Upload, Printer, Barcode } from 'lucide-react';
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
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { BulkActionBar, exportToCSV, SelectCheckbox } from '../components/BulkActions';
import VariantBarcodePrint from '../components/VariantBarcodePrint';
import ActivityFeed from '../components/ActivityFeed';
import VariantPickerDialog from '../components/VariantPickerDialog';
import ReceiptComponent from '../components/Receipt';
import InvoicesTab from '../components/sales/InvoicesTab';
import BarcodeScanDialog from '../components/BarcodeScanDialog';
import { calcLine, calcCart, pickTierDiscount } from '../utils/cartCalc';
import PinNumpad from '../components/PinNumpad';
import useIdleTimeout, { enterKioskFullscreen } from '../utils/kioskMode';
import { authApi, cashDropsApi, shiftsApi } from '../services/api';
import ChangeCalculator from '../components/ChangeCalculator';
import { COUNTRY_TO_CURRENCY } from '../utils/cashDenominations';
import { SOUNDS, haptic, isWebSerialSupported, requestSerialPort, kickCashDrawer, describePeripheralSupport } from '../utils/posPeripherals';
import { queueOfflineSale, syncOfflineSales, offlineQueueCount, onConnectivityChange } from '../utils/offlinePos';

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
  const { confirm, ConfirmDialog } = useConfirm();
  const [products, setProducts] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [sales, setSales] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState([]);
  const [customerName, setCustomerName] = useState('Walk-in Customer');
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [activePricelist, setActivePricelist] = useState(null); // { id, name, discount_pct }
  const [showPickCustomer, setShowPickCustomer] = useState(false);
  const [pickCustQuery, setPickCustQuery] = useState('');
  const [pickCustResults, setPickCustResults] = useState([]);
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [showProductModal, setShowProductModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [saving, setSaving] = useState(false);
  const [productForm, setProductForm] = useState(emptyProduct);
  const [productSearch, setProductSearch] = useState('');
  const [lastReceipt, setLastReceipt] = useState(null);
  const [lastStoreSettings, setLastStoreSettings] = useState(null);
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
  // Variant barcode printing
  const [barcodePrintProduct, setBarcodePrintProduct] = useState(null);
  // Customer profile drawer (receipt history)
  const [customerProfile, setCustomerProfile] = useState(null);
  // Variant picker (when clicking a product with variants on POS)
  const [variantPickerProduct, setVariantPickerProduct] = useState(null);
  // Active tab (controlled — needed for USB scanner focus capture scope)
  const [activeTab, setActiveTab] = useState('pos');
  // Sale Counter location: bound at kiosk-config time (NOT picked per-sale).
  // Resolution order: URL param (/pos/:storeId) → localStorage → user's primary location_id.
  const [saleLocationId, setSaleLocationId] = useState(() =>
    localStorage.getItem('5812_pos_store_id') || user?.location_id || ''
  );
  // Receipt paper size (set before completing sale)
  const [receiptPaperSize, setReceiptPaperSize] = useState('auto');
  // Persist the POS store binding so the kiosk stays locked to its store across refreshes
  useEffect(() => {
    if (saleLocationId) localStorage.setItem('5812_pos_store_id', saleLocationId);
  }, [saleLocationId]);
  // Friendly label for the bound store (custom store_name → location name → fallback)
  const posBoundStoreLabel = (() => {
    if (!saleLocationId) return 'No store assigned — set in Store Settings';
    const loc = (locations || []).find(l => l.id === saleLocationId);
    return (storeSettings.location_id === saleLocationId && storeSettings.store_name) || loc?.name || saleLocationId;
  })();
  // Whether this device is a dedicated POS kiosk (URL was /pos/:storeId)
  const isPosKiosk = typeof window !== 'undefined' && localStorage.getItem('5812_pos_kiosk') === 'true';

  // Cashier shift — independent of platform login. Set by PIN, cleared on idle/switch.
  const [activeCashier, setActiveCashier] = useState(null); // { id, name, role }
  const [pinError, setPinError] = useState('');
  const [pinSubmitting, setPinSubmitting] = useState(false);

  // Idle auto-return: 3 min of inactivity → clear cashier so PIN is required again
  useIdleTimeout(
    () => { if (isPosKiosk && activeCashier) setActiveCashier(null); },
    180000,
    isPosKiosk && !!activeCashier
  );

  // Fullscreen + wake-lock on first interaction (browsers require user gesture for these)
  useEffect(() => {
    if (!isPosKiosk) return undefined;
    let cleanup = null;
    const onFirstInteract = async () => {
      cleanup = await enterKioskFullscreen();
      window.removeEventListener('click', onFirstInteract);
      window.removeEventListener('touchstart', onFirstInteract);
    };
    window.addEventListener('click', onFirstInteract, { once: true });
    window.addEventListener('touchstart', onFirstInteract, { once: true });
    return () => {
      window.removeEventListener('click', onFirstInteract);
      window.removeEventListener('touchstart', onFirstInteract);
      if (cleanup) cleanup();
    };
  }, [isPosKiosk]);

  const handlePinLogin = async (pin) => {
    setPinError('');
    setPinSubmitting(true);
    try {
      const res = await authApi.pinLogin(pin, saleLocationId);
      setActiveCashier(res.data.user);
      toast.success(`Welcome, ${res.data.user.name}`);
    } catch (e) {
      setPinError(e.response?.data?.detail || 'Invalid PIN');
    } finally { setPinSubmitting(false); }
  };
  // Editing a completed sale (admin/director)
  const [editingSale, setEditingSale] = useState(null);
  const [editSaleForm, setEditSaleForm] = useState({ cashier: '', location_id: '', customer_name: '' });
  useEffect(() => {
    if (editingSale) {
      setEditSaleForm({
        cashier: editingSale.cashier || '',
        location_id: editingSale.location_id || '',
        customer_name: editingSale.customer_name || '',
      });
    }
  }, [editingSale]);

  const isAdmin = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager'].includes(user?.role);
  // Admin/Director/Manager can issue & edit product barcodes manually
  const canIssueProductBarcodes = ['admin', 'system_admin', 'Executive Director', 'Adviser', 'Director', 'Manager', 'Leader', 'Coordinator'].includes(user?.role);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [prodRes, salesRes, locRes] = await Promise.all([productsApi.list(), salesApi.list({ limit: 200 }), locationsApi.list()]);
      setProducts(prodRes.data);
      setSales(salesRes.data);
      setLocations(locRes.data || []);
      // Aggregate customers from sales — keep receipts per customer for the profile drawer
      const custMap = {};
      salesRes.data.forEach(s => {
        const name = s.customer_name || 'Walk-in Customer';
        const phone = s.customer_phone || '';
        if (!custMap[name]) custMap[name] = { id: s.customer_id || null, name, phone, total_spent: 0, transactions: 0, last_purchase: s.created_at, receipts: [] };
        // First sale wins the id; later sales fill in if it was missing
        if (!custMap[name].id && s.customer_id) custMap[name].id = s.customer_id;
        custMap[name].total_spent += s.total || 0;
        custMap[name].transactions += 1;
        if (s.created_at > (custMap[name].last_purchase || '')) custMap[name].last_purchase = s.created_at;
        if (!custMap[name].phone && phone) custMap[name].phone = phone;
        custMap[name].receipts.push({
          receipt_number: s.receipt_number || s.id,
          total: s.total || 0,
          date: s.created_at,
          payment_method: s.payment_method,
          payment_status: s.payment_status || 'paid',
          cashier: s.cashier,
          items_count: (s.items || []).length,
          items: s.items || [],
        });
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
  const addToCart = async (product, variant = null) => {
    let effectivePrice = variant?.price ?? product.price;
    let priceSource = 'base';
    // Apply customer pricelist if a registered customer is selected
    if (selectedCustomerId) {
      try {
        const r = await api.get('/pricelists/resolve', { params: { customer_id: selectedCustomerId, product_id: product.id, variant_id: variant?.id || undefined } });
        if (r.data && typeof r.data.price === 'number') {
          effectivePrice = r.data.price;
          priceSource = r.data.source || 'pricelist';
        }
      } catch { /* fall back to base price */ }
    }
    const effectiveStock = variant ? (variant.stock || 0) : (product.stock || 0);
    if (effectiveStock <= 0) { toast.error(`${product.name}${variant ? ` (${variant.name})` : ''} is out of stock`); return; }
    const key = variant ? `${product.id}:${variant.id}` : product.id;
    setCart(prev => {
      const existing = prev.find(i => (i.variant_id ? `${i.product_id}:${i.variant_id}` : i.product_id) === key);
      if (existing) {
        if (existing.qty >= effectiveStock) { toast.error('Not enough stock'); return prev; }
        return prev.map(i => (i.variant_id ? `${i.product_id}:${i.variant_id}` : i.product_id) === key ? { ...i, qty: i.qty + 1 } : i);
      }
      const packCost = Number(variant?.packaging_cost || 0);
      return [...prev, {
        product_id: product.id,
        name: product.name + (variant ? ` — ${variant.name}` : ''),
        variant_id: variant?.id || null,
        variant_name: variant?.name || null,
        unit_price: effectivePrice,
        qty: 1,
        units_per_pack: Number(variant?.units_per_pack || 1),
        packaging_cost: packCost,
        packaging_label: variant?.packaging_label || '',
        include_packaging: packCost > 0,  // default include if there's a cost
        price_source: priceSource,
      }];
    });
    toast.success(`Added ${product.name}${variant ? ` (${variant.name})` : ''}${priceSource !== 'base' ? ` · ${priceSource === 'pricelist_override' ? 'custom price' : 'discount'} applied` : ''}`);
  };

  const togglePackaging = (item) => {
    const key = _cartKey(item);
    setCart(prev => prev.map(i => _cartKey(i) === key ? { ...i, include_packaging: !i.include_packaging } : i));
  };

  // Barcode scan dialog
  const [scanOpen, setScanOpen] = useState(false);

  const handleBarcodeScan = (scanned) => {
    const code = (scanned || '').trim();
    if (!code) return;
    // 1) Match against variant barcodes
    for (const p of products) {
      for (const v of (p.variants || [])) {
        if ((v.barcode || v.id) === code || v.sku === code) {
          SOUNDS.scanSuccess();
          haptic(20);
          addToCart(p, v);
          return;
        }
      }
    }
    // 2) Match against product-level barcode / id / sku
    const prod = products.find(p => p.barcode === code || p.id === code || p.sku === code);
    if (prod) {
      SOUNDS.scanSuccess();
      haptic(20);
      addToCart(prod);
      return;
    }
    // 3) Resource serials start with 5812- — open the public resource page in a new tab
    if (/^5812-/i.test(code)) {
      SOUNDS.scanSuccess();
      window.open(`/resource/${encodeURIComponent(code)}`, '_blank');
      toast.info('Resource lookup opened in new tab');
      return;
    }
    SOUNDS.scanFail();
    haptic([60, 30, 60]);
    toast.error(`Unknown code: ${code}`);
  };

  // Desktop USB scanner focus capture: buffer rapid keystrokes ending with Enter, route to scan handler.
  // Active only on the POS tab; ignored when typing into inputs/textareas.
  useEffect(() => {
    if (activeTab !== 'pos') return;
    let buffer = '';
    let lastKeyTime = 0;
    const SCAN_THRESHOLD_MS = 30;        // human typing > 50ms; USB scanners < 20ms between keys
    const MIN_SCAN_LENGTH = 4;
    const onKeyDown = (e) => {
      // Skip when user is in a text input
      const t = e.target;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      const now = Date.now();
      if (e.key === 'Enter') {
        if (buffer.length >= MIN_SCAN_LENGTH) {
          handleBarcodeScan(buffer);
          buffer = '';
          e.preventDefault();
          e.stopPropagation();
        }
        return;
      }
      // Reset buffer if user typed slowly (probably human)
      if (now - lastKeyTime > 250) buffer = '';
      lastKeyTime = now;
      // Only collect printable chars
      if (e.key.length === 1) buffer += e.key;
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, products]);

  const _cartKey = (i) => i.variant_id ? `${i.product_id}:${i.variant_id}` : i.product_id;

  const updateQty = (item, delta) => {
    const key = _cartKey(item);
    setCart(prev => prev.map(i => _cartKey(i) === key ? { ...i, qty: Math.max(0, i.qty + delta) } : i).filter(i => i.qty > 0));
  };

  const removeFromCart = (item) => {
    const key = _cartKey(item);
    setCart(prev => prev.filter(i => _cartKey(i) !== key));
  };

  // Cart totals — applies per-product tier discounts + packaging cost
  const productsById = Object.fromEntries((products || []).map(p => [p.id, p]));
  const cartTotals = calcCart(cart, productsById);
  const cartTotal = cartTotals.total;

  // Parked / draft sales
  const [drafts, setDrafts] = useState([]);
  const [showDrafts, setShowDrafts] = useState(false);
  const fetchDrafts = async () => {
    try { const res = await salesApi.drafts(); setDrafts(res.data || []); }
    catch (e) { console.warn(e.message || e); }
  };
  useEffect(() => { fetchDrafts(); }, []);

  const parkSale = async () => {
    if (cart.length === 0) { toast.error('Cart is empty — nothing to park'); return; }
    try {
      const payload = { items: cart, customer_name: customerName, payment_method: paymentMethod, total: cartTotal };
      if (locationFilter !== 'all') payload.location_id = locationFilter;
      await salesApi.saveDraft(payload);
      toast.success('Sale parked — reopen later from "Parked Sales"');
      setCart([]); setCustomerName('Walk-in Customer');
      fetchDrafts();
    } catch { toast.error('Failed to park sale'); }
  };

  const reopenDraft = (d) => {
    setCart(d.items || []);
    setCustomerName(d.customer_name || 'Walk-in Customer');
    setPaymentMethod(d.payment_method || 'cash');
    toast.info(`Reopened sale parked by ${d.parked_by_name || 'someone'}`);
    setShowDrafts(false);
  };

  const discardDraft = async (id) => {
    if (!await confirm({ title: 'Discard parked sale?', message: 'This parked cart will be lost.', destructive: true, confirmLabel: 'Discard' })) return;
    try { await salesApi.deleteDraft(id); fetchDrafts(); toast.success('Discarded'); }
    catch { toast.error('Failed'); }
  };

  // Change calculator (cash sales)
  const [changeOpen, setChangeOpen] = useState(false);
  // Peripheral status
  const [drawerConnected, setDrawerConnected] = useState(false);
  // Cash drop dialog
  const [cashDropOpen, setCashDropOpen] = useState(false);
  const [cashDropForm, setCashDropForm] = useState({ amount: '', destination: 'safe', destination_account_id: '', notes: '' });
  // Cashier shift
  const [currentShift, setCurrentShift] = useState(null);
  const [openShiftDlg, setOpenShiftDlg] = useState(false);
  const [closeShiftDlg, setCloseShiftDlg] = useState(false);
  const [shiftForm, setShiftForm] = useState({ opening_cash: '', closing_cash: '', notes: '' });
  const [shiftResult, setShiftResult] = useState(null);

  // Offline POS — IndexedDB queue for cash sales when network is down
  const [isOnline, setIsOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [pendingOfflineCount, setPendingOfflineCount] = useState(0);
  const refreshOfflineCount = async () => {
    try { setPendingOfflineCount(await offlineQueueCount()); } catch (e) { /* ignore */ }
  };
  useEffect(() => {
    refreshOfflineCount();
    const cleanup = onConnectivityChange(
      async () => {
        setIsOnline(true);
        toast.success('Back online — syncing offline sales...');
        try {
          const res = await syncOfflineSales(salesApi);
          if (res.succeeded > 0) toast.success(`Synced ${res.succeeded} offline sale${res.succeeded === 1 ? '' : 's'}`);
          if (res.failed > 0) toast.error(`${res.failed} sales failed to sync — will retry`);
          refreshOfflineCount();
          fetchAll();
        } catch (e) { /* ignore */ }
      },
      () => {
        setIsOnline(false);
        toast.warning('Offline — cash sales only until reconnect');
      }
    );
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch current shift when location or cashier changes
  useEffect(() => {
    if (!saleLocationId) return;
    shiftsApi.current({ location_id: saleLocationId })
      .then(r => setCurrentShift(r.data || null))
      .catch(() => setCurrentShift(null));
  }, [saleLocationId, activeCashier]);

  // Resolve country / currency for change breakdown
  const activeLocation = (locations || []).find(l => l.id === saleLocationId);
  const activeCurrency2 = activeLocation?.currency || COUNTRY_TO_CURRENCY[activeLocation?.country] || 'UGX';

  const handleCheckout = async () => {
    if (cart.length === 0) { toast.error('Cart is empty'); SOUNDS.saleError(); return; }
    // For cash payments, open the change calculator first
    if (paymentMethod === 'cash') {
      setChangeOpen(true);
      return;
    }
    await actuallyCheckout();
  };

  const actuallyCheckout = async (cashInfo = null) => {
    // Offline guard — only cash sales allowed when network is down
    if (!isOnline) {
      if (paymentMethod !== 'cash') {
        toast.error('You are offline. Only CASH sales can be processed until reconnect.');
        SOUNDS.saleError();
        return;
      }
    }
    setCheckoutLoading(true);
    try {
      // Enrich cart items with computed line totals (so receipt + sale record match what was charged)
      const enrichedItems = cart.map(item => {
        const product = productsById[item.product_id] || null;
        const calc = calcLine(item, cart, product);
        return {
          ...item,
          subtotal: calc.subtotal,
          packaging_applied: item.include_packaging !== false ? calc.packaging_total : 0,
          discount_pct: calc.discount_pct,
          discount_amount: calc.discount_amount,
          line_total: calc.line_total,
        };
      });
      const payload = {
        items: enrichedItems,
        customer_name: customerName,
        payment_method: paymentMethod,
        total: cartTotals.total,
        subtotal: cartTotals.subtotal,
        packaging_total: cartTotals.packaging_total,
        discount: cartTotals.discount_total,
      };
      // Active cashier (PIN-authed shift) → recorded on the sale's receipt
      if (activeCashier) {
        payload.cashier = activeCashier.name;
        payload.cashier_id = activeCashier.id;
      }
      // Cash details if provided
      if (cashInfo) {
        payload.amount_given = cashInfo.amount_given;
        payload.change_due = cashInfo.change_due;
      }
      // Sale gets tagged with the explicit Sale Counter location (the actual store/sub-location)
      if (saleLocationId) {
        payload.location_id = saleLocationId;
      } else if (locationFilter !== 'all') {
        payload.location_id = locationFilter;
      }

      // OFFLINE PATH: queue locally and return a synthetic receipt
      if (!isOnline) {
        const queued = await queueOfflineSale(payload);
        const receipt = {
          ...payload,
          id: queued.temp_id,
          receipt_number: queued.temp_id,
          cashier: activeCashier?.name || user?.name || 'Cashier',
          created_at: queued.created_at,
          offline: true,
        };
        const receiptStoreSettings = receiptPaperSize !== 'auto' ? { ...storeSettings, receipt_paper_size: receiptPaperSize } : storeSettings;
        setLastReceipt(receipt); setLastStoreSettings(receiptStoreSettings); setShowReceipt(true);
        setCart([]); setCustomerName('Walk-in Customer');
        SOUNDS.saleComplete(); haptic([30, 50, 30]);
        if (drawerConnected) { kickCashDrawer().catch(() => {}); }
        toast.success(`Sale queued offline (${queued.temp_id}) — will sync when online`);
        refreshOfflineCount();
        return;
      }

      const res = await salesApi.create(payload);
      // Auto-set paper size override on receipt if user picked one (otherwise use store default)
      const receiptStoreSettings = receiptPaperSize !== 'auto' ? { ...storeSettings, receipt_paper_size: receiptPaperSize } : storeSettings;
      setLastReceipt(res.data); setLastStoreSettings(receiptStoreSettings); setShowReceipt(true); setCart([]); setCustomerName('Walk-in Customer');
      SOUNDS.saleComplete();
      haptic([30, 50, 30]);
      // Kick the cash drawer if connected (cash sales only)
      if (paymentMethod === 'cash' && drawerConnected) {
        kickCashDrawer().catch(() => {});
      }
      toast.success(`Sale recorded! Receipt: ${res.data.receipt_number || res.data.id}`);
      fetchAll();
    } catch (e) {
      SOUNDS.saleError();
      toast.error(e.response?.data?.detail || 'Checkout failed');
    } finally { setCheckoutLoading(false); }
  };

  // Product CRUD
  const openAddProduct = () => { setEditingProduct(null); setProductForm({ ...emptyProduct, location_id: locationFilter !== 'all' ? locationFilter : '' }); setShowProductModal(true); };
  const openEditProduct = (p) => {
    setEditingProduct(p);
    setProductForm({ name: p.name, price: String(p.price || 0), currency: p.currency || 'UGX', stock: String(p.stock || 0), category: p.category || '', sku: p.sku || '', reorder_level: String(p.reorder_level || 5), location_id: p.location_id || '', has_variants: p.has_variants || false, product_type: p.product_type || '', variants: p.variants || [], qty_discount_tiers: p.qty_discount_tiers || [], max_discount_pct: p.max_discount_pct ?? 20 });
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
    } catch (err) {
      // Surface the real backend reason so the user knows WHY it failed
      let msg = err.response?.data?.detail;
      if (Array.isArray(msg)) {
        // Pydantic validation errors → join field path + msg
        msg = msg.map(e => `${(e.loc || []).join('.')}: ${e.msg}`).join('; ');
      } else if (typeof msg === 'object' && msg !== null) {
        msg = JSON.stringify(msg);
      }
      toast.error(`Failed to save: ${msg || err.message || 'unknown error'}`);
      console.error('Product save error:', err.response?.data || err);
    }
    finally { setSaving(false); }
  };

  const deleteProduct = async (id) => {
    if (!await confirm({ title: 'Delete product?', message: 'This product will be removed permanently.', destructive: true, confirmLabel: 'Delete' })) return;
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

  // When the Sale Counter location changes on POS, auto-load that store's settings
  // so the receipt header/footer/paper-size match the actual selling location.
  useEffect(() => {
    if (!saleLocationId) return;
    storeSettingsApi.get(saleLocationId)
      .then(res => setStoreSettings(res.data || {}))
      .catch(() => setStoreSettings({}));
  }, [saleLocationId]);

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

  // PIN gate for dedicated POS kiosks — block all UI until cashier authenticates
  if (isPosKiosk && !activeCashier) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-background to-secondary/30 p-4" data-testid="pos-kiosk-pin-gate">
        <div className="w-full max-w-sm bg-card rounded-xl shadow-lg p-6 space-y-5 border border-border">
          <div className="text-center">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{posBoundStoreLabel}</p>
          </div>
          <PinNumpad
            title="Cashier sign-in"
            subtitle="Enter your 4-6 digit PIN"
            onSubmit={handlePinLogin}
            error={pinError}
            loading={pinSubmitting}
          />
          <p className="text-[10px] text-muted-foreground text-center">PIN auto-clears after 3 minutes of no activity.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold font-heading" data-testid="sales-page-title">Sales & Products</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{products.length} products &middot; {sales.length} sales recorded</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Active cashier badge + Switch Cashier (kiosk mode) */}
          {isPosKiosk && activeCashier && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20">
              <span className="text-xs font-medium">Cashier: <span className="font-bold">{activeCashier.name}</span></span>
              <Button variant="ghost" size="sm" className="h-7 text-[10px]" onClick={() => setActiveCashier(null)} data-testid="switch-cashier-btn">Switch</Button>
            </div>
          )}
          {isAdmin && (
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1" onClick={() => openStoreSettings(locationFilter)} data-testid="store-settings-btn">
              <Settings size={12} /> Store
            </Button>
          )}
          <Button variant="outline" size="sm" className="h-8 text-xs gap-1" onClick={() => setShowImportExport(true)} data-testid="import-export-btn">
            <Download size={12} /> Import/Export
          </Button>
          {/* Peripheral: Cash Drawer connect */}
          {isWebSerialSupported() && (
            <Button variant="outline" size="sm" className={`h-8 text-xs gap-1 ${drawerConnected ? 'border-green-300 text-green-700' : ''}`} data-testid="connect-drawer-btn"
              onClick={async () => {
                try {
                  await requestSerialPort();
                  setDrawerConnected(true);
                  toast.success('Cash drawer / printer connected');
                  SOUNDS.drawerOpen();
                } catch (e) { toast.error(e.message || 'Connection cancelled'); }
              }} title="Connect cash drawer (via thermal printer's RJ12 jack)">
              <span className={`w-1.5 h-1.5 rounded-full ${drawerConnected ? 'bg-green-500' : 'bg-muted-foreground'}`} />
              {drawerConnected ? 'Drawer Connected' : 'Connect Drawer'}
            </Button>
          )}
          {/* Peripheral support diagnostics — shows what works in current browser */}
          <PeripheralDiagnostics />
          {/* Offline status indicator */}
          {!isOnline && (
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-amber-50 border border-amber-300 text-xs text-amber-800" data-testid="offline-indicator">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              Offline — cash only
              {pendingOfflineCount > 0 && <span className="font-bold ml-1">({pendingOfflineCount} queued)</span>}
            </div>
          )}
          {isOnline && pendingOfflineCount > 0 && (
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1 border-blue-300 text-blue-700" data-testid="sync-now-btn" onClick={async () => {
              const res = await syncOfflineSales(salesApi);
              toast.success(`Synced ${res.succeeded}, ${res.failed} failed`);
              refreshOfflineCount();
              fetchAll();
            }}>Sync {pendingOfflineCount} queued</Button>
          )}
          {/* Cash Drop button */}
          <Button variant="outline" size="sm" className="h-8 text-xs gap-1" data-testid="cash-drop-btn" onClick={() => setCashDropOpen(true)}>
            <Download size={12} /> Drop Cash
          </Button>
          {/* Cashier Shift status / open / close */}
          {currentShift ? (
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1 border-green-300 text-green-700" data-testid="close-shift-btn" onClick={() => { setShiftForm({...shiftForm, closing_cash: ''}); setCloseShiftDlg(true); }}>
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" /> Shift Open · End Shift
            </Button>
          ) : (
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1" data-testid="open-shift-btn" onClick={() => { setShiftForm({opening_cash: '', closing_cash: '', notes: ''}); setOpenShiftDlg(true); }}>
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground" /> Open Shift
            </Button>
          )}
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={fetchAll} data-testid="sales-refresh"><RefreshCw size={14} /></Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="pos" data-testid="tab-pos">Point of Sale</TabsTrigger>
          <TabsTrigger value="products" data-testid="tab-products">Products</TabsTrigger>
          <TabsTrigger value="invoices" data-testid="tab-invoices">Invoices</TabsTrigger>
          <TabsTrigger value="history" data-testid="tab-history">Sales History</TabsTrigger>
          <TabsTrigger value="customers" data-testid="tab-customers">Customers</TabsTrigger>
        </TabsList>

        {/* POS TAB */}
        <TabsContent value="pos" className="mt-4">
          <div className="grid lg:grid-cols-3 gap-5 h-[calc(100vh-320px)] min-h-[500px]">
            <div className="lg:col-span-2 flex flex-col gap-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input className="pl-9" placeholder="Search products..." value={productSearch} onChange={e => setProductSearch(e.target.value)} data-testid="pos-search" />
                </div>
                <Button variant="outline" size="default" className="gap-1.5" onClick={() => setScanOpen(true)} data-testid="pos-scan-btn" title="Scan barcode (camera or USB scanner)">
                  <Barcode size={14} /> Scan
                </Button>
              </div>
              <div className="overflow-y-auto flex-1">
                {loading ? (
                  <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">{[1,2,3,4,5,6].map(i => <div key={i} className="h-32 bg-muted animate-pulse rounded-xl" />)}</div>
                ) : (
                  <div>
                    {selectedIds.size > 0 && <div className="mb-3"><BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())} onBulkExport={() => { exportToCSV(filteredProducts.filter(p => selectedIds.has(p.id)), 'products-export.csv'); }} onBulkDelete={async () => { if (!await confirm({ title: `Delete ${selectedIds.size} products?`, message: 'This cannot be undone.', destructive: true, confirmLabel: 'Delete all' })) return; for (const id of selectedIds) { try { await productsApi.delete(id); } catch { /* ignore individual failures */ } } setSelectedIds(new Set()); fetchAll(); toast.success('Deleted'); }} /></div>}
                  <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                    {filteredProducts.map(p => (
                      <div key={p.id} className={`relative ${selectedIds.has(p.id) ? 'ring-2 ring-primary/40 rounded-xl' : ''}`}>
                        <div className="absolute top-2 left-2 z-10"><input type="checkbox" className="accent-primary" checked={selectedIds.has(p.id)} onChange={() => setSelectedIds(prev => { const n = new Set(prev); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n; })} onClick={e => e.stopPropagation()} /></div>
                      <button data-testid={`product-card-${p.id}`} onClick={() => {
                        if (p.has_variants && (p.variants || []).length > 0) {
                          setVariantPickerProduct(p);
                        } else {
                          addToCart(p);
                        }
                      }} disabled={(p.has_variants ? (p.variants || []).reduce((s, v) => s + (v.stock || 0), 0) : p.stock) === 0}
                        className={`text-left p-4 rounded-xl border-2 transition-all hover:shadow-soft-lg active:scale-[0.98] ${(p.has_variants ? (p.variants || []).reduce((s, v) => s + (v.stock || 0), 0) : p.stock) === 0 ? 'opacity-50 cursor-not-allowed border-border bg-secondary/30' : 'cursor-pointer border-border hover:border-primary bg-card hover:bg-primary/5'}`}>
                        <div className="flex items-start justify-between mb-2">
                          <div className="p-2 rounded-lg bg-secondary"><Package size={16} className="text-muted-foreground" /></div>
                          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${stockColor(p.has_variants ? (p.variants || []).reduce((s, v) => s + (v.stock || 0), 0) : p.stock, p.reorder_level)}`}>{stockLabel(p.has_variants ? (p.variants || []).reduce((s, v) => s + (v.stock || 0), 0) : p.stock, p.reorder_level)}</span>
                        </div>
                        <p className="font-semibold text-sm leading-tight">{p.name}</p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {p.category && <span className="text-xs text-muted-foreground">{p.category}</span>}
                          {p.has_variants && <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">{(p.variants || []).length} variants</span>}
                          {p.location_id && <span className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground"><MapPin size={8} className="inline mr-0.5" />{locName(p.location_id)}</span>}
                        </div>
                        <p className="text-primary font-bold mt-2 text-sm">{p.has_variants && (p.variants || []).length > 0 ? `From ${fmt(Math.min(...(p.variants || []).map(v => v.price || Infinity)), p.currency || activeCurrency)}` : fmt(p.price, p.currency || activeCurrency)}</p>
                      </button>
                      </div>
                    ))}
                    {filteredProducts.length === 0 && <div className="col-span-3 text-center py-12 text-sm text-muted-foreground">No products found.</div>}
                  </div>
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
                ) : cart.map(item => {
                  const product = productsById[item.product_id] || null;
                  const lineCalc = calcLine(item, cart, product);
                  return (
                  <div key={_cartKey(item)} className="flex flex-col gap-1.5 p-2.5 rounded-lg bg-secondary/40 hover:bg-secondary/60 transition-colors">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium truncate">{item.name}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {fmt(item.unit_price, activeCurrency)} each
                          {item.units_per_pack > 1 && <span className="ml-1 opacity-70">· {item.units_per_pack} units/pack</span>}
                          {lineCalc.discount_pct > 0 && <span className="ml-1 px-1 rounded bg-green-100 text-green-700 font-semibold">-{lineCalc.discount_pct}%</span>}
                        </p>
                      </div>
                      <div className="flex items-center gap-1">
                        <button className="h-5 w-5 rounded bg-secondary flex items-center justify-center hover:bg-border" onClick={() => updateQty(item, -1)}><Minus size={10} /></button>
                        <span className="text-xs font-semibold w-5 text-center">{item.qty}</span>
                        <button className="h-5 w-5 rounded bg-secondary flex items-center justify-center hover:bg-border" onClick={() => updateQty(item, 1)}><Plus size={10} /></button>
                      </div>
                      <span className="text-xs font-bold text-primary min-w-[60px] text-right">{fmt(lineCalc.line_total, activeCurrency)}</span>
                      <button className="text-muted-foreground hover:text-destructive" onClick={() => removeFromCart(item)}><X size={12} /></button>
                    </div>
                    {item.packaging_cost > 0 && (
                      <label className="flex items-center gap-1.5 text-[10px] cursor-pointer pl-1" data-testid={`packaging-toggle-${_cartKey(item)}`}>
                        <input type="checkbox" className="accent-primary" checked={item.include_packaging !== false} onChange={() => togglePackaging(item)} />
                        <span>{item.packaging_label || 'Packaging'} (+{fmt(item.packaging_cost, activeCurrency)} × {item.qty})</span>
                        {item.include_packaging !== false && <span className="ml-auto text-muted-foreground">+{fmt(lineCalc.packaging_total, activeCurrency)}</span>}
                      </label>
                    )}
                    {canIssueProductBarcodes && (
                      <div className="flex items-center gap-1.5 text-[10px] pl-1">
                        <span className="text-muted-foreground">Override discount %</span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={item.manual_discount_pct || 0}
                          onChange={(e) => {
                            const pct = Math.min(100, Math.max(0, parseFloat(e.target.value) || 0));
                            setCart(prev => prev.map(i => _cartKey(i) === _cartKey(item) ? { ...i, manual_discount_pct: pct } : i));
                          }}
                          className="h-6 w-14 px-1 text-[10px] rounded border border-border bg-background text-center"
                          data-testid={`manual-discount-${_cartKey(item)}`}
                        />
                        {lineCalc.manual_pct > 0 && lineCalc.manual_pct > lineCalc.tier_pct && (
                          <span className="text-[9px] text-blue-600">cashier override</span>
                        )}
                        {lineCalc.tier_pct > 0 && lineCalc.discount_pct === lineCalc.tier_pct && (
                          <span className="text-[9px] text-green-600">tier {lineCalc.tier_pct}%</span>
                        )}
                      </div>
                    )}
                  </div>
                  );
                })}
              </div>
              {cart.length > 0 && (cartTotals.discount_total > 0 || cartTotals.packaging_total > 0) && (
                <div className="px-4 py-2 border-t border-border text-xs space-y-0.5 bg-muted/30">
                  <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span>{fmt(cartTotals.subtotal, activeCurrency)}</span></div>
                  {cartTotals.packaging_total > 0 && (
                    <div className="flex justify-between"><span className="text-muted-foreground">Packaging</span><span>+{fmt(cartTotals.packaging_total, activeCurrency)}</span></div>
                  )}
                  {cartTotals.discount_total > 0 && (
                    <div className="flex justify-between text-green-700"><span>Bulk discount</span><span>-{fmt(cartTotals.discount_total, activeCurrency)}</span></div>
                  )}
                </div>
              )}
              <div className="p-4 border-t border-border space-y-3 bg-card">
                <div className="space-y-2">
                  <div className="flex gap-1.5">
                    <Input placeholder="Customer name" value={customerName} onChange={e => { setCustomerName(e.target.value); if (selectedCustomerId) { setSelectedCustomerId(null); setActivePricelist(null); } }} className="text-sm h-8 flex-1" data-testid="customer-name-input" />
                    <Button size="sm" variant="outline" className="h-8 px-2 text-xs" data-testid="pos-pick-customer-btn" onClick={() => setShowPickCustomer(true)} title="Pick registered customer for pricelist">👤</Button>
                  </div>
                  {activePricelist && (
                    <div className="flex items-center justify-between gap-1.5 px-2 py-1 rounded bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/40 text-[10px]" data-testid="active-pricelist-banner">
                      <span className="text-emerald-700 dark:text-emerald-300">Pricelist: <strong>{activePricelist.name}</strong>{activePricelist.discount_pct ? ` · -${activePricelist.discount_pct}%` : ''}</span>
                      <button onClick={() => { setSelectedCustomerId(null); setActivePricelist(null); }} className="text-emerald-700 hover:text-emerald-900 text-xs">×</button>
                    </div>
                  )}
                  <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                    <SelectTrigger className="h-8 text-sm" data-testid="payment-method-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {getPaymentMethods().map(m => <SelectItem key={m} value={m}>{m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {/* Sale store is set by admin in Store Settings — not picked per-sale.
                      Show the bound store name + a small "change" button (admin/director only). */}
                  <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-border bg-muted/30 text-xs">
                    <MapPin size={12} className="text-muted-foreground shrink-0" />
                    <span className="flex-1 truncate" data-testid="pos-bound-store">{posBoundStoreLabel}</span>
                    {canIssueProductBarcodes && !isPosKiosk && (
                      <button type="button" onClick={() => openStoreSettings(saleLocationId || user?.location_id || '')} className="text-[10px] text-primary hover:underline" data-testid="pos-change-store-btn">change</button>
                    )}
                  </div>
                  {/* Receipt paper size — chosen before completing sale */}
                  <Select value={receiptPaperSize} onValueChange={setReceiptPaperSize}>
                    <SelectTrigger className="h-8 text-xs" data-testid="receipt-paper-size-pre"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">Auto-detect paper size</SelectItem>
                      <SelectItem value="58mm">58mm thermal</SelectItem>
                      <SelectItem value="80mm">80mm thermal</SelectItem>
                      <SelectItem value="A5">A5</SelectItem>
                      <SelectItem value="A4">A4</SelectItem>
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
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" className="flex-1 gap-1 text-xs" disabled={cart.length === 0} onClick={parkSale} data-testid="park-sale-btn">
                    Park Sale
                  </Button>
                  <Button variant="outline" size="sm" className="flex-1 gap-1 text-xs" onClick={() => setShowDrafts(true)} data-testid="open-parked-sales-btn">
                    Parked ({drafts.length})
                  </Button>
                </div>
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
                        {p.has_variants && (p.variants || []).length > 0 && (
                          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setBarcodePrintProduct(p)} data-testid="print-variant-barcodes-btn" title="Print variant barcodes"><Printer size={11} /></Button>
                        )}
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

        {/* INVOICES TAB */}
        <TabsContent value="invoices" className="mt-4">
          <InvoicesTab products={products} onConverted={() => fetchAll()} />
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
                      <th className="pb-2 font-medium text-muted-foreground">Status</th>
                      <th className="pb-2 font-medium text-muted-foreground">Location</th>
                      <th className="pb-2 font-medium text-muted-foreground">Date</th>
                      <th className="pb-2 font-medium text-muted-foreground">Cashier</th>
                      {isAdmin && <th className="pb-2 w-8"></th>}
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {sales.map(sale => {
                        const status = sale.payment_status || (sale.payment_method === 'cash' ? 'paid' : 'paid');
                        const isPending = status === 'pending';
                        return (
                        <tr key={sale.id} className={`hover:bg-accent/30 transition-colors ${isPending ? 'bg-amber-50/40 dark:bg-amber-950/10' : ''}`} data-testid="sale-row">
                          <td className="py-3 font-mono text-xs text-primary font-semibold">{sale.receipt_number || sale.id}</td>
                          <td className="py-3">{sale.customer_name || '--'}</td>
                          <td className="py-3 text-muted-foreground">{(sale.items || []).length} items</td>
                          <td className="py-3 font-bold text-primary">{fmt(sale.total)}</td>
                          <td className="py-3"><Badge variant="outline" className="text-xs capitalize">{sale.payment_method}</Badge></td>
                          <td className="py-3">
                            {isPending ? (
                              <Button size="sm" variant="outline" className="h-7 text-xs gap-1 border-amber-300 text-amber-700 hover:bg-amber-50" data-testid={`mark-paid-${sale.id}`} onClick={async (e) => {
                                e.stopPropagation();
                                const ref = window.prompt('Payment reference (transaction ID, optional):') || '';
                                try {
                                  await salesApi.setPaymentStatus(sale.id, 'paid', ref);
                                  setSales(prev => prev.map(s => s.id === sale.id ? { ...s, payment_status: 'paid', payment_reference: ref || s.payment_reference } : s));
                                  toast.success('Marked as paid');
                                } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                              }}>Mark as Paid</Button>
                            ) : (
                              <Badge className="bg-green-100 text-green-700 hover:bg-green-200 text-xs">Paid</Badge>
                            )}
                          </td>
                          <td className="py-3 text-xs text-muted-foreground">{sale.location_id ? locName(sale.location_id) : '--'}</td>
                          <td className="py-3 text-muted-foreground text-xs">{sale.created_at?.slice(0, 16).replace('T', ' ')}</td>
                          <td className="py-3 text-muted-foreground">{sale.cashier || '--'}</td>
                          {isAdmin && <td className="py-3 flex gap-1 flex-wrap">
                            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs gap-1" data-testid={`reprint-${sale.id}`} onClick={() => { setLastReceipt(sale); setLastStoreSettings(null); setShowReceipt(true); }} title="Reprint receipt">
                              <Receipt size={11} />
                            </Button>
                            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs gap-1 text-blue-600" data-testid={`edit-sale-${sale.id}`} onClick={() => setEditingSale(sale)} title="Edit (cashier / location)">
                              <Edit2 size={11} />
                            </Button>
                            {!isPending && (
                              <Button size="sm" variant="ghost" className="h-6 text-xs text-amber-600" data-testid={`mark-pending-${sale.id}`} onClick={async () => {
                                if (!await confirm({ title: 'Revert sale to pending?', message: 'Marks this sale as unpaid again.', confirmLabel: 'Revert' })) return;
                                try {
                                  await salesApi.setPaymentStatus(sale.id, 'pending');
                                  setSales(prev => prev.map(s => s.id === sale.id ? { ...s, payment_status: 'pending' } : s));
                                  toast.success('Reverted to pending');
                                } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
                              }}>↺</Button>
                            )}
                            <Button size="sm" variant="ghost" className="h-6 text-xs text-destructive" onClick={async () => { if (!await confirm({ title: 'Delete sale?', message: 'This removes the receipt and cannot be undone.', destructive: true, confirmLabel: 'Delete' })) return; try { await salesApi.delete(sale.id); setSales(prev => prev.filter(s => s.id !== sale.id)); toast.success('Sale deleted'); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } }} data-testid={`delete-sale-${sale.id}`}>Del</Button>
                          </td>}
                        </tr>);
                      })}
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
                      <th className="pb-2 font-medium text-muted-foreground"></th>
                    </tr></thead>
                    <tbody className="divide-y divide-border">
                      {customers.map((c, i) => (
                        <tr key={c.email || c.name || i} className="hover:bg-accent/30 transition-colors cursor-pointer" data-testid="customer-row" onClick={() => setCustomerProfile(c)}>
                          <td className="py-3 font-medium">{c.name}{c.phone && <span className="block text-[10px] text-muted-foreground">{c.phone}</span>}</td>
                          <td className="py-3 text-primary font-semibold">{fmt(c.total_spent)}</td>
                          <td className="py-3 text-muted-foreground">{c.transactions}</td>
                          <td className="py-3 text-muted-foreground text-xs">{c.last_purchase?.slice(0, 10)}</td>
                          <td className="py-3 text-xs text-primary">View →</td>
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
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
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
            {/* Variants Section */}
            <div className="border-t pt-3 space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-semibold">Variants</Label>
                <div className="flex items-center gap-3">
                  {editingProduct && (productForm.variants || []).length > 0 && (
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setBarcodePrintProduct({ ...editingProduct, ...productForm, price: Number(productForm.price) || 0 })} data-testid="print-variant-barcodes-dialog-btn">
                      <Printer size={12} /> Print barcodes
                    </Button>
                  )}
                  <label className="flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" className="accent-primary" checked={productForm.has_variants || false} onChange={e => setProductForm({...productForm, has_variants: e.target.checked, price: e.target.checked ? 0 : productForm.price})} /> Has variants</label>
                </div>
              </div>
              {productForm.has_variants && (
                <div className="space-y-2">
                  {(productForm.variants || []).map((v, i) => (
                    <div key={v.id || i} className="grid grid-cols-[1fr_70px_70px_1.5fr_24px] gap-2 items-center p-2 rounded bg-muted/50 text-xs">
                      <Input className="h-7 text-xs" value={v.name || ''} placeholder="Variant name"
                        onChange={e => setProductForm(prev => ({ ...prev, variants: prev.variants.map((x, j) => j === i ? { ...x, name: e.target.value, value: e.target.value } : x) }))} />
                      <Input className="h-7 text-xs" type="number" min={0} value={v.price || 0} placeholder="Price"
                        onChange={e => setProductForm(prev => ({ ...prev, variants: prev.variants.map((x, j) => j === i ? { ...x, price: parseFloat(e.target.value) || 0 } : x) }))}
                        data-testid={`variant-price-${i}`} />
                      <Input className="h-7 text-xs" type="number" min={0} value={v.stock || 0} placeholder="Qty"
                        onChange={e => setProductForm(prev => ({ ...prev, variants: prev.variants.map((x, j) => j === i ? { ...x, stock: parseInt(e.target.value) || 0 } : x) }))}
                        data-testid={`variant-qty-${i}`} />
                      {canIssueProductBarcodes ? (
                        <Input className="h-7 text-[10px] font-mono" value={v.barcode || ''} placeholder="Auto-generated on save"
                          onChange={e => setProductForm(prev => ({ ...prev, variants: prev.variants.map((x, j) => j === i ? { ...x, barcode: e.target.value, barcode_auto_generated: false } : x) }))}
                          data-testid={`variant-barcode-${i}`} />
                      ) : (
                        <span className="font-mono text-[10px] truncate" title={v.barcode}>{v.barcode || 'Pending'}</span>
                      )}
                      <button type="button" className="text-destructive text-sm" onClick={() => setProductForm(prev => ({...prev, variants: (prev.variants || []).filter((_, j) => j !== i)}))}>×</button>
                      {/* Pack & packaging row — collapsed by default */}
                      <details className="col-span-5 -mt-1">
                        <summary className="text-[10px] text-muted-foreground cursor-pointer">Pack size & packaging cost</summary>
                        <div className="grid grid-cols-3 gap-2 mt-1.5">
                          <div>
                            <Label className="text-[10px]">Units / pack</Label>
                            <Input className="h-7 text-xs" type="number" min={1} value={v.units_per_pack || 1}
                              onChange={e => setProductForm(prev => ({ ...prev, variants: prev.variants.map((x, j) => j === i ? { ...x, units_per_pack: parseInt(e.target.value) || 1 } : x) }))}
                              data-testid={`variant-units-per-pack-${i}`} />
                            <p className="text-[9px] text-muted-foreground">e.g. tray of 30 → 30</p>
                          </div>
                          <div>
                            <Label className="text-[10px]">Packaging cost</Label>
                            <Input className="h-7 text-xs" type="number" min={0} value={v.packaging_cost || 0}
                              onChange={e => setProductForm(prev => ({ ...prev, variants: prev.variants.map((x, j) => j === i ? { ...x, packaging_cost: parseFloat(e.target.value) || 0 } : x) }))}
                              data-testid={`variant-packaging-cost-${i}`} />
                            <p className="text-[9px] text-muted-foreground">added if buyer doesn't bring own</p>
                          </div>
                          <div>
                            <Label className="text-[10px]">Packaging label</Label>
                            <Input className="h-7 text-xs" value={v.packaging_label || ''} placeholder="e.g. Plastic tray"
                              onChange={e => setProductForm(prev => ({ ...prev, variants: prev.variants.map((x, j) => j === i ? { ...x, packaging_label: e.target.value } : x) }))} />
                          </div>
                        </div>
                      </details>
                    </div>
                  ))}
                  <div className="grid grid-cols-[1fr_70px_70px_1.5fr_60px] gap-1">
                    <Input className="h-7 text-xs" placeholder="Name (e.g. Large)" id="_vname" />
                    <Input className="h-7 text-xs" type="number" placeholder="Price" id="_vprice" />
                    <Input className="h-7 text-xs" type="number" placeholder="Qty" id="_vqty" />
                    <Input className="h-7 text-[10px] font-mono" placeholder={canIssueProductBarcodes ? 'Barcode (optional)' : 'auto'} id="_vbarcode" disabled={!canIssueProductBarcodes} />
                    <Button type="button" size="sm" className="h-7 text-xs" onClick={() => {
                      const n = document.getElementById('_vname')?.value;
                      const p = parseFloat(document.getElementById('_vprice')?.value) || 0;
                      const q = parseInt(document.getElementById('_vqty')?.value) || 0;
                      const b = canIssueProductBarcodes ? (document.getElementById('_vbarcode')?.value || '').trim() : '';
                      if (!n) return;
                      setProductForm(prev => ({...prev, variants: [...(prev.variants || []), {id: `var_${Date.now()}`, name: n, value: n, price: p, stock: q, barcode: b, barcode_auto_generated: !b, units_per_pack: 1, packaging_cost: 0, packaging_label: ''}]}));
                      ['_vname','_vprice','_vqty','_vbarcode'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
                    }}>+ Add</Button>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Total stock = sum of (variant qty × units/pack). Empty barcodes auto-generate as <span className="font-mono">5812-{`{COUNTRY}{ABBR}-{DDMMYY}-V{NN}-{NNNN}`}</span> on save.
                    {!canIssueProductBarcodes && <span className="block text-amber-700">Only admins, directors, and managers can edit barcodes manually.</span>}
                  </p>
                </div>
              )}
            </div>
            {/* Bulk discount tiers */}
            {productForm.has_variants && (
              <div className="border-t pt-3 space-y-2">
                <Label className="text-sm font-semibold">Bulk Discount Tiers (optional)</Label>
                <p className="text-[10px] text-muted-foreground">Auto-applied at POS based on total quantity of this product. Capped at the max %.</p>
                {(productForm.qty_discount_tiers || []).map((t, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1fr_24px] gap-2 items-center">
                    <div>
                      <Label className="text-[10px]">Min qty</Label>
                      <Input className="h-7 text-xs" type="number" min={1} value={t.min_qty || 0}
                        onChange={e => setProductForm(prev => ({ ...prev, qty_discount_tiers: (prev.qty_discount_tiers || []).map((x, j) => j === i ? { ...x, min_qty: parseInt(e.target.value) || 0 } : x) }))}
                        data-testid={`tier-min-qty-${i}`} />
                    </div>
                    <div>
                      <Label className="text-[10px]">Discount %</Label>
                      <Input className="h-7 text-xs" type="number" min={0} max={100} value={t.discount_pct || 0}
                        onChange={e => setProductForm(prev => ({ ...prev, qty_discount_tiers: (prev.qty_discount_tiers || []).map((x, j) => j === i ? { ...x, discount_pct: parseFloat(e.target.value) || 0 } : x) }))}
                        data-testid={`tier-discount-pct-${i}`} />
                    </div>
                    <button type="button" className="text-destructive self-end text-sm h-7" onClick={() => setProductForm(prev => ({ ...prev, qty_discount_tiers: (prev.qty_discount_tiers || []).filter((_, j) => j !== i) }))}>×</button>
                  </div>
                ))}
                <div className="flex gap-2 items-end">
                  <Button type="button" size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setProductForm(prev => ({ ...prev, qty_discount_tiers: [...(prev.qty_discount_tiers || []), { min_qty: 5, discount_pct: 5 }] }))} data-testid="add-tier-btn">
                    <Plus size={11} /> Add tier
                  </Button>
                  <div className="ml-auto flex items-center gap-2">
                    <Label className="text-[10px]">Max discount %</Label>
                    <Input className="h-7 text-xs w-20" type="number" min={0} max={100} value={productForm.max_discount_pct ?? 20}
                      onChange={e => setProductForm({ ...productForm, max_discount_pct: parseFloat(e.target.value) || 0 })}
                      data-testid="max-discount-pct-input" />
                  </div>
                </div>
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setShowProductModal(false)}>Cancel</Button>
              <Button type="submit" className="flex-1" disabled={saving} data-testid="save-product-btn">{saving ? 'Saving...' : editingProduct ? 'Update' : 'Add Product'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Receipt Modal */}
      <Dialog open={showReceipt} onOpenChange={setShowReceipt}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Receipt size={16} /> Receipt {lastReceipt?.receipt_number || ''}</DialogTitle></DialogHeader>
          {lastReceipt && <ReceiptComponent sale={lastReceipt} storeSettings={lastStoreSettings || storeSettings || {}} />}
          {/* 60-second Undo button — quick revert of an oops sale */}
          {lastReceipt && !lastReceipt.voided && (() => {
            const created = new Date(lastReceipt.created_at).getTime();
            const ageS = (Date.now() - created) / 1000;
            return ageS <= 60 ? (
              <Button variant="outline" className="w-full mt-2 border-amber-300 text-amber-700 hover:bg-amber-50 gap-1.5" data-testid="undo-sale-btn" onClick={async () => {
                if (!await confirm({ title: 'Void last sale?', message: 'Restore stock and remove this receipt. Cannot be undone after 60s.', destructive: true, confirmLabel: 'Void' })) return;
                try {
                  await salesApi.undo(lastReceipt.id);
                  setLastReceipt({ ...lastReceipt, voided: true });
                  setSales(prev => prev.map(s => s.id === lastReceipt.id ? { ...s, voided: true } : s));
                  toast.success('Sale voided — stock restored');
                  setShowReceipt(false);
                  fetchAll();
                } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>↶ Undo this sale ({Math.max(0, Math.ceil(60 - ageS))}s left)</Button>
            ) : null;
          })()}
        </DialogContent>
      </Dialog>

      {/* Store Settings Modal */}
      <Dialog open={showStoreSettings} onOpenChange={setShowStoreSettings}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center justify-between gap-2"><span className="flex items-center gap-2"><Settings size={16} /> Store Settings</span>
            <div className="flex gap-2 text-xs flex-wrap">
              <Link to="/pos-setup" className="text-primary hover:underline" data-testid="pos-setup-link">POS Kiosk Setup →</Link>
              <Link to="/accounts-receivable" className="text-primary hover:underline" data-testid="ar-link">Accounts Receivable →</Link>
              <Link to="/customer-statements" className="text-primary hover:underline" data-testid="statements-link">Statements →</Link>
              <Link to="/reconciliation" className="text-primary hover:underline" data-testid="reconciliation-link">Reconciliation →</Link>
              <Link to="/barcode-reissue" className="text-primary hover:underline" data-testid="reissue-link">Re-issue Barcodes →</Link>
            </div>
          </DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2 pb-2 border-b border-border">
              <Label>Configuring store</Label>
              <Select value={storeSettingsLoc || ''} onValueChange={async (v) => {
                setStoreSettingsLoc(v);
                try {
                  const res = await storeSettingsApi.get(v);
                  setStoreSettings(res.data || {});
                } catch { setStoreSettings({}); }
              }}>
                <SelectTrigger data-testid="store-settings-location-select"><SelectValue placeholder="Pick a campus or sub-location" /></SelectTrigger>
                <SelectContent>
                  {locations.filter(l => l.marketplace_enabled !== false).map(l => <SelectItem key={l.id} value={l.id}>{l.type === 'sub-location' ? `   ↳ ${l.name}` : l.name}{l.country ? ` (${l.country})` : ''}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-muted-foreground">Each campus or sub-location has its own store settings. The receipt header uses the store name set here for the sale's location.</p>
            </div>
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
            <div className="grid grid-cols-2 gap-3 p-3 bg-muted/30 rounded-lg">
              <div className="space-y-2"><Label className="text-xs">Receipt Paper Size</Label>
                <Select value={storeSettings.receipt_paper_size || '80mm'} onValueChange={v => setStoreSettings({...storeSettings, receipt_paper_size: v})}>
                  <SelectTrigger data-testid="receipt-paper-size-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="58mm">58mm (Thermal POS)</SelectItem>
                    <SelectItem value="80mm">80mm (Standard POS)</SelectItem>
                    <SelectItem value="A5">A5 (Half-letter)</SelectItem>
                    <SelectItem value="A4">A4 (Full page)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">Auto-detected printer size override</p>
              </div>
              <div className="space-y-2 pt-1">
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input type="checkbox" checked={storeSettings.receipt_show_logo !== false} onChange={e => setStoreSettings({...storeSettings, receipt_show_logo: e.target.checked})} />
                  Show 58:12 logo
                </label>
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input type="checkbox" checked={storeSettings.receipt_show_qr !== false} onChange={e => setStoreSettings({...storeSettings, receipt_show_qr: e.target.checked})} />
                  Show tracking QR code
                </label>
              </div>
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
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
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

      {/* Variant Barcode Print Dialog */}
      <VariantBarcodePrint
        open={!!barcodePrintProduct}
        onOpenChange={(open) => { if (!open) setBarcodePrintProduct(null); }}
        product={barcodePrintProduct}
        currency={barcodePrintProduct?.currency || 'UGX'}
      />

      {/* POS Barcode Scan Dialog */}
      <BarcodeScanDialog
        open={scanOpen}
        onOpenChange={setScanOpen}
        onScan={handleBarcodeScan}
        title="Scan product barcode"
      />

      {/* Change Calculator (cash sales) */}
      <ChangeCalculator
        open={changeOpen}
        onOpenChange={setChangeOpen}
        total={cartTotals.total}
        currency={activeCurrency2 || activeCurrency}
        onAccept={(cashInfo) => actuallyCheckout(cashInfo)}
      />

      {/* Open Shift Dialog */}
      <Dialog open={openShiftDlg} onOpenChange={setOpenShiftDlg}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Open Shift</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Count the cash in the drawer right now and enter the starting amount. This becomes your shift's "opening cash".</p>
            <div className="space-y-1">
              <Label className="text-xs">Opening cash ({activeCurrency2 || 'UGX'})</Label>
              <Input type="number" min={0} value={shiftForm.opening_cash} onChange={e => setShiftForm({...shiftForm, opening_cash: e.target.value})} className="h-12 text-xl text-center" autoFocus data-testid="open-shift-cash" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notes (optional)</Label>
              <Input value={shiftForm.notes} onChange={e => setShiftForm({...shiftForm, notes: e.target.value})} placeholder="e.g. morning shift" />
            </div>
            <div className="flex gap-2 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setOpenShiftDlg(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="open-shift-save" disabled={!shiftForm.opening_cash} onClick={async () => {
                try {
                  const res = await shiftsApi.open({ opening_cash: parseFloat(shiftForm.opening_cash), location_id: saleLocationId, currency: activeCurrency2 || 'UGX', notes: shiftForm.notes });
                  setCurrentShift(res.data);
                  toast.success('Shift opened');
                  setOpenShiftDlg(false);
                } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>Open Shift</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Close Shift Dialog */}
      <Dialog open={closeShiftDlg} onOpenChange={(o) => { if (!o) { setCloseShiftDlg(false); setShiftResult(null); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{shiftResult ? 'Shift Closed' : 'Close Shift'}</DialogTitle></DialogHeader>
          {!shiftResult ? (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Count the cash in the drawer NOW and enter the closing total. We'll compare to expected cash + report any variance.</p>
              <div className="space-y-1">
                <Label className="text-xs">Closing cash ({currentShift?.currency || activeCurrency2 || 'UGX'})</Label>
                <Input type="number" min={0} value={shiftForm.closing_cash} onChange={e => setShiftForm({...shiftForm, closing_cash: e.target.value})} className="h-12 text-xl text-center" autoFocus data-testid="close-shift-cash" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Variance notes (optional)</Label>
                <Input value={shiftForm.notes} onChange={e => setShiftForm({...shiftForm, notes: e.target.value})} placeholder="e.g. customer overpaid, kept tip" />
              </div>
              <div className="flex gap-2 pt-1">
                <Button variant="outline" className="flex-1" onClick={() => setCloseShiftDlg(false)}>Cancel</Button>
                <Button className="flex-1" data-testid="close-shift-save" disabled={!shiftForm.closing_cash || !currentShift} onClick={async () => {
                  try {
                    const res = await shiftsApi.close(currentShift.id, { closing_cash: parseFloat(shiftForm.closing_cash), variance_notes: shiftForm.notes });
                    setShiftResult(res.data);
                  } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
                }}>Close Shift</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3" data-testid="shift-variance-report">
              <div className="space-y-1.5 text-sm bg-muted/30 rounded-lg p-3">
                <div className="flex justify-between"><span className="text-muted-foreground">Opening cash</span><span>{shiftResult.opening_cash?.toLocaleString()}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">+ Cash sales ({shiftResult.cash_sales_count})</span><span>+{shiftResult.cash_sales_total?.toLocaleString()}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">− Cash drops</span><span>-{shiftResult.cash_drops_total?.toLocaleString()}</span></div>
                <div className="flex justify-between border-t pt-1.5 font-semibold"><span>Expected cash</span><span>{shiftResult.expected_cash?.toLocaleString()}</span></div>
                <div className="flex justify-between"><span>Counted cash</span><span>{shiftResult.closing_cash?.toLocaleString()}</span></div>
                <div className={`flex justify-between border-t pt-1.5 font-bold text-base ${Math.abs(shiftResult.variance) < 1 ? 'text-green-700' : shiftResult.variance > 0 ? 'text-amber-700' : 'text-red-700'}`}>
                  <span>Variance</span>
                  <span>{shiftResult.variance > 0 ? '+' : ''}{shiftResult.variance?.toLocaleString()}</span>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">{Math.abs(shiftResult.variance) < 1 ? '✓ Balanced — no discrepancy' : shiftResult.variance > 0 ? '↑ Over: drawer has more than expected' : '↓ Short: missing cash'}</p>
              <Button className="w-full" onClick={() => { setCurrentShift(null); setShiftResult(null); setCloseShiftDlg(false); }}>Done</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Cash Drop dialog */}
      <Dialog open={cashDropOpen} onOpenChange={setCashDropOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Drop Cash to Safe / Bank</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Records a transfer of cash out of this POS drawer (e.g. to the safe, the bank, or a finance account).</p>
            <div className="space-y-1">
              <Label className="text-xs">Amount</Label>
              <Input type="number" min={0} value={cashDropForm.amount} onChange={e => setCashDropForm({...cashDropForm, amount: e.target.value})} className="h-12 text-xl text-center" data-testid="cash-drop-amount" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Destination</Label>
              <Select value={cashDropForm.destination} onValueChange={v => setCashDropForm({...cashDropForm, destination: v})}>
                <SelectTrigger data-testid="cash-drop-destination"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="safe">On-site Safe</SelectItem>
                  <SelectItem value="bank">Bank Deposit</SelectItem>
                  <SelectItem value="finance">Central Finance Account</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notes (optional)</Label>
              <Input placeholder="e.g. Slip #1234, deposited Mon 9am" value={cashDropForm.notes} onChange={e => setCashDropForm({...cashDropForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-2 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setCashDropOpen(false)}>Cancel</Button>
              <Button className="flex-1" data-testid="cash-drop-save" disabled={!cashDropForm.amount} onClick={async () => {
                try {
                  await cashDropsApi.create({
                    amount: parseFloat(cashDropForm.amount),
                    currency: activeCurrency2 || activeCurrency,
                    location_id: saleLocationId,
                    destination: cashDropForm.destination,
                    notes: cashDropForm.notes,
                  });
                  toast.success(`Recorded cash drop: ${activeCurrency2} ${cashDropForm.amount}`);
                  setCashDropOpen(false);
                  setCashDropForm({ amount: '', destination: 'safe', destination_account_id: '', notes: '' });
                } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>Record</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      <VariantPickerDialog
        product={variantPickerProduct}
        open={!!variantPickerProduct}
        onOpenChange={(o) => { if (!o) setVariantPickerProduct(null); }}
        onPick={(variant) => addToCart(variantPickerProduct, variant)}
        currency={variantPickerProduct?.currency || activeCurrency}
      />

      {/* Edit Completed Sale (admin/director) */}
      <Dialog open={!!editingSale} onOpenChange={(o) => { if (!o) setEditingSale(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit Sale {editingSale?.receipt_number || editingSale?.id}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Director / admin only — edits are audit-logged.</p>
            <div className="space-y-1.5">
              <Label className="text-xs">Salesperson / Cashier</Label>
              <Input value={editSaleForm.cashier} onChange={e => setEditSaleForm({ ...editSaleForm, cashier: e.target.value })} data-testid="edit-sale-cashier" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Sale Location / Store</Label>
              <Select value={editSaleForm.location_id || ''} onValueChange={v => setEditSaleForm({ ...editSaleForm, location_id: v })}>
                <SelectTrigger data-testid="edit-sale-location"><SelectValue placeholder="Select store" /></SelectTrigger>
                <SelectContent>
                  {locations.filter(l => l.marketplace_enabled !== false).map(l => <SelectItem key={l.id} value={l.id}>{l.name}{l.country ? ` (${l.country})` : ''}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Customer Name</Label>
              <Input value={editSaleForm.customer_name} onChange={e => setEditSaleForm({ ...editSaleForm, customer_name: e.target.value })} />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setEditingSale(null)}>Cancel</Button>
              <Button className="flex-1" data-testid="edit-sale-save" onClick={async () => {
                try {
                  const res = await salesApi.update(editingSale.id, editSaleForm);
                  setSales(prev => prev.map(s => s.id === editingSale.id ? res.data : s));
                  toast.success('Sale updated');
                  setEditingSale(null);
                } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
              }}>Save Changes</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Parked Sales Dialog */}
      <Dialog open={showDrafts} onOpenChange={setShowDrafts}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Parked Sales</DialogTitle></DialogHeader>
          {drafts.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">No parked sales</p>
          ) : (
            <div className="space-y-2">
              {drafts.map(d => (
                <div key={d.id} className="flex items-center justify-between p-3 rounded-lg border border-border" data-testid={`draft-${d.id}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{d.customer_name || 'Walk-in'}</p>
                    <p className="text-xs text-muted-foreground">{(d.items || []).length} items · {fmt(d.total, activeCurrency)} · by {d.parked_by_name || 'Unknown'}</p>
                    <p className="text-[10px] text-muted-foreground">{new Date(d.created_at).toLocaleString()}</p>
                  </div>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => reopenDraft(d)} data-testid={`reopen-draft-${d.id}`}>Reopen</Button>
                    <Button size="sm" variant="ghost" className="h-7 text-destructive" onClick={() => discardDraft(d.id)}><Trash2 size={13} /></Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Customer Profile Drawer with Receipt History */}
      <Dialog open={!!customerProfile} onOpenChange={(open) => { if (!open) setCustomerProfile(null); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="customer-profile-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">{customerProfile?.name}</DialogTitle>
          </DialogHeader>
          {customerProfile && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-primary/5 rounded-lg p-3 text-center">
                  <p className="text-xs text-muted-foreground">Total Spent</p>
                  <p className="text-lg font-bold text-primary">{fmt(customerProfile.total_spent, activeCurrency)}</p>
                </div>
                <div className="bg-secondary/40 rounded-lg p-3 text-center">
                  <p className="text-xs text-muted-foreground">Transactions</p>
                  <p className="text-lg font-bold">{customerProfile.transactions}</p>
                </div>
                <div className="bg-secondary/40 rounded-lg p-3 text-center">
                  <p className="text-xs text-muted-foreground">Last Visit</p>
                  <p className="text-sm font-bold">{customerProfile.last_purchase?.slice(0, 10) || '—'}</p>
                </div>
              </div>
              {customerProfile.phone && (
                <p className="text-xs text-muted-foreground">📞 {customerProfile.phone}</p>
              )}
              <div>
                <p className="text-sm font-semibold mb-2">Receipt History</p>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {customerProfile.receipts.sort((a, b) => (b.date || '').localeCompare(a.date || '')).map((r, i) => (
                    <div key={r.receipt_number || i} className="flex items-center justify-between p-2.5 rounded-lg border border-border hover:bg-accent/30" data-testid={`customer-receipt-${i}`}>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-mono font-medium">{r.receipt_number}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {r.date?.slice(0, 16).replace('T', ' ')} · {r.cashier} · {r.items_count} item{r.items_count === 1 ? '' : 's'} · <span className="capitalize">{r.payment_method}</span>
                          {r.payment_status === 'pending' && <span className="ml-1 text-amber-600 font-semibold">· UNPAID</span>}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-primary">{fmt(r.total, activeCurrency)}</span>
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => { window.open(`/receipt/${encodeURIComponent(r.receipt_number)}`, '_blank'); }} title="View receipt">
                          View
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {customerProfile.id && (
                <div className="pt-2 border-t">
                  <ActivityFeed subjectKind="customer" subjectId={customerProfile.id} showAddNote={true} showDownload={true} />
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Pick Registered Customer (Pricelist) Dialog */}
      <Dialog open={showPickCustomer} onOpenChange={(o) => { setShowPickCustomer(o); if (!o) { setPickCustQuery(''); setPickCustResults([]); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Pick Registered Customer</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs text-muted-foreground">Pick a registered customer to apply their pricelist & track loyalty.</p>
            <Input
              placeholder="Search by name, phone, or email..."
              value={pickCustQuery}
              autoFocus
              data-testid="pos-pick-customer-search"
              onChange={async e => {
                const q = e.target.value;
                setPickCustQuery(q);
                if (q.trim().length < 2) { setPickCustResults([]); return; }
                try {
                  const r = await api.get('/customers', { params: { search: q } });
                  setPickCustResults((r.data || []).slice(0, 12));
                } catch { /* ignore */ }
              }}
            />
            <div className="max-h-72 overflow-y-auto space-y-1">
              {pickCustResults.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">{pickCustQuery.length < 2 ? 'Start typing to search...' : 'No matches'}</p>
              ) : pickCustResults.map(c => (
                <button
                  key={c.id}
                  type="button"
                  data-testid={`pos-pick-customer-${c.id}`}
                  className="w-full text-left p-2 rounded-md border border-border hover:border-primary hover:bg-muted/50 transition"
                  onClick={async () => {
                    setSelectedCustomerId(c.id);
                    setCustomerName(c.name || 'Customer');
                    // Try to resolve their pricelist (resolve against a dummy product to detect blanket discount)
                    try {
                      const plList = await api.get('/pricelists');
                      const pl = (plList.data || []).find(p => (p.customer_ids || []).includes(c.id) || p.customer_id === c.id);
                      if (pl && (pl.discount_pct || (pl.product_prices || []).length)) {
                        setActivePricelist({ id: pl.id, name: pl.name, discount_pct: pl.discount_pct });
                        toast.success(`Pricelist: ${pl.name}${pl.discount_pct ? ` (-${pl.discount_pct}%)` : ''}`);
                      } else {
                        setActivePricelist(null);
                      }
                    } catch { /* ignore */ }
                    setShowPickCustomer(false);
                    setPickCustQuery(''); setPickCustResults([]);
                  }}
                >
                  <p className="text-sm font-medium">{c.name}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {c.phone || ''} {c.email ? ` · ${c.email}` : ''}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>
      <ConfirmDialog />
    </div>
  );
}

// ============== PERIPHERAL DIAGNOSTICS ==============
function PeripheralDiagnostics() {
  const [open, setOpen] = useState(false);
  const info = describePeripheralSupport();
  const totalSupported = info.supported.length;
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="h-8 text-xs gap-1"
        onClick={() => setOpen(true)}
        data-testid="peripheral-diagnostics-btn"
        title="Show which POS peripherals work in this browser"
      >
        <span className={`w-1.5 h-1.5 rounded-full ${totalSupported >= 3 ? 'bg-emerald-500' : 'bg-amber-500'}`} />
        Peripherals ({totalSupported})
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid="peripheral-diagnostics-dialog">
          <DialogHeader>
            <DialogTitle>Peripheral Support</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2 text-xs">
            <p className="text-muted-foreground">What works on this browser ({info.isMobile ? (info.isAndroid ? 'Android' : 'iOS / mobile') : 'desktop'})</p>
            <div>
              <p className="font-semibold text-emerald-700 uppercase text-[10px] mb-1">✓ Supported ({info.supported.length})</p>
              <ul className="space-y-1">
                {info.supported.map((s, i) => <li key={i} className="flex items-start gap-1.5"><span className="text-emerald-600 mt-0.5">●</span><span>{s}</span></li>)}
              </ul>
            </div>
            {info.unsupported.length > 0 && (
              <div>
                <p className="font-semibold text-muted-foreground uppercase text-[10px] mb-1">✗ Not in this browser</p>
                <ul className="space-y-1">
                  {info.unsupported.map((s, i) => <li key={i} className="flex items-start gap-1.5 text-muted-foreground"><span className="mt-0.5">○</span><span>{s}</span></li>)}
                </ul>
              </div>
            )}
            <div className="text-[10px] text-muted-foreground border-t pt-2">
              <strong>Tip:</strong> USB barcode scanners that emulate keyboards work in EVERY browser — just plug them in and scan; the POS auto-captures rapid keystrokes ending in Enter, regardless of operating system.
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

