import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import Layout from '../components/Layout.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorAlert from '../components/ErrorAlert.jsx'

function ActionBadge({ action }) {
  const map = {
    create: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    update: 'bg-blue-50 text-blue-700 ring-1 ring-blue-200',
    deactivate: 'bg-orange-50 text-orange-700 ring-1 ring-orange-200',
    export: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
    payment: 'bg-teal-50 text-teal-700 ring-1 ring-teal-200',
    reverse: 'bg-red-50 text-red-700 ring-1 ring-red-200',
    notification_sent: 'bg-slate-100 text-slate-600',
    report_generate: 'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200',
    report_export: 'bg-purple-50 text-purple-700 ring-1 ring-purple-200',
  }
  const cls = map[action] ?? 'bg-slate-100 text-slate-600'
  return <span className={`badge text-xs ${cls}`}>{action?.replace(/_/g, ' ')}</span>
}

export default function AuditLogPage() {
  const { currentUser } = useAuth()
  const isAdmin = currentUser?.role === 'admin'

  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [action, setAction] = useState('')
  const [actorId, setActorId] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(50)
  const [applied, setApplied] = useState({})

  const params = { page, per_page: perPage, ...applied }

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => apiClient.get('/api/v1/audit', { params }).then((r) => r.data),
    keepPreviousData: true,
    enabled: isAdmin,
  })

  const logs = data?.data?.logs ?? []
  const total = data?.data?.total ?? 0
  const totalPages = Math.ceil(total / perPage) || 1

  function applyFilters(e) {
    e.preventDefault()
    const f = {}
    if (dateFrom) f.date_from = dateFrom
    if (dateTo) f.date_to = dateTo
    if (resourceType.trim()) f.resource_type = resourceType.trim()
    if (action.trim()) f.action = action.trim()
    if (actorId) f.actor_id = actorId
    setApplied(f)
    setPage(1)
  }

  function clearFilters() {
    setDateFrom(''); setDateTo(''); setResourceType(''); setAction(''); setActorId('')
    setApplied({}); setPage(1)
  }

  const fmtDT = (d) => d ? new Date(d).toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

  return (
    <Layout>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="page-title">Audit Log</h1>
          <p className="mt-1 text-sm text-slate-500">Immutable record of all system actions</p>
        </div>
        {isFetching && !isLoading && (
          <span className="flex items-center gap-1.5 text-xs text-slate-400">
            <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            Refreshing
          </span>
        )}
      </div>

      {!isAdmin ? (
        <div className="card p-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-100">
            <svg className="h-7 w-7 text-amber-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-slate-800">Access Restricted</h3>
          <p className="mt-1 text-sm text-slate-500">Admin role required to view audit logs.</p>
        </div>
      ) : (
        <>
          {/* Filters */}
          <div className="card mb-4 p-5">
            <form onSubmit={applyFilters}>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <label className="label mb-1.5">Date From</label>
                  <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input" />
                </div>
                <div>
                  <label className="label mb-1.5">Date To</label>
                  <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input" />
                </div>
                <div>
                  <label className="label mb-1.5">Resource Type</label>
                  <input type="text" value={resourceType} onChange={(e) => setResourceType(e.target.value)} placeholder="e.g. invoice, student" className="input" />
                </div>
                <div>
                  <label className="label mb-1.5">Action</label>
                  <input type="text" value={action} onChange={(e) => setAction(e.target.value)} placeholder="e.g. create, update" className="input" />
                </div>
                <div>
                  <label className="label mb-1.5">Actor ID</label>
                  <input type="number" value={actorId} onChange={(e) => setActorId(e.target.value)} placeholder="User ID" min="1" className="input" />
                </div>
                <div>
                  <label className="label mb-1.5">Per page</label>
                  <select value={perPage} onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }} className="select">
                    {[50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <button type="submit" className="btn-primary">Apply Filters</button>
                <button type="button" onClick={clearFilters} className="btn-secondary">Clear</button>
                {total > 0 && <span className="ml-auto text-sm text-slate-400">{total} entries</span>}
              </div>
            </form>
          </div>

          {isLoading && <Spinner label="Loading audit log…" />}
          {error && !isLoading && <ErrorAlert error={error} />}

          {!isLoading && !error && (
            <>
              <div className="card overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="border-b border-slate-100 bg-slate-50">
                        {['ID', 'Actor', 'Resource', 'Action', 'Channel', 'Status', 'Timestamp'].map((c) => (
                          <th key={c} className="table-header">{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {logs.length === 0 ? (
                        <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-400">No audit entries found.</td></tr>
                      ) : logs.map((log) => (
                        <tr key={log.id} className="table-row">
                          <td className="table-cell font-mono text-xs text-slate-400">#{log.id}</td>
                          <td className="table-cell text-slate-500">{log.actor_id != null ? `User #${log.actor_id}` : <span className="italic text-slate-300">system</span>}</td>
                          <td className="table-cell">
                            {log.resource_type && (
                              <div>
                                <span className="text-xs font-medium text-slate-600">{log.resource_type}</span>
                                {log.resource_id && <span className="text-xs text-slate-400"> #{log.resource_id}</span>}
                              </div>
                            )}
                          </td>
                          <td className="table-cell"><ActionBadge action={log.action} /></td>
                          <td className="table-cell text-slate-500">{log.channel ?? '—'}</td>
                          <td className="table-cell">
                            {log.delivery_status ? (
                              <span className={`badge text-xs ${log.delivery_status === 'sent' ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-red-50 text-red-700 ring-1 ring-red-200'}`}>
                                {log.delivery_status}
                              </span>
                            ) : '—'}
                          </td>
                          <td className="table-cell whitespace-nowrap text-xs text-slate-400">{fmtDT(log.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {totalPages > 1 && (
                <div className="mt-4 flex items-center justify-between text-sm">
                  <p className="text-slate-500">Page {page} of {totalPages} · {total} total</p>
                  <div className="flex gap-2">
                    <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40">Previous</button>
                    <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40">Next</button>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </Layout>
  )
}
