import * as React from "react"
import { SyncProgressToast } from "@/components/SyncProgressToast"
import { BatchSyncProgressToast } from "@/components/BatchSyncProgressToast"

interface SyncState {
  isOpen: boolean
  mode: "single" | "batch"
  yearMonth: string | null
  months: string[]
  fioToken: string
  gdriveFolderId?: string
  prevMonthGdriveFolderId?: string
}

interface SyncContextValue {
  startSync: (params: {
    yearMonth: string
    fioToken: string
    gdriveFolderId?: string
    prevMonthGdriveFolderId?: string
    onComplete?: () => void
  }) => void
  startBatchSync: (params: {
    months: string[]
    fioToken: string
    onComplete?: () => void
  }) => void
  isSyncing: boolean
  syncingMonth: string | null
}

const SyncContext = React.createContext<SyncContextValue | null>(null)

export function SyncProvider({ children }: { children: React.ReactNode }) {
  const [syncState, setSyncState] = React.useState<SyncState>({
    isOpen: false,
    mode: "single",
    yearMonth: null,
    months: [],
    fioToken: "",
  })
  const [onCompleteCallback, setOnCompleteCallback] = React.useState<(() => void) | null>(null)

  const startSync = React.useCallback((params: {
    yearMonth: string
    fioToken: string
    gdriveFolderId?: string
    prevMonthGdriveFolderId?: string
    onComplete?: () => void
  }) => {
    setSyncState({
      isOpen: true,
      mode: "single",
      yearMonth: params.yearMonth,
      months: [],
      fioToken: params.fioToken,
      gdriveFolderId: params.gdriveFolderId,
      prevMonthGdriveFolderId: params.prevMonthGdriveFolderId,
    })
    if (params.onComplete) {
      setOnCompleteCallback(() => params.onComplete)
    }
  }, [])

  const startBatchSync = React.useCallback((params: {
    months: string[]
    fioToken: string
    onComplete?: () => void
  }) => {
    setSyncState({
      isOpen: true,
      mode: "batch",
      yearMonth: null,
      months: params.months,
      fioToken: params.fioToken,
    })
    if (params.onComplete) {
      setOnCompleteCallback(() => params.onComplete)
    }
  }, [])

  const handleClose = React.useCallback(() => {
    setSyncState(prev => ({ ...prev, isOpen: false }))
  }, [])

  const handleComplete = React.useCallback(() => {
    if (onCompleteCallback) {
      onCompleteCallback()
      setOnCompleteCallback(null)
    }
  }, [onCompleteCallback])

  const value = React.useMemo(() => ({
    startSync,
    startBatchSync,
    isSyncing: syncState.isOpen,
    syncingMonth: syncState.yearMonth,
  }), [startSync, startBatchSync, syncState.isOpen, syncState.yearMonth])

  return (
    <SyncContext.Provider value={value}>
      {children}
      {syncState.mode === "single" && syncState.yearMonth && (
        <SyncProgressToast
          open={syncState.isOpen}
          onClose={handleClose}
          yearMonth={syncState.yearMonth}
          fioToken={syncState.fioToken}
          gdriveFolderId={syncState.gdriveFolderId}
          prevMonthGdriveFolderId={syncState.prevMonthGdriveFolderId}
          onComplete={handleComplete}
        />
      )}
      {syncState.mode === "batch" && syncState.months.length > 0 && (
        <BatchSyncProgressToast
          open={syncState.isOpen}
          onClose={handleClose}
          months={syncState.months}
          fioToken={syncState.fioToken}
          onComplete={handleComplete}
        />
      )}
    </SyncContext.Provider>
  )
}

export function useSync() {
  const context = React.useContext(SyncContext)
  if (!context) {
    throw new Error("useSync must be used within SyncProvider")
  }
  return context
}
