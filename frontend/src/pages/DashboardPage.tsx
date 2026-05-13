import { Link } from 'wouter'
import { useDashboard, useFetchTransactions, useMonthlySummary, useFioVault, showApiError, showSuccess } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { useState } from 'react'
import { FileText, CreditCard, CheckCircle, Download, RefreshCw, TrendingUp } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { unlockStoredSecret } from '../lib/crypto'

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('sk-SK', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount)
}

function formatDateForApi(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function DashboardPage() {
  const { data: dashboard, isLoading, refetch } = useDashboard()
  const { data: monthlySummary } = useMonthlySummary()
  const { data: fioVault } = useFioVault()
  const fetchTransactions = useFetchTransactions()
  const [isFetching, setIsFetching] = useState(false)

  const handleFetchTransactions = async () => {
    if (!fioVault?.configured || !fioVault.ciphertext || !fioVault.nonce || !fioVault.salt || !fioVault.kdf || !fioVault.kdf_params) {
      showApiError(new Error('Fio token not configured. Go to Settings to add it.'), 'Fetch')
      return
    }

    setIsFetching(true)
    try {
      const fioToken = await unlockStoredSecret({
        ciphertext: fioVault.ciphertext,
        nonce: fioVault.nonce,
        salt: fioVault.salt,
        kdf: fioVault.kdf,
        kdf_params: fioVault.kdf_params,
      })
      // Fetch last ~1 month (from 1st of previous month)
      const today = new Date()
      const fromDate = new Date(today.getFullYear(), today.getMonth() - 1, 1)
      const result = await fetchTransactions.mutateAsync({
        fio_token: fioToken,
        from_date: formatDateForApi(fromDate),
        to_date: formatDateForApi(today),
      })
      showSuccess(`Fetched ${result.new} new transactions`)
      refetch()
    } catch (error) {
      showApiError(error, 'Fetch transactions')
    } finally {
      setIsFetching(false)
    }
  }

  if (isLoading) {
    return <div className="flex justify-center py-12">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Button
          variant="outline"
          onClick={handleFetchTransactions}
          disabled={isFetching}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
          Fetch Transactions
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Link href="/transactions?status=unmatched">
          <Card className="cursor-pointer hover:bg-muted/50 transition-colors">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Unmatched Transactions
              </CardTitle>
              <CreditCard className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-600">
                {dashboard?.unmatched_transactions ?? 0}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Need invoices
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/invoices?status=unmatched">
          <Card className="cursor-pointer hover:bg-muted/50 transition-colors">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Unmatched Invoices
              </CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-amber-600">
                {dashboard?.unmatched_invoices ?? 0}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Awaiting payment
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/invoices?status=matched">
          <Card className="cursor-pointer hover:bg-muted/50 transition-colors">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Matched This Month
              </CardTitle>
              <CheckCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                {dashboard?.matched_this_month ?? 0}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Successfully matched
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/export">
          <Card className="cursor-pointer hover:bg-muted/50 transition-colors">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Ready to Export
              </CardTitle>
              <Download className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-blue-600">
                {dashboard?.ready_to_export ?? 0}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Matched invoices
              </p>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Monthly Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Monthly Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          {monthlySummary?.months && monthlySummary.months.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Month</TableHead>
                  <TableHead className="text-right">Income</TableHead>
                  <TableHead className="text-right">Expenses</TableHead>
                  <TableHead className="text-right">Cash</TableHead>
                  <TableHead className="text-right">Fees</TableHead>
                  <TableHead className="text-right">Net</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {monthlySummary.months.slice(0, 6).map((m) => (
                  <TableRow key={m.month}>
                    <TableCell>
                      <Link href={`/transactions?month=${m.month}`} className="hover:underline font-medium">
                        {m.month}
                      </Link>
                    </TableCell>
                    <TableCell className="text-right text-green-600">
                      {m.income > 0 ? '+' : ''}{formatCurrency(m.income)}
                    </TableCell>
                    <TableCell className="text-right text-red-600">
                      {formatCurrency(m.expenses)}
                    </TableCell>
                    <TableCell className="text-right text-orange-600">
                      {formatCurrency(m.cash)}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatCurrency(m.fees)}
                    </TableCell>
                    <TableCell className={`text-right font-semibold ${m.net >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {m.net >= 0 ? '+' : ''}{formatCurrency(m.net)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-muted-foreground text-sm">
              No data yet. Fetch transactions to get started.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Stats */}
      <Card>
        <CardHeader>
          <CardTitle>System Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Known Rules Applied:</span>
              <span className="ml-2 font-medium">{dashboard?.known_transactions ?? 0}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Skipped:</span>
              <span className="ml-2 font-medium">{dashboard?.skipped_transactions ?? 0}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
