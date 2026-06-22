import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import apiClient from '../api/client.js'
import Layout from '../components/Layout.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorAlert from '../components/ErrorAlert.jsx'

function TypeBadge({ type }) {
  const map = {
    payment: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    reversal: 'bg-orange-50 text-orange-700 ring-1 ring-orange-200',
  }
  return <span className={`badge ${map[type] ?? 'bg-slate-100 text-slate-500'}`}>{type}</span>
}

export default function TransactionsPage() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [applied, setApplied] = useState({})

  const params = { page, per_page: perPage, ...applied }

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['transactions', params],
    queryFn: () => apiClient.get('/api/v1/transactions', { params }).then((r) => r.data),
    keepPreviousData: true,
    refetchInterval: 60_000,
  })

  const transactions = data?.data?.transactions ?? data?.data ?? []
  const total = data?.data?.total ?? transactions.length
  const totalPages = Math.ceil(total / perPage) || 1

  const fmt = (n) => n != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n) : '—'
  const fmtDT = (d) => d ? new Date(d).toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

  function applyFilters() {
    const f = {}
    if (dateFrom) f.date_from = dateFrom
    if (dateTo) f.date_to = dateTo
    setApplied(f)
    setPage(1)
  }

  function clearFilters() {
    setDateFrom(''); setDateTo(''); setApplied({}); setPage(1)
  }

  return (
    <Layout>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="page-title">Transactions</h1>
          <p className="mt-1 text-sm text-slate-500">Complete payment history and reversals</p>
        </div>
        {isFetching && !isLoading && (
          <span className="flex items-center gap-1.5 text-xs text-slate-400">
            <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            Refreshing
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="card mb-4 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="label mb-1">Date From</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input w-40" />
          </div>
          <div>
            <label className="label mb-1">Date To</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input w-40" />
          </div>
          <div>
            <label className="label mb-1">Per page</label>
            <select value={perPage} onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }} className="select w-20">
              {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={applyFilters} className="btn-primary">Apply</button>
            <button onClick={clearFilters} className="btn-secondary">Clear</button>
          </div>
          {total > 0 && <span className="ml-auto text-sm text-slate-400">{total} transactions</span>}
        </div>
      </div>

      {isLoading && <Spinner label="Loading transactions…" />}
      {error && !isLoading && <ErrorAlert error={error} />}

      {!isLoading && !error && (
        <>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    {['Reference', 'Student', 'Invoice', 'Amount', 'Method', 'Type', 'Date'].map((c) => (
                      <th key={c} className="table-header">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {transactions.length === 0 ? (
                    <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-400">No transactions found.</td></tr>
                  ) : transactions.map((txn) => (
                    <tr key={txn.id} className="table-row">
                      <td className="table-cell font-mono text-xs text-slate-600">{txn.transaction_ref}</td>
                      <td className="table-cell">
                        <Link to={`/students/${txn.student_id}`} className="font-medium text-violet-600 hover:underline">#{txn.student_id}</Link>
                      </td>
                      <td className="table-cell text-slate-500">#{txn.invoice_id}</td>
                      <td className="table-cell font-semibold">{fmt(txn.amount)}</td>
                      <td className="table-cell text-slate-500 capitalize">{txn.payment_method ?? '—'}</td>
                      <td className="table-cell"><TypeBadge type={txn.type} /></td>
                      <td className="table-cell text-slate-500">{fmtDT(txn.created_at)}</td>
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
