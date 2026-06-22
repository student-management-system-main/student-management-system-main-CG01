import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
} from 'react'
import apiClient, {
  setAccessToken,
  clearAccessToken,
  registerLogout,
} from '../api/client.js'

/**
 * AuthContext — provides JWT-based authentication state to the app.
 *
 * Security model:
 *   - JWT access token stored in React state only (not localStorage / sessionStorage)
 *     to mitigate XSS token theft.
 *   - Refresh token is issued by the server as an httpOnly cookie, so it is
 *     never accessible from JavaScript.
 *
 * Requirements: 8.1, 8.4, 8.5
 */
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // Access token lives in memory only — gone on page refresh (by design)
  const [accessToken, setAccessTokenState] = useState(null)
  // Decoded user object: { id, username, role }
  const [currentUser, setCurrentUser] = useState(null)

  const isAuthenticated = Boolean(accessToken)

  // Keep the module-level token in sync with state so axios interceptors
  // can attach it without importing AuthContext (circular dep prevention).
  useEffect(() => {
    if (accessToken) {
      setAccessToken(accessToken)
    } else {
      clearAccessToken()
    }
  }, [accessToken])

  /**
   * Call POST /api/v1/auth/login, store the returned JWT in memory.
   *
   * @param {string} username
   * @param {string} password
   * @returns {Promise<void>}  Rejects with the Axios error on failure.
   */
  const login = useCallback(async (username, password) => {
    const response = await apiClient.post('/api/v1/auth/login', {
      username,
      password,
    })

    const { access_token, user } = response.data.data

    setAccessTokenState(access_token)
    setCurrentUser({
      id: user.id,
      username: user.username,
      role: user.role,
    })
    // access_token is also pushed to the module store via the useEffect above,
    // but we do it eagerly here too so the very next request after login works.
    setAccessToken(access_token)
  }, [])

  /**
   * Clear local state and call the logout endpoint to invalidate the server-
   * side refresh token blocklist entry.
   */
  const logout = useCallback(async () => {
    // Best-effort: fire-and-forget; don't block the UI on network failure.
    try {
      if (accessToken) {
        await apiClient.post('/api/v1/auth/logout')
      }
    } catch {
      // Ignore — we still clear local state regardless
    }

    setAccessTokenState(null)
    setCurrentUser(null)
    clearAccessToken()
  }, [accessToken])

  // Register the logout function in the client module so the 401 interceptor
  // can trigger it when a token refresh fails.
  useEffect(() => {
    registerLogout(logout)
  }, [logout])

  return (
    <AuthContext.Provider
      value={{
        accessToken,
        currentUser,
        isAuthenticated,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}

export default AuthContext
