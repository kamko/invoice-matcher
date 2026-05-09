import { Route, Switch, Link, useLocation } from 'wouter'
import { Toaster } from 'sonner'
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

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const [location] = useLocation()
  const isActive = location === href || (href !== '/' && location.startsWith(href))

  return (
    <Link href={href}>
      <span
        className={cn(
          'px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer',
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
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/">
              <span className="text-xl font-bold cursor-pointer">Invoice Matcher</span>
            </Link>
            <nav className="flex items-center gap-2">
              <NavLink href="/">Dashboard</NavLink>
              <NavLink href="/transactions">Transactions</NavLink>
              <NavLink href="/invoices">Invoices</NavLink>
              <NavLink href="/export">Export</NavLink>
              <NavLink href="/rules">Rules</NavLink>
              <NavLink href="/settings">Settings</NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-sm font-medium">{auth.fullName || auth.email}</div>
              <div className="text-xs text-muted-foreground">{auth.email}</div>
            </div>
            <Button variant="outline" size="sm" onClick={auth.logout}>
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      <main className="container py-6">
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
