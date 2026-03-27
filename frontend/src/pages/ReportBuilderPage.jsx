import React, { useState, useEffect } from 'react';
import { FileText, Plus, Download, Play, Trash2, Edit2, Save, X, Filter, Columns, Clock, Share2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { reportBuilderApi, locationsApi } from '../services/api';
import { toast } from 'sonner';

const REPORT_TYPES = [
  { value: 'members', label: 'Members Report', icon: '👥' },
  { value: 'financial', label: 'Financial Report', icon: '💰' },
  { value: 'events', label: 'Events Report', icon: '📅' },
  { value: 'attendance', label: 'Attendance Report', icon: '✓' },
  { value: 'custom', label: 'Custom Report', icon: '📊' },
];

const SCHEDULE_OPTIONS = [
  { value: 'manual', label: 'Manual' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
];

export default function ReportBuilderPage() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(null);
  const [showPreview, setShowPreview] = useState(null);
  const [generating, setGenerating] = useState(null);
  const [locations, setLocations] = useState([]);

  const [form, setForm] = useState({
    title: '',
    type: 'custom',
    is_shared: false,
    auto_update: true,
    schedule: 'manual',
    filters: { location_id: '', status: '', date_from: '', date_to: '' },
    columns: [],
  });

  useEffect(() => {
    fetchReports();
    locationsApi.list().then(r => setLocations(r.data || [])).catch(() => {});
  }, []);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const res = await reportBuilderApi.list();
      setReports(res.data || []);
    } catch {
      toast.error('Failed to load reports');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.title.trim()) {
      toast.error('Please enter a report title');
      return;
    }
    try {
      const res = await reportBuilderApi.create(form);
      setReports(prev => [res.data, ...prev]);
      setShowCreate(false);
      resetForm();
      toast.success('Report created');
    } catch {
      toast.error('Failed to create report');
    }
  };

  const handleUpdate = async () => {
    if (!showEdit?.id) return;
    try {
      await reportBuilderApi.update(showEdit.id, form);
      setReports(prev => prev.map(r => r.id === showEdit.id ? { ...r, ...form } : r));
      setShowEdit(null);
      resetForm();
      toast.success('Report updated');
    } catch {
      toast.error('Failed to update report');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this report?')) return;
    try {
      await reportBuilderApi.delete(id);
      setReports(prev => prev.filter(r => r.id !== id));
      toast.success('Report deleted');
    } catch {
      toast.error('Failed to delete report');
    }
  };

  const handleGenerate = async (report) => {
    setGenerating(report.id);
    try {
      const res = await reportBuilderApi.generate(report.id);
      setShowPreview({ ...report, data: res.data.data, generated_at: res.data.generated_at });
      toast.success('Report generated');
      fetchReports();
    } catch {
      toast.error('Failed to generate report');
    } finally {
      setGenerating(null);
    }
  };

  const handleExportXlsx = (report) => {
    const url = reportBuilderApi.exportXlsx(report.id);
    window.open(url, '_blank');
  };

  const resetForm = () => {
    setForm({
      title: '',
      type: 'custom',
      is_shared: false,
      auto_update: true,
      schedule: 'manual',
      filters: { location_id: '', status: '', date_from: '', date_to: '' },
      columns: [],
    });
  };

  const openEdit = (report) => {
    setForm({
      title: report.title,
      type: report.type,
      is_shared: report.is_shared,
      auto_update: report.auto_update,
      schedule: report.schedule,
      filters: report.filters || {},
      columns: report.columns || [],
    });
    setShowEdit(report);
  };

  return (
    <div className="p-6 space-y-6" data-testid="report-builder-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold font-heading">Report Builder</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Create custom reports with auto-updating data</p>
        </div>
        <Button className="gap-2" onClick={() => setShowCreate(true)} data-testid="create-report-btn">
          <Plus size={16} /> Create Report
        </Button>
      </div>

      {/* Reports List */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-40 bg-muted animate-pulse rounded-xl" />
          ))}
        </div>
      ) : reports.length === 0 ? (
        <Card className="shadow-soft rounded-xl">
          <CardContent className="py-16 text-center">
            <FileText size={48} className="mx-auto mb-3 opacity-30 text-muted-foreground" />
            <p className="text-muted-foreground mb-4">No custom reports yet</p>
            <Button onClick={() => setShowCreate(true)} className="gap-2">
              <Plus size={14} /> Create Your First Report
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {reports.map(report => (
            <Card key={report.id} className="shadow-soft rounded-xl hover:shadow-md transition-shadow" data-testid={`report-card-${report.id}`}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{REPORT_TYPES.find(t => t.value === report.type)?.icon || '📊'}</span>
                    <div>
                      <p className="font-semibold text-sm">{report.title}</p>
                      <p className="text-xs text-muted-foreground capitalize">{report.type} report</p>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    {report.is_shared && <Badge variant="outline" className="text-xs">Shared</Badge>}
                    {report.auto_update && <Badge variant="secondary" className="text-xs">Auto</Badge>}
                  </div>
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4">
                  <Clock size={12} />
                  {report.last_generated ? (
                    <span>Generated {new Date(report.last_generated).toLocaleDateString()}</span>
                  ) : (
                    <span>Never generated</span>
                  )}
                </div>

                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1 gap-1.5"
                    onClick={() => handleGenerate(report)}
                    disabled={generating === report.id}
                    data-testid={`generate-report-${report.id}`}
                  >
                    <Play size={12} />
                    {generating === report.id ? 'Generating...' : 'Generate'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleExportXlsx(report)}
                    disabled={!report.last_generated}
                    data-testid={`export-report-${report.id}`}
                  >
                    <Download size={12} />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => openEdit(report)}>
                    <Edit2 size={12} />
                  </Button>
                  <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => handleDelete(report.id)}>
                    <Trash2 size={12} />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate || !!showEdit} onOpenChange={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{showEdit ? 'Edit Report' : 'Create Report'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Report Title *</Label>
              <Input
                placeholder="e.g., Monthly Member Summary"
                value={form.title}
                onChange={e => setForm({ ...form, title: e.target.value })}
                data-testid="report-title-input"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Report Type</Label>
                <Select value={form.type} onValueChange={v => setForm({ ...form, type: v })}>
                  <SelectTrigger data-testid="report-type-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {REPORT_TYPES.map(t => (
                      <SelectItem key={t.value} value={t.value}>{t.icon} {t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Schedule</Label>
                <Select value={form.schedule} onValueChange={v => setForm({ ...form, schedule: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SCHEDULE_OPTIONS.map(s => (
                      <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="p-3 rounded-lg border border-border space-y-3">
              <p className="text-sm font-medium flex items-center gap-2"><Filter size={14} /> Filters</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Location</Label>
                  <Select value={form.filters.location_id || '_all'} onValueChange={v => setForm({ ...form, filters: { ...form.filters, location_id: v === '_all' ? '' : v } })}>
                    <SelectTrigger className="h-8"><SelectValue placeholder="All" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_all">All Locations</SelectItem>
                      {locations.map(l => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Status</Label>
                  <Select value={form.filters.status || '_all'} onValueChange={v => setForm({ ...form, filters: { ...form.filters, status: v === '_all' ? '' : v } })}>
                    <SelectTrigger className="h-8"><SelectValue placeholder="All" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_all">All Status</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="inactive">Inactive</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Date From</Label>
                  <Input type="date" className="h-8" value={form.filters.date_from || ''} onChange={e => setForm({ ...form, filters: { ...form.filters, date_from: e.target.value } })} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Date To</Label>
                  <Input type="date" className="h-8" value={form.filters.date_to || ''} onChange={e => setForm({ ...form, filters: { ...form.filters, date_to: e.target.value } })} />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Share with Team</p>
                <p className="text-xs text-muted-foreground">Make visible to other users</p>
              </div>
              <Switch checked={form.is_shared} onCheckedChange={v => setForm({ ...form, is_shared: v })} />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border">
              <div>
                <p className="text-sm font-medium">Auto-Update Data</p>
                <p className="text-xs text-muted-foreground">Keep report data fresh automatically</p>
              </div>
              <Switch checked={form.auto_update} onCheckedChange={v => setForm({ ...form, auto_update: v })} />
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowCreate(false); setShowEdit(null); resetForm(); }}>
                Cancel
              </Button>
              <Button className="flex-1 gap-2" onClick={showEdit ? handleUpdate : handleCreate} data-testid="save-report-btn">
                <Save size={14} /> {showEdit ? 'Update Report' : 'Create Report'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={!!showPreview} onOpenChange={() => setShowPreview(null)}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText size={18} /> {showPreview?.title}
            </DialogTitle>
          </DialogHeader>
          {showPreview?.data && (
            <div className="space-y-4 mt-2">
              <p className="text-sm text-muted-foreground">Generated: {new Date(showPreview.generated_at).toLocaleString()}</p>
              
              <Tabs defaultValue={Object.keys(showPreview.data).find(k => Array.isArray(showPreview.data[k]))}>
                <TabsList>
                  {Object.keys(showPreview.data).filter(k => Array.isArray(showPreview.data[k])).map(key => (
                    <TabsTrigger key={key} value={key} className="capitalize">{key}</TabsTrigger>
                  ))}
                </TabsList>
                {Object.keys(showPreview.data).filter(k => Array.isArray(showPreview.data[k])).map(key => (
                  <TabsContent key={key} value={key} className="mt-4">
                    <div className="rounded-lg border border-border overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-muted/50">
                          <tr>
                            {showPreview.data[key][0] && Object.keys(showPreview.data[key][0]).slice(0, 8).map(col => (
                              <th key={col} className="px-3 py-2 text-left font-medium text-muted-foreground capitalize">{col.replace(/_/g, ' ')}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {showPreview.data[key].slice(0, 20).map((row, i) => (
                            <tr key={i} className="hover:bg-muted/30">
                              {Object.keys(row).slice(0, 8).map(col => (
                                <td key={col} className="px-3 py-2 truncate max-w-[200px]">{String(row[col] ?? '')}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">Showing {Math.min(20, showPreview.data[key].length)} of {showPreview.data[key].length} rows</p>
                  </TabsContent>
                ))}
              </Tabs>

              <div className="flex gap-3">
                <Button variant="outline" className="gap-2" onClick={() => handleExportXlsx(showPreview)}>
                  <Download size={14} /> Export to Excel
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
