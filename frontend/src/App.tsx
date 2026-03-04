import { Route, Switch, Link, useLocation } from 'wouter'
import { HomePage } from './pages/HomePage'
import { WizardPage } from './pages/WizardPage'
import { ReportPage } from './pages/ReportPage'
import { MonthReportPage } from './pages/MonthReportPage'
import { RulesPage } from './pages/RulesPage'
import { cn } from './lib/utils'

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

function App() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/">
              <span className="text-xl font-bold cursor-pointer">Invoice Matcher</span>
            </Link>
            <nav className="flex items-center gap-2">
              <NavLink href="/">Home</NavLink>
              <NavLink href="/wizard">Wizard</NavLink>
              <NavLink href="/rules">Rules</NavLink>
            </nav>
          </div>
        </div>
      </header>

      <main className="container py-6">
        <Switch>
          <Route path="/" component={HomePage} />
          <Route path="/wizard" component={WizardPage} />
          <Route path="/month/:yearMonth">
            {(params) => <MonthReportPage yearMonth={params.yearMonth} />}
          </Route>
          <Route path="/report/:sessionId">
            {(params) => <ReportPage sessionId={params.sessionId} />}
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

export default App
