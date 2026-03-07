import { Route, Switch, Link, useLocation } from 'wouter'
import { Toaster } from 'sonner'
import { HomePage } from './pages/HomePage'
import { MonthReportPage } from './pages/MonthReportPage'
import { RulesPage } from './pages/RulesPage'
import { cn } from './lib/utils'
import { useLocalMode } from './context/LocalModeContext'
import { Cloud, CloudOff } from 'lucide-react'

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

function LocalModeToggle() {
  const { isLocalMode, setLocalMode } = useLocalMode()

  return (
    <button
      onClick={() => setLocalMode(!isLocalMode)}
      className={cn(
        'flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
        isLocalMode
          ? 'bg-amber-100 text-amber-800 hover:bg-amber-200'
          : 'bg-green-100 text-green-800 hover:bg-green-200'
      )}
      title={isLocalMode ? 'Local mode: Google Drive disabled' : 'Cloud mode: Google Drive enabled'}
    >
      {isLocalMode ? <CloudOff className="h-4 w-4" /> : <Cloud className="h-4 w-4" />}
      {isLocalMode ? 'Local' : 'Cloud'}
    </button>
  )
}

function AppContent() {
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
              <NavLink href="/">Home</NavLink>
              <NavLink href="/rules">Rules</NavLink>
            </nav>
          </div>
          <LocalModeToggle />
        </div>
      </header>

      <main className="container py-6">
        <Switch>
          <Route path="/" component={HomePage} />
          <Route path="/month/:yearMonth">
            {(params) => <MonthReportPage yearMonth={params.yearMonth} />}
          </Route>
          <Route path="/rules" component={RulesPage} />
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
  return <AppContent />
}

export default App
