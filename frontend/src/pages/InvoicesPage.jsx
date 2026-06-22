import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import apiClient from '../api/client.js'
import Layout from '../components/Layout.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorAlert from '../components/ErrorAlert.jsx'
import { StatusBadge } from '../components/StatusBadge.jsx'

export default function InvoicesPage() {
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const params = { page, per_page: perPage, ...(statusFilter !== 'all' ? { status: statusFilter } : {}) }

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['invoices', params],
    queryFn: () => apiClient.get('/api/v1/invoices', { params }).then((r) => r.data),
    keepPreviousData: true,
    refetchInterval: 60_000,
  })

  const invoices = data?.data?.invoices ?? data?.data ?? []
  const total = data?.data?.total ?? invoices.length
  const totalPages = Math.ceil(total / perPage) || 1

  const fmt = (n) => n != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n) : '—'
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—'

  return (
    <Layout>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="page-title">Invoices</h1>
          <p className="mt-1 text-sm text-slate-500">Manage and track all student invoices</p>
        </div>
        {isFetching && !isLoading && (
          <span className="flex items-center gap-1.5 text-xs text-slate-400">
            <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            Refreshing
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="card mb-4 flex flex-wrap items-center gap-3 p-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-600">Status</label>
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }} className="select w-36">
            <option value="all">All</option>
            <option value="unpaid">Unpaid</option>
            <option value="overdue">Overdue</option>
            <option value="paid">Paid</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-600">Per page</label>
          <select value={perPage} onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }} className="select w-20">
            {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        {total > 0 && <span className="ml-auto text-sm text-slate-400">{total} invoices</span>}
      </div>

      {isLoading && <Spinner label="Loading invoices…" />}
      {error && !isLoading && <ErrorAlert error={error} />}

      {!isLoading && !error && (
        <>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    {['Invoice #', 'Student', 'Total', 'Outstanding', 'Status', 'Due Date'].map((c) => (
                      <th key={c} className="table-header">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {invoices.length === 0 ? (
                    <tr><td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">No invoices found.</td></tr>
                  ) : invoices.map((inv) => (
                    <tr key={inv.id} className="table-row">
                      <td className="table-cell font-mono text-xs font-medium text-slate-600">{inv.invoice_number}</td>
                      <td className="table-cell">
                        <Link to={`/students/${inv.student_id}`} className="font-medium text-violet-600 hover:text-violet-700 hover:underline">
                          #{inv.student_id}
                        </Link>
                      </td>
                      <td className="table-cell font-semibold">{fmt(inv.total_amount)}</td>
                      <td className="table-cell">{fmt(inv.outstanding_balance)}</td>
                      <td className="table-cell"><StatusBadge status={inv.status} /></td>
                      <td className="table-cell text-slate-500">{fmtDate(inv.due_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm">
              <p className="text-slate-500">Page {page} of {totalPages}</p>
              <div className="flex gap-2">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40">Previous</button>
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40">Next</button>
              </div>
            </div>
          )}
        </>
      )}
    </Layout>
  )
}
