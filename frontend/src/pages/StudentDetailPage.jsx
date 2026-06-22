import React from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client.js'
import Layout from '../components/Layout.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorAlert from '../components/ErrorAlert.jsx'
import { StatusBadge, RiskBadge } from '../components/StatusBadge.jsx'
import { useAuth } from '../context/AuthContext.jsx'

function Field({ label, value }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-800">{value ?? '—'}</p>
    </div>
  )
}

export default function StudentDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { currentUser } = useAuth()
  const isAdmin = currentUser?.role === 'admin'

  // Student
  const { data: sd, isLoading: sl, error: se } = useQuery({
    queryKey: ['student', id],
    queryFn: () => apiClient.get(`/api/v1/students/${id}`).then(r => r.data),
    enabled: Boolean(id),
    retry: (count, err) => err?.response?.status !== 404 && count < 3,
  })

  // Invoices
  const { data: invData, isLoading: il } = useQuery({
    queryKey: ['invoices', { student_id: id }],
    queryFn: () => apiClient.get('/api/v1/invoices', { params: { student_id: id, per_page: 50 } }).then(r => r.data),
    enabled: Boolean(id),
  })

  // Transactions
  const { data: txnData, isLoading: tl } = useQuery({
    queryKey: ['transactions', { student_id: id }],
    queryFn: () => apiClient.get('/api/v1/transactions', { params: { student_id: id, per_page: 50 } }).then(r => r.data),
    enabled: Boolean(id),
  })

  // Risk score
  const { data: rd, refetch: refetchRisk } = useQuery({
    queryKey: ['risk', id],
    queryFn: () => apiClient.get(`/api/v1/students/${id}/risk`).then(r => r.data).catch(() => null),
    enabled: Boolean(id),
  })

  // Rescore mutation
  const { mutate: rescore, isPending: isRescoring } = useMutation({
    mutationFn: () => apiClient.post('/api/v1/risk/score', { student_id: Number(id) }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['risk', id] })
      queryClient.invalidateQueries({ queryKey: ['student', id] })
      refetchRisk()
    },
  })

  const isLoading = sl || il || tl
  const notFound = se?.response?.status === 404
  const student = sd?.data
  const invoices = invData?.data?.invoices ?? []
  const transactions = txnData?.data?.transactions ?? []
  const risk = rd?.data

  const fmt = (n) => n != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
    : '—'
  const fmtDate = (d) => d
    ? new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    : '—'
  const fullName = student
    ? [student.first_name, student.last_name].filter(Boolean).join(' ') || `Student #${student.id}`
    : ''
  const riskScore = risk?.score ?? risk?.risk_score

  // 404 state
  if (notFound) {
    return (
      <Layout>
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
            <svg className="h-8 w-8 text-red-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-slate-800">Student not found</h2>
          <p className="mt-2 text-sm text-slate-500">No student exists with ID #{id}.</p>
          <button
            onClick={() => navigate('/')}
            className="btn-primary mt-6"
          >
            ← Back to Dashboard
          </button>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <button
        onClick={() => navigate('/')}
        className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-800 transition"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Dashboard
      </button>

      {isLoading && <Spinner label="Loading student…" />}
      {se && !notFound && !isLoading && <ErrorAlert error={se} />}

      {!isLoading && !se && student && (
        <div className="space-y-6">
          {/* Header */}
          <div className="card p-6 flex items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-2xl bg-violet-100 text-xl font-bold text-violet-700">
                {fullName.slice(0, 2).toUpperCase()}
              </div>
              <div>
                <h1 className="page-title">{fullName}</h1>
                <div className="mt-1 flex items-center gap-3">
                  <span className="font-mono text-sm text-slate-500">{student.student_number}</span>
                  <span className={`badge ${student.status === 'active' ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-slate-100 text-slate-500'}`}>
                    {student.status}
                  </span>
                </div>
              </div>
            </div>
            {risk && (
              <div className="flex flex-col items-end gap-1">
                <RiskBadge category={risk.risk_category ?? null} />
                {riskScore != null && (
                  <p className="text-xs text-slate-400">
                    Score: <span className="font-semibold text-slate-600">{Number(riskScore).toFixed(1)}</span>
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Info + Risk */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="card p-6 lg:col-span-2">
              <h2 className="section-title mb-4">Contact Information</h2>
              <div className="grid grid-cols-2 gap-5 sm:grid-cols-3">
                <Field label="Email" value={student.email} />
                <Field label="Phone" value={student.phone} />
                <Field label="Enrollment Date" value={fmtDate(student.enrollment_date)} />
                <Field label="SMS Notifications" value={student.sms_enabled ? 'Enabled' : 'Disabled'} />
              </div>
            </div>

            {/* Risk Assessment */}
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="section-title">Risk Assessment</h2>
                {isAdmin && (
                  <button
                    onClick={() => rescore()}
                    disabled={isRescoring}
                    className="btn-secondary py-1.5 px-3 text-xs"
                    title="Re-run ML scoring for this student"
                  >
                    {isRescoring ? (
                      <><svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Scoring…</>
                    ) : (
                      <>↻ Rescore</>
                    )}
                  </button>
                )}
              </div>

              {risk ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-500">Category</span>
                    <RiskBadge category={risk.risk_category ?? null} />
                  </div>
                  {riskScore != null && (
                    <div>
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="text-sm text-slate-500">Score</span>
                        <span className="text-sm font-bold text-slate-800">
                          {Number(riskScore).toFixed(1)} / 100
                        </span>
                      </div>
                      <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full rounded-full transition-all ${
                            Number(riskScore) >= 70 ? 'bg-red-500' :
                            Number(riskScore) >= 40 ? 'bg-amber-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${Math.min(100, Number(riskScore))}%` }}
                        />
                      </div>
                    </div>
                  )}
                  <Field label="Model Version" value={risk.model_version} />
                  <Field label="Computed At" value={fmtDate(risk.computed_at)} />
                </div>
              ) : (
                <p className="text-sm text-slate-400">Not yet scored.</p>
              )}
            </div>
          </div>

          {/* Invoices */}
          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-4 flex items-center justify-between">
              <h2 className="section-title">Invoices</h2>
              <span className="badge bg-slate-100 text-slate-600">{invoices.length} total</span>
            </div>
            {invoices.length === 0 ? (
              <p className="px-6 py-10 text-center text-sm text-slate-400">No invoices found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50">
                      {['Invoice #', 'Total', 'Outstanding', 'Status', 'Due Date', 'Paid At'].map(c => (
                        <th key={c} className="table-header">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map(inv => (
                      <tr key={inv.id} className="table-row">
                        <td className="table-cell font-mono text-xs font-medium text-slate-600">
                          {inv.invoice_number}
                        </td>
                        <td className="table-cell font-semibold">{fmt(inv.total_amount)}</td>
                        <td className="table-cell">{fmt(inv.outstanding_balance)}</td>
                        <td className="table-cell"><StatusBadge status={inv.status} /></td>
                        <td className="table-cell text-slate-500">{fmtDate(inv.due_date)}</td>
                        <td className="table-cell text-slate-500">{fmtDate(inv.paid_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Transaction History */}
          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-4 flex items-center justify-between">
              <h2 className="section-title">Transaction History</h2>
              <span className="badge bg-slate-100 text-slate-600">{transactions.length} total</span>
            </div>
            {transactions.length === 0 ? (
              <p className="px-6 py-10 text-center text-sm text-slate-400">No transactions found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50">
                      {['Ref', 'Amount', 'Method', 'Type', 'Date'].map(c => (
                        <th key={c} className="table-header">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map(txn => (
                      <tr key={txn.id} className="table-row">
                        <td className="table-cell font-mono text-xs text-slate-600">
                          {txn.transaction_ref}
                        </td>
                        <td className="table-cell font-semibold">{fmt(txn.amount)}</td>
                        <td className="table-cell text-slate-500 capitalize">
                          {(txn.payment_method ?? '').replace(/_/g, ' ')}
                        </td>
                        <td className="table-cell">
                          <span className={`badge ${txn.type === 'reversal' ? 'bg-red-50 text-red-700 ring-1 ring-red-200' : 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'}`}>
                            {txn.type}
                          </span>
                        </td>
                        <td className="table-cell text-slate-500">{fmtDate(txn.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </Layout>
  )
}
