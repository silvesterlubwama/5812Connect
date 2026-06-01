/**
 * BrandingEditor — admin tool to rename / hide / reorder sidebar nav items,
 * change the app name + tagline, set a primary brand color.
 *
 * Settings live in the system_settings collection so they back up + travel with
 * deployments. Changes apply immediately on save via BrandingContext.refresh().
 */
import React, { useEffect, useState } from 'react';
import { Paintbrush, GripVertical, EyeOff, RotateCcw, ChevronUp, ChevronDown } from 'lucide-react';
import api from '../services/api';
import { useBranding } from '../context/BrandingContext';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { toast } from 'sonner';

// Catalogue of every customisable nav row. Source-of-truth labels — admin overrides
// replace these. Keep in sync with NAV_SECTIONS in Layout.jsx (a small price for
// not coupling this dialog to the actual nav config import.)
const NAV_CATALOGUE = [
  { section: 'Operations', items: [
    { to: '/dashboard', defaultLabel: 'Dashboard' },
    { to: '/events', defaultLabel: 'Events' },
    { to: '/calendar', defaultLabel: 'Calendar' },
    { to: '/check-ins', defaultLabel: 'Check-Ins' },
    { to: '/members', defaultLabel: 'People' },
    { to: '/tasks', defaultLabel: 'Tasks' },
    { to: '/social-work', defaultLabel: 'Social Work' },
    { to: '/access', defaultLabel: 'Access' },
    { to: '/volunteer-scheduling', defaultLabel: 'Volunteer Scheduling' },
    { to: '/resources', defaultLabel: 'Resources' },
    { to: '/outreach', defaultLabel: 'Outreach' },
  ] },
  { section: 'Finance', items: [
    { to: '/financial', defaultLabel: 'Financial' },
    { to: '/accounting', defaultLabel: 'Accounting' },
    { to: '/banking', defaultLabel: 'Banking' },
    { to: '/hr', defaultLabel: 'HR & Payroll' },
    { to: '/approvals', defaultLabel: 'Approvals' },
    { to: '/sales', defaultLabel: 'Marketplace' },
  ] },
  { section: 'Communications', items: [
    { to: '/comms', defaultLabel: 'Chat & Calls' },
  ] },
  { section: 'Reports', items: [
    { to: '/reports', defaultLabel: 'Reports' },
    { to: '/analytics', defaultLabel: 'Analytics' },
    { to: '/report-builder', defaultLabel: 'Report Builder' },
  ] },
  { section: 'Admin', items: [
    { to: '/admin', defaultLabel: 'Staff & Users' },
    { to: '/locations', defaultLabel: 'Campuses' },
    { to: '/financial-apis', defaultLabel: 'Financial APIs' },
    { to: '/email-templates', defaultLabel: 'Email Templates' },
    { to: '/settings', defaultLabel: 'Settings' },
    { to: '/audit', defaultLabel: 'Audit Trail' },
    { to: '/gdpr', defaultLabel: 'Privacy & GDPR' },
  ] },
];

export default function BrandingEditor() {
  const { branding, refresh } = useBranding();
  const [open, setOpen] = useState(false);
  const [appName, setAppName] = useState('');
  const [tagline, setTagline] = useState('');
  const [logoUrl, setLogoUrl] = useState('');
  const [primaryColor, setPrimaryColor] = useState('');
  const [navOverrides, setNavOverrides] = useState({});
  const [sectionOverrides, setSectionOverrides] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAppName(branding.app_name || '58:12 Connect');
    setTagline(branding.tagline || '');
    setLogoUrl(branding.logo_url || '');
    setPrimaryColor(branding.primary_color || '');
    setNavOverrides({ ...(branding.nav_overrides || {}) });
    setSectionOverrides({ ...(branding.section_overrides || {}) });
  }, [open, branding]);

  const updateItem = (path, patch) => {
    setNavOverrides(prev => ({ ...prev, [path]: { ...(prev[path] || {}), ...patch } }));
  };
  const updateSection = (name, patch) => {
    setSectionOverrides(prev => ({ ...prev, [name]: { ...(prev[name] || {}), ...patch } }));
  };

  const moveItem = (sectionItems, idx, direction) => {
    const target = sectionItems[idx + direction];
    if (!target) return;
    const me = sectionItems[idx];
    // Recompute order numbers for the whole section to be safe
    const newOrders = {};
    const reordered = [...sectionItems];
    [reordered[idx], reordered[idx + direction]] = [reordered[idx + direction], reordered[idx]];
    reordered.forEach((it, i) => { newOrders[it.to] = i; });
    setNavOverrides(prev => {
      const next = { ...prev };
      Object.entries(newOrders).forEach(([path, order]) => {
        next[path] = { ...(next[path] || {}), order };
      });
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put('/admin/system-settings', {
        branding: {
          app_name: appName.trim() || '58:12 Connect',
          tagline: tagline.trim(),
          logo_url: logoUrl.trim(),
          primary_color: primaryColor.trim(),
          nav_overrides: navOverrides,
          section_overrides: sectionOverrides,
        },
      });
      toast.success('Branding saved — applying now');
      await refresh();
      setOpen(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const resetAll = () => {
    if (!window.confirm('Reset all branding back to defaults? This clears every nav rename + reorder + hide.')) return;
    setAppName('58:12 Connect');
    setTagline('');
    setLogoUrl('');
    setPrimaryColor('');
    setNavOverrides({});
    setSectionOverrides({});
  };

  return (
    <>
      <Card className="rounded-xl mt-4 cursor-pointer hover:border-primary/40" onClick={() => setOpen(true)} data-testid="branding-editor-card">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Paintbrush size={18} className="text-primary" />
            <div>
              <p className="font-medium text-sm">Branding &amp; Navigation</p>
              <p className="text-xs text-muted-foreground">
                Rename / hide / reorder sidebar items, change the app name + brand color. Travels with the backup.
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline">Customise</Button>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="branding-editor-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Paintbrush size={16} /> Branding &amp; Navigation</DialogTitle>
            <DialogDescription className="text-xs">
              Customise how this deployment looks + which nav items show, in what order. Changes apply on save.
            </DialogDescription>
          </DialogHeader>

          {/* Identity */}
          <section className="space-y-3 mt-3 p-3 rounded-lg border">
            <h3 className="text-sm font-semibold">Identity</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">App name</Label>
                <Input value={appName} onChange={e => setAppName(e.target.value)} placeholder="58:12 Connect" data-testid="branding-app-name" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Tagline (optional)</Label>
                <Input value={tagline} onChange={e => setTagline(e.target.value)} placeholder="Multi-tenant CRM" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Logo URL (optional)</Label>
              <Input value={logoUrl} onChange={e => setLogoUrl(e.target.value)} placeholder="https://cdn.example.com/logo.png" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Primary brand color (hex)</Label>
              <div className="flex gap-2">
                <Input value={primaryColor} onChange={e => setPrimaryColor(e.target.value)} placeholder="#10b981" data-testid="branding-primary-color" />
                {primaryColor && <div className="h-9 w-9 rounded border" style={{ background: primaryColor }} />}
              </div>
            </div>
          </section>

          {/* Nav sections */}
          <section className="space-y-3 mt-3 p-3 rounded-lg border">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Sidebar Navigation</h3>
              <Button size="sm" variant="ghost" onClick={resetAll} data-testid="branding-reset-btn"><RotateCcw size={11} className="mr-1" /> Reset all</Button>
            </div>
            {NAV_CATALOGUE.map(section => {
              const sectionLabel = sectionOverrides[section.section]?.label || section.section;
              const sectionHidden = !!sectionOverrides[section.section]?.hidden;
              // Resolve ordered items for the up/down buttons
              const ordered = [...section.items].sort((a, b) => {
                const oa = navOverrides[a.to]?.order ?? section.items.indexOf(a);
                const ob = navOverrides[b.to]?.order ?? section.items.indexOf(b);
                return oa - ob;
              });
              return (
                <div key={section.section} className={`p-2.5 rounded border ${sectionHidden ? 'opacity-50' : ''}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Section</span>
                    <Input
                      value={sectionLabel}
                      onChange={e => updateSection(section.section, { label: e.target.value })}
                      className="h-7 text-sm font-semibold"
                      data-testid={`branding-section-${section.section.toLowerCase()}-label`}
                    />
                    <Button size="sm" variant="ghost" className="h-7" onClick={() => updateSection(section.section, { hidden: !sectionHidden })} title={sectionHidden ? 'Show section' : 'Hide section'}>
                      <EyeOff size={11} />
                    </Button>
                  </div>
                  <div className="space-y-1">
                    {ordered.map((it, idx) => {
                      const o = navOverrides[it.to] || {};
                      const label = o.label || it.defaultLabel;
                      const hidden = !!o.hidden;
                      return (
                        <div key={it.to} className={`flex items-center gap-2 text-xs ${hidden ? 'opacity-50' : ''}`} data-testid={`branding-row-${it.to.replace(/\//g, '-')}`}>
                          <GripVertical size={12} className="text-muted-foreground" />
                          <code className="text-[10px] text-muted-foreground w-32 truncate">{it.to}</code>
                          <Input
                            value={label}
                            onChange={e => updateItem(it.to, { label: e.target.value })}
                            className="h-7 flex-1"
                            placeholder={it.defaultLabel}
                          />
                          <Button size="sm" variant="ghost" className="h-7 px-2" disabled={idx === 0} onClick={() => moveItem(ordered, idx, -1)} title="Move up"><ChevronUp size={12} /></Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2" disabled={idx === ordered.length - 1} onClick={() => moveItem(ordered, idx, 1)} title="Move down"><ChevronDown size={12} /></Button>
                          <label className="flex items-center gap-1 cursor-pointer">
                            <input type="checkbox" checked={!hidden} onChange={e => updateItem(it.to, { hidden: !e.target.checked })} />
                            <span className="text-[10px]">{hidden ? 'hidden' : 'shown'}</span>
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </section>

          <div className="flex gap-2 pt-3 sticky bottom-0 bg-background pb-1">
            <Badge variant="outline" className="self-center text-[10px] mr-auto">Travels with the backup tarball</Badge>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} disabled={saving} data-testid="branding-save-btn">{saving ? 'Saving…' : 'Save & apply'}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
