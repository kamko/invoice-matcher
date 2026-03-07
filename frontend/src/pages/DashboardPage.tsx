import { Link } from 'wouter'
import { useDashboard, useFetchTransactions, useImportGDrive, useSettings, showApiError, showSuccess } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { useState } from 'react'
import { FileText, CreditCard, CheckCircle, Download, RefreshCw, Upload } from 'lucide-react'

const FIO_TOKEN_KEY = 'fio_token'

export function DashboardPage() {
  const { data: dashboard, isLoading, refetch } = useDashboard()
  const { data: settings } = useSettings()
  const fetchTransactions = useFetchTransactions()
  const importGDrive = useImportGDrive()
  const [isFetching, setIsFetching] = useState(false)
  const [isImporting, setIsImporting] = useState(false)

  const handleFetchTransactions = async () => {
    // Get Fio token from localStorage (user's browser storage)
    const fioToken = localStorage.getItem(FIO_TOKEN_KEY)
    if (!fioToken) {
      showApiError(new Error('Fio token not configured. Go to Settings to add it.'), 'Fetch')
      return
    }

    setIsFetching(true)
    try {
      // Fetch last 3 months
      const today = new Date()
      const fromDate = new Date(today.getFullYear(), today.getMonth() - 2, 1)
      const result = await fetchTransactions.mutateAsync({
        fio_token: fioToken,
        from_date: fromDate.toISOString().split('T')[0],
        to_date: today.toISOString().split('T')[0],
      })
      showSuccess(`Fetched ${result.new} new transactions`)
      refetch()
    } catch (error) {
      showApiError(error, 'Fetch transactions')
    } finally {
      setIsFetching(false)
    }
  }

  const handleImportGDrive = async () => {
    const folderId = settings?.invoice_parent_folder_id
    if (!folderId) {
      showApiError(new Error('GDrive folder not configured. Go to Settings.'), 'Import')
      return
    }

    setIsImporting(true)
    try {
      const result = await importGDrive.mutateAsync({ folder_id: folderId })
      showSuccess(`Imported ${result.imported} invoices, auto-matched ${result.auto_matched}`)
      refetch()
    } catch (error) {
      showApiError(error, 'Import from GDrive')
    } finally {
      setIsImporting(false)
    }
  }

  if (isLoading) {
    return <div className="flex justify-center py-12">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleFetchTransactions}
            disabled={isFetching}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
            Fetch Transactions
          </Button>
          <Button
            variant="outline"
            onClick={handleImportGDrive}
            disabled={isImporting}
          >
            <Upload className={`h-4 w-4 mr-2 ${isImporting ? 'animate-spin' : ''}`} />
            Import from GDrive
          </Button>
        </div>
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

      {/* Available Months */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Available Months</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {dashboard?.available_months?.slice(0, 6).map((month: string) => (
                <Link key={month} href={`/transactions?month=${month}`}>
                  <Button variant="outline" size="sm">
                    {month}
                  </Button>
                </Link>
              ))}
              {(!dashboard?.available_months || dashboard.available_months.length === 0) && (
                <p className="text-muted-foreground text-sm">
                  No data yet. Fetch transactions to get started.
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

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
