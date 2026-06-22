import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * ProtectedRoute — wraps routes that require authentication.
 *
 * If the user is not authenticated, they are redirected to /login.
 * The current pathname is preserved in location state so that LoginPage could
 * optionally redirect back after a successful login.
 *
 * Requirements: 8.1, 8.5
 *
 * @param {{ children: React.ReactNode }} props
 */
export default function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}
