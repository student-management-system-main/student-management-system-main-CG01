import React from 'react'

export default function Spinner({ label = 'Loading…' }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col items-center justify-center py-16 gap-3">
      <div className="relative h-10 w-10">
        <div className="absolute inset-0 rounded-full border-4 border-slate-100" />
        <div className="absolute inset-0 animate-spin rounded-full border-4 border-transparent border-t-violet-600" />
      </div>
      <p className="text-sm text-slate-500">{label}</p>
    </div>
  )
}
