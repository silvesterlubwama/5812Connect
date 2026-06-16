/**
 * SocialReviewsPanel — embedded inside the child profile dialog as two new tabs
 * ("School Reviews" + "Welfare Visits"). For each `kind`:
 *
 *   • Toolbar: [Print blank template] [Upload scan] [+ New review]
 *   • Timeline of submitted reviews (newest first) with status pill
 *   • "Fill new review" dialog with the verbatim form schema (academic ratings,
 *     attendance/discipline, welfare indicators, protection concerns, etc.)
 *
 * Saving a form auto-syncs the structured fields into the child profile so the
 * existing /api/members/{id}/profile-pdf report picks them up. No extra wiring.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Plus, Printer, Upload, ClipboardCheck, RefreshCw, Trash2, FileText, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import api, { socialReviewsApi } from '../services/api';
import { toast } from 'sonner';
import EmptyState from './EmptyState';

// Field schemas mirror the .docx templates verbatim so what the social worker sees
// in the dialog matches what they'd fill on paper.
const ACADEMIC_ROWS = [
  { key: 'overall', label: 'Overall academic performance' },
  { key: 'reading_writing', label: 'Reading and writing skills' },
  { key: 'mathematics', label: 'Mathematics performance' },
  { key: 'participation', label: 'Class participation' },
];
const ATTENDANCE_ROWS = [
  { key: 'regular_attendance', label: 'Attends school regularly' },
  { key: 'punctual', label: 'Arrives on time' },
  { key: 'discipline', label: 'Demonstrates good discipline' },
  { key: 'homework', label: 'Completes assignments / homework' },
];
const SOCIAL_EMOTIONAL_ROWS = [
  { key: 'peers', label: 'Relates well with peers' },
  { key: 'respect', label: 'Respects teachers and school rules' },
  { key: 'confidence', label: 'Confidence and self-esteem' },
  { key: 'cocurricular', label: 'Participation in co-curricular activities' },
];
const WELFARE_ROWS = [
  { key: 'physical_health', label: 'Physical Health' },
  { key: 'nutrition', label: 'Nutrition Status' },
  { key: 'hygiene', label: 'Personal Hygiene' },
  { key: 'emotional', label: 'Emotional / Psychological Well-being' },
  { key: 'safety', label: 'Safety and Protection' },
  { key: 'school_attendance', label: 'School Attendance' },
  { key: 'academic_progress', label: 'Academic Progress' },
  { key: 'family_support', label: 'Family Support and Care' },
  { key: 'living_conditions', label: 'Living Conditions' },
];
const HOUSEHOLD_ROWS = [
  { key: 'caregiver_child', label: 'Caregiver-child relationship' },
  { key: 'household_stability', label: 'Household stability' },
  { key: 'housing', label: 'Housing condition' },
  { key: 'water_sanitation', label: 'Water and sanitation facilities' },
  { key: 'family_capacity', label: 'Family capacity to meet basic needs' },
];
const EDUCATION_CHECKS = [
  { key: 'enrolled', label: 'Enrolled in school' },
  { key: 'attends_regularly', label: 'Attends regularly' },
  { key: 'has_materials', label: 'Adequate learning materials' },
  { key: 'fees_met', label: 'School fees / scholastic needs met' },
  { key: 'progressing', label: 'Progressing academically' },
];
const HEALTH_CHECKS = [
  { key: 'healthy', label: 'Appears healthy' },
  { key: 'accessed_medical', label: 'Accessed medical care when needed' },
  { key: 'adequate_meals', label: 'Receives adequate meals daily' },
  { key: 'has_disability', label: 'Disability or chronic illness identified' },
];
const PROTECTION_FLAGS = [
  { key: 'neglect', label: 'Neglect' },
  { key: 'physical_abuse', label: 'Physical Abuse' },
  { key: 'emotional_abuse', label: 'Emotional Abuse' },
  { key: 'child_labour', label: 'Child Labour' },
  { key: 'school_dropout_risk', label: 'School Dropout Risk' },
  { key: 'early_marriage_risk', label: 'Early Marriage Risk' },
  { key: 'other_protection', label: 'Other Protection Concern' },
];
const SCHOOL_OVERALL = [
  'Excellent Progress', 'Good Progress', 'Satisfactory Progress', 'Needs Additional Support', 'Requires Immediate Follow-up',
];
const WELFARE_OVERALL = [
  'Thriving and progressing well', 'Requires routine monitoring', 'Requires additional support services', 'Requires urgent intervention',
];

const RatingRow = ({ row, value, onChange, options, idPrefix }) => (
  <tr data-testid={`${idPrefix}-row-${row.key}`}>
    <td className="text-xs p-2">{row.label}</td>
    {options.map(opt => (
      <td key={opt} className="text-center p-1">
        <input
          type="radio"
          name={`${idPrefix}-${row.key}`}
          checked={value?.rating === opt}
          onChange={() => onChange({ ...(value || {}), rating: opt })}
          data-testid={`${idPrefix}-${row.key}-${opt.toLowerCase().replace(/[^a-z]/g, '')}`}
        />
      </td>
    ))}
    <td className="p-1">
      <Input
        className="h-7 text-xs"
        value={value?.comments || ''}
        onChange={e => onChange({ ...(value || {}), comments: e.target.value })}
        placeholder="—"
      />
    </td>
  </tr>
);

const CheckBox = ({ checked, onChange, label, testid }) => (
  <label className="flex items-center gap-1.5 text-xs cursor-pointer" data-testid={testid}>
    <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
    <span>{label}</span>
  </label>
);

function emptyFormFor(kind) {
  if (kind === 'school_progress') {
    return {
      class_grade: '', school: '', term: '',
      academic_performance: {},
      attendance_discipline: {},
      social_emotional: {},
      strengths: '',
      areas_requiring_support: '',
    };
  }
  return {
    caregiver_name: '', caregiver_relationship: '', village_parish: '', district: '',
    welfare_indicators: {},
    education_checks: {},
    health_nutrition: {},
    protection_concerns: {},
    protection_details: '',
    household: {},
    child_voice: { going_well: '', challenges: '', support_wanted: '' },
    strengths: '',
    challenges: '',
  };
}

export default function SocialReviewsPanel({ child, kind }) {
  const isSchool = kind === 'school_progress';
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(() => ({
    review_date: new Date().toISOString().slice(0, 10),
    next_visit_date: '',
    overall_assessment: '',
    action_plan: [{ no: 1, concern: '', action: '', responsible: '', timeline: '' }],
    fields: emptyFormFor(kind),
  }));
  const [saving, setSaving] = useState(false);
  const [scanFile, setScanFile] = useState(null);

  const refresh = useCallback(async () => {
    if (!child?.id) return;
    setLoading(true);
    try {
      const r = await socialReviewsApi.list(child.id, kind);
      setList(r.data || []);
    } catch (e) { console.warn(e?.message || e); }
    finally { setLoading(false); }
  }, [child?.id, kind]);

  useEffect(() => { refresh(); }, [refresh]);

  const openCreate = () => {
    setEditingId(null);
    setForm({
      review_date: new Date().toISOString().slice(0, 10),
      next_visit_date: '',
      overall_assessment: '',
      action_plan: [{ no: 1, concern: '', action: '', responsible: '', timeline: '' }],
      fields: emptyFormFor(kind),
    });
    setShowCreate(true);
  };

  const openEdit = (rev) => {
    setEditingId(rev.id);
    setForm({
      review_date: rev.review_date || new Date().toISOString().slice(0, 10),
      next_visit_date: rev.next_visit_date || '',
      overall_assessment: rev.overall_assessment || '',
      action_plan: rev.action_plan?.length ? rev.action_plan : [{ no: 1, concern: '', action: '', responsible: '', timeline: '' }],
      fields: { ...emptyFormFor(kind), ...(rev.fields || {}) },
    });
    setShowCreate(true);
  };

  const submit = async () => {
    setSaving(true);
    try {
      const payload = {
        kind,
        review_date: form.review_date,
        next_visit_date: form.next_visit_date || undefined,
        overall_assessment: form.overall_assessment || '',
        action_plan: (form.action_plan || []).filter(a => a.concern || a.action || a.responsible),
        term: form.fields?.term || undefined,
        fields: form.fields,
      };
      if (editingId) {
        await socialReviewsApi.update(editingId, payload);
        toast.success('Review updated');
      } else {
        await socialReviewsApi.create(child.id, payload);
        toast.success('Review saved — child profile updated');
      }
      setShowCreate(false);
      setEditingId(null);
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };

  const remove = async (rev) => {
    if (!window.confirm('Delete this review? The child profile fields linked to it will keep their values until the next review overwrites them.')) return;
    try {
      await socialReviewsApi.remove(rev.id);
      toast.success('Deleted');
      await refresh();
    } catch (e) { toast.error('Delete failed'); }
  };

  const handlePrint = async () => {
    try {
      const r = await api.get(`/social-work/reviews/templates/${kind}.pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = isSchool ? 'school-progress-review-blank.pdf' : 'welfare-visit-blank.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not download template');
    }
  };

  const handleScanUpload = async (file) => {
    if (!file) return;
    const isImage = file.type?.startsWith('image/');
    const msg = toast.loading(isImage ? 'Uploading + running OCR (10–30s)…' : 'Uploading scan…');
    try {
      const r = await socialReviewsApi.uploadScan(child.id, file, kind);
      toast.dismiss(msg);
      const res = r.data || {};
      const ocr = res.ocr || {};
      if (ocr.ran) {
        const conf = ocr.confidence || 'medium';
        toast.success(`OCR complete (confidence: ${conf}) — review and edit if needed`);
      } else if (ocr.error) {
        toast.warning(`Scan uploaded — OCR skipped (${ocr.error}). Click the row to transcribe manually.`);
      } else {
        toast.success('Scan uploaded — transcribe via the in-app form when ready');
      }
      setScanFile(null);
      await refresh();
    } catch (e) {
      toast.dismiss(msg);
      toast.error(e.response?.data?.detail || 'Upload failed');
    }
  };

  const addActionRow = () => setForm({
    ...form,
    action_plan: [...(form.action_plan || []), { no: (form.action_plan?.length || 0) + 1, concern: '', action: '', responsible: '', timeline: '' }],
  });

  const updateField = (path, value) => {
    // path: 'academic_performance.overall' or 'fields.term' etc — we'll just merge under fields
    const parts = path.split('.');
    const next = { ...form.fields };
    let cursor = next;
    for (let i = 0; i < parts.length - 1; i++) {
      cursor[parts[i]] = { ...(cursor[parts[i]] || {}) };
      cursor = cursor[parts[i]];
    }
    cursor[parts[parts.length - 1]] = value;
    setForm({ ...form, fields: next });
  };

  return (
    <div className="space-y-3" data-testid={`reviews-panel-${kind}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-xs text-muted-foreground">
          {isSchool
            ? 'Termly school progress reviews. Print a blank form to take to school visits, then transcribe the teacher\'s ratings back here.'
            : 'Welfare and home-visit reviews. Captures protection concerns, household assessment, and the child\'s voice.'}
        </p>
        <div className="flex gap-1.5 flex-wrap">
          <Button size="sm" variant="outline" onClick={handlePrint} data-testid={`reviews-${kind}-print`}>
            <Printer size={12} className="mr-1" /> Print blank
          </Button>
          <label className="inline-flex" data-testid={`reviews-${kind}-upload-wrapper`}>
            <Button size="sm" variant="outline" asChild>
              <span><Upload size={12} className="mr-1" /> Upload scan</span>
            </Button>
            <input
              type="file"
              accept="application/pdf,image/*"
              className="hidden"
              onChange={e => handleScanUpload(e.target.files?.[0])}
              data-testid={`reviews-${kind}-upload-input`}
            />
          </label>
          <Button size="sm" onClick={openCreate} data-testid={`reviews-${kind}-new`}>
            <Plus size={12} className="mr-1" /> New review
          </Button>
          <Button size="sm" variant="ghost" onClick={refresh} disabled={loading} data-testid={`reviews-${kind}-refresh`}>
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      {list.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title={isSchool ? 'No school progress reviews yet' : 'No welfare visits yet'}
          description={isSchool
            ? 'Each term, fill a Child School Progress Review during a school visit. The data syncs into the child\'s education tab.'
            : 'Log a welfare visit after each home check-in. Protection concerns auto-flag on the child\'s profile.'}
          action={{ label: 'Add the first review', onClick: openCreate, testid: `reviews-${kind}-empty-add` }}
          testid={`reviews-${kind}-empty`}
        />
      ) : (
        <div className="space-y-2">
          {list.map(r => (
            <Card key={r.id} className="rounded-lg" data-testid={`review-row-${r.id}`}>
              <CardContent className="p-3 flex items-start justify-between gap-3 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-sm">{r.review_date}</p>
                    {r.overall_assessment && <Badge variant="outline" className="text-[10px]">{r.overall_assessment}</Badge>}
                    {r.status === 'draft_scan_only' && <Badge className="bg-amber-100 text-amber-700 text-[10px]">Scan attached — transcribe</Badge>}
                    {r.kind === 'welfare_visit' && Object.values(r.fields?.protection_concerns || {}).some(Boolean) && (
                      <Badge className="bg-rose-100 text-rose-700 text-[10px]"><AlertTriangle size={9} className="mr-1" /> Protection flag</Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {r.social_worker_name || 'Staff'}
                    {r.term ? ` · Term ${r.term}` : ''}
                    {r.next_visit_date ? ` · Next visit ${r.next_visit_date}` : ''}
                  </p>
                  {r.attached_scan_url && (
                    <a href={r.attached_scan_url} target="_blank" rel="noreferrer" className="text-[11px] text-primary inline-flex items-center gap-1 mt-1 hover:underline">
                      <FileText size={10} /> View attached scan
                    </a>
                  )}
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => openEdit(r)} data-testid={`review-edit-${r.id}`}>Edit</Button>
                  <Button size="sm" variant="ghost" className="h-7 text-destructive" onClick={() => remove(r)} data-testid={`review-delete-${r.id}`}>
                    <Trash2 size={11} />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ─── Fill-form dialog ────────────────────────────────────────── */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid={`reviews-${kind}-dialog`}>
          <DialogHeader>
            <DialogTitle>{isSchool ? 'School Progress Review' : 'Welfare Visit Review'}{editingId ? ' (editing)' : ''}</DialogTitle>
            <DialogDescription className="text-xs">{child?.name} · {child?.id}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 mt-2">
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1"><Label className="text-xs">Review date</Label>
                <Input type="date" value={form.review_date} onChange={e => setForm({ ...form, review_date: e.target.value })} data-testid={`reviews-${kind}-date`} />
              </div>
              {isSchool && (
                <>
                  <div className="space-y-1"><Label className="text-xs">School</Label>
                    <Input value={form.fields.school || ''} onChange={e => updateField('school', e.target.value)} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Class / Grade</Label>
                    <Input value={form.fields.class_grade || ''} onChange={e => updateField('class_grade', e.target.value)} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Term</Label>
                    <Input value={form.fields.term || ''} onChange={e => updateField('term', e.target.value)} placeholder="e.g. Term 1, 2026" />
                  </div>
                </>
              )}
              {!isSchool && (
                <>
                  <div className="space-y-1"><Label className="text-xs">Caregiver name</Label>
                    <Input value={form.fields.caregiver_name || ''} onChange={e => updateField('caregiver_name', e.target.value)} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Relationship</Label>
                    <Input value={form.fields.caregiver_relationship || ''} onChange={e => updateField('caregiver_relationship', e.target.value)} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Village / Parish</Label>
                    <Input value={form.fields.village_parish || ''} onChange={e => updateField('village_parish', e.target.value)} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">District</Label>
                    <Input value={form.fields.district || ''} onChange={e => updateField('district', e.target.value)} />
                  </div>
                </>
              )}
            </div>

            {/* SCHOOL: academic ratings */}
            {isSchool && (
              <div>
                <p className="text-xs font-semibold mt-2">Academic Performance</p>
                <table className="w-full border-collapse text-xs mt-1">
                  <thead><tr className="bg-muted/40">
                    <th className="p-1 text-left">Area</th>
                    {['Excellent', 'Good', 'Fair', 'Poor'].map(o => <th key={o} className="p-1">{o}</th>)}
                    <th className="p-1">Comments</th>
                  </tr></thead>
                  <tbody>
                    {ACADEMIC_ROWS.map(r => (
                      <RatingRow
                        key={r.key} row={r}
                        value={form.fields.academic_performance?.[r.key]}
                        onChange={v => updateField(`academic_performance.${r.key}`, v)}
                        options={['Excellent', 'Good', 'Fair', 'Poor']}
                        idPrefix="acad"
                      />
                    ))}
                  </tbody>
                </table>

                <p className="text-xs font-semibold mt-3">Attendance &amp; Discipline</p>
                <table className="w-full border-collapse text-xs mt-1">
                  <thead><tr className="bg-muted/40"><th className="p-1 text-left">Indicator</th><th className="p-1">Yes</th><th className="p-1">No</th><th className="p-1">Comments</th></tr></thead>
                  <tbody>
                    {ATTENDANCE_ROWS.map(r => (
                      <RatingRow
                        key={r.key} row={r}
                        value={form.fields.attendance_discipline?.[r.key]}
                        onChange={v => updateField(`attendance_discipline.${r.key}`, v)}
                        options={['Yes', 'No']}
                        idPrefix="att"
                      />
                    ))}
                  </tbody>
                </table>

                <p className="text-xs font-semibold mt-3">Social &amp; Emotional Development</p>
                <table className="w-full border-collapse text-xs mt-1">
                  <thead><tr className="bg-muted/40"><th className="p-1 text-left">Indicator</th><th className="p-1">Good</th><th className="p-1">Fair</th><th className="p-1">Poor</th><th className="p-1">Comments</th></tr></thead>
                  <tbody>
                    {SOCIAL_EMOTIONAL_ROWS.map(r => (
                      <RatingRow
                        key={r.key} row={r}
                        value={form.fields.social_emotional?.[r.key]}
                        onChange={v => updateField(`social_emotional.${r.key}`, v)}
                        options={['Good', 'Fair', 'Poor']}
                        idPrefix="se"
                      />
                    ))}
                  </tbody>
                </table>

                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div className="space-y-1"><Label className="text-xs">Strengths</Label>
                    <Textarea rows={3} value={form.fields.strengths || ''} onChange={e => updateField('strengths', e.target.value)} data-testid="reviews-school_progress-strengths" />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Areas requiring support</Label>
                    <Textarea rows={3} value={form.fields.areas_requiring_support || ''} onChange={e => updateField('areas_requiring_support', e.target.value)} data-testid="reviews-school_progress-areas" />
                  </div>
                </div>
              </div>
            )}

            {/* WELFARE VISIT */}
            {!isSchool && (
              <div>
                <p className="text-xs font-semibold mt-2">Welfare Assessment</p>
                <table className="w-full border-collapse text-xs mt-1">
                  <thead><tr className="bg-muted/40"><th className="p-1 text-left">Indicator</th><th className="p-1">Good</th><th className="p-1">Fair</th><th className="p-1">Poor</th><th className="p-1">Comments</th></tr></thead>
                  <tbody>
                    {WELFARE_ROWS.map(r => (
                      <RatingRow
                        key={r.key} row={r}
                        value={form.fields.welfare_indicators?.[r.key]}
                        onChange={v => updateField(`welfare_indicators.${r.key}`, v)}
                        options={['Good', 'Fair', 'Poor']}
                        idPrefix="wel"
                      />
                    ))}
                  </tbody>
                </table>

                <p className="text-xs font-semibold mt-3">Education status</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-1">
                  {EDUCATION_CHECKS.map(c => (
                    <CheckBox
                      key={c.key} label={c.label}
                      checked={form.fields.education_checks?.[c.key]}
                      onChange={v => updateField(`education_checks.${c.key}`, v)}
                      testid={`reviews-welfare_visit-edu-${c.key}`}
                    />
                  ))}
                </div>

                <p className="text-xs font-semibold mt-3">Health &amp; nutrition</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-1">
                  {HEALTH_CHECKS.map(c => (
                    <CheckBox
                      key={c.key} label={c.label}
                      checked={form.fields.health_nutrition?.[c.key]}
                      onChange={v => updateField(`health_nutrition.${c.key}`, v)}
                      testid={`reviews-welfare_visit-health-${c.key}`}
                    />
                  ))}
                </div>

                <p className="text-xs font-semibold mt-3 text-rose-700">Protection concerns (tick any that apply)</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-1">
                  {PROTECTION_FLAGS.map(c => (
                    <CheckBox
                      key={c.key} label={c.label}
                      checked={form.fields.protection_concerns?.[c.key]}
                      onChange={v => updateField(`protection_concerns.${c.key}`, v)}
                      testid={`reviews-welfare_visit-protection-${c.key}`}
                    />
                  ))}
                </div>
                <div className="space-y-1 mt-2"><Label className="text-xs">Details (if any protection flag is ticked)</Label>
                  <Textarea rows={2} value={form.fields.protection_details || ''} onChange={e => updateField('protection_details', e.target.value)} data-testid="reviews-welfare_visit-protection-details" />
                </div>

                <p className="text-xs font-semibold mt-3">Household &amp; family environment</p>
                <table className="w-full border-collapse text-xs mt-1">
                  <thead><tr className="bg-muted/40"><th className="p-1 text-left">Indicator</th><th className="p-1">Good</th><th className="p-1">Fair</th><th className="p-1">Poor</th><th className="p-1">Comments</th></tr></thead>
                  <tbody>
                    {HOUSEHOLD_ROWS.map(r => (
                      <RatingRow
                        key={r.key} row={r}
                        value={form.fields.household?.[r.key]}
                        onChange={v => updateField(`household.${r.key}`, v)}
                        options={['Good', 'Fair', 'Poor']}
                        idPrefix="hh"
                      />
                    ))}
                  </tbody>
                </table>

                <p className="text-xs font-semibold mt-3">Child&apos;s voice</p>
                <div className="space-y-2 mt-1">
                  <div className="space-y-1"><Label className="text-xs">What is going well at home / school?</Label>
                    <Textarea rows={2} value={form.fields.child_voice?.going_well || ''} onChange={e => updateField('child_voice.going_well', e.target.value)} data-testid="reviews-welfare_visit-voice-going-well" />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">What challenges are you facing?</Label>
                    <Textarea rows={2} value={form.fields.child_voice?.challenges || ''} onChange={e => updateField('child_voice.challenges', e.target.value)} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">What support would you like?</Label>
                    <Textarea rows={2} value={form.fields.child_voice?.support_wanted || ''} onChange={e => updateField('child_voice.support_wanted', e.target.value)} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div className="space-y-1"><Label className="text-xs">Strengths and positive changes</Label>
                    <Textarea rows={3} value={form.fields.strengths || ''} onChange={e => updateField('strengths', e.target.value)} />
                  </div>
                  <div className="space-y-1"><Label className="text-xs">Key challenges identified</Label>
                    <Textarea rows={3} value={form.fields.challenges || ''} onChange={e => updateField('challenges', e.target.value)} />
                  </div>
                </div>
              </div>
            )}

            {/* Action plan */}
            <div>
              <div className="flex items-center justify-between mt-3">
                <p className="text-xs font-semibold">Action Plan</p>
                <Button size="sm" variant="ghost" onClick={addActionRow} data-testid={`reviews-${kind}-add-action`}><Plus size={11} className="mr-1" /> Row</Button>
              </div>
              <table className="w-full border-collapse text-xs mt-1">
                <thead><tr className="bg-muted/40"><th className="p-1 text-center" style={{ width: 30 }}>#</th><th className="p-1 text-left">Identified concern / need</th><th className="p-1 text-left">Action required</th><th className="p-1 text-left">Responsible</th><th className="p-1 text-left" style={{ width: 90 }}>Timeline</th></tr></thead>
                <tbody>
                  {(form.action_plan || []).map((a, i) => (
                    <tr key={i} data-testid={`action-row-${i}`}>
                      <td className="p-1 text-center">{i + 1}</td>
                      <td className="p-1"><Input className="h-7 text-xs" value={a.concern} onChange={e => { const np = [...form.action_plan]; np[i] = { ...np[i], concern: e.target.value }; setForm({ ...form, action_plan: np }); }} /></td>
                      <td className="p-1"><Input className="h-7 text-xs" value={a.action} onChange={e => { const np = [...form.action_plan]; np[i] = { ...np[i], action: e.target.value }; setForm({ ...form, action_plan: np }); }} /></td>
                      <td className="p-1"><Input className="h-7 text-xs" value={a.responsible} onChange={e => { const np = [...form.action_plan]; np[i] = { ...np[i], responsible: e.target.value }; setForm({ ...form, action_plan: np }); }} /></td>
                      <td className="p-1"><Input className="h-7 text-xs" value={a.timeline} onChange={e => { const np = [...form.action_plan]; np[i] = { ...np[i], timeline: e.target.value }; setForm({ ...form, action_plan: np }); }} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="grid grid-cols-2 gap-3 mt-3">
              <div className="space-y-1"><Label className="text-xs">Overall assessment</Label>
                <select
                  className="w-full border rounded h-9 px-2 text-sm bg-background"
                  value={form.overall_assessment}
                  onChange={e => setForm({ ...form, overall_assessment: e.target.value })}
                  data-testid={`reviews-${kind}-overall`}
                >
                  <option value="">— pick one —</option>
                  {(isSchool ? SCHOOL_OVERALL : WELFARE_OVERALL).map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
              {!isSchool && (
                <div className="space-y-1"><Label className="text-xs">Next visit date</Label>
                  <Input type="date" value={form.next_visit_date} onChange={e => setForm({ ...form, next_visit_date: e.target.value })} data-testid="reviews-welfare_visit-next-visit" />
                </div>
              )}
            </div>

            <div className="flex gap-2 pt-3 border-t mt-2">
              <Button variant="ghost" onClick={() => setShowCreate(false)} className="flex-1">Cancel</Button>
              <Button onClick={submit} disabled={saving} className="flex-1" data-testid={`reviews-${kind}-submit`}>
                {saving ? 'Saving…' : (editingId ? 'Update review' : 'Save review')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
