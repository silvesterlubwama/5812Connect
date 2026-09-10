import React, { useRef, useState } from 'react';
import { ImagePlus, Trash2, Loader2 } from 'lucide-react';
import { Button } from './ui/button';
import api from '../services/api';
import { toast } from 'sonner';

/** Photo gallery for a product. Upload needs an existing product id, so for a
 *  brand-new product we say so rather than silently dropping the files. */
export const ProductGalleryEditor = ({ productId, images = [], onChange }) => {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const upload = async (files) => {
    if (!productId) return;
    setBusy(true);
    try {
      let latest = images;
      for (const file of Array.from(files).slice(0, 8)) {
        const fd = new FormData();
        fd.append('file', file);
        const res = await api.post(`/products/${productId}/images`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        latest = res.data.images || latest;
      }
      onChange(latest);
      toast.success('Photo added');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const remove = async (url) => {
    setBusy(true);
    try {
      const res = await api.delete(`/products/${productId}/images`, { params: { url } });
      onChange(res.data.images || []);
    } catch {
      toast.error('Could not remove that photo');
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-2" data-testid="product-gallery-editor">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Photos <span className="text-xs font-normal text-muted-foreground">(first one is the shop cover)</span></p>
        <Button
          type="button" size="sm" variant="outline" className="h-7 text-xs"
          disabled={!productId || busy || images.length >= 8}
          onClick={() => inputRef.current?.click()}
          data-testid="product-image-add-btn"
        >
          {busy ? <Loader2 size={12} className="mr-1 animate-spin" /> : <ImagePlus size={12} className="mr-1" />}
          Add photo
        </Button>
      </div>
      <input
        ref={inputRef} type="file" accept="image/*" multiple hidden
        onChange={e => e.target.files?.length && upload(e.target.files)}
        data-testid="product-image-input"
      />
      {!productId ? (
        <p className="text-xs text-muted-foreground">Save the product first, then add its photos.</p>
      ) : images.length === 0 ? (
        <p className="text-xs text-muted-foreground">No photos yet — online shoppers see a placeholder until you add one.</p>
      ) : (
        <div className="grid grid-cols-4 gap-2">
          {images.map((url, i) => (
            <div key={url} className="relative group aspect-square rounded-md overflow-hidden border border-border" data-testid={`product-image-${i}`}>
              <img src={url} alt={`Product photo ${i + 1}`} className="w-full h-full object-cover" />
              {i === 0 && <span className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[9px] text-center py-0.5">Cover</span>}
              <button
                type="button" onClick={() => remove(url)} disabled={busy}
                className="absolute top-1 right-1 p-1 rounded bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                data-testid={`product-image-delete-${i}`}
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ProductGalleryEditor;
