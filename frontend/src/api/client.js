import axios from 'axios'

/**
 * Pre-configured Axios instance for all API calls.
 * The base URL is read from the Vite env variable; falls back to localhost.
 *
 * Requirements:
 *   8.1 — JWT on every request
 *   8.5 — 401 triggers refresh; on refresh failure, redirect to /login
 *   6.6 — Never expose internal stack traces to the UI
 *
 * To avoid a circular import between AuthContext and this module, we use a
 * module-level token store that AuthContext writes to after login/refresh.
 */

// ---------------------------------------------------------------------------
// Module-level token store (avoids circular dependency with AuthContext)
// ---------------------------------------------------------------------------

/** @type {string | null} */
let _accessToken = null
/** @type {(() => void) | null} In-memory reference to AuthContext.logout */
let _logoutFn = null

/**
 * Called by AuthContext after a successful login or token refresh.
 * @param {string} token  The new JWT access token.
 */
export function setAccessToken(token) {
  _accessToken = token
}

/**
 * Called by AuthContext on logout (or when refresh fails).
 */
export function clearAccessToken() {
  _accessToken = null
}

/**
 * Register the logout callback so the response interceptor can trigger it.
 * AuthContext calls this once on mount.
 * @param {() => void} fn
 */
export function registerLogout(fn) {
  _logoutFn = fn
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000',
  headers: {
    'Content-Type': 'application/json',
  },
})

// ---------------------------------------------------------------------------
// Request interceptor — attach current JWT to Authorization header
// ---------------------------------------------------------------------------

apiClient.interceptors.request.use((config) => {
  if (_accessToken) {
    config.headers.Authorization = `Bearer ${_accessToken}`
  }
  return config
})

// ---------------------------------------------------------------------------
// Response interceptor — token refresh on 401 (Req 8.5)
// ---------------------------------------------------------------------------

let _isRefreshing = false
let _pendingQueue = [] // [{ resolve, reject }]

function _processQueue(error, token = null) {
  _pendingQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error)
    } else {
      resolve(token)
    }
  })
  _pendingQueue = []
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Only attempt refresh on 401, and avoid infinite loops
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Skip refresh on the login and refresh endpoints themselves
      const url = originalRequest.url || ''
      if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
        return Promise.reject(error)
      }

      if (_isRefreshing) {
        // Queue this request until the in-flight refresh completes
        return new Promise((resolve, reject) => {
          _pendingQueue.push({ resolve, reject })
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`
            return apiClient(originalRequest)
          })
          .catch((err) => Promise.reject(err))
      }

      originalRequest._retry = true
      _isRefreshing = true

      try {
        // Attempt to get a new access token using the refresh token
        // The backend reads the refresh token from the Authorization header or
        // an httpOnly cookie depending on server configuration.
        const response = await axios.post(
          `${apiClient.defaults.baseURL}/api/v1/auth/refresh`,
          {},
          {
            // Pass the current (expired) token so the server can identify the
            // user; if the server uses httpOnly cookies the header can be empty.
            headers: {
              Authorization: `Bearer ${_accessToken}`,
            },
          },
        )

        const newToken = response.data?.data?.access_token
        if (!newToken) throw new Error('No access_token in refresh response')

        setAccessToken(newToken)
        _processQueue(null, newToken)

        // Retry the original request with the new token
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return apiClient(originalRequest)
      } catch (refreshError) {
        _processQueue(refreshError, null)
        // Refresh failed — log out and redirect
        clearAccessToken()
        if (_logoutFn) _logoutFn()
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        _isRefreshing = false
      }
    }

    // For all other errors, reject with the original error
    return Promise.reject(error)
  },
)

export default apiClient
