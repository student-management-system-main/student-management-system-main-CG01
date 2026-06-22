import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../api/client.js'
import Layout from '../components/Layout.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorAlert from '../components/ErrorAlert.jsx'
import { RiskBadge, StatusBadge } from '../components/StatusBadge.jsx'

export default function ReportsPage() {
  const [reportType, setReportType] = useState('fee_collection')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [invoiceStatus, setInvoiceStatus] = useState('all')
  const [riskCategory, setRiskCategory] = useState('all')
  const [reportData, setReportData] = useState(null)
  const [exportLoading, setExportLoading] = useState(null)

  const { mutate: generate, isPending: isGenerating, error: generateError } = useMutation({
    mutationFn: (payload) => apiClient.post('/api/v1/reports', payload).then((r) => r.data),
    onSuccess: (data) => {
      const d = data?.data ?? {}
      setReportData({ id: d.report_id, records: d.records ?? [], report_type: d.report_type ?? reportType, total: d.total ?? 0 })
    },
  })

  function handleGenerate(e) {
    e.preventDefault()
    setReportData(null)
    const payload = { report_type: reportType }
    if (dateFrom) payload.date_from = dateFrom
    if (dateTo) payload.date_to = dateTo
    if (invoiceStatus !== 'all') payload.invoice_status = invoiceStatus
    if (riskCategory !== 'all') payload.risk_category = riskCategory
    generate(payload)
  }

  async function handleExport(format) {
    if (!reportData?.id) return
    setExportLoading(format)
    try {
      const res = await apiClient.get(`/api/v1/reports/${reportData.id}/export`, { params: { format }, responseType: 'blob' })
      const mime = format === 'pdf' ? 'application/pdf' : 'text/csv'
      const url = URL.createObjectURL(new Blob([res.data], { type: mime }))
      const a = document.createElement('a')
      a.href = url
      a.download = `report_${reportData.report_type}_${reportData.id.slice(0, 8)}.${format}`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
    } catch (err) { console.error('Export failed:', err) }
    finally { setExportLoading(null) }
  }

  const feeCollectionCols = [
    { key: 'invoice_number', label: 'Invoice #' },
    { key: 'student_name', label: 'Student' },
    { key: 'invoice_status', label: 'Status' },
    { key: 'total_amount', label: 'Total' },
    { key: 'outstanding_balance', label: 'Outstanding' },
    { key: 'due_date', label: 'Due Date' },
  ]
  const highRiskCols = [
    { key: 'student_name', label: 'Student' },
    { key: 'student_number', label: 'Student No.' },
    { key: 'risk_score', label: 'Score' },
    { key: 'risk_category', label: 'Risk' },
    { key: 'total_outstanding_balance', label: 'Outstanding' },
    { key: 'last_payment_date', label: 'Last Payment' },
  ]
  const columns = reportData?.report_type === 'high_risk_students' ? highRiskCols : feeCollectionCols

  const fmt = (n) => n != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n) : '—'
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—'

  function renderCell(record, col) {
    const v = record[col.key]
    if (col.key === 'invoice_status') return <StatusBadge status={v} />
    if (col.key === 'risk_category') return <RiskBadge category={v} />
    if (['total_amount', 'outstanding_balance', 'total_outstanding_balance'].includes(col.key)) return fmt(v)
    if (['due_date', 'last_payment_date'].includes(col.key)) return fmtDate(v)
    return v ?? '—'
  }

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="page-title">Reports</h1>
        <p className="mt-1 text-sm text-slate-500">Generate and export fee collection and risk reports</p>
      </div>

      {/* Filter card */}
      <div className="card mb-6 p-6">
        <h2 className="section-title mb-4">Report Configuration</h2>
        <form onSubmit={handleGenerate}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="label mb-1.5">Report Type</label>
              <select value={reportType} onChange={(e) => setReportType(e.target.value)} className="select">
                <option value="fee_collection">Fee Collection</option>
                <option value="high_risk_students">High Risk Students</option>
              </select>
            </div>
            <div>
              <label className="label mb-1.5">Date From</label>
              <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input" />
            </div>
            <div>
              <label className="label mb-1.5">Date To</label>
              <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input" />
            </div>
            <div>
              <label className="label mb-1.5">Invoice Status</label>
              <select value={invoiceStatus} onChange={(e) => setInvoiceStatus(e.target.value)} className="select">
                <option value="all">All</option>
                <option value="unpaid">Unpaid</option>
                <option value="overdue">Overdue</option>
                <option value="paid">Paid</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
            <div>
              <label className="label mb-1.5">Risk Category</label>
              <select value={riskCategory} onChange={(e) => setRiskCategory(e.target.value)} className="select">
                <option value="all">All</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button type="submit" disabled={isGenerating} className="btn-primary">
              {isGenerating ? (
                <><svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Generating…</>
              ) : (
                <><svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>Generate Report</>
              )}
            </button>

            {reportData && (
              <>
                <button type="button" onClick={() => handleExport('csv')} disabled={exportLoading === 'csv'} className="btn-secondary">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                  {exportLoading === 'csv' ? 'Exporting…' : 'Export CSV'}
                </button>
                <button type="button" onClick={() => handleExport('pdf')} disabled={exportLoading === 'pdf'} className="btn-secondary">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                  {exportLoading === 'pdf' ? 'Exporting…' : 'Export PDF'}
                </button>
              </>
            )}
          </div>
        </form>
      </div>

      {isGenerating && <Spinner label="Generating report…" />}
      {generateError && !isGenerating && <div className="mb-4"><ErrorAlert error={generateError} /></div>}

      {reportData && !isGenerating && (
        <div className="card overflow-hidden">
          <div className="border-b border-slate-100 bg-slate-50 px-6 py-4 flex items-center justify-between">
            <h2 className="section-title capitalize">{reportData.report_type.replace(/_/g, ' ')}</h2>
            <span className="badge bg-violet-100 text-violet-700">{reportData.total} records</span>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {columns.map((c) => <th key={c.key} className="table-header">{c.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {reportData.records.length === 0 ? (
                  <tr><td colSpan={columns.length} className="px-4 py-10 text-center text-sm text-slate-400">No records matched the filters.</td></tr>
                ) : reportData.records.map((rec, i) => (
                  <tr key={rec.invoice_id ?? rec.student_id ?? i} className="table-row">
                    {columns.map((c) => (
                      <td key={c.key} className="table-cell">{renderCell(rec, c)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Layout>
  )
}
