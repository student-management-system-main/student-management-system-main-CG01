import React from 'react'

export function StatusBadge({ status }) {
  const map = {
    paid:      'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    unpaid:    'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    overdue:   'bg-red-50 text-red-700 ring-1 ring-red-200',
    cancelled: 'bg-slate-100 text-slate-500 ring-1 ring-slate-200',
  }
  const cls = map[status] ?? 'bg-slate-100 text-slate-500 ring-1 ring-slate-200'
  const dots = {
    paid: 'bg-emerald-500', unpaid: 'bg-amber-500',
    overdue: 'bg-red-500', cancelled: 'bg-slate-400',
  }
  return (
    <span className={`badge gap-1.5 ${cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dots[status] ?? 'bg-slate-400'}`} />
      {status}
    </span>
  )
}

export function RiskBadge({ category }) {
  const map = {
    low:    'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    medium: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    high:   'bg-red-50 text-red-700 ring-1 ring-red-200',
  }
  const dots = { low: 'bg-emerald-500', medium: 'bg-amber-500', high: 'bg-red-500' }
  const cls = map[category] ?? 'bg-slate-100 text-slate-400 ring-1 ring-slate-200'
  const label = category ?? '—'
  return (
    <span className={`badge gap-1.5 ${cls}`}>
      {category && <span className={`h-1.5 w-1.5 rounded-full ${dots[category]}`} />}
      {label}
    </span>
  )
}
