import * as React from "react"
import { Loader2, CheckCircle, XCircle, Check, ChevronDown, ChevronUp, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useLocalMode } from "@/context/LocalModeContext"

interface SyncProgressToastProps {
  open: boolean
  onClose: () => void
  yearMonth: string
  fioToken: string
  gdriveFolderId?: string
  prevMonthGdriveFolderId?: string
  fioOnly?: boolean  // Only refresh transactions, don't re-parse PDFs
  onComplete: () => void
}

const STEPS = [
  { id: "fetching", label: "Fetching transactions" },
  { id: "downloading", label: "Downloading invoices" },
  { id: "downloading_prev", label: "Previous month invoices" },
  { id: "checking_known", label: "Checking known rules" },
  { id: "matching", label: "Matching" },
  { id: "saving", label: "Saving results" },
]

export function SyncProgressToast({
  open,
  onClose,
  yearMonth,
  fioToken,
  gdriveFolderId,
  prevMonthGdriveFolderId,
  fioOnly,
  onComplete,
}: SyncProgressToastProps) {
  const { isLocalMode } = useLocalMode()
  const [expanded, setExpanded] = React.useState(false)
  const [currentStep, setCurrentStep] = React.useState<string>("started")
  const [message, setMessage] = React.useState("Starting...")
  const [error, setError] = React.useState<string | null>(null)
  const [completed, setCompleted] = React.useState(false)
  const [completedSteps, setCompletedSteps] = React.useState<Set<string>>(new Set())
  const [stats, setStats] = React.useState({
    transactions: 0,
    invoices: 0,
    matched: 0,
    unmatched: 0,
    known: 0,
  })

  // Use ref for onComplete to avoid re-triggering useEffect
  const onCompleteRef = React.useRef(onComplete)
  React.useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  React.useEffect(() => {
    if (!open) return

    // Reset state
    setCurrentStep("started")
    setMessage("Starting...")
    setError(null)
    setCompleted(false)
    setCompletedSteps(new Set())
    setStats({ transactions: 0, invoices: 0, matched: 0, unmatched: 0, known: 0 })
    setExpanded(false)

    const abortController = new AbortController()

    const runSync = async () => {
      try {
        // Use different endpoint for Fio-only refresh (faster, no PDF re-parsing)
        const endpoint = fioOnly
          ? `/api/months/${yearMonth}/fio-refresh-stream`
          : `/api/months/${yearMonth}/sync-stream`

        const body = fioOnly
          ? { fio_token: fioToken }
          : {
              year_month: yearMonth,
              fio_token: fioToken,
              gdrive_folder_id: isLocalMode ? undefined : (gdriveFolderId || undefined),
              prev_month_gdrive_folder_id: isLocalMode ? undefined : (prevMonthGdriveFolderId || undefined),
              local_only: isLocalMode,
            }

        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: abortController.signal,
        })

        if (!response.ok) {
          const err = await response.json()
          setError(err.detail || "Failed to start sync")
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
      switch (event) {
        case "progress":
          setCurrentStep(data.step as string)
          setMessage(data.message as string)

          if (data.step === "fetched") {
            setCompletedSteps((s) => new Set([...s, "fetching"]))
            setStats((s) => ({ ...s, transactions: data.count as number }))
          } else if (data.step === "downloaded") {
            setCompletedSteps((s) => new Set([...s, "downloading"]))
            setStats((s) => ({ ...s, invoices: data.count as number }))
          } else if (data.step === "downloaded_prev") {
            setCompletedSteps((s) => new Set([...s, "downloading_prev"]))
          } else if (data.step === "parsed") {
            setStats((s) => ({ ...s, invoices: data.count as number }))
          } else if (data.step === "known_checked") {
            setCompletedSteps((s) => new Set([...s, "checking_known"]))
            setStats((s) => ({ ...s, known: data.known_count as number }))
          } else if (data.step === "matched") {
            setCompletedSteps((s) => new Set([...s, "matching"]))
            setStats((s) => ({
              ...s,
              matched: data.matched_count as number,
              unmatched: data.unmatched_count as number,
            }))
          } else if (data.step === "saving") {
            setCompletedSteps((s) => new Set([...s, "saving"]))
          }
          break
        case "complete":
          setCompleted(true)
          setCompletedSteps(new Set(STEPS.map((s) => s.id)))
          setStats({
            transactions: 0,
            invoices: 0,
            matched: data.matched_count as number,
            unmatched: data.unmatched_count as number,
            known: data.known_count as number,
          })
          onCompleteRef.current()
          break
        case "error":
          setError(data.message as string)
          toast.error(`Sync failed: ${data.message}`)
          break
      }
    }

    runSync()

    return () => {
      abortController.abort()
    }
  }, [open, yearMonth, fioToken, gdriveFolderId, prevMonthGdriveFolderId])

  if (!open) return null

  const handleClose = () => {
    if (completed || error) {
      onClose()
    }
  }

  return (
    <div className="fixed top-4 right-4 z-50">
      <div
        className={cn(
          "bg-background border rounded-lg shadow-lg transition-all duration-200",
          expanded ? "w-80" : "w-auto"
        )}
      >
        {/* Collapsed view - clickable header */}
        <div
          className={cn(
            "flex items-center gap-3 px-4 py-3 cursor-pointer",
            !expanded && "pr-3"
          )}
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
              {error ? "Sync Failed" : completed ? "Sync Complete" : "Syncing..."}
            </div>
            {!expanded && (
              <div className="text-xs text-muted-foreground truncate">
                {error ? error : completed ? `${stats.matched} matched, ${stats.unmatched} unmatched` : message}
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
                  <div className="text-lg font-bold text-green-600">{stats.matched}</div>
                  <div className="text-xs text-muted-foreground">Matched</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-amber-600">{stats.unmatched}</div>
                  <div className="text-xs text-muted-foreground">Unmatched</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-blue-600">{stats.known}</div>
                  <div className="text-xs text-muted-foreground">Known</div>
                </div>
              </div>
            ) : (
              <>
                {/* Current action detail */}
                <div className="bg-muted/50 p-2 rounded text-xs font-mono truncate" title={message}>
                  {message}
                </div>

                {/* Step list */}
                <div className="space-y-1">
                  {STEPS.map((step) => {
                    const isCompleted = completedSteps.has(step.id)
                    const isActive = currentStep === step.id || currentStep === step.id.replace("ing", "ed")

                    return (
                      <div
                        key={step.id}
                        className={cn(
                          "flex items-center gap-2 py-0.5 text-xs",
                          isCompleted && "text-green-600",
                          isActive && !isCompleted && "text-primary",
                          !isCompleted && !isActive && "text-muted-foreground"
                        )}
                      >
                        {isCompleted ? (
                          <Check className="h-3 w-3" />
                        ) : isActive ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <div className="h-3 w-3" />
                        )}
                        <span>{step.label}</span>
                      </div>
                    )
                  })}
                </div>

                {/* Stats */}
                {(stats.transactions > 0 || stats.invoices > 0) && (
                  <div className="bg-muted p-2 rounded text-xs space-y-0.5">
                    {stats.transactions > 0 && <div>Transactions: {stats.transactions}</div>}
                    {stats.invoices > 0 && <div>Invoices: {stats.invoices}</div>}
                    {stats.known > 0 && <div>Known: {stats.known}</div>}
                    {stats.matched > 0 && <div>Matched: {stats.matched}</div>}
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
