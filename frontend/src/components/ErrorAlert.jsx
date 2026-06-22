import React from 'react'

export default function ErrorAlert({ error, fallback = 'Something went wrong. Please try again.' }) {
  const message =
    error?.response?.data?.error?.message ||
    (typeof error?.message === 'string' && !error.message.includes('Error:')
      ? error.message
      : null) ||
    fallback

  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <svg className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
      <div>
        <p className="font-semibold">Error</p>
        <p className="mt-0.5 text-red-600">{message}</p>
      </div>
    </div>
  )
}
