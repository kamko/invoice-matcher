import { createContext, useContext, useEffect } from 'react'
import { Loader2, Lock } from 'lucide-react'
import { useAuthLogin, useAuthSession, useLogout, setCsrfToken, showApiError } from './api/client'
import { Button } from './components/ui/button'

interface AuthContextValue {
  authenticated: boolean
  isLoading: boolean
  email?: string
  fullName?: string
  login: () => Promise<void>
  logout: () => Promise<void>
  refetch: () => Promise<unknown>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const authQuery = useAuthSession()
  const loginMutation = useAuthLogin()
  const logoutMutation = useLogout()

  useEffect(() => {
    setCsrfToken(authQuery.data?.authenticated ? authQuery.data.csrf_token ?? null : null)
  }, [authQuery.data])

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'auth-complete') {
        authQuery.refetch()
      }
    }

    const handleUnauthorized = () => {
      authQuery.refetch()
    }

    window.addEventListener('message', handleMessage)
    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => {
      window.removeEventListener('message', handleMessage)
      window.removeEventListener('auth:unauthorized', handleUnauthorized)
    }
  }, [authQuery])

  const login = async () => {
    try {
      const { auth_url } = await loginMutation.mutateAsync()
      const width = 520
      const height = 720
      const left = window.screenX + (window.outerWidth - width) / 2
      const top = window.screenY + (window.outerHeight - height) / 2
      window.open(
        auth_url,
        'google-login',
        `width=${width},height=${height},left=${left},top=${top}`
      )
    } catch (error) {
      showApiError(error, 'Sign in with Google')
    }
  }

  const logout = async () => {
    try {
      await logoutMutation.mutateAsync()
      setCsrfToken(null)
      await authQuery.refetch()
    } catch (error) {
      showApiError(error, 'Sign out')
    }
  }

  return (
    <AuthContext.Provider
      value={{
        authenticated: !!authQuery.data?.authenticated,
        isLoading: authQuery.isLoading,
        email: authQuery.data?.user?.email,
        fullName: authQuery.data?.user?.full_name,
        login,
        logout,
        refetch: authQuery.refetch,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const auth = useAuth()

  if (auth.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!auth.authenticated) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-6">
        <div className="max-w-md w-full rounded-2xl border bg-card p-8 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Lock className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">Invoice Matcher</h1>
              <p className="text-sm text-muted-foreground">Sign in to access the deployed service</p>
            </div>
          </div>
          <p className="text-sm text-muted-foreground mb-6">
            This instance uses one Google sign-in flow for both app access and Google Drive access. Only approved accounts can use it.
          </p>
          <Button className="w-full" onClick={auth.login}>
            Sign In With Google And Drive
          </Button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
