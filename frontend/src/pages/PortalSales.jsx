import React, { useState, useEffect } from 'react';
import { ShoppingBag, DollarSign } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { portalApi } from '../services/api';
import { toast } from 'sonner';

export default function PortalSales() {
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    portalApi.sales()
      .then(res => setSales(res.data))
      .catch(() => toast.error('Failed to load sales'))
      .finally(() => setLoading(false));
  }, []);

  const totalRevenue = sales.reduce((s, sale) => s + (sale.total || 0), 0);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6 max-w-4xl" data-testid="portal-sales">
      <div>
        <h1 className="text-2xl font-bold font-heading">My Sales</h1>
        <p className="text-sm text-muted-foreground mt-1">{sales.length} sales recorded</p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5 flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-green-500"><DollarSign size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Total Revenue</p>
              <p className="text-lg font-bold">{totalRevenue.toLocaleString()} UGX</p>
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-soft rounded-xl">
          <CardContent className="p-5 flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-blue-500"><ShoppingBag size={18} className="text-white" /></div>
            <div>
              <p className="text-xs text-muted-foreground">Total Sales</p>
              <p className="text-lg font-bold">{sales.length}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Sales List */}
      <Card className="shadow-soft rounded-xl">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Sales History</CardTitle>
        </CardHeader>
        <CardContent>
          {sales.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <ShoppingBag size={40} className="mx-auto mb-3 opacity-30" />
              <p>No sales recorded yet</p>
            </div>
          ) : (
            <div className="divide-y">
              {sales.map(sale => (
                <div key={sale.id} className="flex items-center justify-between py-3" data-testid={`sale-${sale.id}`}>
                  <div>
                    <p className="text-sm font-medium">{sale.customer_name || 'Walk-in'}</p>
                    <p className="text-xs text-muted-foreground">{sale.date || sale.created_at?.split('T')[0]} — {(sale.items || []).length} items</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold">{(sale.total || 0).toLocaleString()} {sale.currency || 'UGX'}</span>
                    <Badge variant="outline" className="text-xs">{sale.payment_method || 'cash'}</Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
