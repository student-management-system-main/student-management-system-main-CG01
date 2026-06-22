import React, { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'

import LoginPage from './pages/LoginPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import StudentDetailPage from './pages/StudentDetailPage.jsx'
import InvoicesPage from './pages/InvoicesPage.jsx'
import TransactionsPage from './pages/TransactionsPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import AuditLogPage from './pages/AuditLogPage.jsx'
import RiskMonitoringPage from './pages/RiskMonitoringPage.jsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000, // 60 seconds — aligns with Req 6.1 refresh interval
      retry: 1,
    },
  },
})

/**
 * MaintenanceBanner fetches the maintenance window on mount and displays a
 * yellow warning banner when maintenance is scheduled within 24 hours.
 * Requirement 10.4
 */
function MaintenanceBanner() {
  const [maintenance, setMaintenance] = useState(null)

  useEffect(() => {
    fetch('/api/v1/system/maintenance')
      .then((res) => res.json())
      .then((body) => {
        const info = body?.data?.maintenance
        if (!info) return

        // Only show the banner when maintenance starts within the next 24 h
        const startTime = new Date(info.start).getTime()
        const now = Date.now()
        const twentyFourHours = 24 * 60 * 60 * 1000

        if (startTime - now <= twentyFourHours && startTime > now) {
          setMaintenance(info)
        }
      })
      .catch(() => {
        // Silently ignore — a failed maintenance check must never break the app
      })
  }, [])

  if (!maintenance) return null

  return (
    <div
      role="alert"
      style={{
        backgroundColor: '#fef08a',
        color: '#713f12',
        padding: '0.625rem 1rem',
        textAlign: 'center',
        fontWeight: 500,
        fontSize: '0.9rem',
        borderBottom: '1px solid #fde047',
        position: 'sticky',
        top: 0,
        zIndex: 9999,
      }}
    >
      ⚠️ Scheduled maintenance: {maintenance.start} – {maintenance.end}
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <MaintenanceBanner />
          <Routes>
            {/* Public route */}
            <Route path="/login" element={<LoginPage />} />

            {/* Protected routes — redirect to /login if not authenticated */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/students/:id"
              element={
                <ProtectedRoute>
                  <StudentDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/invoices"
              element={
                <ProtectedRoute>
                  <InvoicesPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/transactions"
              element={
                <ProtectedRoute>
                  <TransactionsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/reports"
              element={
                <ProtectedRoute>
                  <ReportsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/audit-log"
              element={
                <ProtectedRoute>
                  <AuditLogPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/risk"
              element={
                <ProtectedRoute>
                  <RiskMonitoringPage />
                </ProtectedRoute>
              }
            />

            {/* Fallback: redirect unknown routes to dashboard (also guarded) */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
