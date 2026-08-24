import { useState } from 'react'
import { useSearch } from 'wouter'
import {
  authFetch,
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
import { Check, CreditCard, Upload, Trash2, Link2Off, Pencil, RefreshCw, MessageSquareText, FileText, X, Car, Archive } from 'lucide-react'

interface UploadDraft {
  id: string
  file: File
  vendor: string
  documentType: string
  invoiceDate: string
  amount: string
  paymentType: string
  comment: string
  vehicleRegistration: string
  isVehicleExpense: boolean
  includeInExport: boolean
  skipAnalyze: boolean
  analyzing: boolean
  error?: string
}

const createUploadDraft = (file: File): UploadDraft => ({
  id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2)}`,
  file,
  vendor: '',
  documentType: 'invoice',
  invoiceDate: '',
  amount: '',
  paymentType: 'card',
  comment: '',
  vehicleRegistration: '',
  isVehicleExpense: false,
  includeInExport: true,
  skipAnalyze: false,
  analyzing: false,
})

export function InvoicesPage() {
  const search = useSearch()
  const params = new URLSearchParams(search)
  const initialMonth = params.get('month') || ''
  const initialStatus = params.get('status') || ''
  const initialDocumentType = params.get('document_type') || ''

  const [month, setMonth] = useState(initialMonth)
  const [status, setStatus] = useState(initialStatus)
  const [documentType, setDocumentType] = useState(initialDocumentType)
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null)
  const [showMatchModal, setShowMatchModal] = useState(false)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [uploadDrafts, setUploadDrafts] = useState<UploadDraft[]>([])
  const [selectedUploadId, setSelectedUploadId] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [editFilename, setEditFilename] = useState('')
  const [editVendor, setEditVendor] = useState('')
  const [editDocumentType, setEditDocumentType] = useState('invoice')
  const [editAmount, setEditAmount] = useState('')
  const [editDate, setEditDate] = useState('')
  const [editPaymentType, setEditPaymentType] = useState('')
  const [editVs, setEditVs] = useState('')
  const [editIban, setEditIban] = useState('')
  const [editCurrency, setEditCurrency] = useState('EUR')
  const [editComment, setEditComment] = useState('')
  const [editVehicleRegistration, setEditVehicleRegistration] = useState('')
  const [editIsVehicleExpense, setEditIsVehicleExpense] = useState(false)
  const [editIncludeInExport, setEditIncludeInExport] = useState(true)
  // Track parsed/suggested values from reanalyze
  const [parsedValues, setParsedValues] = useState<{
    vendor?: string
    document_type?: string
    amount?: string
    currency?: string
    invoice_date?: string
    payment_type?: string
    vs?: string
    iban?: string
  } | null>(null)

  const { data: dashboard } = useDashboard()
  const { data, isLoading, refetch } = useInvoices(month || undefined, status || undefined, documentType || undefined)
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
  const selectedUpload = uploadDrafts.find((draft) => draft.id === selectedUploadId) || null
  const uploadAnalyzing = uploadDrafts.some((draft) => draft.analyzing)
  const uploadVendor = selectedUpload?.vendor || ''
  const uploadDocumentType = selectedUpload?.documentType || 'invoice'
  const uploadDate = selectedUpload?.invoiceDate || ''
  const uploadAmount = selectedUpload?.amount || ''
  const uploadPaymentType = selectedUpload?.paymentType || 'card'
  const uploadComment = selectedUpload?.comment || ''
  const uploadSkipAnalyze = selectedUpload?.skipAnalyze || false
  const setUploadVendor = (value: string) => selectedUploadId && updateUploadDraft(selectedUploadId, { vendor: value })
  const setUploadDocumentType = (value: string) => selectedUploadId && updateUploadDraft(selectedUploadId, { documentType: value })
  const setUploadDate = (value: string) => selectedUploadId && updateUploadDraft(selectedUploadId, { invoiceDate: value })
  const setUploadAmount = (value: string) => selectedUploadId && updateUploadDraft(selectedUploadId, { amount: value })
  const setUploadPaymentType = (value: string) => selectedUploadId && updateUploadDraft(selectedUploadId, { paymentType: value })
  const setUploadComment = (value: string) => selectedUploadId && updateUploadDraft(selectedUploadId, { comment: value })
  const setUploadSkipAnalyze = (value: boolean) => selectedUploadId && updateUploadDraft(selectedUploadId, { skipAnalyze: value })

  const updateUploadDraft = (id: string, changes: Partial<UploadDraft>) => {
    setUploadDrafts((drafts) => drafts.map((draft) => (
      draft.id === id ? { ...draft, ...changes, error: changes.error } : draft
    )))
  }

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
    if (uploadDrafts.length === 0) return

    const folderId = settings?.invoice_parent_folder_id
    if (!folderId) {
      showApiError(new Error('No invoice folder configured. Go to Settings first.'), 'Upload')
      return
    }

    if (!gdriveStatus?.authenticated) {
      showApiError(new Error('Google Drive not connected. Go to Settings to connect.'), 'Upload')
      return
    }

    const invalidDraft = uploadDrafts.find((draft) => (
      !draft.invoiceDate
      || (draft.isVehicleExpense && !/^[A-Z]{2}\d{3}[A-Z]{2}$/.test(
        draft.vehicleRegistration.replace(/[\s-]/g, '').toUpperCase()
      ))
    ))
    if (invalidDraft) {
      setSelectedUploadId(invalidDraft.id)
      showApiError(
        new Error(
          !invalidDraft.invoiceDate
            ? `Add a date for ${invalidDraft.file.name}`
            : `Add a vehicle registration in the format KE885HH for ${invalidDraft.file.name}`
        ),
        'Upload'
      )
      return
    }

    setIsUploading(true)
    const successfulIds: string[] = []
    const failures: Array<{ id: string; message: string }> = []

    for (const draft of uploadDrafts) {
      try {
        await uploadInvoice.mutateAsync({
          file: draft.file,
          vendor: draft.vendor || undefined,
          documentType: draft.documentType || undefined,
          invoiceDate: draft.invoiceDate || undefined,
          paymentType: draft.paymentType || 'card',
          amount: draft.amount || undefined,
          comment: draft.comment.trim() || undefined,
          vehicleRegistration: draft.vehicleRegistration.replace(/[\s-]/g, '').toUpperCase() || undefined,
          isVehicleExpense: draft.isVehicleExpense,
          includeInExport: draft.includeInExport,
          gdriveFolderId: folderId,
          skipAnalyze: draft.skipAnalyze,
        })
        successfulIds.push(draft.id)
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Upload failed'
        failures.push({ id: draft.id, message })
        updateUploadDraft(draft.id, { error: message })
      }
    }

    setIsUploading(false)
    if (failures.length === 0) {
      showSuccess(`${successfulIds.length} ${successfulIds.length === 1 ? 'PDF uploaded' : 'PDFs uploaded'} to Google Drive`)
      setShowUploadModal(false)
      resetUploadForm()
    } else {
      setUploadDrafts((drafts) => drafts.filter((draft) => !successfulIds.includes(draft.id)))
      setSelectedUploadId(failures[0].id)
      showApiError(
        new Error(`${failures.length} ${failures.length === 1 ? 'file needs' : 'files need'} attention. ${failures[0].message}`),
        'Upload'
      )
    }
    refetch()
  }

  const resetUploadForm = () => {
    setUploadDrafts([])
    setSelectedUploadId(null)
  }

  const removeUploadDraft = (id: string) => {
    setUploadDrafts((drafts) => {
      const remaining = drafts.filter((draft) => draft.id !== id)
      if (selectedUploadId === id) {
        setSelectedUploadId(remaining[0]?.id || null)
      }
      return remaining
    })
  }

  // Generate preview of the final filename
  const getPreviewFilename = (draft: UploadDraft | null = selectedUpload) => {
    if (!draft) return null
    if (!draft.invoiceDate) return null
    const vendorSlug = draft.vendor
      ? draft.vendor.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').slice(0, 30)
      : 'unknown'
    const plateSuffix = draft.vehicleRegistration
      ? `_${draft.vehicleRegistration.replace(/[\s-]/g, '').toUpperCase()}`
      : ''
    return `${draft.invoiceDate}-001_${draft.paymentType || 'card'}_${vendorSlug}${plateSuffix}.pdf`
  }

  const handleFileDrop = async (files: File[]) => {
    const pdfFiles = files.filter((file) => file.name.toLowerCase().endsWith('.pdf'))
    if (pdfFiles.length !== files.length) {
      showApiError(new Error('Only PDF files are supported'), 'Upload')
    }
    if (pdfFiles.length === 0) {
      return
    }

    const existingKeys = new Set(uploadDrafts.map((draft) => (
      `${draft.file.name}-${draft.file.size}-${draft.file.lastModified}`
    )))
    const newDrafts = pdfFiles
      .filter((file) => !existingKeys.has(`${file.name}-${file.size}-${file.lastModified}`))
      .map(createUploadDraft)

    if (newDrafts.length === 0) return
    setUploadDrafts((drafts) => [...drafts, ...newDrafts])
    setSelectedUploadId((current) => current || newDrafts[0].id)
    await Promise.all(newDrafts.map((draft) => analyzeUploadedFile(draft.id, draft.file)))
  }

  const analyzeUploadedFile = async (id: string, file: File, showToast = false) => {
    updateUploadDraft(id, { analyzing: true, error: undefined })
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await authFetch('/invoices/analyze', {
        method: 'POST',
        body: formData,
      })

      if (response.ok) {
        const data = await response.json()
        // Check if we got any extracted data
        const extracted = data.extracted || {}
        const hasData = extracted.vendor || extracted.document_type || extracted.amount || extracted.invoice_date || extracted.payment_type

        setUploadDrafts((drafts) => drafts.map((draft) => draft.id === id ? {
          ...draft,
          vendor: extracted.vendor || draft.vendor,
          documentType: extracted.document_type || draft.documentType,
          amount: extracted.amount || draft.amount,
          invoiceDate: extracted.invoice_date || draft.invoiceDate,
          paymentType: extracted.payment_type || draft.paymentType,
          analyzing: false,
          error: undefined,
        } : draft))

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
      updateUploadDraft(id, {
        error: error instanceof Error ? error.message : 'Analyze failed',
      })
      if (showToast) {
        showApiError(error, 'Analyze PDF')
      }
    } finally {
      setUploadDrafts((drafts) => drafts.map((draft) => (
        draft.id === id ? { ...draft, analyzing: false } : draft
      )))
    }
  }

  const handleReanalyze = async () => {
    if (!selectedInvoice) return
    try {
      const result = await reanalyzeInvoice.mutateAsync(selectedInvoice.id)
      const extracted = result.extracted || {}
      const hasData = extracted.vendor || extracted.document_type || extracted.amount || extracted.invoice_date || extracted.payment_type

      // Store parsed values for comparison UI
      setParsedValues(extracted)

      // Auto-fill empty fields, but don't overwrite existing values
      // User can click on the suggestion to apply it
      if (!editVendor && extracted.vendor) setEditVendor(extracted.vendor)
      if (!editDocumentType && extracted.document_type) setEditDocumentType(extracted.document_type)
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
      case 'document_type': setEditDocumentType(value); break
      case 'amount': setEditAmount(value); break
      case 'invoice_date': setEditDate(value); break
      case 'payment_type': setEditPaymentType(value); break
      case 'vs': setEditVs(value); break
      case 'iban': setEditIban(value); break
    }
  }

  // Generate filename from parts: YYYY-MM-DD-NNN_type_vendor.pdf
  const generateFilename = (
    date: string,
    type: string,
    vendor: string,
    vehicleRegistration: string,
    originalFilename: string
  ) => {
    // Extract the sequence number from original filename (e.g., "001" from "2026-03-07-001_card_obi.pdf")
    const match = originalFilename.match(/^\d{4}-\d{2}-\d{2}-(\d+)_/)
    const seq = match ? match[1] : '001'

    // Slugify vendor: lowercase, replace spaces with dashes, remove special chars
    const vendorSlug = vendor
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .substring(0, 30) || 'unknown'

    const plateSuffix = vehicleRegistration
      ? `_${vehicleRegistration.replace(/[\s-]/g, '').toUpperCase()}`
      : ''
    return `${date}-${seq}_${type}_${vendorSlug}${plateSuffix}.pdf`
  }

  // Compute preview filename based on current edit values
  const previewFilename = selectedInvoice && editDate && editPaymentType
    ? generateFilename(
        editDate,
        editPaymentType,
        editVendor,
        editVehicleRegistration,
        selectedInvoice.filename || ''
      )
    : editFilename

  const openEditModal = (inv: Invoice) => {
    setSelectedInvoice(inv)
    setEditFilename(inv.filename || '')
    setEditVendor(inv.vendor || '')
    setEditDocumentType(inv.document_type || 'invoice')
    setEditAmount(inv.amount || '')
    setEditCurrency(inv.currency || 'EUR')
    setEditDate(inv.invoice_date || '')
    const validPaymentTypes = ['card', 'wire', 'cash', 'sepa-debit', 'cod']
    setEditPaymentType(validPaymentTypes.includes(inv.payment_type || '') ? inv.payment_type! : 'card')
    setEditVs(inv.vs || '')
    setEditIban(inv.iban || '')
    setEditComment(inv.comment || '')
    setEditVehicleRegistration(inv.vehicle_registration || '')
    setEditIsVehicleExpense(inv.is_vehicle_expense || false)
    setEditIncludeInExport(inv.include_in_export)
    setParsedValues(null) // Reset parsed values
    setShowEditModal(true)
  }

  const handleEdit = async () => {
    if (!selectedInvoice) return

    const normalizedRegistration = editVehicleRegistration.replace(/[\s-]/g, '').toUpperCase()
    if (editIsVehicleExpense && !/^[A-Z]{2}\d{3}[A-Z]{2}$/.test(normalizedRegistration)) {
      showApiError(new Error('Use the vehicle registration format KE885HH'), 'Update invoice')
      return
    }
    if (selectedInvoice.status === 'matched' && !editIncludeInExport) {
      showApiError(
        new Error('Unmatch this document before excluding it from accountant export'),
        'Update invoice'
      )
      return
    }

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
        document_type: editDocumentType || undefined,
        amount: editAmount || undefined,
        currency: editCurrency || undefined,
        invoice_date: editDate || undefined,
        payment_type: editPaymentType || undefined,
        vs: editVs || undefined,
        iban: editIban || undefined,
        comment: editComment.trim(),
        vehicle_registration: normalizedRegistration,
        is_vehicle_expense: editIsVehicleExpense,
        include_in_export: editIncludeInExport,
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
      case 'reference':
        return <Badge variant="outline">Internal only</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  const getDocumentTypeBadge = (value?: string) => {
    switch (value) {
      case 'receipt':
        return <Badge className="bg-amber-100 text-amber-800">Receipt</Badge>
      case 'other':
        return <Badge className="bg-slate-100 text-slate-800">Other</Badge>
      default:
        return <Badge className="bg-sky-100 text-sky-800">Invoice</Badge>
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
    { value: 'reference', label: 'Internal only' },
  ]

  const documentTypeOptions = [
    { value: '', label: 'All document types' },
    { value: 'invoice', label: 'Invoices' },
    { value: 'receipt', label: 'Receipts' },
    { value: 'other', label: 'Other' },
  ]

  const documentTypeInputOptions = [
    { value: 'invoice', label: 'Invoice' },
    { value: 'receipt', label: 'Receipt' },
    { value: 'other', label: 'Other' },
  ]

  const knownVehicleRegistrations = Array.from(new Set(
    (data?.invoices || [])
      .map((invoice) => invoice.vehicle_registration)
      .filter((value): value is string => Boolean(value))
  )).sort()

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Invoices</h1>
        <Button className="w-full sm:w-auto" onClick={() => setShowUploadModal(true)}>
          <Upload className="h-4 w-4 mr-2" />
          Upload Invoice
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap">
            <div className="w-full sm:w-48">
              <Label>Month</Label>
              <Select
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                options={monthOptions}
              />
            </div>
            <div className="w-full sm:w-48">
              <Label>Status</Label>
              <Select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                options={statusOptions}
              />
            </div>
            <div className="w-full sm:w-48">
              <Label>Document Type</Label>
              <Select
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value)}
                options={documentTypeOptions}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      {data && (
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
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
                  <TableHead>Document</TableHead>
                  <TableHead>Payment</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.invoices.map((inv) => (
                  <TableRow key={inv.id} className={inv.status === 'unmatched' ? 'bg-orange-50' : ''}>
                    <TableCell>{inv.invoice_date || '-'}</TableCell>
                    <TableCell>
                      <div className="flex max-w-xs items-center gap-2">
                        <div className="truncate" title={inv.filename}>
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
                        {inv.comment && (
                          <MessageSquareText
                            className="h-4 w-4 shrink-0 text-muted-foreground"
                            aria-label="Has accountant comment"
                          >
                            <title>{inv.comment}</title>
                          </MessageSquareText>
                        )}
                        {!inv.include_in_export && (
                          <Archive className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="Internal only">
                            <title>Internal only, excluded from accountant export</title>
                          </Archive>
                        )}
                      </div>
                      {inv.vehicle_registration && (
                        <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                          <Car className="h-3.5 w-3.5" />
                          {inv.vehicle_registration}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>{inv.vendor || '-'}</TableCell>
                    <TableCell>
                      {formatAmount(inv.amount, inv.currency)}
                      {inv.currency !== 'EUR' && (
                        <span className="ml-1 text-xs text-orange-600 font-medium">{inv.currency}</span>
                      )}
                    </TableCell>
                    <TableCell>{getDocumentTypeBadge(inv.document_type)}</TableCell>
                    <TableCell><Badge variant="outline">{inv.payment_type || 'card'}</Badge></TableCell>
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
                        {inv.status === 'unmatched' && inv.include_in_export && (
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
                        {inv.status === 'reference' && (
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
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {data?.invoices.length === 0 && (
                  <TableRow>
                      <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
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
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Upload PDFs</DialogTitle>
          </DialogHeader>
          <div className="min-w-0 space-y-4">
            {/* Drag & Drop Zone */}
            <div
              className={`min-w-0 overflow-hidden border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                isDragging
                  ? 'border-blue-500 bg-blue-50'
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
                handleFileDrop(Array.from(e.dataTransfer.files))
              }}
            >
              <div className="flex min-w-0 flex-col items-center gap-2">
                <Upload className="h-8 w-8 text-gray-400" />
                <span className="text-sm text-muted-foreground">
                  Drag and drop one or more PDFs here, or
                </span>
                <label className="cursor-pointer">
                  <span className="text-sm text-blue-600 hover:underline">browse files</span>
                  <input
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      const files = Array.from(e.target.files || [])
                      if (files.length) handleFileDrop(files)
                      e.target.value = ''
                    }}
                  />
                </label>
              </div>
            </div>

            {uploadDrafts.length > 0 && (
              <div className="overflow-hidden rounded-md border">
                {uploadDrafts.map((draft) => (
                  <div
                    key={draft.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedUploadId(draft.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setSelectedUploadId(draft.id)
                      }
                    }}
                    className={`flex w-full items-center gap-3 border-b px-3 py-2.5 text-left last:border-b-0 ${
                      selectedUploadId === draft.id ? 'bg-muted' : 'hover:bg-muted/50'
                    }`}
                  >
                    {draft.analyzing ? (
                      <RefreshCw className="h-4 w-4 shrink-0 animate-spin text-blue-600" />
                    ) : draft.error ? (
                      <FileText className="h-4 w-4 shrink-0 text-red-600" />
                    ) : (
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{draft.file.name}</span>
                    {draft.vehicleRegistration && (
                      <span className="hidden text-xs font-medium text-muted-foreground sm:inline">
                        {draft.vehicleRegistration.replace(/[\s-]/g, '').toUpperCase()}
                      </span>
                    )}
                    <Badge variant={draft.includeInExport ? 'default' : 'outline'}>
                      {draft.includeInExport ? 'Export' : 'Internal'}
                    </Badge>
                    <button
                      type="button"
                      aria-label={`Remove ${draft.file.name}`}
                      onClick={(event) => {
                        event.stopPropagation()
                        removeUploadDraft(draft.id)
                      }}
                      className="rounded p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {selectedUpload?.error && (
              <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {selectedUpload.error}
              </p>
            )}

            {selectedUpload && (
              <div className="flex items-center justify-between gap-3 border-b pb-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">Document details</p>
                  <p className="truncate text-xs text-muted-foreground">{selectedUpload.file.name}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => analyzeUploadedFile(selectedUpload.id, selectedUpload.file, true)}
                  disabled={selectedUpload.analyzing}
                >
                  <RefreshCw className={`mr-1 h-4 w-4 ${selectedUpload.analyzing ? 'animate-spin' : ''}`} />
                  Re-analyze
                </Button>
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="min-w-0">
                <Label>Vendor</Label>
                <Input
                  value={uploadVendor}
                  onChange={(e) => setUploadVendor(e.target.value)}
                  placeholder="e.g., Alza, Hetzner"
                />
              </div>
              <div className="min-w-0">
                <Label>Amount</Label>
                <Input
                  value={uploadAmount}
                  onChange={(e) => setUploadAmount(e.target.value)}
                  placeholder="e.g., 123.45"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="min-w-0">
                <Label>Invoice Date</Label>
                <Input
                  type="date"
                  value={uploadDate}
                  onChange={(e) => setUploadDate(e.target.value)}
                />
              </div>
              <div className="min-w-0">
                <Label>Document Type</Label>
                <Select
                  value={uploadDocumentType}
                  onChange={(e) => setUploadDocumentType(e.target.value)}
                  options={documentTypeInputOptions}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="min-w-0">
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
              <div />
            </div>

            {selectedUpload && (
              <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    checked={selectedUpload.includeInExport}
                    onChange={(event) => updateUploadDraft(selectedUpload.id, {
                      includeInExport: event.target.checked,
                    })}
                    className="mt-0.5 h-4 w-4 shrink-0"
                  />
                  <span>
                    <span className="block text-sm font-medium">Include in accountant export</span>
                    <span className="block text-xs text-muted-foreground">
                      Turn off for internal statements and supporting files.
                    </span>
                  </span>
                </label>
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    checked={selectedUpload.isVehicleExpense}
                    onChange={(event) => updateUploadDraft(selectedUpload.id, {
                      isVehicleExpense: event.target.checked,
                    })}
                    className="mt-0.5 h-4 w-4 shrink-0"
                  />
                  <span>
                    <span className="flex items-center gap-1 text-sm font-medium">
                      <Car className="h-3.5 w-3.5" /> Vehicle expense
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      A vehicle registration is required.
                    </span>
                  </span>
                </label>
              </div>
            )}

            {selectedUpload?.isVehicleExpense && (
              <div className="max-w-sm">
                <Label htmlFor="upload-vehicle-registration">Vehicle registration (ŠPZ)</Label>
                <Input
                  id="upload-vehicle-registration"
                  list="known-vehicle-registrations"
                  value={selectedUpload.vehicleRegistration}
                  onChange={(event) => updateUploadDraft(selectedUpload.id, {
                    vehicleRegistration: event.target.value.toUpperCase(),
                  })}
                  placeholder="KE885HH"
                  maxLength={9}
                  autoComplete="off"
                />
                <datalist id="known-vehicle-registrations">
                  {knownVehicleRegistrations.map((registration) => (
                    <option key={registration} value={registration} />
                  ))}
                </datalist>
                <p className="mt-1 text-xs text-muted-foreground">
                  Saved without spaces or dashes and added to the PDF filename.
                </p>
              </div>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="upload-comment">Accountant Comment</Label>
                <span className="text-xs text-muted-foreground">{uploadComment.length}/2000</span>
              </div>
              <textarea
                id="upload-comment"
                value={uploadComment}
                onChange={(event) => setUploadComment(event.target.value)}
                maxLength={2000}
                rows={3}
                placeholder="Optional context for the summary email"
                className="flex w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              <p className="text-xs text-muted-foreground">
                Included when this document is emailed to the accountant.
              </p>
            </div>

            {/* Filename Preview */}
            {getPreviewFilename() && (
              <div className="min-w-0 rounded-lg bg-muted p-3">
                <Label className="text-xs text-muted-foreground">Will be saved as:</Label>
                <div className="mt-1 break-all font-mono text-sm">{getPreviewFilename()}</div>
              </div>
            )}

            {/* Skip analyze checkbox */}
            <div className="flex min-w-0 items-start gap-2">
              <input
                type="checkbox"
                id="skipAnalyze"
                checked={uploadSkipAnalyze}
                onChange={(e) => setUploadSkipAnalyze(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0"
              />
              <Label htmlFor="skipAnalyze" className="min-w-0 cursor-pointer text-sm font-normal leading-5">
                Skip PDF analysis (use manually entered values only)
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadModal(false)} disabled={isUploading}>
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={uploadDrafts.length === 0 || uploadAnalyzing || isUploading}>
              {isUploading ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                `Upload ${uploadDrafts.length || ''} ${uploadDrafts.length === 1 ? 'PDF' : 'PDFs'}`
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

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                  <Label>Document Type</Label>
                  {hasSuggestion('document_type', editDocumentType) && (
                    <button
                      type="button"
                      className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                      onClick={() => applySuggestion('document_type')}
                    >
                      Use: {parsedValues?.document_type}
                    </button>
                  )}
                </div>
                <Select
                  value={editDocumentType}
                  onChange={(e) => setEditDocumentType(e.target.value)}
                  options={documentTypeInputOptions}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                    { value: 'cod', label: 'Cash on Delivery' },
                  ]}
                />
              </div>
              <div />
            </div>

            {editPaymentType === 'wire' && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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

            <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
              <label className="flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  checked={editIncludeInExport}
                  onChange={(event) => setEditIncludeInExport(event.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0"
                />
                <span>
                  <span className="block text-sm font-medium">Include in accountant export</span>
                  <span className="block text-xs text-muted-foreground">
                    Internal files stay in this tool and Drive only.
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  checked={editIsVehicleExpense}
                  onChange={(event) => setEditIsVehicleExpense(event.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0"
                />
                <span>
                  <span className="flex items-center gap-1 text-sm font-medium">
                    <Car className="h-3.5 w-3.5" /> Vehicle expense
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    Adds the registration to the PDF filename.
                  </span>
                </span>
              </label>
            </div>

            {editIsVehicleExpense && (
              <div className="max-w-sm">
                <Label htmlFor="edit-vehicle-registration">Vehicle registration (ŠPZ)</Label>
                <Input
                  id="edit-vehicle-registration"
                  list="known-vehicle-registrations-edit"
                  value={editVehicleRegistration}
                  onChange={(event) => setEditVehicleRegistration(event.target.value.toUpperCase())}
                  placeholder="KE885HH"
                  maxLength={9}
                  autoComplete="off"
                />
                <datalist id="known-vehicle-registrations-edit">
                  {knownVehicleRegistrations.map((registration) => (
                    <option key={registration} value={registration} />
                  ))}
                </datalist>
              </div>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="invoice-comment">Accountant Comment</Label>
                <span className="text-xs text-muted-foreground">{editComment.length}/2000</span>
              </div>
              <textarea
                id="invoice-comment"
                value={editComment}
                onChange={(event) => setEditComment(event.target.value)}
                maxLength={2000}
                rows={3}
                placeholder="Context to include in the summary email"
                className="flex w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              <p className="text-xs text-muted-foreground">
                Included only when this document is part of an accountant export.
              </p>
            </div>
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
