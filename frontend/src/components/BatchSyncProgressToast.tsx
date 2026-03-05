import * as React from "react"
import { Loader2, CheckCircle, XCircle, Check, ChevronDown, ChevronUp, X } from "lucide-react"
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
  status: "pending" | "processing" | "completed" | "error"
  message?: string
  matched?: number
  unmatched?: number
  known?: number
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
  const [currentStep, setCurrentStep] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [completed, setCompleted] = React.useState(false)
  const [monthProgress, setMonthProgress] = React.useState<Record<string, MonthProgress>>({})
  const [totals, setTotals] = React.useState({ matched: 0, unmatched: 0, known: 0 })

  const onCompleteRef = React.useRef(onComplete)
  React.useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  React.useEffect(() => {
    if (!open) return

    // Reset state
    setCurrentMonth(null)
    setCurrentStep("")
    setError(null)
    setCompleted(false)
    setMonthProgress(
      months.reduce((acc, m) => ({ ...acc, [m]: { status: "pending" } }), {})
    )
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
          setCurrentStep("Starting batch sync...")
          break

        case "progress": {
          const step = data.step as string
          const message = data.message as string
          setCurrentStep(message)

          // Handle month-specific progress
          if (step === "processing_month" && month) {
            setCurrentMonth(month)
            setMonthProgress((prev) => ({
              ...prev,
              [month]: { status: "processing", message: "Processing..." },
            }))
          } else if (step === "downloaded_month" && month) {
            setMonthProgress((prev) => ({
              ...prev,
              [month]: { ...prev[month], message: `Downloaded ${data.count} invoices` },
            }))
          }
          break
        }

        case "month_complete":
          if (month) {
            setMonthProgress((prev) => ({
              ...prev,
              [month]: {
                status: "completed",
                matched: data.matched_count as number,
                unmatched: data.unmatched_count as number,
                known: data.known_count as number,
              },
            }))
            // Calculate running totals
            setTotals((prev) => ({
              matched: prev.matched + (data.matched_count as number),
              unmatched: prev.unmatched + (data.unmatched_count as number),
              known: prev.known + (data.known_count as number),
            }))
          }
          break

        case "complete":
          setCompleted(true)
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

  return (
    <div className="fixed top-4 right-4 z-50">
      <div
        className={cn(
          "bg-background border rounded-lg shadow-lg transition-all duration-200",
          expanded ? "w-96" : "w-auto"
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
                : `Syncing ${months.length} months...`}
            </div>
            {!expanded && (
              <div className="text-xs text-muted-foreground truncate">
                {error
                  ? error
                  : completed
                  ? `${totals.matched} matched, ${totals.unmatched} unmatched`
                  : `${completedCount}/${months.length} months done`}
              </div>
            )}
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
            ) : completed ? (
              <div className="grid grid-cols-3 gap-2 text-center text-sm">
                <div>
                  <div className="text-lg font-bold text-green-600">
                    {totals.matched}
                  </div>
                  <div className="text-xs text-muted-foreground">Matched</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-amber-600">
                    {totals.unmatched}
                  </div>
                  <div className="text-xs text-muted-foreground">Unmatched</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-blue-600">
                    {totals.known}
                  </div>
                  <div className="text-xs text-muted-foreground">Known</div>
                </div>
              </div>
            ) : (
              <>
                <div className="text-xs text-muted-foreground">{currentStep}</div>

                {/* Month progress list */}
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {months.map((month) => {
                    const progress = monthProgress[month]
                    const isActive = currentMonth === month

                    return (
                      <div
                        key={month}
                        className={cn(
                          "flex items-center gap-2 py-1 px-2 text-sm rounded",
                          isActive && "bg-muted"
                        )}
                      >
                        {progress?.status === "completed" ? (
                          <Check className="h-4 w-4 text-green-600 flex-shrink-0" />
                        ) : progress?.status === "error" ? (
                          <XCircle className="h-4 w-4 text-destructive flex-shrink-0" />
                        ) : progress?.status === "processing" ? (
                          <Loader2 className="h-4 w-4 animate-spin text-primary flex-shrink-0" />
                        ) : (
                          <div className="h-4 w-4 rounded-full border border-muted-foreground flex-shrink-0" />
                        )}
                        <span className="flex-1 truncate">{formatMonth(month)}</span>
                        {progress?.status === "completed" && (
                          <span className="text-xs text-muted-foreground">
                            {progress.matched}m / {progress.unmatched}u
                          </span>
                        )}
                        {progress?.status === "error" && (
                          <span className="text-xs text-destructive truncate max-w-24">
                            {progress.message}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
