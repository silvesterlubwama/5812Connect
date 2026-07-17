/**
 * ShipmentPackingPanel (iter223)
 *
 * Adds mode-aware UI to a shipment:
 *   - Container mode: polymorphic packing units (pallet/box/tote/crate)
 *     with 2D top-down floor plan, stacking parents, and per-unit editing.
 *   - Airport mode: passengers + suitcases (incl. bag-tag tracking #), with
 *     over-limit warnings.
 *   - AI tracking button that surfaces Gemini's status estimate + direct
 *     carrier tracking URLs.
 *
 * Designed as a drop-in section inside ShipmentsAdminPage.jsx (see mount).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Plus, Trash2, Pencil, Plane, Ship, Sparkles, PackageOpen, Loader2, ExternalLink } from 'lucide-react';
import api from '../../services/api';

const CONTAINER_LENGTH_CM = 1203;
const CONTAINER_WIDTH_CM = 235;

const UNIT_COLORS = {
  pallet: '#8b5cf6',
  box: '#f59e0b',
  tote: '#06b6d4',
  crate: '#84cc16',
  suitcase: '#334155',
  carry_on: '#6366f1',
  duffel: '#ec4899',
};

export function ShipmentPackingPanel({ shipment, refresh }) {
  const [presets, setPresets] = useState({});
  const [addingUnit, setAddingUnit] = useState(false);
  const [editingUnit, setEditingUnit] = useState(null);
  const [addingPassenger, setAddingPassenger] = useState(false);
  const [addingSuitcase, setAddingSuitcase] = useState(null); // passenger_id
  const [editingSuitcase, setEditingSuitcase] = useState(null);
  const [tracking, setTracking] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);

  useEffect(() => {
    api.get('/shipments/presets/packing-units').then(r => setPresets(r.data || {})).catch(() => {});
  }, []);

  const mode = shipment?.mode || 'container';
  const sid = shipment?.id;

  const setMode = async (m) => {
    try {
      await api.put(`/shipments/${sid}`, { mode: m });
      toast.success(`Mode set to ${m}`);
      refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const saveWaybill = async (fields) => {
    try {
      await api.put(`/shipments/${sid}`, fields);
      toast.success('Waybill updated');
      refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const runAiTrack = async () => {
    setAiBusy(true);
    try {
      const r = await api.post(`/shipments/${sid}/ai-tracking`);
      setTracking(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Tracking failed'); }
    finally { setAiBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="ship-packing-panel">
      {/* Mode picker + waybill */}
      <ModeAndTrackingHeader shipment={shipment} mode={mode} setMode={setMode} saveWaybill={saveWaybill}
                             onAiTrack={runAiTrack} aiBusy={aiBusy} />

      {/* Container OR Airport panel */}
      {mode === 'container' ? (
        <ContainerModePanel
          shipment={shipment}
          presets={presets}
          onAdd={() => setAddingUnit(true)}
          onEdit={setEditingUnit}
          refresh={refresh}
        />
      ) : (
        <AirportModePanel
          shipment={shipment}
          presets={presets}
          onAddPassenger={() => setAddingPassenger(true)}
          onAddSuitcase={setAddingSuitcase}
          onEditSuitcase={setEditingSuitcase}
          refresh={refresh}
        />
      )}

      {/* Dialogs */}
      {addingUnit && (
        <PackingUnitDialog sid={sid} presets={presets} shipment={shipment} onClose={() => setAddingUnit(false)}
                           onSaved={() => { setAddingUnit(false); refresh(); }} />
      )}
      {editingUnit && (
        <PackingUnitDialog sid={sid} presets={presets} shipment={shipment} unit={editingUnit}
                           onClose={() => setEditingUnit(null)}
                           onSaved={() => { setEditingUnit(null); refresh(); }} />
      )}
      {addingPassenger && (
        <PassengerDialog sid={sid} onClose={() => setAddingPassenger(false)}
                         onSaved={() => { setAddingPassenger(false); refresh(); }} />
      )}
      {addingSuitcase && (
        <SuitcaseDialog sid={sid} presets={presets} passengerId={addingSuitcase}
                        onClose={() => setAddingSuitcase(null)}
                        onSaved={() => { setAddingSuitcase(null); refresh(); }} />
      )}
      {editingSuitcase && (
        <SuitcaseDialog sid={sid} presets={presets} suitcase={editingSuitcase}
                        passengerId={editingSuitcase.passenger_id}
                        onClose={() => setEditingSuitcase(null)}
                        onSaved={() => { setEditingSuitcase(null); refresh(); }} />
      )}
      {tracking && (
        <TrackingResultDialog data={tracking} onClose={() => setTracking(null)} />
      )}
    </div>
  );
}

// ─── Header: mode picker + waybill + AI-track ────────────────────
function ModeAndTrackingHeader({ shipment, mode, setMode, saveWaybill, onAiTrack, aiBusy }) {
  const [form, setForm] = useState({
    waybill_no: shipment?.waybill_no || '',
    flight_no: shipment?.flight_no || '',
    carrier_name: shipment?.carrier_name || '',
    tracking_url: shipment?.tracking_url || '',
    departure_date: shipment?.departure_date || '',
    arrival_date: shipment?.arrival_date || '',
  });
  useEffect(() => {
    setForm({
      waybill_no: shipment?.waybill_no || '',
      flight_no: shipment?.flight_no || '',
      carrier_name: shipment?.carrier_name || '',
      tracking_url: shipment?.tracking_url || '',
      departure_date: shipment?.departure_date || '',
      arrival_date: shipment?.arrival_date || '',
    });
  }, [shipment?.id, shipment?.waybill_no, shipment?.flight_no, shipment?.carrier_name, shipment?.tracking_url, shipment?.departure_date, shipment?.arrival_date]);

  return (
    <div className="rounded-lg border border-border p-3 bg-slate-50/50 space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant={mode === 'container' ? 'default' : 'outline'} onClick={() => setMode('container')} data-testid="ship-mode-container">
            <Ship size={12} className="mr-1" /> Container
          </Button>
          <Button size="sm" variant={mode === 'airport' ? 'default' : 'outline'} onClick={() => setMode('airport')} data-testid="ship-mode-airport">
            <Plane size={12} className="mr-1" /> Airport
          </Button>
        </div>
        <Button size="sm" variant="outline" onClick={onAiTrack} disabled={aiBusy} data-testid="ship-ai-track-btn"
                className="text-purple-700 border-purple-300 hover:bg-purple-50">
          {aiBusy ? <><Loader2 size={12} className="mr-1 animate-spin" />Tracking…</> : <><Sparkles size={12} className="mr-1" />AI Track</>}
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
        <div className="space-y-0.5">
          <Label className="text-[10px]">Carrier</Label>
          <Input className="h-7 text-xs" placeholder="Maersk / Emirates" value={form.carrier_name}
                 onChange={e => setForm({ ...form, carrier_name: e.target.value })}
                 onBlur={() => saveWaybill({ carrier_name: form.carrier_name })} data-testid="ship-carrier" />
        </div>
        <div className="space-y-0.5">
          <Label className="text-[10px]">{mode === 'container' ? 'Waybill / BOL #' : 'Flight #'}</Label>
          <Input className="h-7 text-xs font-mono"
                 placeholder={mode === 'container' ? 'MAEU12345678' : 'KQ411'}
                 value={mode === 'container' ? form.waybill_no : form.flight_no}
                 onChange={e => setForm({ ...form, [mode === 'container' ? 'waybill_no' : 'flight_no']: e.target.value })}
                 onBlur={() => saveWaybill(mode === 'container' ? { waybill_no: form.waybill_no } : { flight_no: form.flight_no })}
                 data-testid="ship-waybill-flight" />
        </div>
        <div className="space-y-0.5">
          <Label className="text-[10px]">Tracking URL (optional)</Label>
          <Input className="h-7 text-xs" placeholder="https://…" value={form.tracking_url}
                 onChange={e => setForm({ ...form, tracking_url: e.target.value })}
                 onBlur={() => saveWaybill({ tracking_url: form.tracking_url })} data-testid="ship-tracking-url" />
        </div>
        <div className="space-y-0.5">
          <Label className="text-[10px]">Departure date</Label>
          <Input type="date" className="h-7 text-xs" value={form.departure_date}
                 onChange={e => setForm({ ...form, departure_date: e.target.value })}
                 onBlur={() => saveWaybill({ departure_date: form.departure_date })} data-testid="ship-departure" />
        </div>
        <div className="space-y-0.5">
          <Label className="text-[10px]">Arrival date</Label>
          <Input type="date" className="h-7 text-xs" value={form.arrival_date}
                 onChange={e => setForm({ ...form, arrival_date: e.target.value })}
                 onBlur={() => saveWaybill({ arrival_date: form.arrival_date })} data-testid="ship-arrival" />
        </div>
      </div>
    </div>
  );
}

// ─── Container mode: 2D floor plan + packing units list ──────────
function ContainerModePanel({ shipment, presets, onAdd, onEdit, refresh }) {
  const units = shipment?.packing_units || [];
  // Only floor-level (parent_id=null) units are placed; children stack on top
  const floorUnits = units.filter(u => !u.parent_id);
  const childrenOf = (id) => units.filter(u => u.parent_id === id);
  const dims = shipment?.container_dims_cm || {};
  const L = dims.length_cm || CONTAINER_LENGTH_CM;
  const W = dims.width_cm || CONTAINER_WIDTH_CM;
  const usedFloor = floorUnits.reduce((s, u) => s + (u.L_cm * u.W_cm), 0);
  const totalFloor = L * W;
  const floorPct = totalFloor ? Math.min(100, (usedFloor / totalFloor) * 100) : 0;
  const totalWeight = units.reduce((s, u) => s + (u.weight_capacity_kg || 0), 0);

  const del = async (u) => {
    if (!window.confirm(`Delete ${u.name}? Items in it move back to unassigned.`)) return;
    try {
      await api.delete(`/shipments/${shipment.id}/packing-units/${u.id}`);
      toast.success('Deleted'); refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  return (
    <div className="space-y-2" data-testid="container-mode-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs">
          <span className="font-semibold">Packing units ({units.length})</span>
          <span className="text-muted-foreground ml-2">
            Floor {floorPct.toFixed(0)}% · Capacity {totalWeight.toLocaleString()} kg
          </span>
        </div>
        <Button size="sm" variant="outline" onClick={onAdd} data-testid="ship-add-packing-unit">
          <Plus size={12} className="mr-1" /> Add pallet / box / tote
        </Button>
        <Button size="sm" variant="outline" className="text-purple-700 border-purple-300 hover:bg-purple-50"
                onClick={async () => {
                  const items = shipment?.items || [];
                  if (items.length === 0) { toast.warning('Add items first, then AI can suggest packing.'); return; }
                  const t = toast.loading('AI analysing items…');
                  try {
                    const r = await api.post(`/shipments/${shipment.id}/ai-suggest-packing`);
                    toast.dismiss(t);
                    const msg = `AI proposes ${r.data.units.length} units:\n\n${r.data.strategy}\n\n${r.data.units.map(u => `• ${u.type.toUpperCase()} · ${u.preset_key} — ${u.reason || ''}`).join('\n')}\n\nApply this layout to your container?`;
                    if (!window.confirm(msg)) return;
                    const apply = await api.post(`/shipments/${shipment.id}/apply-suggested-packing`, { units: r.data.units });
                    toast.success(`Created ${apply.data.created} packing units`); refresh();
                  } catch (e) { toast.dismiss(t); toast.error(e.response?.data?.detail || 'AI packing failed'); }
                }} data-testid="ship-ai-suggest-packing">
          <Sparkles size={12} className="mr-1" /> AI Suggest
        </Button>
        <Button size="sm" variant="outline"
                onClick={async () => {
                  if ((shipment?.packing_units || []).length === 0) { toast.warning('Add packing units first.'); return; }
                  try {
                    const r = await api.get(`/shipments/${shipment.id}/labels.pdf`, { responseType: 'blob' });
                    const url = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
                    const a = document.createElement('a'); a.href = url;
                    a.download = `labels-${(shipment?.name || 'shipment').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 40)}.pdf`;
                    document.body.appendChild(a); a.click(); document.body.removeChild(a);
                    URL.revokeObjectURL(url); toast.success('Labels PDF downloaded');
                  } catch (e) { toast.error(e.response?.data?.detail || 'Label generation failed'); }
                }} data-testid="ship-print-labels">
          <PackageOpen size={12} className="mr-1" /> Print QR labels
        </Button>
      </div>

      {/* 2D top-down floor plan */}
      <FloorPlanSVG L={L} W={W} floorUnits={floorUnits} childrenOf={childrenOf}
                    onSelect={onEdit} sid={shipment.id} refresh={refresh} />

      {/* List of units by parent */}
      <div className="space-y-1.5">
        {floorUnits.length === 0 && (
          <p className="text-[11px] italic text-muted-foreground">No packing units yet. Click &ldquo;Add pallet / box / tote&rdquo; to plan your container layout.</p>
        )}
        {floorUnits.map(u => (
          <UnitCard key={u.id} unit={u} stackedChildren={childrenOf(u.id)} onEdit={onEdit} onDelete={del} />
        ))}
      </div>
    </div>
  );
}

// ─── 2D top-down container floor plan (with drag-and-drop) ──────
function FloorPlanSVG({ L, W, floorUnits, childrenOf, onSelect, sid, refresh }) {
  const SCALE = 0.6; // px per cm
  const svgW = L * SCALE + 20;
  const svgH = W * SCALE + 20;
  const [dragging, setDragging] = useState(null); // {id, offsetX, offsetY}

  const onPointerDown = (e, u) => {
    e.stopPropagation();
    const svgRect = e.currentTarget.ownerSVGElement.getBoundingClientRect();
    const px = e.clientX - svgRect.left - 10;  // svg-local x in px (minus 10 padding)
    const py = e.clientY - svgRect.top - 10;
    setDragging({ id: u.id, offX: px - u.floor_x_cm * SCALE, offY: py - u.floor_y_cm * SCALE, u });
  };
  const onPointerMove = (e) => {
    if (!dragging) return;
    const svgRect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - svgRect.left - 10;
    const py = e.clientY - svgRect.top - 10;
    const newX = Math.max(0, Math.min(L - dragging.u.L_cm, (px - dragging.offX) / SCALE));
    const newY = Math.max(0, Math.min(W - dragging.u.W_cm, (py - dragging.offY) / SCALE));
    // Live-update the SVG rect via DOM (avoids state churn during drag)
    const rect = e.currentTarget.querySelector(`[data-uid="${dragging.id}"] rect`);
    const nameLbl = e.currentTarget.querySelector(`[data-uid="${dragging.id}"] text`);
    if (rect) { rect.setAttribute('x', 10 + newX * SCALE); rect.setAttribute('y', 10 + newY * SCALE); }
    if (nameLbl) { nameLbl.setAttribute('x', 10 + newX * SCALE + 4); nameLbl.setAttribute('y', 10 + newY * SCALE + 12); }
    dragging._pendingX = newX; dragging._pendingY = newY;
  };
  const onPointerUp = async () => {
    if (!dragging) return;
    const d = dragging; setDragging(null);
    if (d._pendingX === undefined) return;
    try {
      await api.put(`/shipments/${sid}/packing-units/${d.id}`,
                    { floor_x_cm: d._pendingX, floor_y_cm: d._pendingY });
      refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Move failed'); refresh(); }
  };

  return (
    <svg
      width={svgW} height={svgH}
      className="border border-slate-300 rounded bg-slate-50 select-none"
      data-testid="floor-plan-svg"
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
    >
      <rect x={10} y={10} width={L * SCALE} height={W * SCALE} fill="#fff" stroke="#334155" strokeWidth="2" />
      <text x={12} y={svgH - 4} fontSize="9" fill="#64748b">{(L / 100).toFixed(1)}m × {(W / 100).toFixed(1)}m container floor · drag units to reposition</text>
      {floorUnits.map((u) => {
        const stackCount = childrenOf(u.id).length;
        return (
          <g key={u.id} data-uid={u.id} onPointerDown={(e) => onPointerDown(e, u)}
             onDoubleClick={() => onSelect(u)} style={{ cursor: dragging?.id === u.id ? 'grabbing' : 'grab' }}
             data-testid={`floor-unit-${u.id}`}>
            <rect x={10 + u.floor_x_cm * SCALE} y={10 + u.floor_y_cm * SCALE}
                  width={u.L_cm * SCALE} height={u.W_cm * SCALE}
                  fill={u.color || UNIT_COLORS[u.type] || '#94a3b8'}
                  fillOpacity="0.7" stroke="#0f172a" strokeWidth="1" />
            <text x={10 + u.floor_x_cm * SCALE + 4} y={10 + u.floor_y_cm * SCALE + 12}
                  fontSize="9" fill="#0f172a" fontWeight="600" pointerEvents="none">
              {u.name}{stackCount > 0 ? ` (+${stackCount})` : ''}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── Single packing-unit card + its stacked children ─────────────
function UnitCard({ unit, stackedChildren, onEdit, onDelete }) {
  return (
    <div className="rounded border border-border p-2 text-xs" style={{ borderLeftColor: unit.color || UNIT_COLORS[unit.type], borderLeftWidth: 4 }} data-testid={`unit-card-${unit.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Badge variant="outline" className="text-[10px] capitalize">{unit.type}</Badge>
          <span className="font-semibold truncate">{unit.name}</span>
          <span className="text-muted-foreground text-[10px] font-mono">
            {unit.L_cm}×{unit.W_cm}×{unit.H_cm}cm · {unit.weight_capacity_kg}kg
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => onEdit(unit)} data-testid={`unit-edit-${unit.id}`}><Pencil size={12} /></Button>
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-rose-600" onClick={() => onDelete(unit)} data-testid={`unit-del-${unit.id}`}><Trash2 size={12} /></Button>
        </div>
      </div>
      {stackedChildren.length > 0 && (
        <div className="ml-3 mt-1 pl-2 border-l border-dashed border-slate-300 space-y-1">
          {stackedChildren.map(c => (
            <div key={c.id} className="text-[11px] flex items-center gap-2" data-testid={`stacked-${c.id}`}>
              <Badge variant="outline" className="text-[9px] capitalize">{c.type}</Badge>
              <span>{c.name}</span>
              <span className="text-muted-foreground text-[10px] font-mono">{c.L_cm}×{c.W_cm}×{c.H_cm}cm</span>
              <button onClick={() => onEdit(c)} className="ml-auto text-slate-500 hover:text-slate-800"><Pencil size={10} /></button>
              <button onClick={() => onDelete(c)} className="text-rose-500 hover:text-rose-800"><Trash2 size={10} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Airport mode: passengers + suitcases ────────────────────────
function AirportModePanel({ shipment, presets, onAddPassenger, onAddSuitcase, onEditSuitcase, refresh }) {
  const passengers = shipment?.passengers || [];
  const suitcases = shipment?.suitcases || [];
  const delPassenger = async (p) => {
    if (!window.confirm(`Delete ${p.name} and all their suitcases?`)) return;
    try { await api.delete(`/shipments/${shipment.id}/passengers/${p.id}`); toast.success('Deleted'); refresh(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const delSuitcase = async (sc) => {
    if (!window.confirm(`Delete ${sc.name}?`)) return;
    try { await api.delete(`/shipments/${shipment.id}/suitcases/${sc.id}`); toast.success('Deleted'); refresh(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  return (
    <div className="space-y-2" data-testid="airport-mode-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-xs font-semibold">Passengers ({passengers.length}) · Suitcases ({suitcases.length})</p>
        <Button size="sm" variant="outline" onClick={onAddPassenger} data-testid="ship-add-passenger">
          <Plus size={12} className="mr-1" /> Add passenger
        </Button>
      </div>
      {passengers.length === 0 && (
        <p className="text-[11px] italic text-muted-foreground">No passengers yet. Add a passenger to start tracking suitcases.</p>
      )}
      {passengers.map(p => {
        const paxCases = suitcases.filter(s => s.passenger_id === p.id);
        const totalKg = paxCases.reduce((s, x) => s + (x.weight_kg || 0), 0);
        const allowanceKg = (p.suitcase_allowance_kg || 0) * (p.suitcase_count_allowance || 0);
        const overWeight = totalKg > allowanceKg && allowanceKg > 0;
        const overCount = paxCases.length > (p.suitcase_count_allowance || 0);
        return (
          <div key={p.id} className="rounded border border-border p-2" data-testid={`passenger-${p.id}`}>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-sm">{p.name}</span>
                {p.flight_no && <Badge variant="outline" className="text-[10px] font-mono">✈ {p.flight_no}</Badge>}
                {p.passport_no && <Badge variant="outline" className="text-[10px]">Passport {p.passport_no}</Badge>}
                <Badge className={`text-[10px] ${overWeight ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'}`}>
                  {totalKg.toFixed(1)}/{allowanceKg}kg
                </Badge>
                <Badge className={`text-[10px] ${overCount ? 'bg-rose-100 text-rose-800' : 'bg-slate-100 text-slate-700'}`}>
                  {paxCases.length}/{p.suitcase_count_allowance || 0} bags
                </Badge>
              </div>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" className="h-6 text-[10px]" onClick={() => onAddSuitcase(p.id)} data-testid={`add-suitcase-${p.id}`}>
                  <Plus size={10} className="mr-0.5" /> Suitcase
                </Button>
                <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-rose-600" onClick={() => delPassenger(p)} data-testid={`passenger-del-${p.id}`}>
                  <Trash2 size={12} />
                </Button>
              </div>
            </div>
            {paxCases.length > 0 && (
              <div className="mt-1 space-y-0.5">
                {paxCases.map(sc => {
                  const scOver = sc.weight_kg > sc.weight_limit_kg && sc.weight_limit_kg > 0;
                  return (
                    <div key={sc.id} className="flex items-center gap-2 text-[11px] py-0.5" data-testid={`suitcase-${sc.id}`}>
                      <Badge variant="outline" className="text-[9px] capitalize" style={{ borderLeftColor: sc.color || UNIT_COLORS[sc.type], borderLeftWidth: 3 }}>{sc.type}</Badge>
                      <span className="font-medium">{sc.name}</span>
                      <span className={`font-mono ${scOver ? 'text-rose-700 font-bold' : 'text-muted-foreground'}`}>
                        {sc.weight_kg}/{sc.weight_limit_kg}kg
                      </span>
                      {sc.tracking_no && <Badge variant="outline" className="text-[9px] font-mono bg-teal-50">🏷 {sc.tracking_no}</Badge>}
                      <button className="ml-auto text-slate-500 hover:text-slate-800" onClick={() => onEditSuitcase(sc)}><Pencil size={10} /></button>
                      <button className="text-rose-500 hover:text-rose-800" onClick={() => delSuitcase(sc)}><Trash2 size={10} /></button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Packing-unit add/edit dialog ────────────────────────────────
function PackingUnitDialog({ sid, presets, shipment, unit, onClose, onSaved }) {
  const isEdit = !!unit;
  const [form, setForm] = useState(unit || {
    type: 'pallet', preset_key: 'eur_pallet', name: '', L_cm: 120, W_cm: 80, H_cm: 14.5,
    weight_capacity_kg: 1500, color: '#8b5cf6', parent_id: null, floor_x_cm: 0, floor_y_cm: 0,
  });
  const applyPreset = (key) => {
    const p = presets[key] || {};
    setForm(f => ({ ...f, preset_key: key, L_cm: p.L_cm || f.L_cm, W_cm: p.W_cm || f.W_cm, H_cm: p.H_cm || f.H_cm, weight_capacity_kg: p.cap_kg || f.weight_capacity_kg, name: p.label || f.name }));
  };
  const save = async () => {
    try {
      if (isEdit) await api.put(`/shipments/${sid}/packing-units/${unit.id}`, form);
      else await api.post(`/shipments/${sid}/packing-units`, form);
      toast.success(isEdit ? 'Updated' : 'Added');
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  const otherUnits = (shipment?.packing_units || []).filter(u => !unit || u.id !== unit.id);
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="packing-unit-dialog">
        <DialogHeader><DialogTitle>{isEdit ? 'Edit' : 'Add'} Packing Unit</DialogTitle></DialogHeader>
        <div className="space-y-2 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs">Type</Label>
              <Select value={form.type} onValueChange={v => setForm({ ...form, type: v })}>
                <SelectTrigger data-testid="pu-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="pallet">Pallet</SelectItem>
                  <SelectItem value="box">Box</SelectItem>
                  <SelectItem value="tote">Tote</SelectItem>
                  <SelectItem value="crate">Crate</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Preset</Label>
              <Select value={form.preset_key || ''} onValueChange={applyPreset}>
                <SelectTrigger data-testid="pu-preset"><SelectValue placeholder="Custom" /></SelectTrigger>
                <SelectContent>
                  {Object.entries(presets).map(([k, p]) => (
                    <SelectItem key={k} value={k}>{p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div><Label className="text-xs">Name</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="pu-name" /></div>
          <div className="grid grid-cols-4 gap-2">
            <div><Label className="text-[10px]">L cm</Label><Input type="number" value={form.L_cm} onChange={e => setForm({ ...form, L_cm: parseFloat(e.target.value) || 0 })} /></div>
            <div><Label className="text-[10px]">W cm</Label><Input type="number" value={form.W_cm} onChange={e => setForm({ ...form, W_cm: parseFloat(e.target.value) || 0 })} /></div>
            <div><Label className="text-[10px]">H cm</Label><Input type="number" value={form.H_cm} onChange={e => setForm({ ...form, H_cm: parseFloat(e.target.value) || 0 })} /></div>
            <div><Label className="text-[10px]">Kg cap</Label><Input type="number" value={form.weight_capacity_kg} onChange={e => setForm({ ...form, weight_capacity_kg: parseFloat(e.target.value) || 0 })} /></div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-[10px]">Floor X cm</Label><Input type="number" value={form.floor_x_cm} onChange={e => setForm({ ...form, floor_x_cm: parseFloat(e.target.value) || 0 })} data-testid="pu-x" /></div>
            <div><Label className="text-[10px]">Floor Y cm</Label><Input type="number" value={form.floor_y_cm} onChange={e => setForm({ ...form, floor_y_cm: parseFloat(e.target.value) || 0 })} data-testid="pu-y" /></div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-[10px]">Color</Label><Input type="color" value={form.color} onChange={e => setForm({ ...form, color: e.target.value })} className="h-8" data-testid="pu-color" /></div>
            <div>
              <Label className="text-[10px]">Stacked on</Label>
              <Select value={form.parent_id || '__floor__'} onValueChange={v => setForm({ ...form, parent_id: v === '__floor__' ? null : v })}>
                <SelectTrigger data-testid="pu-parent"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__floor__">Container floor</SelectItem>
                  {otherUnits.map(u => <SelectItem key={u.id} value={u.id}>{u.name} ({u.type})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} data-testid="pu-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Passenger dialog ────────────────────────────────────────────
function PassengerDialog({ sid, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', passport_no: '', ticket_no: '', flight_no: '', suitcase_allowance_kg: 23, suitcase_count_allowance: 2 });
  const save = async () => {
    try {
      await api.post(`/shipments/${sid}/passengers`, form);
      toast.success('Passenger added'); onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="passenger-dialog">
        <DialogHeader><DialogTitle>Add Passenger</DialogTitle></DialogHeader>
        <div className="space-y-2 text-sm">
          <div><Label className="text-xs">Full name *</Label><Input autoFocus value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="pax-name" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-[10px]">Passport #</Label><Input value={form.passport_no} onChange={e => setForm({ ...form, passport_no: e.target.value })} data-testid="pax-passport" /></div>
            <div><Label className="text-[10px]">Ticket #</Label><Input value={form.ticket_no} onChange={e => setForm({ ...form, ticket_no: e.target.value })} data-testid="pax-ticket" /></div>
          </div>
          <div><Label className="text-[10px]">Flight #</Label><Input value={form.flight_no} onChange={e => setForm({ ...form, flight_no: e.target.value })} placeholder="KQ411" data-testid="pax-flight" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-[10px]">Kg per bag</Label><Input type="number" value={form.suitcase_allowance_kg} onChange={e => setForm({ ...form, suitcase_allowance_kg: parseFloat(e.target.value) || 0 })} /></div>
            <div><Label className="text-[10px]">Bag count</Label><Input type="number" value={form.suitcase_count_allowance} onChange={e => setForm({ ...form, suitcase_count_allowance: parseInt(e.target.value, 10) || 0 })} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={!form.name.trim()} data-testid="pax-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Suitcase dialog ─────────────────────────────────────────────
function SuitcaseDialog({ sid, presets, passengerId, suitcase, onClose, onSaved }) {
  const isEdit = !!suitcase;
  const [form, setForm] = useState(suitcase || {
    passenger_id: passengerId, type: 'suitcase', preset_key: 'suitcase_lg',
    name: '', L_cm: 76, W_cm: 51, H_cm: 31, weight_kg: 0, weight_limit_kg: 23,
    tracking_no: '', color: '#334155',
  });
  const applyPreset = (key) => {
    const p = presets[key] || {};
    setForm(f => ({ ...f, preset_key: key, L_cm: p.L_cm || f.L_cm, W_cm: p.W_cm || f.W_cm, H_cm: p.H_cm || f.H_cm, weight_limit_kg: p.cap_kg || f.weight_limit_kg, name: p.label || f.name }));
  };
  const save = async () => {
    try {
      if (isEdit) await api.put(`/shipments/${sid}/suitcases/${suitcase.id}`, form);
      else await api.post(`/shipments/${sid}/suitcases`, form);
      toast.success(isEdit ? 'Updated' : 'Added');
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="suitcase-dialog">
        <DialogHeader><DialogTitle>{isEdit ? 'Edit' : 'Add'} Suitcase</DialogTitle></DialogHeader>
        <div className="space-y-2 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs">Type</Label>
              <Select value={form.type} onValueChange={v => setForm({ ...form, type: v })}>
                <SelectTrigger data-testid="sc-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="suitcase">Suitcase</SelectItem>
                  <SelectItem value="carry_on">Carry-on</SelectItem>
                  <SelectItem value="duffel">Duffel</SelectItem>
                  <SelectItem value="tote">Tote</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Preset</Label>
              <Select value={form.preset_key || ''} onValueChange={applyPreset}>
                <SelectTrigger data-testid="sc-preset"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(presets).filter(([k]) => k.startsWith('suitcase') || k === 'carry_on' || k === 'duffel' || k === 'plastic_tote').map(([k, p]) => (
                    <SelectItem key={k} value={k}>{p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div><Label className="text-xs">Name</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="sc-name" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-[10px]">Weight kg</Label><Input type="number" step="0.1" value={form.weight_kg} onChange={e => setForm({ ...form, weight_kg: parseFloat(e.target.value) || 0 })} data-testid="sc-weight" /></div>
            <div><Label className="text-[10px]">Limit kg</Label><Input type="number" step="0.1" value={form.weight_limit_kg} onChange={e => setForm({ ...form, weight_limit_kg: parseFloat(e.target.value) || 0 })} data-testid="sc-limit" /></div>
          </div>
          <div><Label className="text-xs">Bag-tag / tracking #</Label><Input value={form.tracking_no} onChange={e => setForm({ ...form, tracking_no: e.target.value })} placeholder="KQ411-BAG-001" className="font-mono" data-testid="sc-tracking" /></div>
          <div><Label className="text-xs">Color</Label><Input type="color" value={form.color} onChange={e => setForm({ ...form, color: e.target.value })} className="h-8" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} data-testid="sc-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── AI tracking results ─────────────────────────────────────────
function TrackingResultDialog({ data, onClose }) {
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="ai-tracking-dialog">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><Sparkles size={16} className="text-purple-600" /> AI Tracking Status</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="rounded-lg bg-purple-50 border border-purple-200 p-3">
            <p className="text-xs font-semibold text-purple-900 uppercase tracking-wide mb-1">Estimated status</p>
            <p className="text-sm text-purple-950 whitespace-pre-wrap">{data.summary}</p>
          </div>
          {data.tracking_urls?.length > 0 && (
            <div>
              <p className="text-xs font-semibold mb-1">Direct tracking links</p>
              <div className="space-y-1">
                {data.tracking_urls.map((u, i) => (
                  <a key={i} href={u.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-xs text-blue-700 hover:underline" data-testid={`tracking-url-${i}`}>
                    <ExternalLink size={11} /> {u.label}
                  </a>
                ))}
              </div>
            </div>
          )}
          <p className="text-[10px] text-muted-foreground italic">{data.hint}</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
