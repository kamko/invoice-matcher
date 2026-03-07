import { useState } from 'react'
import { useSearch } from 'wouter'
import {
  useTransactions,
  useTransactionSuggestions,
  useMatchTransaction,
  useSkipTransaction,
  useMarkKnown,
  useDashboard,
  showApiError,
  showSuccess,
  Transaction,
  InvoiceSuggestion,
} from '../api/client'
import { Card, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select } from '../components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../components/ui/dialog'
import { Check, FileText, Ban } from 'lucide-react'

export function TransactionsPage() {
  const search = useSearch()
  const params = new URLSearchParams(search)
  const initialMonth = params.get('month') || ''
  const initialStatus = params.get('status') || ''

  const [month, setMonth] = useState(initialMonth)
  const [status, setStatus] = useState(initialStatus)
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null)
  const [showMatchModal, setShowMatchModal] = useState(false)
  const [showSkipModal, setShowSkipModal] = useState(false)
  const [showKnownModal, setShowKnownModal] = useState(false)
  const [skipReason, setSkipReason] = useState('')
  const [knownReason, setKnownReason] = useState('')
  const [knownRuleType, setKnownRuleType] = useState('vendor')

  const { data: dashboard } = useDashboard()
  const { data, isLoading, refetch } = useTransactions(month || undefined, status || undefined)
  const { data: suggestions } = useTransactionSuggestions(
    showMatchModal ? selectedTransaction?.id ?? null : null
  )

  const matchTransaction = useMatchTransaction()
  const skipTransaction = useSkipTransaction()
  const markKnown = useMarkKnown()

  const handleMatch = async (invoiceId: number) => {
    if (!selectedTransaction) return
    try {
      await matchTransaction.mutateAsync({
        transactionId: selectedTransaction.id,
        invoiceId,
      })
      showSuccess('Transaction matched successfully')
      setShowMatchModal(false)
      setSelectedTransaction(null)
      refetch()
    } catch (error) {
      showApiError(error, 'Match transaction')
    }
  }

  const handleSkip = async () => {
    if (!selectedTransaction) return
    try {
      await skipTransaction.mutateAsync({
        transactionId: selectedTransaction.id,
        reason: skipReason,
      })
      showSuccess('Transaction skipped')
      setShowSkipModal(false)
      setSelectedTransaction(null)
      setSkipReason('')
      refetch()
    } catch (error) {
      showApiError(error, 'Skip transaction')
    }
  }

  const handleMarkKnown = async () => {
    if (!selectedTransaction) return
    try {
      const result = await markKnown.mutateAsync({
        transactionId: selectedTransaction.id,
        rule_type: knownRuleType,
        reason: knownReason,
        vendor_pattern: selectedTransaction.counter_name || undefined,
      })
      showSuccess(`Rule created, matched ${result.matched_count} transactions`)
      setShowKnownModal(false)
      setSelectedTransaction(null)
      setKnownReason('')
      refetch()
    } catch (error) {
      showApiError(error, 'Create known rule')
    }
  }

  const formatAmount = (amount: string) => {
    const num = parseFloat(amount)
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(num)
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'matched':
        return <Badge className="bg-green-100 text-green-800">Matched</Badge>
      case 'unmatched':
        return <Badge className="bg-orange-100 text-orange-800">Unmatched</Badge>
      case 'known':
        return <Badge className="bg-blue-100 text-blue-800">Known</Badge>
      case 'skipped':
        return <Badge className="bg-gray-100 text-gray-800">Skipped</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  const monthOptions = [
    { value: '', label: 'All months' },
    ...(dashboard?.available_months?.map((m: string) => ({ value: m, label: m })) || [])
  ]

  const statusOptions = [
    { value: '', label: 'All statuses' },
    { value: 'unmatched', label: 'Unmatched' },
    { value: 'matched', label: 'Matched' },
    { value: 'known', label: 'Known' },
    { value: 'skipped', label: 'Skipped' },
  ]

  const ruleTypeOptions = [
    { value: 'vendor', label: 'Match by vendor name' },
    { value: 'exact', label: 'Match exact amount' },
    { value: 'account', label: 'Match counter account' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Transactions</h1>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <div className="w-48">
              <Label>Month</Label>
              <Select
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                options={monthOptions}
              />
            </div>
            <div className="w-48">
              <Label>Status</Label>
              <Select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                options={statusOptions}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      {data && (
        <div className="flex gap-4 text-sm">
          <span>Total: <strong>{data.total}</strong></span>
          <span>Unmatched: <strong className="text-orange-600">{data.unmatched}</strong></span>
          <span>Matched: <strong className="text-green-600">{data.matched}</strong></span>
          <span>Known: <strong className="text-blue-600">{data.known}</strong></span>
          <span>Skipped: <strong className="text-gray-600">{data.skipped}</strong></span>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-12">Loading...</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Counter Party</TableHead>
                  <TableHead>VS</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.transactions.map((t) => (
                  <TableRow key={t.id} className={t.status === 'unmatched' ? 'bg-orange-50' : ''}>
                    <TableCell>{t.date}</TableCell>
                    <TableCell className={parseFloat(t.amount) < 0 ? 'text-red-600' : 'text-green-600'}>
                      {formatAmount(t.amount)}
                    </TableCell>
                    <TableCell>
                      <div className="max-w-xs truncate" title={t.counter_name || t.note || ''}>
                        {t.counter_name || t.note || '-'}
                      </div>
                    </TableCell>
                    <TableCell>{t.vs || '-'}</TableCell>
                    <TableCell>
                      {getStatusBadge(t.status)}
                      {t.rule_reason && (
                        <span className="ml-2 text-xs text-muted-foreground">{t.rule_reason}</span>
                      )}
                      {t.skip_reason && (
                        <span className="ml-2 text-xs text-muted-foreground">{t.skip_reason}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {t.status === 'unmatched' && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedTransaction(t)
                                setShowMatchModal(true)
                              }}
                              title="Match to invoice"
                            >
                              <FileText className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedTransaction(t)
                                setShowSkipModal(true)
                              }}
                              title="Skip"
                            >
                              Skip
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedTransaction(t)
                                setKnownReason('')
                                setShowKnownModal(true)
                              }}
                              title="Mark as known"
                            >
                              <Ban className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                        {t.status === 'matched' && (
                          <Button variant="outline" size="sm" disabled>
                            <Check className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {data?.transactions.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      No transactions found
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Match Modal */}
      <Dialog open={showMatchModal} onOpenChange={setShowMatchModal}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Match Transaction</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {selectedTransaction && (
              <div className="p-4 bg-muted rounded-lg">
                <div className="font-medium">{formatAmount(selectedTransaction.amount)}</div>
                <div className="text-sm text-muted-foreground">
                  {selectedTransaction.date} - {selectedTransaction.counter_name || selectedTransaction.note}
                </div>
              </div>
            )}
            <div className="space-y-2">
              <Label>Suggested Invoices</Label>
              {suggestions?.suggestions.length === 0 && (
                <p className="text-sm text-muted-foreground">No suggestions found</p>
              )}
              {suggestions?.suggestions.map((s: InvoiceSuggestion) => (
                <div
                  key={s.invoice_id}
                  className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted cursor-pointer"
                  onClick={() => handleMatch(s.invoice_id)}
                >
                  <div>
                    <div className="font-medium">{s.filename}</div>
                    <div className="text-sm text-muted-foreground">
                      {s.vendor} - {s.amount ? formatAmount(s.amount) : 'N/A'} - {s.invoice_date}
                    </div>
                  </div>
                  <Badge variant="outline">Score: {s.score}</Badge>
                </div>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowMatchModal(false)}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Skip Modal */}
      <Dialog open={showSkipModal} onOpenChange={setShowSkipModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Skip Transaction</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Reason (optional)</Label>
              <Input
                value={skipReason}
                onChange={(e) => setSkipReason(e.target.value)}
                placeholder="e.g., Personal expense, duplicate"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSkipModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleSkip}>Skip</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Mark Known Modal */}
      <Dialog open={showKnownModal} onOpenChange={setShowKnownModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Known Transaction Rule</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {selectedTransaction && (
              <div className="p-4 bg-muted rounded-lg text-sm">
                <div>{selectedTransaction.counter_name || selectedTransaction.note}</div>
                <div className="text-muted-foreground">{formatAmount(selectedTransaction.amount)}</div>
              </div>
            )}
            <div>
              <Label>Rule Type</Label>
              <Select
                value={knownRuleType}
                onChange={(e) => setKnownRuleType(e.target.value)}
                options={ruleTypeOptions}
              />
            </div>
            <div>
              <Label>Reason / Description</Label>
              <Input
                value={knownReason}
                onChange={(e) => setKnownReason(e.target.value)}
                placeholder="e.g., Bank fees, Monthly subscription"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowKnownModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleMarkKnown} disabled={!knownReason}>
              Create Rule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
