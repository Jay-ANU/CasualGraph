import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import useDocumentTitle from '../utils/useDocumentTitle';

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

const statusDotClass = (status: string) => {
  if (status === 'completed') return 'bg-ok';
  if (status === 'failed') return 'bg-err';
  if (status === 'rejected' || status === 'deleted_with_warnings') return 'bg-warn';
  if (status === 'running' || status === 'queued') return 'bg-info';
  if (status === 'deleted') return 'bg-ink-5';
  return 'bg-line-strong';
};

const cleanupClass = (status?: string) => {
  if (status === 'cleanup_completed') return 'text-ok';
  if (status === 'cleanup_failed') return 'text-warn';
  if (status === 'cleanup_pending') return 'text-info';
  return 'text-ink-4';
};

const humanize = (value?: string) => String(value || '').replace(/_/g, ' ');

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
  useDocumentTitle('Admin');

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
      if (!unlimitedUsersRes.ok) throw new Error(unlimitedUsersPayload.detail || unlimitedUsersPayload.message || 'Unable to load Pro users');
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
      if (!response.ok) throw new Error(payload.detail || payload.message || 'Unable to add Pro user');
      setUnlimitedEmail('');
      setUnlimitedNote('');
      setActionMessage(`${payload?.user?.email || 'User'} is now on Pro with 300 daily points.`);
      await loadAdminData();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to add Pro user');
    } finally {
      setSavingUnlimitedUser(false);
    }
  };

  const deleteUnlimitedUser = async (email: string) => {
    if (!window.confirm(`Remove Pro access for ${email}?`)) {
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
      if (!response.ok) throw new Error(payload.detail || payload.message || 'Unable to remove Pro user');
      setActionMessage(`${email} now uses the Free 30-point daily limit.`);
      await loadAdminData();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to remove Pro user');
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

  const metrics: Array<{ label: string; value: number; tone?: 'err' | 'warn' }> = [
    { label: 'Uploads', value: totals.uploads },
    { label: 'Completed', value: totals.completed },
    { label: 'In progress', value: totals.active },
    { label: 'Failed', value: totals.failed, tone: 'err' },
    { label: 'Rejected', value: totals.rejected || 0, tone: 'warn' },
    { label: 'Deleted', value: totals.deleted || 0 },
  ];

  return (
    <div className="mx-auto max-w-content px-5 pb-24 pt-10 sm:px-8 lg:pt-14">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Document operations</h1>
          <p className="mt-1 text-sm text-ink-3">Uploads, processing status and corpus growth across the workspace.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-ink-4">
            Signed in as <span className="text-ink-2">{user?.email || 'unknown'}</span>
          </span>
          <button type="button" onClick={loadAdminData} disabled={loading} className="btn btn-secondary btn-sm">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <div role="alert" className="mt-6 rounded-lg border border-err-line bg-err-bg px-4 py-3 text-sm text-err">
          <p className="font-medium">Admin data unavailable</p>
          <p className="mt-0.5">{error}</p>
        </div>
      )}

      <dl className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
        {metrics.map((metric) => (
          <div key={metric.label} className="bg-white px-4 py-4">
            <dt className="text-xs text-ink-4">{metric.label}</dt>
            <dd
              className={`mt-1 text-2xl font-medium tabular-nums ${
                metric.tone === 'err' && metric.value > 0
                  ? 'text-err'
                  : metric.tone === 'warn' && metric.value > 0
                    ? 'text-warn'
                    : 'text-ink'
              }`}
            >
              {metric.value.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-12 grid gap-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <section>
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-base font-semibold text-ink">Uploads per day</h2>
            <span className="text-xs text-ink-4">Last 14 days</span>
          </div>
          <div className="mt-5 flex h-48 items-end gap-1.5 border-b border-line">
            {(overview?.daily || []).map(day => (
              <div
                key={day.date}
                className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1"
                title={`${day.date}: ${day.uploads} upload${day.uploads === 1 ? '' : 's'}`}
              >
                {day.uploads > 0 && (
                  <span className="text-[10px] tabular-nums text-ink-3">{day.uploads}</span>
                )}
                <div
                  className={`w-full rounded-t-sm ${day.uploads > 0 ? 'bg-ink' : 'bg-line'}`}
                  style={{ height: `${day.uploads > 0 ? Math.max(8, (day.uploads / maxDaily) * 160) : 2}px` }}
                />
              </div>
            ))}
          </div>
          <div className="mt-1.5 flex gap-1.5">
            {(overview?.daily || []).map(day => (
              <span key={day.date} className="min-w-0 flex-1 text-center font-mono text-[10px] text-ink-4">
                {day.date.slice(8)}
              </span>
            ))}
          </div>
          {!loading && (overview?.daily || []).length === 0 && (
            <p className="mt-3 text-sm text-ink-4">No upload activity in this period.</p>
          )}
        </section>

        <section>
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-base font-semibold text-ink">Corpus</h2>
            <span className="text-xs text-ink-4">From completed jobs</span>
          </div>
          <dl className="mt-5 divide-y divide-line border-y border-line">
            {[
              ['Passages', totals.chunks],
              ['Entities', totals.entities],
              ['Relationships', totals.relations],
            ].map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between py-3 text-sm">
                <dt className="text-ink-3">{label}</dt>
                <dd className="font-medium tabular-nums text-ink">{Number(value).toLocaleString()}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>

      <section className="mt-14">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
          <div>
            <h2 className="text-base font-semibold text-ink">Access</h2>
            <p className="mt-0.5 text-sm text-ink-3">Admin invite codes and Pro accounts.</p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowAccessControls(prev => !prev)}
              aria-expanded={showAccessControls}
              className="btn btn-secondary btn-sm"
            >
              {showAccessControls ? 'Hide' : 'Show'}
            </button>
            {showAccessControls && (
              <button type="button" onClick={createInviteCode} disabled={creatingInvite} className="btn btn-primary btn-sm">
                {creatingInvite ? 'Generating…' : 'Generate invite code'}
              </button>
            )}
          </div>
        </div>

        {showAccessControls && inviteCode && (
          <div className="mt-4 rounded-lg border border-line bg-white px-4 py-3">
            <p className="text-xs text-ink-4">Invite code</p>
            <p className="mt-1 select-all font-mono text-base text-ink">{inviteCode}</p>
            <p className="mt-1 text-xs text-ink-4">Valid until {formatDateTime(inviteExpiresAt)}, for one sign-up.</p>
          </div>
        )}

        {showAccessControls && (
          <div className="mt-8">
            <h3 className="text-sm font-semibold text-ink">Pro accounts</h3>
            <p className="mt-0.5 text-sm text-ink-3">These accounts get 300 AI points a day. They do not get admin access.</p>
            <form
              className="mt-4 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
              onSubmit={(event) => {
                event.preventDefault();
                if (unlimitedEmail.trim()) addUnlimitedUser();
              }}
            >
              <input
                value={unlimitedEmail}
                onChange={event => setUnlimitedEmail(event.target.value)}
                className="input h-9 text-sm"
                placeholder="user@example.com"
                type="email"
                aria-label="Email"
              />
              <input
                value={unlimitedNote}
                onChange={event => setUnlimitedNote(event.target.value)}
                className="input h-9 text-sm"
                placeholder="Note (optional)"
                aria-label="Note"
              />
              <button
                type="submit"
                disabled={savingUnlimitedUser || !unlimitedEmail.trim()}
                className="btn btn-primary btn-sm h-9"
              >
                {savingUnlimitedUser ? 'Adding…' : 'Add Pro account'}
              </button>
            </form>
            <div className="relative mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-xs text-ink-4">
                    <th className="py-2.5 pr-6 font-medium">Email</th>
                    <th className="py-2.5 pr-6 font-medium">Note</th>
                    <th className="py-2.5 pr-6 font-medium">Added</th>
                    <th className="py-2.5 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {ragUnlimitedUsers.map(item => (
                    <tr key={item.email}>
                      <td className="py-3 pr-6 font-medium text-ink">{item.email}</td>
                      <td className="py-3 pr-6 text-ink-3">{item.note || '—'}</td>
                      <td className="whitespace-nowrap py-3 pr-6 text-ink-3">{formatDateTime(item.created_at)}</td>
                      <td className="py-3 text-right">
                        <button type="button" onClick={() => deleteUnlimitedUser(item.email)} className="btn btn-ghost btn-sm hover:text-err">
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!loading && ragUnlimitedUsers.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-ink-4">No Pro accounts yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="mt-14">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
          <div>
            <h2 className="text-base font-semibold text-ink">Upload log</h2>
            <p className="mt-0.5 text-sm text-ink-3">Who uploaded what, when, and how processing ended.</p>
          </div>
          {loading && <span className="text-xs text-ink-4">Loading…</span>}
        </div>
        {actionMessage && (
          <p role="status" className="mt-4 rounded-lg bg-paper-sunken px-3 py-2 text-sm text-ink-2">
            {actionMessage}
          </p>
        )}
        <div className="relative mt-1 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-ink-4">
                <th className="py-2.5 pr-6 font-medium">Document</th>
                <th className="py-2.5 pr-6 font-medium">Uploaded by</th>
                <th className="py-2.5 pr-6 font-medium">Date</th>
                <th className="py-2.5 pr-6 font-medium">Category</th>
                <th className="py-2.5 pr-6 font-medium">Status</th>
                <th className="py-2.5 pr-6 font-medium">Output</th>
                <th className="py-2.5 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {uploads.map(upload => {
                const isDeleted = upload.status === 'deleted' || upload.status === 'deleted_with_warnings';
                return (
                  <tr key={upload.job_id} className="align-top">
                    <td className="max-w-sm py-3.5 pr-6">
                      {editingJobId === upload.job_id ? (
                        <input
                          value={editForm.title}
                          onChange={event => setEditForm(prev => ({ ...prev, title: event.target.value }))}
                          className="input h-8 min-w-[220px] text-sm"
                          aria-label="Title"
                        />
                      ) : (
                        <div className="font-medium text-ink">{upload.title}</div>
                      )}
                      <div className="mt-0.5 truncate font-mono text-xs text-ink-4">{upload.filename || upload.document_id || upload.job_id}</div>
                      {upload.error && <div className="mt-1.5 text-xs text-err">{upload.error}</div>}
                      {upload.duplicate_of_document_id && (
                        <div className="mt-1.5 text-xs text-warn">Duplicate of {upload.duplicate_of_document_id}</div>
                      )}
                    </td>
                    <td className="py-3.5 pr-6">
                      <div className="text-ink-2">{upload.uploader?.username || '—'}</div>
                      <div className="text-xs text-ink-4">{upload.uploader?.email || ''}</div>
                    </td>
                    <td className="whitespace-nowrap py-3.5 pr-6 text-ink-3">{formatDateTime(upload.created_at)}</td>
                    <td className="py-3.5 pr-6">
                      {editingJobId === upload.job_id ? (
                        <div className="grid min-w-[200px] gap-2">
                          <select
                            value={editForm.domain}
                            onChange={event => setEditForm(prev => ({ ...prev, domain: event.target.value }))}
                            className="input h-8 text-sm"
                            aria-label="Category"
                          >
                            {domainOptions.map(option => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                          <select
                            value={editForm.source_type}
                            onChange={event => setEditForm(prev => ({ ...prev, source_type: event.target.value }))}
                            className="input h-8 text-sm"
                            aria-label="Source type"
                          >
                            {sourceTypeOptions.map(option => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                          <input
                            value={editForm.source}
                            onChange={event => setEditForm(prev => ({ ...prev, source: event.target.value }))}
                            className="input h-8 text-sm"
                            placeholder="Source"
                            aria-label="Source"
                          />
                        </div>
                      ) : (
                        <>
                          <div className="text-ink-2">{humanize(upload.domain || 'general')}</div>
                          <div className="text-xs text-ink-4">{humanize(upload.source_type) || 'auto'}</div>
                          {upload.source && <div className="mt-0.5 max-w-[12rem] truncate text-xs text-ink-4">{upload.source}</div>}
                        </>
                      )}
                    </td>
                    <td className="py-3.5 pr-6">
                      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-ink-2">
                        <span className={`status-dot ${statusDotClass(upload.status)}`} />
                        {humanize(upload.status)}
                      </span>
                      {upload.stage && <div className="mt-0.5 text-xs text-ink-4">{humanize(upload.stage)}</div>}
                      {upload.cleanup_status && (
                        <div className={`mt-1 text-xs ${cleanupClass(upload.cleanup_status)}`}>{humanize(upload.cleanup_status)}</div>
                      )}
                      {upload.cleanup_detail && (
                        <div className="mt-0.5 max-w-[14rem] truncate text-xs text-ink-4" title={upload.cleanup_detail}>
                          {upload.cleanup_detail}
                        </div>
                      )}
                    </td>
                    <td className="whitespace-nowrap py-3.5 pr-6 text-xs leading-5 text-ink-3 tabular-nums">
                      <div>{upload.stats?.chunks || 0} passages</div>
                      <div>{upload.stats?.entities || 0} entities</div>
                      <div>{upload.stats?.relations || 0} relationships</div>
                    </td>
                    <td className="py-3 text-right">
                      {editingJobId === upload.job_id ? (
                        <div className="flex justify-end gap-1">
                          <button type="button" onClick={() => setEditingJobId(null)} className="btn btn-ghost btn-sm">
                            Cancel
                          </button>
                          <button type="button" onClick={() => saveEdit(upload.job_id)} className="btn btn-primary btn-sm">
                            Save
                          </button>
                        </div>
                      ) : (
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => startEdit(upload)}
                            disabled={isDeleted}
                            className="btn btn-ghost btn-sm"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => deleteUpload(upload)}
                            disabled={isDeleted || upload.status === 'running' || upload.status === 'queued'}
                            className="btn btn-ghost btn-sm hover:text-err"
                            aria-label={`Delete ${upload.title}`}
                            title="Delete"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!loading && uploads.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-ink-4">
                    No uploads yet. New uploads appear here as soon as they are submitted.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default Admin;
