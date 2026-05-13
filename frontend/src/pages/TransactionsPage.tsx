import { useState } from 'react'
import { useSearch } from 'wouter'
import {
  useTransactions,
  useTransactionSuggestions,
  useMatchTransaction,
  useSkipTransaction,
  useMarkKnown,
  useDashboard,
  useFetchTransactions,
  useFioVault,
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
import { Checkbox } from '../components/ui/checkbox'
import { Check, FileText, Ban, RefreshCw } from 'lucide-react'
import { unlockStoredSecret } from '../lib/crypto'

function formatDateForApi(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

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
  const [isFetching, setIsFetching] = useState(false)
  const [createSkipRule, setCreateSkipRule] = useState(false)
  const [skipRuleType, setSkipRuleType] = useState('vendor')

  const { data: dashboard } = useDashboard()
  const { data: fioVault } = useFioVault()
  const fetchTransactions = useFetchTransactions()
  const { data, isLoading, refetch } = useTransactions(month || undefined, status || undefined)
  const { data: suggestions } = useTransactionSuggestions(
    showMatchModal ? selectedTransaction?.id ?? null : null
  )

  const matchTransaction = useMatchTransaction()
  const skipTransaction = useSkipTransaction()
  const markKnown = useMarkKnown()

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
      const today = new Date()
      const oneMonthAgo = new Date(today.getFullYear(), today.getMonth() - 1, 1)
      const result = await fetchTransactions.mutateAsync({
        fio_token: fioToken,
        from_date: formatDateForApi(oneMonthAgo),
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
      // If creating a rule, use markKnown which will also skip this transaction
      if (createSkipRule && skipReason) {
        const result = await markKnown.mutateAsync({
          transactionId: selectedTransaction.id,
          rule_type: skipRuleType,
          reason: skipReason,
          vendor_pattern: selectedTransaction.counter_name || selectedTransaction.extracted_vendor || undefined,
        })
        showSuccess(`Rule created, matched ${result.matched_count} transactions`)
      } else {
        await skipTransaction.mutateAsync({
          transactionId: selectedTransaction.id,
          reason: skipReason,
        })
        showSuccess('Transaction skipped')
      }
      setShowSkipModal(false)
      setSelectedTransaction(null)
      setSkipReason('')
      setCreateSkipRule(false)
      refetch()
    } catch (error) {
      showApiError(error, 'Skip transaction')
    }
  }

  const handleMarkKnown = async () => {
    if (!selectedTransaction) return
    try {
      // Build pattern data based on rule type
      const patternData: Record<string, string | undefined> = {}
      switch (knownRuleType) {
        case 'vendor':
        case 'pattern':
          patternData.vendor_pattern = selectedTransaction.counter_name || selectedTransaction.extracted_vendor || undefined
          break
        case 'note':
          patternData.note_pattern = selectedTransaction.note || undefined
          break
        case 'exact':
          patternData.amount = selectedTransaction.amount
          break
        case 'account':
          patternData.counter_account = selectedTransaction.counter_account || undefined
          break
      }

      const result = await markKnown.mutateAsync({
        transactionId: selectedTransaction.id,
        rule_type: knownRuleType,
        reason: knownReason,
        ...patternData,
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
    return new Intl.NumberFormat('sk-SK', {
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
    { value: 'vendor', label: 'Match by vendor name (regex)' },
    { value: 'note', label: 'Match by note text (regex)' },
    { value: 'exact', label: 'Match exact amount' },
    { value: 'account', label: 'Match by counter account' },
    { value: 'pattern', label: 'Pattern (vendor regex + amount range)' },
  ]

  // Generate preview of what the rule will match
  const getRulePreview = (ruleType: string, transaction: Transaction | null) => {
    if (!transaction) return null
    switch (ruleType) {
      case 'vendor':
        return {
          label: 'Will match transactions where vendor matches regex:',
          value: transaction.counter_name || transaction.extracted_vendor || '(no vendor)',
        }
      case 'note':
        return {
          label: 'Will match transactions where note matches regex:',
          value: transaction.note?.substring(0, 50) + (transaction.note && transaction.note.length > 50 ? '...' : '') || '(no note)',
        }
      case 'exact':
        return {
          label: 'Will match transactions with exact amount:',
          value: formatAmount(transaction.amount),
        }
      case 'account':
        return {
          label: 'Will match transactions from account:',
          value: transaction.counter_account || '(no account)',
        }
      case 'pattern':
        return {
          label: 'Will match vendor regex + amount range (configure in Rules page):',
          value: `${transaction.counter_name || transaction.extracted_vendor || '?'} around ${formatAmount(transaction.amount)}`,
        }
      default:
        return null
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Transactions</h1>
        <Button
          variant="outline"
          onClick={handleFetchTransactions}
          disabled={isFetching}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
          {isFetching ? 'Fetching...' : 'Fetch from Bank'}
        </Button>
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
                  <TableHead>Vendor</TableHead>
                  <TableHead>Counter Party</TableHead>
                  <TableHead>VS</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.transactions.map((t) => (
                  <TableRow key={t.id} className={t.status === 'unmatched' && t.type === 'expense' ? 'bg-orange-50' : ''}>
                    <TableCell>{t.date}</TableCell>
                    <TableCell className={parseFloat(t.amount) < 0 ? 'text-red-600' : 'text-green-600'}>
                      {formatAmount(t.amount)}
                    </TableCell>
                    <TableCell>
                      {t.extracted_vendor ? (
                        <span className="font-medium">{t.extracted_vendor}</span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="max-w-xs truncate" title={t.counter_name || t.note || ''}>
                        {t.counter_name || t.note || '-'}
                      </div>
                    </TableCell>
                    <TableCell>{t.vs || '-'}</TableCell>
                    <TableCell>
                      {t.type === 'income' ? (
                        <Badge className="bg-purple-100 text-purple-800">Income</Badge>
                      ) : t.type === 'fee' ? (
                        <Badge className="bg-gray-100 text-gray-800">Fee</Badge>
                      ) : (
                        getStatusBadge(t.status)
                      )}
                      {t.rule_reason && (
                        <span className="ml-2 text-xs text-muted-foreground">{t.rule_reason}</span>
                      )}
                      {t.skip_reason && (
                        <span className="ml-2 text-xs text-muted-foreground">{t.skip_reason}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {/* Only show actions for expenses (negative amounts) */}
                        {t.status === 'unmatched' && t.type === 'expense' && (
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
                        {/* Fees and income are auto-skipped, no buttons needed */}
                        {(t.type === 'fee' || t.type === 'income') && t.status !== 'matched' && (
                          <span className="text-xs text-muted-foreground">auto</span>
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
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
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
            {selectedTransaction && (
              <div className="p-3 bg-muted rounded-lg text-sm">
                <div className="font-medium">{selectedTransaction.extracted_vendor || selectedTransaction.counter_name || 'Unknown'}</div>
                <div className="text-muted-foreground">{formatAmount(selectedTransaction.amount)} - {selectedTransaction.date}</div>
              </div>
            )}
            <div>
              <Label>Reason {createSkipRule ? '(required for rule)' : '(optional)'}</Label>
              <Input
                value={skipReason}
                onChange={(e) => setSkipReason(e.target.value)}
                placeholder="e.g., Personal expense, Bank fees"
              />
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="create-rule"
                checked={createSkipRule}
                onCheckedChange={(checked) => setCreateSkipRule(checked === true)}
              />
              <Label htmlFor="create-rule" className="text-sm font-normal">
                Create rule to auto-skip similar transactions
              </Label>
            </div>
            {createSkipRule && (
              <>
                <div>
                  <Label>Match by</Label>
                  <Select
                    value={skipRuleType}
                    onChange={(e) => setSkipRuleType(e.target.value)}
                    options={ruleTypeOptions}
                  />
                </div>
                {getRulePreview(skipRuleType, selectedTransaction) && (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm">
                    <div className="text-blue-700 font-medium">
                      {getRulePreview(skipRuleType, selectedTransaction)?.label}
                    </div>
                    <div className="font-mono mt-1">
                      {getRulePreview(skipRuleType, selectedTransaction)?.value}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSkipModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleSkip} disabled={createSkipRule && !skipReason}>
              {createSkipRule ? 'Skip & Create Rule' : 'Skip'}
            </Button>
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
            {getRulePreview(knownRuleType, selectedTransaction) && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm">
                <div className="text-blue-700 font-medium">
                  {getRulePreview(knownRuleType, selectedTransaction)?.label}
                </div>
                <div className="font-mono mt-1">
                  {getRulePreview(knownRuleType, selectedTransaction)?.value}
                </div>
              </div>
            )}
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
