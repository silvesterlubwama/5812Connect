/**
 * ProfileCompletenessWidget — KPI card surfacing children with incomplete files.
 *
 * Mounted next to ReviewsDueWidget on the Social Work hub. Counts active cases
 * whose profile-completeness % is below a configurable threshold (default 70%).
 * Click opens a drill-down dialog listing each child + which indicators are
 * missing — drives the OVCMIS / donor-audit prep work.
 *
 * Backend: GET /api/social-work/reviews/compliance/completeness?threshold_pct=N
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { ClipboardList, RefreshCw, ChevronRight, CheckCircle2, XCircle } from 'lucide-react';
import api from '../services/api';
import EmptyState from './EmptyState';

const INDICATOR_LABELS = {
  has_photo: 'Profile photo',
  has_welfare: 'Welfare visit',
  has_school: 'School review',
  has_medical: 'Medical exam / scan',
  doc_ovcmis_form_008: 'OVCMIS Form 008',
  doc_sponsorship_assessment: 'Sponsorship Assessment',
  doc_lc1_introduction_letter: 'LC1 Letter',
  doc_school_report: 'School Report',
  doc_guardian_national_id: 'Guardian National ID',
  doc_family_consent_letter: 'Family Consent Letter',
  doc_medical_assessment: 'Medical Assessment scan',
  doc_exit_form: 'Exit Form',
  doc_sponsor_letter_in: 'Letter from Sponsor',
  doc_sponsor_letter_out: 'Letter to Sponsor',
};

export default function ProfileCompletenessWidget({ onOpenCase }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [threshold, setThreshold] = useState(70);
  const [tab, setTab] = useState('children');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/social-work/reviews/compliance/completeness?threshold_pct=${threshold}&group_by=location_id`);
      setData(r.data);
    } catch (e) { console.warn(e?.message || e); }
    finally { setLoading(false); }
  }, [threshold]);

  useEffect(() => { refresh(); }, [refresh]);

  const below = data?.below_threshold ?? 0;
  const tone = below === 0 ? 'text-emerald-600' : below < 5 ? 'text-amber-600' : 'text-rose-600';

  return (
    <>
      <Card
        className="rounded-xl cursor-pointer hover:border-primary/40"
        onClick={() => setOpen(true)}
        data-testid="sw-completeness-card"
      >
        <CardContent className="p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground uppercase">Incomplete files</p>
            <ClipboardList size={12} className="text-muted-foreground" />
          </div>
          <p className={`text-2xl font-bold ${tone}`} data-testid="sw-completeness-count">{below}</p>
          <p className="text-[10px] text-muted-foreground">
            children below {threshold}% profile-completeness
          </p>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="sw-completeness-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><ClipboardList size={16} /> Profile-completeness audit</DialogTitle>
            <DialogDescription className="text-xs">
              Each child is scored on 14 indicators (photo + 3 review kinds + 10 checklist docs).
              Click a row to open the case &amp; fill the gap.
            </DialogDescription>
          </DialogHeader>

          <div className="flex items-center gap-2 mt-1 mb-3">
            <div className="flex rounded border overflow-hidden text-[11px]">
              <button
                className={`px-2.5 py-1 ${tab === 'children' ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
                onClick={() => setTab('children')}
                data-testid="sw-completeness-tab-children"
              >By child ({data?.list?.length ?? 0})</button>
              <button
                className={`px-2.5 py-1 border-l ${tab === 'campus' ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'}`}
                onClick={() => setTab('campus')}
                data-testid="sw-completeness-tab-campus"
              >By campus ({data?.by_campus?.length ?? 0})</button>
            </div>
            <span className="text-xs text-muted-foreground ml-2">Threshold</span>
            <Select value={String(threshold)} onValueChange={v => setThreshold(parseInt(v))}>
              <SelectTrigger className="h-7 w-24 text-xs" data-testid="sw-completeness-threshold"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="50">50%</SelectItem>
                <SelectItem value="70">70%</SelectItem>
                <SelectItem value="85">85%</SelectItem>
                <SelectItem value="100">100%</SelectItem>
              </SelectContent>
            </Select>
            <Badge variant="outline" className="text-[10px]">
              {data ? `${data.above_threshold}/${data.total_active} fully on file` : '…'}
            </Badge>
            <Button size="sm" variant="ghost" onClick={refresh} disabled={loading} className="ml-auto">
              <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            </Button>
          </div>

          {!data || (tab === 'children' ? data.list.length === 0 : (data.by_campus || []).length === 0) ? (
            <EmptyState
              icon={CheckCircle2}
              title={!data ? 'Loading…' : tab === 'children' ? 'No active cases to audit' : 'No campus data yet'}
              description={tab === 'children'
                ? 'Once cases are opened on children, their file-completeness will surface here.'
                : 'Open at least one case per campus to populate the leaderboard.'}
              testid="sw-completeness-empty"
            />
          ) : tab === 'children' ? (
            <div className="space-y-1.5">
              {data.list.filter(r => r.completeness_pct < threshold).map(row => {
                const missing = Object.entries(row.indicators).filter(([, v]) => !v).map(([k]) => INDICATOR_LABELS[k] || k);
                return (
                  <Card
                    key={row.child_id}
                    className="rounded-lg cursor-pointer hover:border-primary/40"
                    onClick={() => { if (onOpenCase) onOpenCase(row.child_id); setOpen(false); }}
                    data-testid={`sw-completeness-row-${row.child_id}`}
                  >
                    <CardContent className="p-2.5 flex items-start gap-3">
                      <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs shrink-0">{(row.name || '?').slice(0, 1)}</div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{row.name}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {row.present}/{row.total_indicators} indicators present
                        </p>
                        {missing.length > 0 && (
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            <XCircle size={9} className="inline mr-1 text-rose-500" />
                            Missing: <span className="italic">{missing.slice(0, 5).join(', ')}{missing.length > 5 ? `, +${missing.length - 5} more` : ''}</span>
                          </p>
                        )}
                      </div>
                      <Badge className={row.completeness_pct >= 85 ? 'bg-emerald-100 text-emerald-700 text-[10px]'
                        : row.completeness_pct >= 50 ? 'bg-amber-100 text-amber-700 text-[10px]'
                        : 'bg-rose-100 text-rose-700 text-[10px]'}>
                        {row.completeness_pct}%
                      </Badge>
                      <ChevronRight size={14} className="text-muted-foreground" />
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          ) : (
            /* By-campus leaderboard — surfaces which campus is keeping the cleanest files
               and drives healthy peer-comparison for the social-work team. */
            <div className="space-y-1.5" data-testid="sw-completeness-campus-list">
              {(data.by_campus || []).map((g, idx) => (
                <Card key={g.location_id} className="rounded-lg" data-testid={`sw-completeness-campus-${g.location_id}`}>
                  <CardContent className="p-2.5 flex items-center gap-3">
                    <div className={`h-8 w-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                      idx === 0 ? 'bg-yellow-100 text-yellow-800'
                      : idx === 1 ? 'bg-slate-200 text-slate-700'
                      : idx === 2 ? 'bg-orange-100 text-orange-800'
                      : 'bg-muted text-muted-foreground'
                    }`}>{idx + 1}</div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{g.location_name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {g.total_active} active case{g.total_active === 1 ? '' : 's'} ·
                        {' '}<span className="text-emerald-700">{g.above_threshold} fully on file</span> ·
                        {' '}<span className="text-rose-700">{g.below_threshold} incomplete</span>
                      </p>
                    </div>
                    <Badge className={g.avg_pct >= 85 ? 'bg-emerald-100 text-emerald-700'
                      : g.avg_pct >= 50 ? 'bg-amber-100 text-amber-700'
                      : 'bg-rose-100 text-rose-700'}>
                      avg {g.avg_pct}%
                    </Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
