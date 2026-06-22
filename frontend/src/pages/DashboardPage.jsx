import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import apiClient from '../api/client.js'
import Layout from '../components/Layout.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorAlert from '../components/ErrorAlert.jsx'
import { RiskBadge } from '../components/StatusBadge.jsx'

// ---------------------------------------------------------------------------
// KPI Stat Card
// ---------------------------------------------------------------------------
function StatCard({ label, value, sub, icon, color }) {
  return (
    <div className="card p-6 flex items-start gap-4">
      <div className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl ${color}`}>
        {icon}
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
        <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
        {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Risk Distribution Chart (inline bar)
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
    <div className="space-y-2.5">
      {bars.map(({ label, count, color, text, bg }) => {
        const pct = total > 0 ? Math.round((count / total) * 100) : 0
        return (
          <div key={label}>
            <div className="mb-1 flex justify-between text-xs font-semibold">
              <span className={text}>{label}</span>
              <span className="text-slate-500">{count} ({pct}%)</span>
            </div>
            <div className={`h-2 w-full overflow-hidden rounded-full ${bg}`}>
              <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Dashboard Page
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('all')

  // KPI summary from server
  const {
    data: summaryData,
    isLoading: summaryLoading,
    error: summaryError,
    isStale: summaryStale,
  } = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: () => apiClient.get('/api/v1/dashboard/summary').then(r => r.data),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    retry: 3,
    retryDelay: 10_000,
  })

  // Students list
  const {
    data: studentsData,
    isLoading: studentsLoading,
    error: studentsError,
  } = useQuery({
    queryKey: ['students', 'dashboard'],
    queryFn: () => apiClient.get('/api/v1/students', { params: { per_page: 200 } }).then(r => r.data),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    retry: 3,
    retryDelay: 10_000,
  })

  // Risk distribution
  const {
    data: distData,
  } = useQuery({
    queryKey: ['risk', 'distribution'],
    queryFn: () => apiClient.get('/api/v1/risk/distribution').then(r => r.data),
    refetchInterval: 60_000,
  })

  // Invoices for overdue count per student
  const { data: invoicesData } = useQuery({
    queryKey: ['invoices', 'dashboard'],
    queryFn: () => apiClient.get('/api/v1/invoices', { params: { per_page: 500 } }).then(r => r.data),
    refetchInterval: 60_000,
  })

  const isLoading = summaryLoading || studentsLoading
  const hasError = summaryError || studentsError

  const summary = summaryData?.data ?? {}

  // Overdue count map per student
  const overdueMap = useMemo(() => {
    const invoices = invoicesData?.data?.invoices ?? []
    const map = {}
    for (const inv of invoices) {
      if (inv.status === 'overdue') map[inv.student_id] = (map[inv.student_id] || 0) + 1
    }
    return map
  }, [invoicesData])

  // Outstanding balance per student
  const balanceMap = useMemo(() => {
    const invoices = invoicesData?.data?.invoices ?? []
    const map = {}
    for (const inv of invoices) {
      if (['unpaid', 'overdue'].includes(inv.status)) {
        map[inv.student_id] = (map[inv.student_id] || 0) + Number(inv.outstanding_balance || 0)
      }
    }
    return map
  }, [invoicesData])

  // Filter students
  const filteredRows = useMemo(() => {
    const students = studentsData?.data?.students ?? []
    return students.filter(s => {
      const fullName = `${s.first_name ?? ''} ${s.last_name ?? ''}`.toLowerCase()
      const matchesName = search === '' || fullName.includes(search.toLowerCase())
      const matchesRisk = riskFilter === 'all' || s.risk_category === riskFilter
      return matchesName && matchesRisk
    })
  }, [studentsData, search, riskFilter])

  const fmt = (n) => n != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 }).format(Number(n))
    : '—'

  const name = (s) => [s.first_name, s.last_name].filter(Boolean).join(' ') || `Student #${s.id}`

  return (
    <Layout>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">Real-time fee collection and student risk overview</p>
        </div>
        {hasError && !isLoading && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
            ⚠ Auto-refresh error — showing last known data
          </div>
        )}
      </div>

      {isLoading && <Spinner label="Loading dashboard…" />}

      {!isLoading && (
        <>
          {/* KPI Cards */}
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard
              label="Total Collected"
              value={fmt(summary.total_collected ?? 0)}
              sub="All paid invoices"
              color="bg-emerald-100"
              icon={<svg className="h-5 w-5 text-emerald-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
            />
            <StatCard
              label="Outstanding"
              value={fmt(summary.total_outstanding ?? 0)}
              sub="Unpaid + Overdue"
              color="bg-amber-100"
              icon={<svg className="h-5 w-5 text-amber-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
            />
            <StatCard
              label="Overdue Invoices"
              value={summary.overdue_count ?? 0}
              sub="Require attention"
              color="bg-red-100"
              icon={<svg className="h-5 w-5 text-red-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
            />
            <StatCard
              label="Active Students"
              value={summary.active_student_count ?? 0}
              sub="Currently enrolled"
              color="bg-violet-100"
              icon={<svg className="h-5 w-5 text-violet-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" /></svg>}
            />
            <StatCard
              label="30-Day Forecast"
              value={fmt(summary.forecast_30d ?? 0)}
              sub="Due in next 30 days"
              color="bg-sky-100"
              icon={<svg className="h-5 w-5 text-sky-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>}
            />
          </div>

          {/* Risk Distribution */}
          <div className="mb-6 card p-5">
            <h2 className="section-title mb-4">Risk Distribution</h2>
            <RiskDistributionChart distribution={distData?.data} />
          </div>

          {/* Filters */}
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="section-title">Students</h2>
            <div className="flex gap-3">
              <div className="relative">
                <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="search"
                  placeholder="Search students…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="input pl-9 w-56"
                />
              </div>
              <select value={riskFilter} onChange={e => setRiskFilter(e.target.value)} className="select w-40">
                <option value="all">All Risk Levels</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>

          {/* Student table */}
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="table-header">Student</th>
                    <th className="table-header">Student No.</th>
                    <th className="table-header">Outstanding</th>
                    <th className="table-header">Overdue</th>
                    <th className="table-header">Risk</th>
                    <th className="table-header">Status</th>
                    <th className="table-header" />
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-400">
                        No students match your filters.
                      </td>
                    </tr>
                  ) : (
                    filteredRows.map(s => (
                      <tr
                        key={s.id}
                        onClick={() => navigate(`/students/${s.id}`)}
                        className="table-row cursor-pointer"
                      >
                        <td className="table-cell">
                          <div className="flex items-center gap-3">
                            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-violet-100 text-xs font-bold text-violet-700">
                              {name(s).slice(0, 2).toUpperCase()}
                            </div>
                            <span className="font-medium text-slate-800">{name(s)}</span>
                          </div>
                        </td>
                        <td className="table-cell font-mono text-xs text-slate-500">{s.student_number ?? '—'}</td>
                        <td className="table-cell font-semibold">{fmt(balanceMap[s.id] ?? 0)}</td>
                        <td className="table-cell">
                          {(overdueMap[s.id] ?? 0) > 0
                            ? <span className="font-semibold text-red-600">{overdueMap[s.id]}</span>
                            : <span className="text-slate-400">0</span>}
                        </td>
                        <td className="table-cell">
                          <RiskBadge category={s.risk_category ?? null} />
                        </td>
                        <td className="table-cell">
                          <span className={`badge ${s.status === 'active' ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-slate-100 text-slate-500'}`}>
                            {s.status}
                          </span>
                        </td>
                        <td className="table-cell text-right">
                          <svg className="ml-auto h-4 w-4 text-slate-300" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                          </svg>
                        </td>
                      </tr>
                    ))
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
