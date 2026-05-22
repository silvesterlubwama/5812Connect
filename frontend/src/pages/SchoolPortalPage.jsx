/**
 * SchoolPortalPage — public, password-gated portal for external school staff.
 * Lives at /school-portal/:portal_token
 *
 * Auth model:
 *   - User pastes the password their social worker sent them.
 *   - We POST {portal_token, password} → /api/school-portal/login and receive
 *     a session token good for 6 hours.
 *   - Token is held in component state only (NOT localStorage — short-lived
 *     and avoids XSS persistence for an external-user surface).
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { GraduationCap, Lock, Clock, FileText, ArrowLeft, LogOut, AlertCircle, BookOpen, Heart } from 'lucide-react';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function SchoolPortalPage() {
  const { portalToken } = useParams();
  const [session, setSession] = useState(null);  // { session_token, school_id, school_name, expires_at }
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState('');

  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [studentDetail, setStudentDetail] = useState(null);

  // Add-note dialog state
  const [showAddNote, setShowAddNote] = useState(false);
  const [noteForm, setNoteForm] = useState({ kind: 'school', body: '', attachment_url: '', attachment_name: '' });

  // Live session-expiry countdown
  const [secondsLeft, setSecondsLeft] = useState(null);
  useEffect(() => {
    if (!session) return;
    const tick = () => {
      const remaining = Math.max(0, Math.floor((new Date(session.expires_at).getTime() - Date.now()) / 1000));
      setSecondsLeft(remaining);
      if (remaining <= 0) {
        toast.error('Session expired — please log in again.');
        setSession(null);
      }
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [session]);

  const login = async (e) => {
    e?.preventDefault?.();
    if (!password.trim()) return;
    setSubmitting(true); setLoginError('');
    try {
      const r = await axios.post(`${API}/school-portal/login`, {
        portal_token: portalToken,
        password: password.trim(),
      });
      setSession(r.data);
      setPassword('');
    } catch (err) {
      setLoginError(err.response?.data?.detail || 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  const loadMe = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/school-portal/me`, {
        headers: { Authorization: `Bearer ${session.session_token}` },
      });
      setMe(r.data);
    } catch (err) {
      if (err.response?.status === 401) setSession(null);
      else toast.error('Failed to load students');
    } finally { setLoading(false); }
  }, [session]);
  useEffect(() => { loadMe(); }, [loadMe]);

  const openStudent = async (caseRow) => {
    setSelectedStudent(caseRow);
    setStudentDetail(null);
    try {
      const r = await axios.get(`${API}/school-portal/students/${caseRow.id}`, {
        headers: { Authorization: `Bearer ${session.session_token}` },
      });
      setStudentDetail(r.data);
    } catch (err) { toast.error('Failed to load student detail'); }
  };

  const submitNote = async () => {
    if (!noteForm.body.trim()) { toast.error('Note body required'); return; }
    try {
      const attachments = noteForm.attachment_url.trim()
        ? [{ name: noteForm.attachment_name || 'Attachment', url: noteForm.attachment_url.trim() }]
        : [];
      await axios.post(
        `${API}/school-portal/students/${selectedStudent.id}/notes`,
        { kind: noteForm.kind, body: noteForm.body, attachments },
        { headers: { Authorization: `Bearer ${session.session_token}` } },
      );
      toast.success('Submitted to 58:12 social work team');
      setShowAddNote(false);
      setNoteForm({ kind: 'school', body: '', attachment_url: '', attachment_name: '' });
      openStudent(selectedStudent);  // refresh notes
    } catch (err) { toast.error(err.response?.data?.detail || 'Submission failed'); }
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/school-portal/logout`, {}, {
        headers: { Authorization: `Bearer ${session?.session_token}` },
      });
    } catch { /* best-effort */ }
    setSession(null); setMe(null); setSelectedStudent(null);
  };

  // -------- LOGIN VIEW --------
  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-950">
        <Card className="w-full max-w-md rounded-2xl shadow-lg" data-testid="school-portal-login">
          <CardHeader className="text-center">
            <div className="mx-auto h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center mb-2">
              <GraduationCap size={24} className="text-primary" />
            </div>
            <CardTitle>School Portal</CardTitle>
            <CardDescription>
              Enter the password your 58:12 social worker shared with you.
              <br />
              <span className="text-[10px] text-muted-foreground font-mono break-all mt-1 inline-block">{portalToken}</span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={login} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs">One-time Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="paste password here"
                  autoFocus
                  required
                  data-testid="portal-password-input"
                />
              </div>
              {loginError && (
                <div className="text-xs text-red-600 flex items-center gap-1.5 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/30 rounded p-2" data-testid="portal-login-error">
                  <AlertCircle size={12} /> {loginError}
                </div>
              )}
              <Button type="submit" className="w-full" disabled={submitting || !password.trim()} data-testid="portal-login-btn">
                <Lock size={14} className="mr-1.5" />
                {submitting ? 'Logging in...' : 'Log In'}
              </Button>
              <p className="text-[10px] text-muted-foreground text-center pt-2">
                If your password has expired, please contact the 58:12 social work team to request a new one.
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  // -------- LOGGED IN: STUDENT LIST OR DETAIL --------
  const fmtSeconds = (s) => {
    const h = Math.floor(s / 3600); const m = Math.floor((s % 3600) / 60); const sec = s % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen p-4 sm:p-6 bg-slate-50 dark:bg-slate-950">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <GraduationCap size={20} className="text-primary" /> {me?.school?.name || 'School Portal'}
            </h1>
            {me?.school?.head_teacher && <p className="text-xs text-muted-foreground mt-0.5">Head Teacher: {me.school.head_teacher}</p>}
          </div>
          <div className="flex items-center gap-2">
            {secondsLeft !== null && (
              <Badge variant="outline" className="gap-1 text-xs" data-testid="portal-session-timer">
                <Clock size={11} /> {fmtSeconds(secondsLeft)} left
              </Badge>
            )}
            <Button variant="outline" size="sm" onClick={logout} data-testid="portal-logout-btn">
              <LogOut size={13} className="mr-1" />Log out
            </Button>
          </div>
        </div>

        {!selectedStudent && (
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-base">Students at your school ({me?.students?.length || 0})</CardTitle>
              <CardDescription className="text-xs">
                Click a student to upload report cards, attendance notes, or to flag any disciplinary / medical issues.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {loading && [1, 2, 3].map(i => <div key={i} className="h-16 bg-muted animate-pulse rounded" />)}
              {!loading && me?.students?.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No students currently registered at your school in our system. If you believe this is wrong, please contact your social worker.
                </p>
              )}
              {!loading && (me?.students || []).map(s => (
                <div
                  key={s.id}
                  onClick={() => openStudent(s)}
                  className="flex items-center gap-3 p-3 rounded-lg border hover:border-primary cursor-pointer transition-colors"
                  data-testid={`portal-student-${s.id}`}
                >
                  {s.subject_photo_url
                    ? <img src={s.subject_photo_url} alt="" className="h-10 w-10 rounded-full object-cover" />
                    : <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold">{(s.subject_name || '?').slice(0, 1)}</div>}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{s.subject_name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {s.education?.grade ? `Grade ${s.education.grade}` : 'Grade not set'}
                      {s.subject_dob ? ` · DOB ${s.subject_dob.slice(0, 10)}` : ''}
                    </p>
                  </div>
                  <Badge variant="outline" className="text-[10px] capitalize">{s.category?.replace('_', ' ')}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {selectedStudent && studentDetail && (
          <div className="space-y-3">
            <Button variant="ghost" size="sm" onClick={() => { setSelectedStudent(null); setStudentDetail(null); }} data-testid="portal-back-btn">
              <ArrowLeft size={14} className="mr-1" />Back to students
            </Button>
            <Card className="rounded-xl">
              <CardHeader className="flex flex-row items-center gap-3 space-y-0">
                {studentDetail.student.subject_photo_url
                  ? <img src={studentDetail.student.subject_photo_url} alt="" className="h-14 w-14 rounded-full object-cover" />
                  : <div className="h-14 w-14 rounded-full bg-primary/10 flex items-center justify-center text-primary text-lg font-semibold">{(studentDetail.student.subject_name || '?').slice(0, 1)}</div>}
                <div className="flex-1">
                  <CardTitle className="text-base" data-testid="portal-student-name">{studentDetail.student.subject_name}</CardTitle>
                  <CardDescription className="text-xs">
                    {studentDetail.student.education?.grade ? `Grade ${studentDetail.student.education.grade}` : 'Grade —'}
                    {studentDetail.student.subject_dob ? ` · DOB ${studentDetail.student.subject_dob.slice(0, 10)}` : ''}
                    {studentDetail.student.education?.enrollment_date ? ` · enrolled ${studentDetail.student.education.enrollment_date.slice(0, 10)}` : ''}
                  </CardDescription>
                </div>
                <Button size="sm" onClick={() => setShowAddNote(true)} data-testid="portal-add-note-btn">
                  <FileText size={13} className="mr-1" />Submit note / report card
                </Button>
              </CardHeader>
              <CardContent>
                {/* Medical heads-up (limited info) */}
                {studentDetail.student.medical_summary && (studentDetail.student.medical_summary.allergies?.length > 0 || studentDetail.student.medical_summary.receives_medical_support) && (
                  <div className="text-xs bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/30 rounded p-2.5 mb-3 flex items-start gap-2" data-testid="portal-medical-alert">
                    <Heart size={12} className="text-amber-600 mt-0.5" />
                    <div>
                      <strong>Medical:</strong>
                      {studentDetail.student.medical_summary.allergies?.length > 0 && (
                        <span> Allergies: {studentDetail.student.medical_summary.allergies.join(', ')}.</span>
                      )}
                      {studentDetail.student.medical_summary.receives_medical_support && <span> Receives medical support.</span>}
                    </div>
                  </div>
                )}
                {studentDetail.student.education?.extracurricular?.length > 0 && (
                  <div className="text-xs mb-3">
                    <strong>Extracurricular:</strong>{' '}
                    {studentDetail.student.education.extracurricular.map((a, i) => (
                      <Badge key={i} variant="outline" className="text-[10px] mr-1">{a}</Badge>
                    ))}
                  </div>
                )}
                {/* Previous entries from this school */}
                <h4 className="text-xs uppercase font-semibold text-muted-foreground mb-2 flex items-center gap-1.5"><BookOpen size={11} /> Previous entries</h4>
                {studentDetail.notes.length === 0
                  ? <p className="text-xs text-muted-foreground text-center py-4">No school entries yet — be the first to add one.</p>
                  : (
                    <div className="space-y-2">
                      {studentDetail.notes.map(n => (
                        <div key={n.id} className="p-2 rounded border" data-testid={`portal-note-${n.id}`}>
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <Badge variant="outline" className="text-[10px] capitalize">{n.kind}</Badge>
                            <span className="text-[10px] text-muted-foreground">{n.created_at?.slice(0, 16).replace('T', ' ')} · {n.created_by_name}</span>
                          </div>
                          <p className="text-sm whitespace-pre-wrap">{n.body}</p>
                          {(n.attachments || []).map((a, i) => (
                            <a key={i} href={a.url} target="_blank" rel="noopener noreferrer" className="text-[10px] text-primary underline mt-1 inline-block mr-2">📎 {a.name || 'Attachment'}</a>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
              </CardContent>
            </Card>
          </div>
        )}

        {selectedStudent && !studentDetail && (
          <div className="space-y-2">{[1, 2].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded" />)}</div>
        )}
      </div>

      {/* Add Note Dialog */}
      <Dialog open={showAddNote} onOpenChange={setShowAddNote}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Submit note / report card</DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Type</Label>
              <Select value={noteForm.kind} onValueChange={v => setNoteForm({ ...noteForm, kind: v })}>
                <SelectTrigger data-testid="portal-note-kind"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="school">School (report card, grade, behaviour)</SelectItem>
                  <SelectItem value="medical">Medical (illness, injury at school)</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Message *</Label>
              <Textarea rows={5} value={noteForm.body} onChange={e => setNoteForm({ ...noteForm, body: e.target.value })} placeholder="Term results, attendance summary, disciplinary concerns, requirements for next term, etc." data-testid="portal-note-body" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Attachment URL (optional)</Label>
              <Input type="url" value={noteForm.attachment_url} onChange={e => setNoteForm({ ...noteForm, attachment_url: e.target.value })} placeholder="https://drive.google.com/..." />
              {noteForm.attachment_url && (
                <Input placeholder="Attachment label (e.g. 'Term 1 Report')" value={noteForm.attachment_name} onChange={e => setNoteForm({ ...noteForm, attachment_name: e.target.value })} className="mt-1" />
              )}
            </div>
            <p className="text-[10px] text-muted-foreground">
              This will be visible to the 58:12 social work team. Please do not upload sensitive medical details — call us instead.
            </p>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowAddNote(false)}>Cancel</Button>
              <Button className="flex-1" onClick={submitNote} disabled={!noteForm.body.trim()} data-testid="portal-note-submit">Submit</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
