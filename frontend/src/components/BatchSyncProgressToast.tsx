import * as React from "react"
import { Loader2, CheckCircle, XCircle, Check, ChevronDown, ChevronUp, X, FileText, Receipt, FolderDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface BatchSyncProgressToastProps {
  open: boolean
  onClose: () => void
  months: string[]
  fioToken: string
  onComplete: () => void
}

interface MonthProgress {
  status: "pending" | "downloading" | "processing" | "completed" | "error"
  message?: string
  invoiceCount?: number
  transactionCount?: number
  matched?: number
  unmatched?: number
  known?: number
  fees?: number
  income?: number
}

interface GlobalStats {
  totalTransactions: number
  foldersDownloaded: number
  foldersTotal: number
}

export function BatchSyncProgressToast({
  open,
  onClose,
  months,
  fioToken,
  onComplete,
}: BatchSyncProgressToastProps) {
  const [expanded, setExpanded] = React.useState(true)
  const [currentMonth, setCurrentMonth] = React.useState<string | null>(null)
  const [phase, setPhase] = React.useState<"fetching" | "downloading" | "processing" | "complete">("fetching")
  const [error, setError] = React.useState<string | null>(null)
  const [completed, setCompleted] = React.useState(false)
  const [monthProgress, setMonthProgress] = React.useState<Record<string, MonthProgress>>({})
  const [globalStats, setGlobalStats] = React.useState<GlobalStats>({
    totalTransactions: 0,
    foldersDownloaded: 0,
    foldersTotal: 0,
  })
  const [totals, setTotals] = React.useState({ matched: 0, unmatched: 0, known: 0 })

  const onCompleteRef = React.useRef(onComplete)
  React.useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  React.useEffect(() => {
    if (!open) return

    // Reset state
    setCurrentMonth(null)
    // currentStep removed("")
    setPhase("fetching")
    setError(null)
    setCompleted(false)
    setMonthProgress(
      months.reduce((acc, m) => ({ ...acc, [m]: { status: "pending" } }), {})
    )
    setGlobalStats({ totalTransactions: 0, foldersDownloaded: 0, foldersTotal: 0 })
    setTotals({ matched: 0, unmatched: 0, known: 0 })
    setExpanded(true)

    const abortController = new AbortController()

    const runBatchSync = async () => {
      try {
        const response = await fetch("/api/batch-sync-stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            months,
            fio_token: fioToken,
          }),
          signal: abortController.signal,
        })

        if (!response.ok) {
          const err = await response.json()
          setError(err.detail || "Failed to start batch sync")
          return
        }

        const reader = response.body?.getReader()
        if (!reader) return

        const decoder = new TextDecoder()
        let buffer = ""

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() || ""

          let eventType = ""
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7)
            } else if (line.startsWith("data: ") && eventType) {
              try {
                const data = JSON.parse(line.slice(6))
                handleEvent(eventType, data)
              } catch {
                // ignore parse errors
              }
              eventType = ""
            }
          }
        }
      } catch (err) {
        if (!abortController.signal.aborted) {
          setError(err instanceof Error ? err.message : "Unknown error")
        }
      }
    }

    const handleEvent = (event: string, data: Record<string, unknown>) => {
      const month = data.month as string | undefined

      switch (event) {
        case "started":
          // currentStep removed("Starting batch sync...")
          setPhase("fetching")
          break

        case "progress": {
          const step = data.step as string
          const message = data.message as string
          // currentStep removed(message)

          if (step === "fetching") {
            setPhase("fetching")
          } else if (step === "fetched") {
            setGlobalStats((prev) => ({
              ...prev,
              totalTransactions: data.count as number,
            }))
            setPhase("downloading")
          } else if (step === "downloading") {
            setPhase("downloading")
            // Extract folder count from message if available
            const match = message.match(/(\d+) months/)
            if (match) {
              setGlobalStats((prev) => ({
                ...prev,
                foldersTotal: parseInt(match[1]),
              }))
            }
          } else if (step === "downloaded_month" && month) {
            setGlobalStats((prev) => ({
              ...prev,
              foldersDownloaded: prev.foldersDownloaded + 1,
            }))
            setMonthProgress((prev) => ({
              ...prev,
              [month]: {
                ...prev[month],
                status: "downloading",
                invoiceCount: data.count as number,
                message: `${data.count} invoices`,
              },
            }))
          } else if (step === "folder_not_found" && month) {
            setGlobalStats((prev) => ({
              ...prev,
              foldersDownloaded: prev.foldersDownloaded + 1,
            }))
            setMonthProgress((prev) => ({
              ...prev,
              [month]: {
                ...prev[month],
                status: "downloading",
                invoiceCount: 0,
                message: "No folder",
              },
            }))
          } else if (step === "processing_month" && month) {
            setPhase("processing")
            setCurrentMonth(month)
            setMonthProgress((prev) => ({
              ...prev,
              [month]: {
                ...prev[month],
                status: "processing",
                message: "Matching...",
              },
            }))
          }
          break
        }

        case "month_complete":
          if (month) {
            const matched = data.matched_count as number
            const unmatched = data.unmatched_count as number
            const known = data.known_count as number

            setMonthProgress((prev) => ({
              ...prev,
              [month]: {
                status: "completed",
                matched,
                unmatched,
                known,
                invoiceCount: prev[month]?.invoiceCount,
              },
            }))
            // Calculate running totals
            setTotals((prev) => ({
              matched: prev.matched + matched,
              unmatched: prev.unmatched + unmatched,
              known: prev.known + known,
            }))
          }
          break

        case "complete":
          setCompleted(true)
          setPhase("complete")
          onCompleteRef.current()
          break

        case "error":
          setError(data.message as string)
          break
      }
    }

    runBatchSync()

    return () => {
      abortController.abort()
    }
  }, [open, months, fioToken])

  if (!open) return null

  const handleClose = () => {
    if (completed || error) {
      onClose()
    }
  }

  const formatMonth = (ym: string) => {
    const [year, mon] = ym.split("-")
    const date = new Date(parseInt(year), parseInt(mon) - 1)
    return date.toLocaleDateString("en-US", { month: "short", year: "numeric" })
  }

  const completedCount = Object.values(monthProgress).filter(
    (p) => p.status === "completed"
  ).length

  const getPhaseLabel = () => {
    switch (phase) {
      case "fetching":
        return "Fetching transactions..."
      case "downloading":
        return `Downloading invoices (${globalStats.foldersDownloaded}/${globalStats.foldersTotal || "?"})`
      case "processing":
        return `Processing months (${completedCount}/${months.length})`
      case "complete":
        return "Complete"
    }
  }

  return (
    <div className="fixed top-4 right-4 z-50">
      <div
        className={cn(
          "bg-background border rounded-lg shadow-lg transition-all duration-200",
          expanded ? "w-[420px]" : "w-auto"
        )}
      >
        {/* Header */}
        <div
          className="flex items-center gap-3 px-4 py-3 cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          {error ? (
            <XCircle className="h-5 w-5 text-destructive flex-shrink-0" />
          ) : completed ? (
            <CheckCircle className="h-5 w-5 text-green-600 flex-shrink-0" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin text-primary flex-shrink-0" />
          )}

          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">
              {error
                ? "Batch Sync Failed"
                : completed
                ? "Batch Sync Complete"
                : `Syncing ${months.length} months`}
            </div>
            <div className="text-xs text-muted-foreground truncate">
              {error
                ? error
                : completed
                ? `${totals.matched} matched, ${totals.unmatched} unmatched, ${totals.known} known`
                : getPhaseLabel()}
            </div>
          </div>

          <div className="flex items-center gap-1">
            {expanded ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )}
            {(completed || error) && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={(e) => {
                  e.stopPropagation()
                  handleClose()
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Expanded view */}
        {expanded && (
          <div className="px-4 pb-4 space-y-3">
            {error ? (
              <div className="text-sm text-destructive">{error}</div>
            ) : (
              <>
                {/* Global stats bar */}
                <div className="flex items-center gap-4 text-xs bg-muted/50 rounded-lg p-2">
                  <div className="flex items-center gap-1.5">
                    <Receipt className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium">{globalStats.totalTransactions}</span>
                    <span className="text-muted-foreground">transactions</span>
                  </div>
                  {globalStats.foldersTotal > 0 && (
                    <div className="flex items-center gap-1.5">
                      <FolderDown className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="font-medium">{globalStats.foldersDownloaded}/{globalStats.foldersTotal}</span>
                      <span className="text-muted-foreground">folders</span>
                    </div>
                  )}
                  {completedCount > 0 && (
                    <div className="flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="font-medium">{completedCount}/{months.length}</span>
                      <span className="text-muted-foreground">processed</span>
                    </div>
                  )}
                </div>

                {/* Running totals (show during processing) */}
                {phase === "processing" && (completedCount > 0 || completed) && (
                  <div className="grid grid-cols-3 gap-2 text-center text-xs bg-muted/30 rounded-lg p-2">
                    <div>
                      <div className="font-bold text-green-600">{totals.matched}</div>
                      <div className="text-muted-foreground">matched</div>
                    </div>
                    <div>
                      <div className="font-bold text-amber-600">{totals.unmatched}</div>
                      <div className="text-muted-foreground">unmatched</div>
                    </div>
                    <div>
                      <div className="font-bold text-blue-600">{totals.known}</div>
                      <div className="text-muted-foreground">known</div>
                    </div>
                  </div>
                )}

                {/* Final totals (show when complete) */}
                {completed && (
                  <div className="grid grid-cols-3 gap-2 text-center text-sm">
                    <div>
                      <div className="text-lg font-bold text-green-600">{totals.matched}</div>
                      <div className="text-xs text-muted-foreground">Matched</div>
                    </div>
                    <div>
                      <div className="text-lg font-bold text-amber-600">{totals.unmatched}</div>
                      <div className="text-xs text-muted-foreground">Unmatched</div>
                    </div>
                    <div>
                      <div className="text-lg font-bold text-blue-600">{totals.known}</div>
                      <div className="text-xs text-muted-foreground">Known</div>
                    </div>
                  </div>
                )}

                {/* Month progress list */}
                {!completed && (
                  <div className="space-y-1 max-h-56 overflow-y-auto">
                    {months.map((month) => {
                      const progress = monthProgress[month]
                      const isActive = currentMonth === month && progress?.status === "processing"

                      return (
                        <div
                          key={month}
                          className={cn(
                            "flex items-center gap-2 py-1.5 px-2 text-sm rounded transition-colors",
                            isActive && "bg-primary/10 border border-primary/20"
                          )}
                        >
                          {/* Status icon */}
                          {progress?.status === "completed" ? (
                            <Check className="h-4 w-4 text-green-600 flex-shrink-0" />
                          ) : progress?.status === "error" ? (
                            <XCircle className="h-4 w-4 text-destructive flex-shrink-0" />
                          ) : progress?.status === "processing" ? (
                            <Loader2 className="h-4 w-4 animate-spin text-primary flex-shrink-0" />
                          ) : progress?.status === "downloading" ? (
                            <FolderDown className="h-4 w-4 text-blue-500 flex-shrink-0" />
                          ) : (
                            <div className="h-4 w-4 rounded-full border border-muted-foreground/40 flex-shrink-0" />
                          )}

                          {/* Month name */}
                          <span className={cn(
                            "flex-shrink-0 w-20",
                            isActive && "font-medium"
                          )}>
                            {formatMonth(month)}
                          </span>

                          {/* Progress details */}
                          <div className="flex-1 text-xs text-muted-foreground truncate">
                            {progress?.status === "completed" ? (
                              <span className="flex items-center gap-2">
                                <span className="text-green-600">{progress.matched}m</span>
                                <span className="text-amber-600">{progress.unmatched}u</span>
                                <span className="text-blue-600">{progress.known}k</span>
                                {progress.invoiceCount !== undefined && (
                                  <span className="text-muted-foreground">({progress.invoiceCount} inv)</span>
                                )}
                              </span>
                            ) : progress?.status === "downloading" ? (
                              <span>{progress.invoiceCount ?? 0} invoices downloaded</span>
                            ) : progress?.status === "processing" ? (
                              <span>Matching transactions...</span>
                            ) : progress?.status === "error" ? (
                              <span className="text-destructive">{progress.message}</span>
                            ) : (
                              <span>Waiting...</span>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Per-month summary when complete */}
                {completed && (
                  <div className="space-y-1 max-h-40 overflow-y-auto border-t pt-2">
                    <div className="text-xs text-muted-foreground mb-1">Per-month breakdown:</div>
                    {months.map((month) => {
                      const progress = monthProgress[month]
                      return (
                        <div
                          key={month}
                          className="flex items-center gap-2 py-1 px-2 text-xs rounded bg-muted/30"
                        >
                          <Check className="h-3 w-3 text-green-600 flex-shrink-0" />
                          <span className="w-16 font-medium">{formatMonth(month)}</span>
                          <span className="flex-1 flex items-center gap-2 text-muted-foreground">
                            <span className="text-green-600">{progress?.matched ?? 0}m</span>
                            <span className="text-amber-600">{progress?.unmatched ?? 0}u</span>
                            <span className="text-blue-600">{progress?.known ?? 0}k</span>
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
