import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

const API_BASE = '/api'
let csrfToken: string | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

function dispatchUnauthorized() {
  window.dispatchEvent(new Event('auth:unauthorized'))
}

export async function authFetch(url: string, options?: RequestInit): Promise<Response> {
  const method = (options?.method || 'GET').toUpperCase()
  const headers = new Headers(options?.headers)

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken)
  }

  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    credentials: 'same-origin',
    headers,
  })

  if (response.status === 401) {
    dispatchUnauthorized()
  }

  return response
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  const hasFormData = options?.body instanceof FormData
  if (!hasFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await authFetch(url, {
    ...options,
    headers,
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

export interface AuthUser {
  id: number
  email: string
  full_name?: string
  picture_url?: string
}

export interface AuthSession {
  authenticated: boolean
  csrf_token?: string
  user?: AuthUser
}

export interface Invoice {
  id: number
  gdrive_file_id?: string
  receipt_index: number
  filename: string
  vendor?: string
  document_type: 'invoice' | 'receipt' | 'other'
  amount?: string
  currency: string  // EUR, USD, CZK, etc.
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
  extracted_vendor?: string  // LLM-extracted clean vendor name
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
  extracted_vendor?: string  // Clean vendor (LLM or regex extracted)
  score: number  // Total 0-100
  // Score breakdown
  amount_score: number      // 0-50
  date_score: number        // 0-30
  vendor_score: number      // 0-20
  date_diff_days?: number
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

export interface EncryptedSecretPayload {
  configured: boolean
  ciphertext?: string
  nonce?: string
  salt?: string
  kdf?: 'argon2id'
  kdf_params?: {
    iterations: number
    memorySize: number
    parallelism: number
    hashLength: number
  }
  updated_at?: string
}

// ============================================================================
// Auth Hooks
// ============================================================================

export function useAuthSession() {
  return useQuery({
    queryKey: ['auth-session'],
    retry: false,
    queryFn: async (): Promise<AuthSession> => {
      const response = await authFetch('/auth/me')
      if (response.status === 401) {
        return { authenticated: false }
      }

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
  })
}

export function useAuthLogin() {
  return useMutation({
    mutationFn: () => fetchJson<{ auth_url: string }>('/auth/login?popup=true'),
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => fetchJson<{ success: boolean }>('/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-session'] })
    },
  })
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
      amounts: { income: number; expenses: number; fees: number; net: number }
    }>(`/stats/${yearMonth}`),
    enabled: !!yearMonth,
  })
}

export interface MonthlySummary {
  month: string
  income: number
  expenses: number
  fees: number
  cash: number
  net: number
}

export function useMonthlySummary() {
  return useQuery({
    queryKey: ['monthly-summary'],
    queryFn: () => fetchJson<{ months: MonthlySummary[] }>('/monthly-summary'),
  })
}

export function useCopyToGDrive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ yearMonth, folderId, markExported }: {
      yearMonth: string
      folderId: string
      markExported: boolean
    }) =>
      fetchJson<{ success: boolean; copied: number; skipped: number; total: number; errors: string[] }>(
        `/export/${yearMonth}/copy-to-gdrive?folder_id=${encodeURIComponent(folderId)}&mark_exported=${markExported}`,
        { method: 'POST' }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// ============================================================================
// Invoice Hooks
// ============================================================================

export function useInvoices(month?: string, status?: string, documentType?: string) {
  const params = new URLSearchParams()
  if (month) params.set('month', month)
  if (status) params.set('status', status)
  if (documentType) params.set('document_type', documentType)
  const queryString = params.toString()

  return useQuery({
    queryKey: ['invoices', month, status, documentType],
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
    mutationFn: async ({ file, vendor, documentType, invoiceDate, paymentType, amount, gdriveFolderId, skipAnalyze }: {
      file: File
      vendor?: string
      documentType?: string
      invoiceDate?: string
      paymentType?: string
      amount?: string
      gdriveFolderId: string  // Required - parent folder ID
      skipAnalyze?: boolean
    }): Promise<Invoice> => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('gdrive_folder_id', gdriveFolderId)
      if (vendor) formData.append('vendor', vendor)
      if (documentType) formData.append('document_type', documentType)
      if (invoiceDate) formData.append('invoice_date', invoiceDate)
      if (paymentType) formData.append('payment_type', paymentType)
      if (amount) formData.append('amount', amount)
      if (skipAnalyze) formData.append('skip_analyze', 'true')

      const response = await authFetch('/invoices/upload', {
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

export function useImportSubfolders(parentId: string) {
  return useQuery({
    queryKey: ['import-subfolders', parentId],
    queryFn: () =>
      fetchJson<{ folders: Array<{ id: string; name: string }> }>(
        `/invoices/import-gdrive/subfolders?folder_id=${parentId}`
      ),
    enabled: !!parentId,
  })
}

export function useUpdateInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ invoiceId, ...data }: {
      invoiceId: number
      filename?: string
      vendor?: string
      document_type?: string
      amount?: string
      currency?: string
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
    document_type?: string
    amount?: string
    currency?: string
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

      const response = await authFetch('/gdrive/rename', {
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

export function useFioVault() {
  return useQuery({
    queryKey: ['fio-vault'],
    queryFn: () => fetchJson<EncryptedSecretPayload>('/secrets/fio'),
  })
}

export function useSaveFioVault() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      ciphertext: string
      nonce: string
      salt: string
      kdf: 'argon2id'
      kdf_params: {
        iterations: number
        memorySize: number
        parallelism: number
        hashLength: number
      }
    }) =>
      fetchJson<EncryptedSecretPayload>('/secrets/fio', {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fio-vault'] })
    },
  })
}

export function useDeleteFioVault() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => fetchJson<{ success: boolean }>('/secrets/fio', { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fio-vault'] })
    },
  })
}

export function useGDriveAuthUrl() {
  return useMutation({
    mutationFn: () => fetchJson<{ auth_url: string }>('/gdrive/auth-url'),
  })
}

export function useGDriveFolderInfo() {
  return useMutation({
    mutationFn: (folderId: string) =>
      fetchJson<{ id: string; name: string; shared?: boolean }>(`/gdrive/folder/${folderId}`),
  })
}

export function useGDriveFolders(
  parentId: string,
  options: { showAll?: boolean; search?: string; shared?: boolean } = {}
) {
  const { showAll = false, search, shared = false } = options
  const params = new URLSearchParams()
  params.set('parent_id', parentId)
  if (showAll) params.set('all', 'true')
  if (search) params.set('search', search)
  if (shared) params.set('shared', 'true')

  return useQuery({
    queryKey: ['gdrive-folders', parentId, showAll, search, shared],
    queryFn: () =>
      fetchJson<{ folders: Array<{ id: string; name: string; parent_id?: string; shared?: boolean }> }>(
        `/gdrive/folders?${params.toString()}`
      ),
    enabled: !!parentId || !!search || shared,
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
