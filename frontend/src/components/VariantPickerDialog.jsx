import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Package } from 'lucide-react';

const fmt = (n, c = 'UGX') => `${c} ${(Number(n) || 0).toLocaleString()}`;

/**
 * VariantPickerDialog — opens when a product with variants is clicked on POS.
 * User picks which variant (size/pack) to add to cart.
 */
export default function VariantPickerDialog({ product, open, onOpenChange, onPick, currency = 'UGX' }) {
  if (!product) return null;
  const variants = product.variants || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package size={16} /> Pick variant — {product.name}
          </DialogTitle>
        </DialogHeader>
        {variants.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">No variants configured.</p>
        ) : (
          <div className="space-y-2" data-testid="variant-picker-list">
            {variants.map((v) => {
              const stock = Number(v.stock || 0);
              const outOfStock = stock <= 0;
              return (
                <button
                  key={v.id}
                  type="button"
                  disabled={outOfStock}
                  onClick={() => { onPick(v); onOpenChange(false); }}
                  data-testid={`variant-pick-${v.id}`}
                  className={`w-full text-left p-3 rounded-lg border transition-all ${outOfStock ? 'opacity-50 cursor-not-allowed border-border' : 'cursor-pointer border-border hover:border-primary hover:bg-primary/5'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm">{v.name || v.value}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {v.units_per_pack > 1 && <span className="mr-2">{v.units_per_pack} units/pack</span>}
                        {v.packaging_cost > 0 && <span className="mr-2">+{fmt(v.packaging_cost, currency)} pkg</span>}
                        <span className={outOfStock ? 'text-destructive' : 'text-muted-foreground'}>
                          {outOfStock ? 'Out of stock' : `${stock} in stock`}
                        </span>
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-primary">{fmt(v.price, currency)}</p>
                      {v.barcode && <p className="text-[10px] font-mono text-muted-foreground truncate max-w-[120px]" title={v.barcode}>{v.barcode}</p>}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
        <div className="flex justify-end pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
