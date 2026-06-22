import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client.js'
import Layout from '../components/Layout.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorAlert from '../components/ErrorAlert.jsx'
import { RiskBadge } from '../components/StatusBadge.jsx'
import { useAuth } from '../context/AuthContext.jsx'

// ---------------------------------------------------------------------------
// Risk Distribution Chart (CSS bar chart)
// ---------------------------------------------------------------------------
function RiskDistributionChart({ distribution }) {
  if (!distribution) return null
  const { low_count = 0, medium_count = 0, high_count = 0, total = 0 } = distribution
  if (total === 0) return <p className="text-sm text-slate-400">No scored students yet.</p>

  const bars = [
    { label: 'Low', count: low_count, color: 'bg-emerald-500', text: 'text-emerald-700', bg: 'bg-emerald-50' },
    { label: 'Medium', count: medium_count, color: 'bg-amber-500', text: 'text-amber-700', bg: 'bg-amber-50' },
    { label: 'High', count: high_count, color: 'bg-red-500', text: 'text-red-700', bg: 'bg-red-50' },
  ]

  return (
    <div className="space-y-3">
      {bars.map(({ label, count, color, text, bg }) => {
        const pct = total > 0 ? Math.round((count / total) * 100) : 0
        return (
          <div key={label}>
            <div className="mb-1 flex items-center justify-between text-xs font-semibold">
              <span className={text}>{label}</span>
              <span className="text-slate-500">{count} ({pct}%)</span>
            </div>
            <div className={`h-2.5 w-full overflow-hidden rounded-full ${bg}`}>
              <div
                className={`h-full rounded-full ${color} transition-all duration-500`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })}
      <p className="text-right text-xs text-slate-400">{total} scored students</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Retrain Result Panel
// ---------------------------------------------------------------------------
function RetrainResult({ result }) {
  if (!result) return null
  return (
    <div className={`mt-3 rounded-lg border px-4 py-3 text-sm ${result.replaced ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-slate-50'}`}>
      <p className="font-semibold text-slate-800">
        {result.replaced ? '✅ Model replaced' : 'ℹ️ Model NOT replaced (no improvement)'}
      </p>
      <div className="mt-1 flex flex-wrap gap-4 text-xs text-slate-600">
        <span>New ROC-AUC: <strong>{typeof result.new_roc_auc === 'number' ? result.new_roc_auc.toFixed(4) : '—'}</strong></span>
        <span>Previous ROC-AUC: <strong>{typeof result.current_roc_auc === 'number' ? result.current_roc_auc.toFixed(4) : '—'}</strong></span>
        <span>Version: <strong>{result.version ?? '—'}</strong></span>
        <span>Samples: <strong>{result.n_samples ?? '—'}</strong></span>
      </div>
      {result.error && <p className="mt-1 text-xs text-amber-600">{result.error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
export default function RiskMonitoringPage() {
  const { currentUser } = useAuth()
  const isAdmin = currentUser?.role === 'admin'
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('all')
  const [retrainResult, setRetrainResult] = useState(null)

  // Fetch students (with risk fields)
  const { data: studentsData, isLoading: studentsLoading, error: studentsError } = useQuery({
    queryKey: ['students', 'risk-monitoring'],
    queryFn: () => apiClient.get('/api/v1/students', { params: { per_page: 200 } }).then(r => r.data),
  })

  // Fetch risk distribution
  const { data: distData, isLoading: distLoading, error: distError } = useQuery({
    queryKey: ['risk', 'distribution'],
    queryFn: () => apiClient.get('/api/v1/risk/distribution').then(r => r.data),
  })

  // Fetch invoices for overdue counts
  const { data: invoicesData } = useQuery({
    queryKey: ['invoices', 'risk-monitoring'],
    queryFn: () => apiClient.get('/api/v1/invoices', { params: { per_page: 500 } }).then(r => r.data),
  })

  // Batch scoring mutation
  const { mutate: runBatchScoring, isPending: isBatchPending } = useMutation({
    mutationFn: () => apiClient.post('/api/v1/risk/batch').then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students', 'risk-monitoring'] })
      queryClient.invalidateQueries({ queryKey: ['risk', 'distribution'] })
    },
  })

  // Retrain mutation
  const { mutate: retrainModel, isPending: isRetrainPending } = useMutation({
    mutationFn: () => apiClient.post('/api/v1/risk/retrain').then(r => r.data),
    onSuccess: (data) => {
      setRetrainResult(data)
      queryClient.invalidateQueries({ queryKey: ['students', 'risk-monitoring'] })
      queryClient.invalidateQueries({ queryKey: ['risk', 'distribution'] })
    },
  })

  const isLoading = studentsLoading || distLoading
  const error = studentsError || distError

  // Build overdue count map per student
  const overdueMap = useMemo(() => {
    const invoices = invoicesData?.data?.invoices ?? []
    const map = {}
    for (const inv of invoices) {
      if (inv.status === 'overdue') {
        map[inv.student_id] = (map[inv.student_id] || 0) + 1
      }
    }
    return map
  }, [invoicesData])

  // Filter students
  const filteredStudents = useMemo(() => {
    const students = studentsData?.data?.students ?? []
    return students.filter(s => {
      const fullName = `${s.first_name ?? ''} ${s.last_name ?? ''}`.toLowerCase()
      const matchesName = search === '' || fullName.includes(search.toLowerCase())
      const matchesRisk = riskFilter === 'all' || s.risk_category === riskFilter
      return matchesName && matchesRisk
    })
  }, [studentsData, search, riskFilter])

  const fmt = (n) => n != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
    : '—'
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="page-title">Risk Monitoring</h1>
        <p className="mt-1 text-sm text-slate-500">AI-powered payment risk scores for all students</p>
      </div>

      {isLoading && <Spinner label="Loading risk data…" />}
      {error && !isLoading && <ErrorAlert error={error} />}

      {!isLoading && !error && (
        <>
          {/* Top row: chart + controls */}
          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* Distribution chart */}
            <div className="card p-5">
              <h2 className="section-title mb-4">Risk Distribution</h2>
              <RiskDistributionChart distribution={distData?.data} />
            </div>

            {/* Search, filter, and action buttons */}
            <div className="card p-5 lg:col-span-2">
              <h2 className="section-title mb-4">Controls</h2>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex-1">
                  <label className="label mb-1.5">Search by name</label>
                  <div className="relative">
                    <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="search"
                      placeholder="Search students…"
                      value={search}
                      onChange={e => setSearch(e.target.value)}
                      className="input pl-9"
                    />
                  </div>
                </div>
                <div className="w-40">
                  <label className="label mb-1.5">Risk Category</label>
                  <select value={riskFilter} onChange={e => setRiskFilter(e.target.value)} className="select">
                    <option value="all">All</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
              </div>

              {isAdmin && (
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    onClick={() => runBatchScoring()}
                    disabled={isBatchPending}
                    className="btn-primary"
                  >
                    {isBatchPending ? (
                      <><svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Scoring…</>
                    ) : (
                      <><svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" /></svg>Run Batch Scoring</>
                    )}
                  </button>
                  <button
                    onClick={() => { setRetrainResult(null); retrainModel() }}
                    disabled={isRetrainPending}
                    className="btn-secondary"
                  >
                    {isRetrainPending ? (
                      <><svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Retraining…</>
                    ) : (
                      <><svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>Retrain Model</>
                    )}
                  </button>
                </div>
              )}

              {retrainResult && <RetrainResult result={retrainResult} />}
            </div>
          </div>

          {/* Student risk table */}
          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-4 flex items-center justify-between">
              <h2 className="section-title">Students</h2>
              <span className="badge bg-slate-100 text-slate-600">{filteredStudents.length} shown</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="table-header">Student</th>
                    <th className="table-header">Risk</th>
                    <th className="table-header">Score</th>
                    <th className="table-header">Computed At</th>
                    <th className="table-header">Overdue</th>
                    <th className="table-header">Outstanding</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStudents.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">
                        No students match your filters.
                      </td>
                    </tr>
                  ) : (
                    filteredStudents.map(s => {
                      const fullName = [s.first_name, s.last_name].filter(Boolean).join(' ') || `Student #${s.id}`
                      const initials = fullName.slice(0, 2).toUpperCase()
                      const overdueCount = overdueMap[s.id] ?? 0
                      return (
                        <tr key={s.id} className="table-row">
                          <td className="table-cell">
                            <div className="flex items-center gap-3">
                              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-violet-100 text-xs font-bold text-violet-700">
                                {initials}
                              </div>
                              <div>
                                <p className="font-medium text-slate-800">{fullName}</p>
                                <p className="font-mono text-xs text-slate-400">{s.student_number}</p>
                              </div>
                            </div>
                          </td>
                          <td className="table-cell">
                            <RiskBadge category={s.risk_category ?? null} />
                          </td>
                          <td className="table-cell">
                            {s.risk_score != null ? (
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                                  <div
                                    className={`h-full rounded-full ${
                                      s.risk_category === 'high' ? 'bg-red-500' :
                                      s.risk_category === 'medium' ? 'bg-amber-500' : 'bg-emerald-500'
                                    }`}
                                    style={{ width: `${Math.min(100, Number(s.risk_score))}%` }}
                                  />
                                </div>
                                <span className="text-xs font-semibold text-slate-700">
                                  {Number(s.risk_score).toFixed(1)}
                                </span>
                              </div>
                            ) : (
                              <span className="text-xs text-slate-400">N/A</span>
                            )}
                          </td>
                          <td className="table-cell text-slate-500 text-xs">
                            {s.risk_computed_at ? fmtDate(s.risk_computed_at) : '—'}
                          </td>
                          <td className="table-cell">
                            {overdueCount > 0
                              ? <span className="font-semibold text-red-600">{overdueCount}</span>
                              : <span className="text-slate-400">0</span>}
                          </td>
                          <td className="table-cell font-semibold">
                            {fmt(s.outstanding_balance ?? 0)}
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </Layout>
  )
}
