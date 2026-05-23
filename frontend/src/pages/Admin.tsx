import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BarChart3, CheckCircle2, Clock3, Database, Edit3, RefreshCw, Save, Shield, Ticket, Trash2, UploadCloud, UserCheck, UserPlus, X, XCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface UploadAudit {
  job_id: string;
  document_id?: string;
  title: string;
  filename?: string;
  domain?: string;
  source_type?: string;
  source?: string;
  uploader?: {
    email?: string;
    username?: string;
  };
  status: string;
  stage?: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  error?: string;
  deleted_at?: string;
  delete_reason?: string;
  cleanup_status?: string;
  cleanup_detail?: string;
  cleanup_completed_at?: string;
  duplicate_of_document_id?: string;
  stats?: {
    chunks?: number;
    entities?: number;
    relations?: number;
  };
}

interface AdminOverview {
  totals: {
    uploads: number;
    completed: number;
    failed: number;
    rejected?: number;
    deleted?: number;
    active: number;
    chunks: number;
    entities: number;
    relations: number;
  };
  daily: Array<{ date: string; uploads: number }>;
  recent_uploads: UploadAudit[];
}

interface RagUnlimitedUser {
  email: string;
  note?: string;
  created_by_user_id?: string;
  created_at: string;
}

const apiBase = () => {
  const host = window.location.hostname || '127.0.0.1';
  const localApiHost = host === 'localhost' || host === '127.0.0.1';
  return process.env.REACT_APP_ESG_API_BASE || (localApiHost ? 'http://127.0.0.1:8000' : '');
};

const formatDateTime = (value?: string) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const statusClass = (status: string) => {
  if (status === 'completed') return 'bg-emerald-50 text-emerald-700 ring-emerald-200';
  if (status === 'failed') return 'bg-red-50 text-red-700 ring-red-200';
  if (status === 'rejected') return 'bg-amber-50 text-amber-700 ring-amber-200';
  if (status === 'deleted_with_warnings') return 'bg-amber-50 text-amber-700 ring-amber-200';
  if (status === 'deleted') return 'bg-hairline text-ink-charcoal ring-hairline';
  if (status === 'running') return 'bg-blue-50 text-blue-700 ring-blue-200';
  return 'bg-surface-soft text-ink-charcoal ring-hairline';
};

const cleanupClass = (status?: string) => {
  if (status === 'cleanup_completed') return 'text-emerald-700';
  if (status === 'cleanup_failed') return 'text-amber-700';
  if (status === 'cleanup_pending') return 'text-blue-700';
  if (status === 'cleanup_skipped') return 'text-ink-steel';
  return 'text-ink-stone';
};

const domainOptions = [
  { value: 'general', label: 'General' },
  { value: 'esg_report', label: 'ESG report' },
  { value: 'academic', label: 'Academic prior' },
  { value: 'regulatory', label: 'Regulatory context' },
  { value: 'news', label: 'News' },
  { value: 'environmental', label: 'Environmental' },
  { value: 'social', label: 'Social' },
  { value: 'governance', label: 'Governance' },
];

const sourceTypeOptions = [
  { value: '', label: 'Auto-detect' },
  { value: 'corporate_disclosure', label: 'Corporate disclosure' },
  { value: 'peer_reviewed', label: 'Peer reviewed' },
  { value: 'regulatory_doc', label: 'Regulatory document' },
  { value: 'analyst_report', label: 'Analyst report' },
  { value: 'news_article', label: 'News article' },
  { value: 'uploaded_file', label: 'Uploaded file' },
  { value: 'manual_input', label: 'Manual input' },
];

const Admin: React.FC = () => {
  const { token, user } = useAuth();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [uploads, setUploads] = useState<UploadAudit[]>([]);
  const [ragUnlimitedUsers, setRagUnlimitedUsers] = useState<RagUnlimitedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editingJobId, setEditingJobId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ title: '', domain: '', source_type: '', source: '' });
  const [actionMessage, setActionMessage] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [inviteExpiresAt, setInviteExpiresAt] = useState('');
  const [showAccessControls, setShowAccessControls] = useState(false);
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [unlimitedEmail, setUnlimitedEmail] = useState('');
  const [unlimitedNote, setUnlimitedNote] = useState('');
  const [savingUnlimitedUser, setSavingUnlimitedUser] = useState(false);
  const base = useMemo(apiBase, []);

  const loadAdminData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
      const [overviewRes, uploadsRes, unlimitedUsersRes] = await Promise.all([
        fetch(`${base}/admin/overview?days=14`, { headers }),
        fetch(`${base}/admin/uploads?limit=100`, { headers }),
        fetch(`${base}/admin/rag-unlimited-users`, { headers }),
      ]);
      const overviewPayload = await overviewRes.json();
      const uploadsPayload = await uploadsRes.json();
      const unlimitedUsersPayload = await unlimitedUsersRes.json();
      if (!overviewRes.ok) throw new Error(overviewPayload.detail || overviewPayload.message || 'Unable to load admin overview');
      if (!uploadsRes.ok) throw new Error(uploadsPayload.detail || uploadsPayload.message || 'Unable to load upload logs');
      if (!unlimitedUsersRes.ok) throw new Error(unlimitedUsersPayload.detail || unlimitedUsersPayload.message || 'Unable to load exclusive users');
      setOverview(overviewPayload);
      setUploads(Array.isArray(uploadsPayload.uploads) ? uploadsPayload.uploads : []);
      setRagUnlimitedUsers(Array.isArray(unlimitedUsersPayload.users) ? unlimitedUsersPayload.users : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load admin data');
    } finally {
      setLoading(false);
    }
  }, [base, token]);

  useEffect(() => {
    loadAdminData();
  }, [loadAdminData]);

  const maxDaily = Math.max(1, ...(overview?.daily || []).map(item => item.uploads));
  const totals = overview?.totals || {
    uploads: 0,
    completed: 0,
    failed: 0,
    rejected: 0,
    deleted: 0,
    active: 0,
    chunks: 0,
    entities: 0,
    relations: 0,
  };

  const startEdit = (upload: UploadAudit) => {
    setEditingJobId(upload.job_id);
    setEditForm({
      title: upload.title || '',
      domain: upload.domain || 'general',
      source_type: upload.source_type || '',
      source: upload.source || '',
    });
    setActionMessage('');
  };

  const saveEdit = async (jobId: string) => {
    setActionMessage('');
    try {
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };
      const response = await fetch(`${base}/admin/uploads/${jobId}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify(editForm),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || 'Unable to update upload');
      setEditingJobId(null);
      setActionMessage('Upload metadata updated.');
      await loadAdminData();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to update upload');
    }
  };

  const deleteUpload = async (upload: UploadAudit) => {
    if (!window.confirm(`Delete "${upload.title}" from the managed corpus? This action is recorded in the audit log.`)) {
      return;
    }
    setActionMessage('');
    try {
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await fetch(`${base}/admin/uploads/${upload.job_id}?reason=admin_deleted`, {
        method: 'DELETE',
        headers,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || 'Unable to delete upload');
      setActionMessage(
        payload?.cleanup?.queued
          ? 'Upload marked as deleted. Resource cleanup is running in the background.'
          : 'Upload marked as deleted.'
      );
      await loadAdminData();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to delete upload');
    }
  };

  const addUnlimitedUser = async () => {
    setSavingUnlimitedUser(true);
    setActionMessage('');
    try {
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };
      const response = await fetch(`${base}/admin/rag-unlimited-users`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ email: unlimitedEmail, note: unlimitedNote }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || 'Unable to add exclusive user');
      setUnlimitedEmail('');
      setUnlimitedNote('');
      setActionMessage(`${payload?.user?.email || 'User'} now bypasses RAG usage limits.`);
      await loadAdminData();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to add exclusive user');
    } finally {
      setSavingUnlimitedUser(false);
    }
  };

  const deleteUnlimitedUser = async (email: string) => {
    if (!window.confirm(`Remove unlimited RAG access for ${email}?`)) {
      return;
    }
    setActionMessage('');
    try {
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await fetch(`${base}/admin/rag-unlimited-users/${encodeURIComponent(email)}`, {
        method: 'DELETE',
        headers,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || 'Unable to remove exclusive user');
      setActionMessage(`${email} now uses the standard RAG limits.`);
      await loadAdminData();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to remove exclusive user');
    }
  };

  const createInviteCode = async () => {
    setCreatingInvite(true);
    setActionMessage('');
    try {
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };
      const response = await fetch(`${base}/admin/invite-codes`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ ttl_minutes: 5 }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || 'Unable to create invite code');
      setInviteCode(payload.invite_code || '');
      setInviteExpiresAt(payload.expires_at || '');
      setActionMessage('Admin invite code created. It expires in 5 minutes or after one successful use.');
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to create invite code');
    } finally {
      setCreatingInvite(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-72px)] bg-surface px-5 py-6 text-ink lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-6 flex flex-col justify-between gap-4 border-b border-hairline pb-5 lg:flex-row lg:items-end">
          <div>
            <div className="cg-badge-success mb-3 inline-flex items-center gap-2">
              <Shield className="h-3.5 w-3.5" />
              <span className="uppercase tracking-[0.08em]">Admin</span>
            </div>
            <h1
              className="font-display text-heading-md font-semibold text-ink"
              style={{ letterSpacing: 0, lineHeight: 1.20 }}
            >
              Document Operations
            </h1>
            <p className="mt-3 max-w-2xl text-body-md text-ink-steel">
              Audit upload activity, processing status, and corpus growth from the local ESG workspace.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-hairline bg-canvas px-4 py-2 text-body-sm text-ink-charcoal">
              Signed in as <span className="font-semibold text-ink">{user?.email || 'unknown'}</span>
            </div>
            <button onClick={loadAdminData} className="cg-btn-primary">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </header>

        {error && (
          <div className="mb-5 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-5 w-5" />
            <div>
              <div className="font-semibold">Admin data unavailable</div>
              <div>{error}</div>
            </div>
          </div>
        )}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
          <MetricCard icon={UploadCloud} label="Total uploads" value={totals.uploads} />
          <MetricCard icon={CheckCircle2} label="Completed" value={totals.completed} />
          <MetricCard icon={Clock3} label="Active jobs" value={totals.active} />
          <MetricCard icon={XCircle} label="Failed" value={totals.failed} tone="red" />
          <MetricCard icon={AlertTriangle} label="Rejected" value={totals.rejected || 0} tone="amber" />
          <MetricCard icon={Trash2} label="Deleted" value={totals.deleted || 0} />
        </section>

        <section className="mt-4 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-2xl border border-hairline bg-white p-5 shadow-sm">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-ink">Daily document growth</h2>
                <p className="text-sm text-ink-steel">New uploads over the last 14 days</p>
              </div>
              <BarChart3 className="h-5 w-5 text-ink-stone" />
            </div>
            <div className="flex h-56 items-end gap-2 border-b border-hairline px-1 pb-2">
              {(overview?.daily || []).map(day => (
                <div key={day.date} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
                  <span className={`text-[10px] font-semibold ${day.uploads > 0 ? 'text-ink-charcoal' : 'text-ink-stone'}`}>
                    {day.uploads}
                  </span>
                  <div
                    className={`w-full rounded-t-md transition-all ${day.uploads > 0 ? 'bg-emerald-500/85' : 'bg-hairline'}`}
                    style={{ height: `${day.uploads > 0 ? Math.max(10, (day.uploads / maxDaily) * 180) : 4}px` }}
                    title={`${day.date}: ${day.uploads}`}
                  />
                  <span className="text-[10px] text-ink-steel">{day.date.slice(5)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-hairline bg-white p-5 shadow-sm">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-ink">Corpus output</h2>
                <p className="text-sm text-ink-steel">Generated artifacts across completed jobs</p>
              </div>
              <Database className="h-5 w-5 text-ink-stone" />
            </div>
            <div className="grid gap-3">
              <StatLine label="Chunks" value={totals.chunks} />
              <StatLine label="Entities" value={totals.entities} />
              <StatLine label="Relationships" value={totals.relations} />
            </div>
          </div>
        </section>

        <section className="mt-4 rounded-2xl border border-hairline bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Access controls</h2>
              <p className="text-sm text-ink-steel">Invite codes and unlimited AI users are hidden until needed.</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={() => setShowAccessControls(prev => !prev)}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-hairline bg-canvas px-4 py-2 text-sm font-semibold text-ink-charcoal transition hover:border-ink"
              >
                {showAccessControls ? 'Hide controls' : 'Show controls'}
              </button>
              {showAccessControls && (
                <button
                  onClick={createInviteCode}
                  disabled={creatingInvite}
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink-charcoal disabled:opacity-50"
                >
                  <Ticket className="h-4 w-4" />
                  {creatingInvite ? 'Generating…' : 'Generate code'}
                </button>
              )}
            </div>
          </div>
          {showAccessControls && inviteCode && (
            <div className="mt-4 rounded-xl border border-hairline bg-surface px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-steel">Current code</p>
              <p className="mt-1 font-mono text-base font-semibold text-ink">{inviteCode}</p>
              <p className="mt-1 text-xs text-ink-steel">Expires at: {formatDateTime(inviteExpiresAt)}</p>
            </div>
          )}
        </section>

        {showAccessControls && (
        <section className="mt-4 rounded-2xl border border-hairline bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Exclusive AI users</h2>
              <p className="text-sm text-ink-steel">Accounts listed here bypass Flash and Deep usage limits without receiving admin permissions.</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-[minmax(180px,1fr)_minmax(180px,1fr)_auto] lg:min-w-[620px]">
              <input
                value={unlimitedEmail}
                onChange={event => setUnlimitedEmail(event.target.value)}
                className="rounded-full border border-hairline bg-canvas px-4 py-2 text-sm text-ink outline-none transition focus:border-ink"
                placeholder="user@example.com"
                type="email"
              />
              <input
                value={unlimitedNote}
                onChange={event => setUnlimitedNote(event.target.value)}
                className="rounded-full border border-hairline bg-canvas px-4 py-2 text-sm text-ink outline-none transition focus:border-ink"
                placeholder="note"
              />
              <button
                onClick={addUnlimitedUser}
                disabled={savingUnlimitedUser || !unlimitedEmail.trim()}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink-charcoal disabled:opacity-50"
              >
                <UserPlus className="h-4 w-4" />
                {savingUnlimitedUser ? 'Adding...' : 'Add'}
              </button>
            </div>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-hairline-soft text-left text-sm">
              <thead className="bg-surface text-xs uppercase tracking-[0.12em] text-ink-steel">
                <tr>
                  <th className="px-4 py-3 font-semibold">Email</th>
                  <th className="px-4 py-3 font-semibold">Note</th>
                  <th className="px-4 py-3 font-semibold">Added at</th>
                  <th className="px-4 py-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline-soft">
                {ragUnlimitedUsers.map(item => (
                  <tr key={item.email} className="hover:bg-surface">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 font-semibold text-ink">
                        <UserCheck className="h-4 w-4 text-emerald-600" />
                        {item.email}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-ink-charcoal">{item.note || '-'}</td>
                    <td className="px-4 py-3 text-ink-charcoal">{formatDateTime(item.created_at)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => deleteUnlimitedUser(item.email)}
                        className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-canvas px-3 py-1.5 text-xs font-semibold text-red-700 transition hover:border-red-400"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
                {!loading && ragUnlimitedUsers.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-ink-steel">
                      No exclusive AI users yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
        )}

        <section className="mt-4 rounded-2xl border border-hairline bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-hairline px-5 py-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">Upload audit log</h2>
              <p className="text-sm text-ink-steel">Who uploaded what, when, and how processing ended</p>
            </div>
            {loading && <span className="text-sm text-ink-steel">Loading...</span>}
          </div>
          {actionMessage && (
            <div className="border-b border-hairline bg-surface px-5 py-3 text-sm text-ink-charcoal">
              {actionMessage}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-hairline-soft text-left text-sm">
              <thead className="bg-surface text-xs uppercase tracking-[0.12em] text-ink-steel">
                <tr>
                  <th className="px-5 py-3 font-semibold">Document</th>
                  <th className="px-5 py-3 font-semibold">Uploader</th>
                  <th className="px-5 py-3 font-semibold">Uploaded at</th>
                  <th className="px-5 py-3 font-semibold">Category</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Stats</th>
                  <th className="px-5 py-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline-soft">
                {uploads.map(upload => (
                  <tr key={upload.job_id} className="align-top hover:bg-surface">
                    <td className="max-w-sm px-5 py-4">
                      {editingJobId === upload.job_id ? (
                        <input
                          value={editForm.title}
                          onChange={event => setEditForm(prev => ({ ...prev, title: event.target.value }))}
                          className="w-full rounded-lg border border-hairline px-3 py-2 text-sm"
                        />
                      ) : (
                        <div className="font-semibold text-ink">{upload.title}</div>
                      )}
                      <div className="mt-1 text-xs text-ink-steel">{upload.filename || upload.document_id || upload.job_id}</div>
                      {upload.error && <div className="mt-2 text-xs text-red-600">{upload.error}</div>}
                      {upload.duplicate_of_document_id && (
                        <div className="mt-2 text-xs text-amber-700">Duplicate of {upload.duplicate_of_document_id}</div>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-medium text-ink-charcoal">{upload.uploader?.username || '-'}</div>
                      <div className="text-xs text-ink-steel">{upload.uploader?.email || '-'}</div>
                    </td>
                    <td className="px-5 py-4 text-ink-charcoal">{formatDateTime(upload.created_at)}</td>
                    <td className="px-5 py-4">
                      {editingJobId === upload.job_id ? (
                        <div className="grid gap-2">
                          <select
                            value={editForm.domain}
                            onChange={event => setEditForm(prev => ({ ...prev, domain: event.target.value }))}
                            className="rounded-lg border border-hairline px-3 py-2 text-sm"
                          >
                            {domainOptions.map(option => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                          <select
                            value={editForm.source_type}
                            onChange={event => setEditForm(prev => ({ ...prev, source_type: event.target.value }))}
                            className="rounded-lg border border-hairline px-3 py-2 text-sm"
                          >
                            {sourceTypeOptions.map(option => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                          <input
                            value={editForm.source}
                            onChange={event => setEditForm(prev => ({ ...prev, source: event.target.value }))}
                            className="rounded-lg border border-hairline px-3 py-2 text-sm"
                            placeholder="source"
                          />
                        </div>
                      ) : (
                        <>
                          <div className="text-ink-charcoal">{upload.domain || 'general'}</div>
                          <div className="text-xs text-ink-steel">{upload.source_type || 'auto'}</div>
                          {upload.source && <div className="mt-1 max-w-[12rem] truncate text-xs text-ink-stone">{upload.source}</div>}
                        </>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${statusClass(upload.status)}`}>
                        {upload.status}
                      </span>
                      <div className="mt-1 text-xs text-ink-steel">{upload.stage || '-'}</div>
                      {upload.cleanup_status && (
                        <div className={`mt-2 text-xs font-semibold ${cleanupClass(upload.cleanup_status)}`}>
                          {upload.cleanup_status}
                        </div>
                      )}
                      {upload.cleanup_detail && (
                        <div className="mt-1 max-w-[14rem] truncate text-xs text-ink-steel" title={upload.cleanup_detail}>
                          {upload.cleanup_detail}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-4 text-ink-charcoal">
                      <div>{upload.stats?.chunks || 0} chunks</div>
                      <div>{upload.stats?.entities || 0} entities</div>
                      <div>{upload.stats?.relations || 0} relations</div>
                    </td>
                    <td className="px-5 py-4">
                      {editingJobId === upload.job_id ? (
                        <div className="flex gap-2">
                          <button
                            onClick={() => saveEdit(upload.job_id)}
                            className="inline-flex items-center gap-1 rounded-full bg-ink px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-ink-charcoal"
                          >
                            <Save className="h-3.5 w-3.5" />
                            Save
                          </button>
                          <button
                            onClick={() => setEditingJobId(null)}
                            className="inline-flex items-center gap-1 rounded-full border border-hairline bg-canvas px-3 py-1.5 text-xs font-semibold text-ink-charcoal transition hover:border-ink"
                          >
                            <X className="h-3.5 w-3.5" />
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button
                            onClick={() => startEdit(upload)}
                            disabled={upload.status === 'deleted' || upload.status === 'deleted_with_warnings'}
                            className="inline-flex items-center gap-1 rounded-full border border-hairline bg-canvas px-3 py-1.5 text-xs font-semibold text-ink-charcoal transition hover:border-ink disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <Edit3 className="h-3.5 w-3.5" />
                            Organize
                          </button>
                          <button
                            onClick={() => deleteUpload(upload)}
                            disabled={
                              upload.status === 'deleted' ||
                              upload.status === 'deleted_with_warnings' ||
                              upload.status === 'running' ||
                              upload.status === 'queued'
                            }
                            className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-canvas px-3 py-1.5 text-xs font-semibold text-red-700 transition hover:border-red-400 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {!loading && uploads.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-5 py-10 text-center text-ink-steel">
                      No upload records yet. New uploads will appear here after they are submitted.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
};

// MiniMax stat tile — flat white card, hairline border, heading-md numeral.
const MetricCard = ({
  icon: Icon,
  label,
  value,
  tone = 'slate',
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  tone?: 'slate' | 'red' | 'amber';
}) => (
  <div className="rounded-xl border border-hairline bg-canvas p-5">
    <div className="flex items-start justify-between">
      <div>
        <div className="text-body-sm font-medium text-ink-steel">{label}</div>
        <div
          className="mt-3 font-display font-semibold text-ink"
          style={{ fontSize: '32px', lineHeight: 1.25, letterSpacing: 0 }}
        >
          {value}
        </div>
      </div>
      <div
        className={`flex h-9 w-9 items-center justify-center rounded-full ${
          tone === 'red'
            ? 'bg-red-50 text-red-600'
            : tone === 'amber'
              ? 'bg-amber-50 text-amber-600'
              : 'bg-surface-soft text-ink-charcoal'
        }`}
      >
        <Icon className="h-4 w-4" />
      </div>
    </div>
  </div>
);

const StatLine = ({ label, value }: { label: string; value: number }) => (
  <div className="flex items-center justify-between rounded-lg border border-hairline-soft bg-surface px-4 py-3">
    <span className="text-body-sm font-medium text-ink-charcoal">{label}</span>
    <span className="text-card-title font-semibold text-ink">{value}</span>
  </div>
);

export default Admin;
