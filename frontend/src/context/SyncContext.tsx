import * as React from "react"
import { SyncProgressToast } from "@/components/SyncProgressToast"

interface SyncState {
  isOpen: boolean
  yearMonth: string | null
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
  isSyncing: boolean
  syncingMonth: string | null
}

const SyncContext = React.createContext<SyncContextValue | null>(null)

export function SyncProvider({ children }: { children: React.ReactNode }) {
  const [syncState, setSyncState] = React.useState<SyncState>({
    isOpen: false,
    yearMonth: null,
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
      yearMonth: params.yearMonth,
      fioToken: params.fioToken,
      gdriveFolderId: params.gdriveFolderId,
      prevMonthGdriveFolderId: params.prevMonthGdriveFolderId,
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
    isSyncing: syncState.isOpen,
    syncingMonth: syncState.yearMonth,
  }), [startSync, syncState.isOpen, syncState.yearMonth])

  return (
    <SyncContext.Provider value={value}>
      {children}
      {syncState.yearMonth && (
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
