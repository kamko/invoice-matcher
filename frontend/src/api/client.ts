import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

const API_BASE = '/api'

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    const errorMessage = error.detail || `HTTP ${response.status}`
    throw new Error(errorMessage)
  }

  if (response.status === 204) {
    return null as T
  }

  return response.json()
}

// Show error toast for API errors
export function showApiError(error: unknown, context?: string) {
  const message = error instanceof Error ? error.message : 'Unknown error'
  toast.error(context ? `${context}: ${message}` : message)
}

// Show success toast
export function showSuccess(message: string) {
  toast.success(message)
}

// ============================================================================
// Types
// ============================================================================

export interface Invoice {
  id: number
  gdrive_file_id?: string
  receipt_index: number
  filename: string
  vendor?: string
  amount?: string
  invoice_date?: string
  payment_type?: string
  vs?: string
  iban?: string
  is_credit_note: boolean
  status: 'unmatched' | 'matched' | 'cash' | 'exported'
  transaction_id?: string
  created_at: string
  invoice_month?: string
}

export interface InvoiceListResponse {
  invoices: Invoice[]
  total: number
  unmatched: number
  matched: number
}

export interface Transaction {
  id: string
  date: string
  amount: string
  currency: string
  counter_account?: string
  counter_name?: string
  vs?: string
  note?: string
  type?: string
  raw_type?: string
  status: 'unmatched' | 'matched' | 'known' | 'skipped'
  known_rule_id?: number
  skip_reason?: string
  fetched_at?: string
  rule_reason?: string
}

export interface TransactionListResponse {
  transactions: Transaction[]
  total: number
  unmatched: number
  matched: number
  known: number
  skipped: number
}

export interface MatchSuggestion {
  transaction_id: string
  date: string
  amount: string
  counter_name?: string
  vs?: string
  note?: string
  score: number
}

export interface InvoiceSuggestion {
  invoice_id: number
  filename: string
  vendor?: string
  amount?: string
  invoice_date?: string
  score: number
}

export interface DashboardData {
  unmatched_transactions: number
  unmatched_invoices: number
  matched_this_month: number
  ready_to_export: number
  known_transactions: number
  skipped_transactions: number
  available_months: string[]
}

export interface KnownTransaction {
  id: number
  rule_type: 'exact' | 'pattern' | 'vendor' | 'note' | 'account'
  vendor_pattern?: string
  note_pattern?: string
  amount?: string
  amount_min?: string
  amount_max?: string
  vs_pattern?: string
  counter_account?: string
  reason: string
  is_active: boolean
  created_at: string
  updated_at?: string
}

// ============================================================================
// Dashboard Hooks
// ============================================================================

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: () => fetchJson<DashboardData>('/dashboard'),
  })
}

export function useMonthStats(yearMonth: string | null) {
  return useQuery({
    queryKey: ['month-stats', yearMonth],
    queryFn: () => fetchJson<{
      year_month: string
      invoices: { total: number; unmatched: number; matched: number; exported: number }
      transactions: { total: number; unmatched: number; matched: number; known: number; skipped: number }
    }>(`/stats/${yearMonth}`),
    enabled: !!yearMonth,
  })
}

// ============================================================================
// Invoice Hooks
// ============================================================================

export function useInvoices(month?: string, status?: string) {
  const params = new URLSearchParams()
  if (month) params.set('month', month)
  if (status) params.set('status', status)
  const queryString = params.toString()

  return useQuery({
    queryKey: ['invoices', month, status],
    queryFn: () => fetchJson<InvoiceListResponse>(`/invoices${queryString ? `?${queryString}` : ''}`),
  })
}

export function useInvoice(invoiceId: number | null) {
  return useQuery({
    queryKey: ['invoice', invoiceId],
    queryFn: () => fetchJson<Invoice>(`/invoices/${invoiceId}`),
    enabled: invoiceId !== null,
  })
}

export function useUploadInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, vendor, invoiceDate, paymentType, amount }: {
      file: File
      vendor?: string
      invoiceDate?: string
      paymentType?: string
      amount?: string
    }): Promise<Invoice> => {
      const formData = new FormData()
      formData.append('file', file)
      if (vendor) formData.append('vendor', vendor)
      if (invoiceDate) formData.append('invoice_date', invoiceDate)
      if (paymentType) formData.append('payment_type', paymentType)
      if (amount) formData.append('amount', amount)

      const response = await fetch(`${API_BASE}/invoices/upload`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useImportGDrive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { folder_id: string; year_month?: string }) =>
      fetchJson<{ success: boolean; imported: number; skipped: number; auto_matched: number }>(
        '/invoices/import-gdrive',
        { method: 'POST', body: JSON.stringify(data) }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useUpdateInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ invoiceId, ...data }: {
      invoiceId: number
      filename?: string
      vendor?: string
      amount?: string
      invoice_date?: string
      payment_type?: string
      vs?: string
      iban?: string
    }) =>
      fetchJson<Invoice>(`/invoices/${invoiceId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
    },
  })
}

export function useDeleteInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (invoiceId: number) =>
      fetchJson<{ success: boolean }>(`/invoices/${invoiceId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useMatchInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ invoiceId, transactionId }: { invoiceId: number; transactionId: string }) =>
      fetchJson<Invoice>(`/invoices/${invoiceId}/match`, {
        method: 'POST',
        body: JSON.stringify({ transaction_id: transactionId }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useUnmatchInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (invoiceId: number) =>
      fetchJson<Invoice>(`/invoices/${invoiceId}/unmatch`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useInvoiceSuggestions(invoiceId: number | null) {
  return useQuery({
    queryKey: ['invoice-suggestions', invoiceId],
    queryFn: () => fetchJson<{ invoice_id: number; suggestions: MatchSuggestion[] }>(
      `/invoices/${invoiceId}/suggestions`
    ),
    enabled: invoiceId !== null,
  })
}

export interface ReanalyzeResult {
  success: boolean
  extracted: {
    vendor?: string
    amount?: string
    invoice_date?: string
    payment_type?: string
    vs?: string
    iban?: string
  }
}

export function useReanalyzeInvoice() {
  return useMutation({
    mutationFn: (invoiceId: number) =>
      fetchJson<ReanalyzeResult>(`/invoices/${invoiceId}/reanalyze`, { method: 'POST' }),
  })
}

// ============================================================================
// Transaction Hooks
// ============================================================================

export function useTransactions(month?: string, status?: string, type?: string) {
  const params = new URLSearchParams()
  if (month) params.set('month', month)
  if (status) params.set('status', status)
  if (type) params.set('type', type)
  const queryString = params.toString()

  return useQuery({
    queryKey: ['transactions', month, status, type],
    queryFn: () => fetchJson<TransactionListResponse>(`/transactions${queryString ? `?${queryString}` : ''}`),
  })
}

export function useTransaction(transactionId: string | null) {
  return useQuery({
    queryKey: ['transaction', transactionId],
    queryFn: () => fetchJson<Transaction>(`/transactions/${transactionId}`),
    enabled: transactionId !== null,
  })
}

export function useFetchTransactions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { fio_token: string; from_date: string; to_date: string }) =>
      fetchJson<{ fetched: number; new: number; existing: number; known_matched: number }>(
        '/transactions/fetch',
        { method: 'POST', body: JSON.stringify(data) }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useSkipTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionId, reason }: { transactionId: string; reason?: string }) =>
      fetchJson<Transaction>(`/transactions/${transactionId}/skip`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason || '' }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useUnskipTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (transactionId: string) =>
      fetchJson<Transaction>(`/transactions/${transactionId}/unskip`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useMarkKnown() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionId, ...data }: {
      transactionId: string
      rule_type: string
      reason: string
      vendor_pattern?: string
      note_pattern?: string
      amount?: string
      counter_account?: string
    }) =>
      fetchJson<{ success: boolean; rule_id: number; matched_count: number }>(
        `/transactions/${transactionId}/mark-known`,
        { method: 'POST', body: JSON.stringify(data) }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['known-transactions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useTransactionSuggestions(transactionId: string | null) {
  return useQuery({
    queryKey: ['transaction-suggestions', transactionId],
    queryFn: () => fetchJson<{ transaction_id: string; suggestions: InvoiceSuggestion[] }>(
      `/transactions/${transactionId}/suggestions`
    ),
    enabled: transactionId !== null,
  })
}

export function useUpdateTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionId, ...data }: {
      transactionId: string
      counter_name?: string
      note?: string
      vs?: string
      type?: string
    }) =>
      fetchJson<Transaction>(`/transactions/${transactionId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}

export function useMatchTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionId, invoiceId }: { transactionId: string; invoiceId: number }) =>
      fetchJson<{ success: boolean }>(`/transactions/${transactionId}/match?invoice_id=${invoiceId}`, {
        method: 'POST',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// ============================================================================
// Known Transactions Hooks
// ============================================================================

export function useKnownTransactions(activeOnly = false) {
  return useQuery({
    queryKey: ['known-transactions', activeOnly],
    queryFn: () =>
      fetchJson<KnownTransaction[]>(`/known-transactions?active_only=${activeOnly}`),
  })
}

export function useCreateKnownTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Omit<KnownTransaction, 'id' | 'created_at' | 'updated_at'>) =>
      fetchJson<KnownTransaction>('/known-transactions', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['known-transactions'] })
    },
  })
}

export function useUpdateKnownTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<KnownTransaction> & { id: number }) =>
      fetchJson<KnownTransaction>(`/known-transactions/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['known-transactions'] })
    },
  })
}

export function useDeleteKnownTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      fetchJson<void>(`/known-transactions/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['known-transactions'] })
    },
  })
}

// ============================================================================
// Google Drive Hooks
// ============================================================================

export function useGDriveStatus() {
  return useQuery({
    queryKey: ['gdrive-status'],
    queryFn: () => fetchJson<{ available: boolean; authenticated: boolean }>('/gdrive/status'),
  })
}

export function useRenameGDriveFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ fileId, newFilename }: { fileId: string; newFilename: string }) => {
      const formData = new FormData()
      formData.append('file_id', fileId)
      formData.append('new_filename', newFilename)

      const response = await fetch(`${API_BASE}/gdrive/rename`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
    },
  })
}

export function useGDriveAuthUrl() {
  return useMutation({
    mutationFn: () => fetchJson<{ auth_url: string }>('/gdrive/auth-url'),
  })
}

export function useGDriveFolders(parentId: string, showAll = false) {
  return useQuery({
    queryKey: ['gdrive-folders', parentId, showAll],
    queryFn: () =>
      fetchJson<{ folders: Array<{ id: string; name: string; parent_id?: string }> }>(
        `/gdrive/folders?parent_id=${parentId}&all=${showAll}`
      ),
    enabled: !!parentId,
  })
}

// ============================================================================
// Settings Hooks
// ============================================================================

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => fetchJson<Record<string, string | null>>('/settings'),
  })
}

export function useSetting(key: string) {
  return useQuery({
    queryKey: ['settings', key],
    queryFn: () => fetchJson<{ key: string; value: string | null }>(`/settings/${key}`),
  })
}

export function useSetSetting() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      fetchJson<{ key: string; value: string | null }>(`/settings/${key}?value=${encodeURIComponent(value)}`, {
        method: 'PUT',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })
}

// ============================================================================
// App Config
// ============================================================================

export interface AppConfig {
  llm_model: string
  llm_enabled: boolean
}

export function useAppConfig() {
  return useQuery({
    queryKey: ['app-config'],
    queryFn: () => fetchJson<AppConfig>('/config'),
  })
}
