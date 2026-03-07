import { useState } from 'react'
import { useSearch } from 'wouter'
import {
  useInvoices,
  useInvoiceSuggestions,
  useMatchInvoice,
  useUnmatchInvoice,
  useDeleteInvoice,
  useUploadInvoice,
  useUpdateInvoice,
  useGDriveStatus,
  useRenameGDriveFile,
  useDashboard,
  showApiError,
  showSuccess,
  Invoice,
  MatchSuggestion,
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
import { Check, CreditCard, Upload, Trash2, Link2Off, Pencil } from 'lucide-react'

export function InvoicesPage() {
  const search = useSearch()
  const params = new URLSearchParams(search)
  const initialMonth = params.get('month') || ''
  const initialStatus = params.get('status') || ''

  const [month, setMonth] = useState(initialMonth)
  const [status, setStatus] = useState(initialStatus)
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null)
  const [showMatchModal, setShowMatchModal] = useState(false)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadVendor, setUploadVendor] = useState('')
  const [uploadDate, setUploadDate] = useState('')
  const [editFilename, setEditFilename] = useState('')
  const [editVendor, setEditVendor] = useState('')
  const [editAmount, setEditAmount] = useState('')
  const [editDate, setEditDate] = useState('')
  const [editPaymentType, setEditPaymentType] = useState('')
  const [editVs, setEditVs] = useState('')
  const [editIban, setEditIban] = useState('')

  const { data: dashboard } = useDashboard()
  const { data, isLoading, refetch } = useInvoices(month || undefined, status || undefined)
  const { data: suggestions } = useInvoiceSuggestions(
    showMatchModal ? selectedInvoice?.id ?? null : null
  )

  const matchInvoice = useMatchInvoice()
  const unmatchInvoice = useUnmatchInvoice()
  const deleteInvoice = useDeleteInvoice()
  const uploadInvoice = useUploadInvoice()
  const updateInvoice = useUpdateInvoice()
  const { data: gdriveStatus } = useGDriveStatus()
  const renameGDriveFile = useRenameGDriveFile()

  const handleMatch = async (transactionId: string) => {
    if (!selectedInvoice) return
    try {
      await matchInvoice.mutateAsync({
        invoiceId: selectedInvoice.id,
        transactionId,
      })
      showSuccess('Invoice matched successfully')
      setShowMatchModal(false)
      setSelectedInvoice(null)
      refetch()
    } catch (error) {
      showApiError(error, 'Match invoice')
    }
  }

  const handleUnmatch = async (invoice: Invoice) => {
    try {
      await unmatchInvoice.mutateAsync(invoice.id)
      showSuccess('Invoice unmatched')
      refetch()
    } catch (error) {
      showApiError(error, 'Unmatch invoice')
    }
  }

  const handleDelete = async () => {
    if (!selectedInvoice) return
    try {
      await deleteInvoice.mutateAsync(selectedInvoice.id)
      showSuccess('Invoice deleted')
      setShowDeleteModal(false)
      setSelectedInvoice(null)
      refetch()
    } catch (error) {
      showApiError(error, 'Delete invoice')
    }
  }

  const handleUpload = async () => {
    if (!uploadFile) return
    try {
      await uploadInvoice.mutateAsync({
        file: uploadFile,
        vendor: uploadVendor || undefined,
        invoiceDate: uploadDate || undefined,
      })
      showSuccess('Invoice uploaded')
      setShowUploadModal(false)
      setUploadFile(null)
      setUploadVendor('')
      setUploadDate('')
      refetch()
    } catch (error) {
      showApiError(error, 'Upload invoice')
    }
  }

  const openEditModal = (inv: Invoice) => {
    setSelectedInvoice(inv)
    setEditFilename(inv.filename || '')
    setEditVendor(inv.vendor || '')
    setEditAmount(inv.amount || '')
    setEditDate(inv.invoice_date || '')
    setEditPaymentType(inv.payment_type || 'card')
    setEditVs(inv.vs || '')
    setEditIban(inv.iban || '')
    setShowEditModal(true)
  }

  const handleEdit = async () => {
    if (!selectedInvoice) return

    const filenameChanged = editFilename !== selectedInvoice.filename

    // If filename changed, require GDrive connection for GDrive files
    if (filenameChanged && selectedInvoice.gdrive_file_id) {
      if (!gdriveStatus?.authenticated) {
        showApiError(new Error('Connect to Google Drive first to rename files'), 'Rename')
        return
      }

      try {
        // Rename in GDrive first
        await renameGDriveFile.mutateAsync({
          fileId: selectedInvoice.gdrive_file_id,
          newFilename: editFilename,
        })
      } catch (error) {
        showApiError(error, 'Rename in GDrive')
        return
      }
    }

    try {
      await updateInvoice.mutateAsync({
        invoiceId: selectedInvoice.id,
        vendor: editVendor || undefined,
        amount: editAmount || undefined,
        invoice_date: editDate || undefined,
        payment_type: editPaymentType || undefined,
        vs: editVs || undefined,
        iban: editIban || undefined,
      })
      showSuccess('Invoice updated')
      setShowEditModal(false)
      setSelectedInvoice(null)
      refetch()
    } catch (error) {
      showApiError(error, 'Update invoice')
    }
  }

  const formatAmount = (amount?: string) => {
    if (!amount) return '-'
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
      case 'exported':
        return <Badge className="bg-blue-100 text-blue-800">Exported</Badge>
      case 'cash':
        return <Badge className="bg-purple-100 text-purple-800">Cash</Badge>
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
    { value: 'exported', label: 'Exported' },
    { value: 'cash', label: 'Cash' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Invoices</h1>
        <Button onClick={() => setShowUploadModal(true)}>
          <Upload className="h-4 w-4 mr-2" />
          Upload Invoice
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
                  <TableHead>Filename</TableHead>
                  <TableHead>Vendor</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.invoices.map((inv) => (
                  <TableRow key={inv.id} className={inv.status === 'unmatched' ? 'bg-orange-50' : ''}>
                    <TableCell>{inv.invoice_date || '-'}</TableCell>
                    <TableCell>
                      <div className="max-w-xs truncate" title={inv.filename}>
                        {inv.gdrive_file_id ? (
                          <a
                            href={`/api/invoices/${inv.id}/pdf`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline"
                          >
                            {inv.filename}
                          </a>
                        ) : (
                          inv.filename
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{inv.vendor || '-'}</TableCell>
                    <TableCell>{formatAmount(inv.amount)}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{inv.payment_type || 'card'}</Badge>
                    </TableCell>
                    <TableCell>{getStatusBadge(inv.status)}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openEditModal(inv)}
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        {inv.status === 'unmatched' && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedInvoice(inv)
                                setShowMatchModal(true)
                              }}
                              title="Match to transaction"
                            >
                              <CreditCard className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedInvoice(inv)
                                setShowDeleteModal(true)
                              }}
                              title="Delete"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                        {inv.status === 'matched' && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleUnmatch(inv)}
                              title="Unmatch"
                            >
                              <Link2Off className="h-4 w-4" />
                            </Button>
                            <Button variant="outline" size="sm" disabled>
                              <Check className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {data?.invoices.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      No invoices found
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
            <DialogTitle>Match Invoice</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {selectedInvoice && (
              <div className="p-4 bg-muted rounded-lg">
                <div className="font-medium">{selectedInvoice.filename}</div>
                <div className="text-sm text-muted-foreground">
                  {selectedInvoice.vendor} - {formatAmount(selectedInvoice.amount)} - {selectedInvoice.invoice_date}
                </div>
              </div>
            )}
            <div className="space-y-2">
              <Label>Suggested Transactions</Label>
              {suggestions?.suggestions.length === 0 && (
                <p className="text-sm text-muted-foreground">No suggestions found</p>
              )}
              {suggestions?.suggestions.map((s: MatchSuggestion) => (
                <div
                  key={s.transaction_id}
                  className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted cursor-pointer"
                  onClick={() => handleMatch(s.transaction_id)}
                >
                  <div>
                    <div className="font-medium">{formatAmount(s.amount)}</div>
                    <div className="text-sm text-muted-foreground">
                      {s.date} - {s.counter_name || s.note || 'N/A'}
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

      {/* Upload Modal */}
      <Dialog open={showUploadModal} onOpenChange={setShowUploadModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Invoice</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>PDF File</Label>
              <Input
                type="file"
                accept=".pdf"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              />
            </div>
            <div>
              <Label>Vendor (optional)</Label>
              <Input
                value={uploadVendor}
                onChange={(e) => setUploadVendor(e.target.value)}
                placeholder="e.g., Alza, Hetzner"
              />
            </div>
            <div>
              <Label>Invoice Date (optional)</Label>
              <Input
                type="date"
                value={uploadDate}
                onChange={(e) => setUploadDate(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={!uploadFile}>
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <Dialog open={showDeleteModal} onOpenChange={setShowDeleteModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Invoice</DialogTitle>
          </DialogHeader>
          <p>Are you sure you want to delete this invoice?</p>
          {selectedInvoice && (
            <div className="p-4 bg-muted rounded-lg text-sm">
              <div className="font-medium">{selectedInvoice.filename}</div>
              <div className="text-muted-foreground">{selectedInvoice.vendor}</div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteModal(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Invoice Modal */}
      <Dialog open={showEditModal} onOpenChange={setShowEditModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Invoice</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Filename</Label>
              <Input
                value={editFilename}
                onChange={(e) => setEditFilename(e.target.value)}
                placeholder="filename.pdf"
              />
              {selectedInvoice?.gdrive_file_id && editFilename !== selectedInvoice.filename && (
                <p className="text-xs text-amber-600 mt-1">
                  {gdriveStatus?.authenticated
                    ? 'Will rename in Google Drive'
                    : 'Connect to Google Drive to rename files'}
                </p>
              )}
            </div>
            <div>
              <Label>Vendor</Label>
              <Input
                value={editVendor}
                onChange={(e) => setEditVendor(e.target.value)}
                placeholder="e.g., Google, Hetzner"
              />
            </div>
            <div>
              <Label>Amount</Label>
              <Input
                value={editAmount}
                onChange={(e) => setEditAmount(e.target.value)}
                placeholder="e.g., 123.45"
              />
            </div>
            <div>
              <Label>Invoice Date</Label>
              <Input
                type="date"
                value={editDate}
                onChange={(e) => setEditDate(e.target.value)}
              />
            </div>
            <div>
              <Label>Payment Type</Label>
              <Select
                value={editPaymentType}
                onChange={(e) => setEditPaymentType(e.target.value)}
                options={[
                  { value: 'card', label: 'Card' },
                  { value: 'wire', label: 'Wire Transfer' },
                  { value: 'cash', label: 'Cash' },
                  { value: 'sepa-debit', label: 'SEPA Direct Debit' },
                ]}
              />
            </div>
            <div>
              <Label>Variable Symbol (VS)</Label>
              <Input
                value={editVs}
                onChange={(e) => setEditVs(e.target.value)}
                placeholder="e.g., 2024001234"
              />
            </div>
            <div>
              <Label>IBAN</Label>
              <Input
                value={editIban}
                onChange={(e) => setEditIban(e.target.value)}
                placeholder="e.g., SK12 1234 5678 9012 3456"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleEdit}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
