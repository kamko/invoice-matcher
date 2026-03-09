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
  useReanalyzeInvoice,
  useGDriveStatus,
  useRenameGDriveFile,
  useDashboard,
  useSettings,
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
import { Check, CreditCard, Upload, Trash2, Link2Off, Pencil, RefreshCw } from 'lucide-react'

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
  const [uploadAmount, setUploadAmount] = useState('')
  const [uploadPaymentType, setUploadPaymentType] = useState('card')
  const [uploadAnalyzing, setUploadAnalyzing] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [editFilename, setEditFilename] = useState('')
  const [editVendor, setEditVendor] = useState('')
  const [editAmount, setEditAmount] = useState('')
  const [editDate, setEditDate] = useState('')
  const [editPaymentType, setEditPaymentType] = useState('')
  const [editVs, setEditVs] = useState('')
  const [editIban, setEditIban] = useState('')
  const [editCurrency, setEditCurrency] = useState('EUR')
  // Track parsed/suggested values from reanalyze
  const [parsedValues, setParsedValues] = useState<{
    vendor?: string
    amount?: string
    currency?: string
    invoice_date?: string
    payment_type?: string
    vs?: string
    iban?: string
  } | null>(null)

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
  const reanalyzeInvoice = useReanalyzeInvoice()
  const { data: gdriveStatus } = useGDriveStatus()
  const { data: settings } = useSettings()
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

    const folderId = settings?.invoice_parent_folder_id
    if (!folderId) {
      showApiError(new Error('No invoice folder configured. Go to Settings first.'), 'Upload')
      return
    }

    if (!gdriveStatus?.authenticated) {
      showApiError(new Error('Google Drive not connected. Go to Settings to connect.'), 'Upload')
      return
    }

    setIsUploading(true)
    try {
      await uploadInvoice.mutateAsync({
        file: uploadFile,
        vendor: uploadVendor || undefined,
        invoiceDate: uploadDate || undefined,
        paymentType: uploadPaymentType || 'card',  // Default to card if empty
        amount: uploadAmount || undefined,
        gdriveFolderId: folderId,
      })
      showSuccess('Invoice uploaded to Google Drive')
      setShowUploadModal(false)
      resetUploadForm()
      refetch()
    } catch (error) {
      showApiError(error, 'Upload invoice')
    } finally {
      setIsUploading(false)
    }
  }

  const resetUploadForm = () => {
    setUploadFile(null)
    setUploadVendor('')
    setUploadDate('')
    setUploadAmount('')
    setUploadPaymentType('card')
  }

  // Generate preview of the final filename
  const getPreviewFilename = () => {
    if (!uploadDate) return null
    const vendorSlug = uploadVendor
      ? uploadVendor.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').slice(0, 30)
      : 'unknown'
    return `${uploadDate}-001_${uploadPaymentType || 'card'}_${vendorSlug}.pdf`
  }

  const handleFileDrop = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      showApiError(new Error('Only PDF files allowed'), 'Upload')
      return
    }
    setUploadFile(file)
    // Auto-analyze after drop
    await analyzeUploadedFile(file)
  }

  const analyzeUploadedFile = async (file: File, showToast = false) => {
    setUploadAnalyzing(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/invoices/analyze', {
        method: 'POST',
        body: formData,
      })

      if (response.ok) {
        const data = await response.json()
        // Check if we got any extracted data
        const extracted = data.extracted || {}
        const hasData = extracted.vendor || extracted.amount || extracted.invoice_date || extracted.payment_type

        if (extracted.vendor) setUploadVendor(extracted.vendor)
        if (extracted.amount) setUploadAmount(extracted.amount)
        if (extracted.invoice_date) setUploadDate(extracted.invoice_date)
        if (extracted.payment_type) setUploadPaymentType(extracted.payment_type)

        if (showToast) {
          if (hasData) {
            showSuccess('PDF analyzed - fields updated')
          } else if (data.error) {
            showApiError(new Error(data.error), 'Analyze')
          } else {
            showApiError(new Error('No data extracted from PDF'), 'Analyze')
          }
        }
      } else {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        if (showToast) {
          showApiError(new Error(error.detail || 'Analyze failed'), 'Analyze')
        }
      }
    } catch (error) {
      if (showToast) {
        showApiError(error, 'Analyze PDF')
      }
    } finally {
      setUploadAnalyzing(false)
    }
  }

  const handleReanalyze = async () => {
    if (!selectedInvoice) return
    try {
      const result = await reanalyzeInvoice.mutateAsync(selectedInvoice.id)
      const extracted = result.extracted || {}
      const hasData = extracted.vendor || extracted.amount || extracted.invoice_date || extracted.payment_type

      // Store parsed values for comparison UI
      setParsedValues(extracted)

      // Auto-fill empty fields, but don't overwrite existing values
      // User can click on the suggestion to apply it
      if (!editVendor && extracted.vendor) setEditVendor(extracted.vendor)
      if (!editAmount && extracted.amount) setEditAmount(extracted.amount)
      if (extracted.currency) setEditCurrency(extracted.currency) // Always update currency
      if (!editDate && extracted.invoice_date) setEditDate(extracted.invoice_date)
      if (!editPaymentType && extracted.payment_type) setEditPaymentType(extracted.payment_type)
      if (!editVs && extracted.vs) setEditVs(extracted.vs)
      if (!editIban && extracted.iban) setEditIban(extracted.iban)

      if (hasData) {
        showSuccess('Parsed data loaded - click suggestions to apply')
      } else {
        showApiError(new Error('No data could be extracted from PDF'), 'Reanalyze')
      }
    } catch (error) {
      showApiError(error, 'Reanalyze invoice')
    }
  }

  // Helper to check if a field has a different parsed suggestion
  const hasSuggestion = (field: keyof NonNullable<typeof parsedValues>, currentValue: string) => {
    if (!parsedValues || !parsedValues[field]) return false
    return parsedValues[field] !== currentValue
  }

  // Apply a parsed suggestion to a field
  const applySuggestion = (field: keyof NonNullable<typeof parsedValues>) => {
    if (!parsedValues || !parsedValues[field]) return
    const value = parsedValues[field]!
    switch (field) {
      case 'vendor': setEditVendor(value); break
      case 'amount': setEditAmount(value); break
      case 'invoice_date': setEditDate(value); break
      case 'payment_type': setEditPaymentType(value); break
      case 'vs': setEditVs(value); break
      case 'iban': setEditIban(value); break
    }
  }

  // Generate filename from parts: YYYY-MM-DD-NNN_type_vendor.pdf
  const generateFilename = (date: string, type: string, vendor: string, originalFilename: string) => {
    // Extract the sequence number from original filename (e.g., "001" from "2026-03-07-001_card_obi.pdf")
    const match = originalFilename.match(/^\d{4}-\d{2}-\d{2}-(\d+)_/)
    const seq = match ? match[1] : '001'

    // Slugify vendor: lowercase, replace spaces with dashes, remove special chars
    const vendorSlug = vendor
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .substring(0, 30) || 'unknown'

    return `${date}-${seq}_${type}_${vendorSlug}.pdf`
  }

  // Compute preview filename based on current edit values
  const previewFilename = selectedInvoice && editDate && editPaymentType && editVendor
    ? generateFilename(editDate, editPaymentType, editVendor, selectedInvoice.filename || '')
    : editFilename

  const openEditModal = (inv: Invoice) => {
    setSelectedInvoice(inv)
    setEditFilename(inv.filename || '')
    setEditVendor(inv.vendor || '')
    setEditAmount(inv.amount || '')
    setEditCurrency(inv.currency || 'EUR')
    setEditDate(inv.invoice_date || '')
    setEditPaymentType(inv.payment_type || 'card')
    setEditVs(inv.vs || '')
    setEditIban(inv.iban || '')
    setParsedValues(null) // Reset parsed values
    setShowEditModal(true)
  }

  const handleEdit = async () => {
    if (!selectedInvoice) return

    // Use the generated preview filename
    const newFilename = previewFilename
    const filenameChanged = newFilename !== selectedInvoice.filename

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
          newFilename: newFilename,
        })
      } catch (error) {
        showApiError(error, 'Rename in GDrive')
        return
      }
    }

    try {
      await updateInvoice.mutateAsync({
        invoiceId: selectedInvoice.id,
        filename: filenameChanged ? newFilename : undefined,
        vendor: editVendor || undefined,
        amount: editAmount || undefined,
        currency: editCurrency || undefined,
        invoice_date: editDate || undefined,
        payment_type: editPaymentType || undefined,
        vs: editVs || undefined,
        iban: editIban || undefined,
      })
      showSuccess(filenameChanged ? 'Invoice updated & renamed' : 'Invoice updated')
      setShowEditModal(false)
      setSelectedInvoice(null)
      refetch()
    } catch (error) {
      showApiError(error, 'Update invoice')
    }
  }

  const formatAmount = (amount?: string, currency: string = 'EUR') => {
    if (!amount) return '-'
    const num = parseFloat(amount)
    return new Intl.NumberFormat('sk-SK', {
      style: 'currency',
      currency: currency,
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
                    <TableCell>
                      {formatAmount(inv.amount, inv.currency)}
                      {inv.currency !== 'EUR' && (
                        <span className="ml-1 text-xs text-orange-600 font-medium">{inv.currency}</span>
                      )}
                    </TableCell>
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
        <DialogContent className="max-w-3xl">
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
              {suggestions?.suggestions && suggestions.suggestions.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-24">Date</TableHead>
                      <TableHead>Vendor</TableHead>
                      <TableHead className="w-24 text-right">Amount</TableHead>
                      <TableHead>Why</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {suggestions.suggestions.map((s: MatchSuggestion) => (
                      <TableRow
                        key={s.transaction_id}
                        className="cursor-pointer hover:bg-muted"
                        onClick={() => handleMatch(s.transaction_id)}
                      >
                        <TableCell className="text-sm">{s.date}</TableCell>
                        <TableCell>
                          <div className="font-medium">
                            {s.extracted_vendor || s.counter_name || '(unknown)'}
                          </div>
                          {s.extracted_vendor && s.counter_name && s.extracted_vendor !== s.counter_name && (
                            <div className="text-xs text-muted-foreground truncate max-w-48" title={s.counter_name}>
                              {s.counter_name}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="text-right font-mono">{formatAmount(s.amount)}</TableCell>
                        <TableCell>
                          <div className="flex gap-2 text-xs">
                            <span className={s.amount_score >= 50 ? 'text-green-600' : 'text-muted-foreground'}>
                              Amt {s.amount_score >= 50 ? '✓' : '✗'}
                            </span>
                            <span className={s.date_score >= 20 ? 'text-green-600' : 'text-orange-500'}>
                              {s.date_diff_days !== undefined && s.date_diff_days !== null
                                ? `${s.date_diff_days}d`
                                : '?d'
                              }
                            </span>
                            <span className={s.vendor_score >= 10 ? 'text-green-600' : 'text-muted-foreground'}>
                              Vnd {s.vendor_score >= 10 ? '~' : '?'}
                            </span>
                            <Badge variant="outline" className="text-xs px-1.5 py-0">
                              {s.score}
                            </Badge>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
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
      <Dialog open={showUploadModal} onOpenChange={(open) => {
        setShowUploadModal(open)
        if (!open) resetUploadForm()
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Invoice</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {/* Drag & Drop Zone */}
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                isDragging
                  ? 'border-blue-500 bg-blue-50'
                  : uploadFile
                    ? 'border-green-500 bg-green-50'
                    : 'border-gray-300 hover:border-gray-400'
              }`}
              onDragOver={(e) => {
                e.preventDefault()
                setIsDragging(true)
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setIsDragging(false)
                const file = e.dataTransfer.files[0]
                if (file) handleFileDrop(file)
              }}
            >
              {uploadAnalyzing ? (
                <div className="flex flex-col items-center gap-2">
                  <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
                  <span className="text-sm text-muted-foreground">Analyzing PDF...</span>
                </div>
              ) : uploadFile ? (
                <div className="flex flex-col items-center gap-2">
                  <Check className="h-8 w-8 text-green-600" />
                  <span className="font-medium">{uploadFile.name}</span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => analyzeUploadedFile(uploadFile, true)}
                      disabled={uploadAnalyzing}
                    >
                      <RefreshCw className={`h-4 w-4 mr-1 ${uploadAnalyzing ? 'animate-spin' : ''}`} />
                      Re-analyze
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => resetUploadForm()}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Upload className="h-8 w-8 text-gray-400" />
                  <span className="text-sm text-muted-foreground">
                    Drag & drop PDF here, or
                  </span>
                  <label className="cursor-pointer">
                    <span className="text-sm text-blue-600 hover:underline">browse files</span>
                    <input
                      type="file"
                      accept=".pdf"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) handleFileDrop(file)
                      }}
                    />
                  </label>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Vendor</Label>
                <Input
                  value={uploadVendor}
                  onChange={(e) => setUploadVendor(e.target.value)}
                  placeholder="e.g., Alza, Hetzner"
                />
              </div>
              <div>
                <Label>Amount</Label>
                <Input
                  value={uploadAmount}
                  onChange={(e) => setUploadAmount(e.target.value)}
                  placeholder="e.g., 123.45"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Invoice Date</Label>
                <Input
                  type="date"
                  value={uploadDate}
                  onChange={(e) => setUploadDate(e.target.value)}
                />
              </div>
              <div>
                <Label>Payment Type</Label>
                <Select
                  value={uploadPaymentType}
                  onChange={(e) => setUploadPaymentType(e.target.value)}
                  options={[
                    { value: 'card', label: 'Card' },
                    { value: 'wire', label: 'Wire Transfer' },
                    { value: 'cash', label: 'Cash' },
                    { value: 'sepa-debit', label: 'SEPA Direct Debit' },
                  ]}
                />
              </div>
            </div>

            {/* Filename Preview */}
            {getPreviewFilename() && (
              <div className="p-3 bg-muted rounded-lg">
                <Label className="text-xs text-muted-foreground">Will be saved as:</Label>
                <div className="font-mono text-sm mt-1">{getPreviewFilename()}</div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadModal(false)} disabled={isUploading}>
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={!uploadFile || uploadAnalyzing || isUploading}>
              {isUploading ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                'Upload'
              )}
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
            {/* Reanalyze button */}
            {selectedInvoice?.gdrive_file_id && (
              <div className="flex justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReanalyze}
                  disabled={reanalyzeInvoice.isPending}
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${reanalyzeInvoice.isPending ? 'animate-spin' : ''}`} />
                  {reanalyzeInvoice.isPending ? 'Analyzing...' : 'Re-analyze PDF'}
                </Button>
              </div>
            )}
            {/* Filename Preview */}
            <div>
              <Label>Filename Preview</Label>
              <div className="flex items-center gap-2">
                <code className={`flex-1 px-3 py-2 bg-muted rounded text-sm ${
                  previewFilename !== selectedInvoice?.filename ? 'ring-2 ring-blue-500' : ''
                }`}>
                  {previewFilename}
                </code>
              </div>
              {selectedInvoice?.gdrive_file_id && previewFilename !== selectedInvoice.filename && (
                <p className="text-xs text-blue-600 mt-1">
                  {gdriveStatus?.authenticated
                    ? 'Will rename in Google Drive on save'
                    : 'Connect to Google Drive to rename files'}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Label>Vendor</Label>
                  {hasSuggestion('vendor', editVendor) && (
                    <button
                      type="button"
                      className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                      onClick={() => applySuggestion('vendor')}
                    >
                      Use: {parsedValues?.vendor}
                    </button>
                  )}
                </div>
                <Input
                  value={editVendor}
                  onChange={(e) => setEditVendor(e.target.value)}
                  placeholder="e.g., Google, Hetzner"
                  className={hasSuggestion('vendor', editVendor) ? 'border-blue-300' : ''}
                />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <Label>Amount</Label>
                  {hasSuggestion('amount', editAmount) && (
                    <button
                      type="button"
                      className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                      onClick={() => applySuggestion('amount')}
                    >
                      Use: {parsedValues?.amount}
                    </button>
                  )}
                </div>
                <div className="flex gap-2">
                  <Input
                    value={editAmount}
                    onChange={(e) => setEditAmount(e.target.value)}
                    placeholder="e.g., 123.45"
                    className={`flex-1 ${hasSuggestion('amount', editAmount) ? 'border-blue-300' : ''}`}
                  />
                  <Select
                    value={editCurrency}
                    onChange={(e) => setEditCurrency(e.target.value)}
                    options={[
                      { value: 'EUR', label: 'EUR' },
                      { value: 'USD', label: 'USD' },
                      { value: 'CZK', label: 'CZK' },
                      { value: 'GBP', label: 'GBP' },
                    ]}
                    className="w-20"
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Label>Invoice Date</Label>
                  {hasSuggestion('invoice_date', editDate) && (
                    <button
                      type="button"
                      className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                      onClick={() => applySuggestion('invoice_date')}
                    >
                      Use: {parsedValues?.invoice_date}
                    </button>
                  )}
                </div>
                <Input
                  type="date"
                  value={editDate}
                  onChange={(e) => setEditDate(e.target.value)}
                  className={hasSuggestion('invoice_date', editDate) ? 'border-blue-300' : ''}
                />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <Label>Payment Type</Label>
                  {hasSuggestion('payment_type', editPaymentType) && (
                    <button
                      type="button"
                      className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                      onClick={() => applySuggestion('payment_type')}
                    >
                      Use: {parsedValues?.payment_type}
                    </button>
                  )}
                </div>
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
            </div>

            {editPaymentType === 'wire' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <Label>Variable Symbol (VS)</Label>
                    {hasSuggestion('vs', editVs) && (
                      <button
                        type="button"
                        className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                        onClick={() => applySuggestion('vs')}
                      >
                        Use: {parsedValues?.vs}
                      </button>
                    )}
                  </div>
                  <Input
                    value={editVs}
                    onChange={(e) => setEditVs(e.target.value)}
                    placeholder="e.g., 2024001234"
                    className={hasSuggestion('vs', editVs) ? 'border-blue-300' : ''}
                  />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <Label>IBAN</Label>
                    {hasSuggestion('iban', editIban) && (
                      <button
                        type="button"
                        className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                        onClick={() => applySuggestion('iban')}
                      >
                        Use: {parsedValues?.iban}
                      </button>
                    )}
                  </div>
                  <Input
                    value={editIban}
                    onChange={(e) => setEditIban(e.target.value)}
                    placeholder="e.g., SK12 1234 5678 9012 3456"
                    className={hasSuggestion('iban', editIban) ? 'border-blue-300' : ''}
                  />
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleEdit}
              className={previewFilename !== selectedInvoice?.filename ? 'ring-2 ring-blue-500' : ''}
            >
              {previewFilename !== selectedInvoice?.filename ? 'Save & Rename' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
