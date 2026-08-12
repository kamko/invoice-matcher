import { useState } from 'react'
import { Route, Switch, Link, useLocation } from 'wouter'
import { Toaster } from 'sonner'
import { Menu, X } from 'lucide-react'
import { DashboardPage } from './pages/DashboardPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { InvoicesPage } from './pages/InvoicesPage'
import { ExportPage } from './pages/ExportPage'
import { RulesPage } from './pages/RulesPage'
import { SettingsPage } from './pages/SettingsPage'
import { AuthGate, useAuth } from './auth'
import { Button } from './components/ui/button'
import { cn } from './lib/utils'
import { useSSE } from './hooks/useSSE'

function NavLink({
  href,
  children,
  mobile = false,
  onNavigate,
}: {
  href: string
  children: React.ReactNode
  mobile?: boolean
  onNavigate?: () => void
}) {
  const [location] = useLocation()
  const isActive = location === href || (href !== '/' && location.startsWith(href))

  return (
    <Link href={href} onClick={onNavigate}>
      <span
        className={cn(
          'rounded-md px-3 py-2 text-sm font-medium transition-colors cursor-pointer',
          mobile && 'block w-full',
          isActive
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'
        )}
      >
        {children}
      </span>
    </Link>
  )
}

function AppContent() {
  const auth = useAuth()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  // Connect to SSE for real-time updates
  useSSE()

  return (
    <div className="min-h-screen bg-background">
      <Toaster
        richColors
        position="top-right"
        toastOptions={{
          style: { userSelect: 'text' },
          className: 'select-text',
        }}
      />
      <header className="border-b bg-background">
        <div className="container py-3">
          <div className="flex h-10 items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-5">
              <Link href="/">
                <span className="block truncate text-lg font-bold cursor-pointer sm:text-xl">Invoice Matcher</span>
              </Link>
              <nav className="hidden items-center gap-1 lg:flex" aria-label="Main navigation">
                <NavLink href="/">Dashboard</NavLink>
                <NavLink href="/transactions">Transactions</NavLink>
                <NavLink href="/invoices">Invoices</NavLink>
                <NavLink href="/export">Export</NavLink>
                <NavLink href="/rules">Rules</NavLink>
                <NavLink href="/settings">Settings</NavLink>
              </nav>
            </div>
            <div className="hidden items-center gap-3 lg:flex">
              <div className="max-w-48 text-right">
                <div className="text-sm font-medium">{auth.fullName || auth.email}</div>
                <div className="truncate text-xs text-muted-foreground">{auth.email}</div>
              </div>
              <Button variant="outline" size="sm" onClick={auth.logout}>
                Sign Out
              </Button>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0 lg:hidden"
              aria-label={mobileNavOpen ? 'Close navigation' : 'Open navigation'}
              aria-expanded={mobileNavOpen}
              aria-controls="mobile-navigation"
              onClick={() => setMobileNavOpen((open) => !open)}
            >
              {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>

          <div
            id="mobile-navigation"
            className={cn('border-t pt-3 lg:hidden', mobileNavOpen ? 'mt-3 block' : 'hidden')}
          >
            <nav className="grid grid-cols-2 gap-1" aria-label="Mobile navigation">
              <NavLink href="/" mobile onNavigate={() => setMobileNavOpen(false)}>Dashboard</NavLink>
              <NavLink href="/transactions" mobile onNavigate={() => setMobileNavOpen(false)}>Transactions</NavLink>
              <NavLink href="/invoices" mobile onNavigate={() => setMobileNavOpen(false)}>Invoices</NavLink>
              <NavLink href="/export" mobile onNavigate={() => setMobileNavOpen(false)}>Export</NavLink>
              <NavLink href="/rules" mobile onNavigate={() => setMobileNavOpen(false)}>Rules</NavLink>
              <NavLink href="/settings" mobile onNavigate={() => setMobileNavOpen(false)}>Settings</NavLink>
            </nav>
            <div className="mt-3 flex items-center justify-between gap-3 border-t pt-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{auth.fullName || auth.email}</div>
                <div className="truncate text-xs text-muted-foreground">{auth.email}</div>
              </div>
              <Button variant="outline" size="sm" className="shrink-0" onClick={auth.logout}>
                Sign Out
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className="container py-4 sm:py-6">
        <Switch>
          <Route path="/" component={DashboardPage} />
          <Route path="/transactions" component={TransactionsPage} />
          <Route path="/invoices" component={InvoicesPage} />
          <Route path="/export" component={ExportPage} />
          <Route path="/rules" component={RulesPage} />
          <Route path="/settings" component={SettingsPage} />
          <Route>
            <div className="text-center py-12">
              <h1 className="text-2xl font-bold">Page Not Found</h1>
              <p className="text-muted-foreground mt-2">
                <Link href="/">
                  <span className="text-primary hover:underline cursor-pointer">Go to home</span>
                </Link>
              </p>
            </div>
          </Route>
        </Switch>
      </main>
    </div>
  )
}

function App() {
  return (
    <AuthGate>
      <AppContent />
    </AuthGate>
  )
}

export default App
