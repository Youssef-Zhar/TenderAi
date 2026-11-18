import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { authService, type AuthCredentials, type AuthUser } from '../services/auth'
import { TOKEN_STORAGE_KEY } from '../lib/api'

interface AuthContextValue {
  user: AuthUser | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (credentials: AuthCredentials) => Promise<void>
  register: (credentials: AuthCredentials) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY)
    setUser(null)
  }, [])

  useEffect(() => {
    const token = sessionStorage.getItem(TOKEN_STORAGE_KEY)

    if (!token) {
      setIsLoading(false)
      return
    }

    authService.me()
      .then(setUser)
      .catch(logout)
      .finally(() => setIsLoading(false))
  }, [logout])

  const login = useCallback(async (credentials: AuthCredentials) => {
    const tokenResponse = await authService.login(credentials)
    sessionStorage.setItem(TOKEN_STORAGE_KEY, tokenResponse.access_token)

    try {
      const currentUser = await authService.me()
      setUser(currentUser)
    } catch (error) {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY)
      throw error
    }
  }, [])

  const register = useCallback(async (credentials: AuthCredentials) => {
    await authService.register(credentials)
    await login(credentials)
  }, [login])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isLoading,
    isAuthenticated: user !== null,
    login,
    register,
    logout,
  }), [user, isLoading, login, register, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  return context
}
