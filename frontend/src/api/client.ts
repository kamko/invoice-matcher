import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

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
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  if (response.status === 204) {
    return null as T
  }

  return response.json()
}

// Types
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

export interface Transaction {
  id: string
  date: string
  amount: string
  currency: string
  counter_account: string
  counter_name: string
  vs: string
  note: string
  transaction_type: string
  rule_reason?: string
  skip_reason?: string
}

export interface Invoice {
  file_path: string
  filename: string
  invoice_date: string
  invoice_number: string
  payment_type: string
  vendor: string
  amount?: string
  vs?: string
  gdrive_file_id?: string
  is_credit_note?: boolean
  is_cash?: boolean
}

export interface MatchResult {
  transaction: Transaction
  invoice?: Invoice
  confidence: number
  confidence_pct: number
  status: 'OK' | 'REVIEW' | 'NO_MATCH'
  strategy_scores: Record<string, number>
}

export interface Session {
  id: number
  from_date: string
  to_date: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  completed_at?: string
  matched_count: number
  unmatched_count: number
  review_count: number
  known_count: number
  fee_count: number
  income_count: number
  matched: MatchResult[]
  unmatched: Transaction[]
  known: Transaction[]
  fees: Transaction[]
  income: Transaction[]
  unmatched_invoices: Invoice[]
  error_message?: string
}

export interface ReconcileRequest {
  from_date: string
  to_date: string
  fio_token: string
  gdrive_folder_id?: string
  invoice_dir?: string
}

export interface MonthlyReconcileRequest {
  year_month: string
  fio_token: string
  gdrive_folder_id?: string
  invoice_dir?: string
  prev_month_gdrive_folder_id?: string
  prev_month_invoice_dir?: string
}

export interface MonthData {
  year_month: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  last_synced_at?: string
  created_at: string
  matched_count: number
  unmatched_count: number
  review_count: number
  known_count: number
  fee_count: number
  income_count: number
  matched: MatchResult[]
  unmatched: Transaction[]
  known: Transaction[]
  skipped: Transaction[]
  fees: Transaction[]
  income: Transaction[]
  unmatched_invoices: Invoice[]
  error_message?: string
}

export interface MonthListItem {
  year_month: string
  status: string
  matched_count: number
  unmatched_count: number
  last_synced_at?: string
  gdrive_folder_id?: string
  gdrive_folder_name?: string
}

export interface MarkKnownRequest {
  transaction_id: string
  rule_type: 'exact' | 'pattern' | 'vendor' | 'note' | 'account'
  reason: string
  vendor_pattern?: string
  note_pattern?: string
  amount?: string
  amount_min?: string
  amount_max?: string
  counter_account?: string
}

// Hooks

// Known Transactions
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

export function useReapplyRules() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      fetchJson<{ success: boolean; months_updated: number; transactions_moved: number }>(
        '/known-transactions/reapply-all',
        { method: 'POST' }
      ),
    onSuccess: () => {
      // Invalidate month data to refresh counts
      queryClient.invalidateQueries({ queryKey: ['months'] })
    },
  })
}

// Reconciliation
export function useStartReconciliation() {
  return useMutation({
    mutationFn: (data: ReconcileRequest) =>
      fetchJson<{ session_id: number; status: string; message: string }>('/reconcile', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  })
}

export function useSession(sessionId: number | null) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => fetchJson<Session>(`/sessions/${sessionId}`),
    enabled: sessionId !== null,
    refetchInterval: (data) => {
      // Poll while processing
      if (data?.state?.data?.status === 'processing') {
        return 2000
      }
      return false
    },
  })
}

export function useMarkKnown() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sessionId, ...data }: MarkKnownRequest & { sessionId: number }) =>
      fetchJson<{ success: boolean; rule_id: number }>(`/sessions/${sessionId}/mark-known`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['session', variables.sessionId] })
      queryClient.invalidateQueries({ queryKey: ['known-transactions'] })
    },
  })
}

export interface MatchWithPdfResponse {
  success: boolean
  message: string
  gdrive_file_id?: string
  invoice?: Invoice
}

export function useMatchWithPdf() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ sessionId, transactionId, file }: {
      sessionId: number
      transactionId: string
      file: File
    }): Promise<MatchWithPdfResponse> => {
      const formData = new FormData()
      formData.append('transaction_id', transactionId)
      formData.append('file', file)

      const response = await fetch(`/api/sessions/${sessionId}/match-with-pdf`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['session', variables.sessionId] })
    },
  })
}

// ===== Month-Based Hooks =====

export function useMonths() {
  return useQuery({
    queryKey: ['months'],
    queryFn: () => fetchJson<MonthListItem[]>('/months'),
  })
}

export function useMonth(yearMonth: string | null) {
  return useQuery({
    queryKey: ['month', yearMonth],
    queryFn: () => fetchJson<MonthData>(`/months/${yearMonth}`),
    enabled: yearMonth !== null,
    refetchInterval: (data) => {
      if (data?.state?.data?.status === 'processing') {
        return 2000
      }
      return false
    },
  })
}

export interface FolderInvoice {
  gdrive_file_id: string
  filename: string
  vendor?: string
  amount?: string
  status: 'paid' | 'unpaid'
  paid_month?: string
  transaction_id?: string
}

export function useMonthInvoices(yearMonth: string | null) {
  return useQuery({
    queryKey: ['month-invoices', yearMonth],
    queryFn: () => fetchJson<{ invoices: FolderInvoice[]; total: number }>(`/months/${yearMonth}/invoices`),
    enabled: yearMonth !== null,
  })
}

export function useSyncMonth() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ yearMonth, ...data }: MonthlyReconcileRequest & { yearMonth: string }) =>
      fetchJson<{ session_id: number; status: string; message: string }>(`/months/${yearMonth}/sync`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['month', variables.yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['months'] })
    },
  })
}

export function useMarkKnownMonthly() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ yearMonth, ...data }: MarkKnownRequest & { yearMonth: string }) =>
      fetchJson<{ success: boolean; rule_id: number; matched_count: number }>(`/months/${yearMonth}/mark-known`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['month', variables.yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['known-transactions'] })
    },
  })
}

export function useSkipTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ yearMonth, transactionId, reason }: {
      yearMonth: string
      transactionId: string
      reason?: string
    }) => {
      const formData = new FormData()
      formData.append('transaction_id', transactionId)
      formData.append('reason', reason || '')

      const response = await fetch(`/api/months/${yearMonth}/skip-transaction`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['month', variables.yearMonth] })
    },
  })
}

export function useManualMatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ yearMonth, transactionId, invoiceFileId }: {
      yearMonth: string
      transactionId: string
      invoiceFileId: string
    }) => {
      const formData = new FormData()
      formData.append('transaction_id', transactionId)
      formData.append('invoice_file_id', invoiceFileId)

      const response = await fetch(`/api/months/${yearMonth}/manual-match`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['month', variables.yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['month-invoices', variables.yearMonth] })
    },
  })
}

// Parse PDF preview (extract data without uploading)
export interface ParsePdfResponse {
  success: boolean
  invoice_date: string | null
  vendor: string | null
  amount: string | null
  vs: string | null
  message?: string
}

export function useParsePdf() {
  return useMutation({
    mutationFn: async (file: File): Promise<ParsePdfResponse> => {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/parse-pdf', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
  })
}

export function useMatchWithPdfMonthly() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ yearMonth, transactionId, file, vendor, invoiceDate }: {
      yearMonth: string
      transactionId: string
      file: File
      vendor?: string  // Optional: override extracted vendor
      invoiceDate?: string  // Optional: override extracted date (YYYY-MM-DD)
    }): Promise<MatchWithPdfResponse> => {
      const formData = new FormData()
      formData.append('transaction_id', transactionId)
      formData.append('file', file)
      if (vendor) formData.append('vendor', vendor)
      if (invoiceDate) formData.append('invoice_date', invoiceDate)

      const response = await fetch(`/api/months/${yearMonth}/match-with-pdf`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['month', variables.yearMonth] })
    },
  })
}

export function useSetMonthFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ yearMonth, folderId, folderName }: {
      yearMonth: string
      folderId: string
      folderName: string
    }) =>
      fetchJson<{ success: boolean }>(`/months/${yearMonth}/set-folder`, {
        method: 'POST',
        body: JSON.stringify({ folder_id: folderId, folder_name: folderName }),
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['month', variables.yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['months'] })
    },
  })
}

export interface UploadInvoiceResponse {
  success: boolean
  gdrive_file_id: string
  filename: string
  message: string
}

export function useUploadInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ yearMonth, file, invoiceDate }: {
      yearMonth: string
      file: File
      invoiceDate: string  // YYYY-MM-DD format
    }): Promise<UploadInvoiceResponse> => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('invoice_date', invoiceDate)

      const response = await fetch(`/api/months/${yearMonth}/upload-invoice`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      return response.json()
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['month', variables.yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['month-invoices', variables.yearMonth] })
    },
  })
}

// Google Drive
export function useGDriveStatus() {
  return useQuery({
    queryKey: ['gdrive-status'],
    queryFn: () => fetchJson<{ available: boolean; authenticated: boolean }>('/gdrive/status'),
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
    enabled: !!parentId, // Only fetch when parentId is provided
  })
}

export function useRenameInvoice() {
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
        const err = await response.json().catch(() => ({ detail: response.statusText }))
        throw new Error(err.detail || 'Failed to rename')
      }
      return response.json()
    },
    onSuccess: () => {
      // Invalidate queries that might show the filename
      queryClient.invalidateQueries({ queryKey: ['months'] })
      queryClient.invalidateQueries({ queryKey: ['month-detail'] })
    },
  })
}

export interface ParseCachedInvoiceResponse {
  success: boolean
  vendor: string | null
  amount: string | null
  invoice_date: string | null
  vs: string | null
  message?: string
}

export function useParseCachedInvoice() {
  return useMutation({
    mutationFn: async (fileId: string): Promise<ParseCachedInvoiceResponse> => {
      const response = await fetch(`${API_BASE}/invoices/${fileId}/parse`)
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }))
        throw new Error(err.detail || 'Failed to parse')
      }
      return response.json()
    },
  })
}

export interface RenameInvoiceResponse {
  success: boolean
  old_filename: string
  new_filename: string
  vendor: string | null
  amount: string | null
  invoice_date: string | null
  renamed_in_gdrive: boolean
}

export function useRenameInvoiceFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ fileId, vendor, invoiceDate, paymentType }: {
      fileId: string
      vendor: string
      invoiceDate: string
      paymentType?: string
    }): Promise<RenameInvoiceResponse> => {
      const formData = new FormData()
      formData.append('vendor', vendor)
      formData.append('invoice_date', invoiceDate)
      if (paymentType) formData.append('payment_type', paymentType)

      const response = await fetch(`${API_BASE}/invoices/${fileId}/rename`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }))
        throw new Error(err.detail || 'Failed to rename invoice')
      }
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['months'] })
      queryClient.invalidateQueries({ queryKey: ['month-invoices'] })
    },
  })
}

// Settings
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

// App Config
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
