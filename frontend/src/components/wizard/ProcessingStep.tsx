import * as React from "react"
import { Loader2, CheckCircle, XCircle, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useLocation } from "wouter"
import { cn } from "@/lib/utils"

interface ProcessingStepProps {
  fromDate: string
  toDate: string
  fioToken: string
  gdriveFolderId: string | null
  invoiceDir: string
}

const STEPS = [
  { id: "fetching", label: "Fetching transactions" },
  { id: "downloading", label: "Downloading invoices" },
  { id: "parsing", label: "Parsing PDFs" },
  { id: "checking_known", label: "Checking known rules" },
  { id: "matching", label: "Matching" },
  { id: "saving", label: "Saving results" },
]

export function ProcessingStep({
  fromDate,
  toDate,
  fioToken,
  gdriveFolderId,
  invoiceDir,
}: ProcessingStepProps) {
  const [, setLocation] = useLocation()
  const [currentStep, setCurrentStep] = React.useState<string>("started")
  const [message, setMessage] = React.useState("Starting reconciliation...")
  const [error, setError] = React.useState<string | null>(null)
  const [sessionId, setSessionId] = React.useState<number | null>(null)
  const [completed, setCompleted] = React.useState(false)
  const [completedSteps, setCompletedSteps] = React.useState<Set<string>>(new Set())
  const [stats, setStats] = React.useState({
    transactions: 0,
    invoices: 0,
    matched: 0,
    unmatched: 0,
    known: 0,
  })

  React.useEffect(() => {
    const abortController = new AbortController()

    const runReconciliation = async () => {
      try {
        const response = await fetch("/api/reconcile-stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            from_date: fromDate,
            to_date: toDate,
            fio_token: fioToken,
            gdrive_folder_id: gdriveFolderId || undefined,
            invoice_dir: invoiceDir || undefined,
          }),
          signal: abortController.signal,
        })

        if (!response.ok) {
          const err = await response.json()
          setError(err.detail || "Failed to start reconciliation")
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
        case "session":
          setSessionId(data.session_id as number)
          break
        case "progress":
          setCurrentStep(data.step as string)
          setMessage(data.message as string)
          // Mark previous step as completed
          if (data.step === "fetched") {
            setCompletedSteps((s) => new Set([...s, "fetching"]))
            setStats((s) => ({ ...s, transactions: data.count as number }))
          } else if (data.step === "downloaded") {
            setCompletedSteps((s) => new Set([...s, "downloading"]))
            setStats((s) => ({ ...s, invoices: data.count as number }))
          } else if (data.step === "parsed") {
            setCompletedSteps((s) => new Set([...s, "parsing"]))
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
          // Auto redirect after delay
          setTimeout(() => {
            setLocation(`/report/${data.session_id}`)
          }, 1500)
          break
        case "error":
          setError(data.message as string)
          break
      }
    }

    runReconciliation()

    return () => {
      abortController.abort()
    }
  }, [fromDate, toDate, fioToken, gdriveFolderId, invoiceDir, setLocation])

  if (error) {
    return (
      <div className="space-y-6 text-center py-8">
        <XCircle className="h-16 w-16 mx-auto text-destructive" />
        <div>
          <h3 className="text-lg font-semibold">Error</h3>
          <p className="text-destructive mt-2">{error}</p>
        </div>
        <Button variant="outline" onClick={() => window.location.reload()}>
          Try Again
        </Button>
      </div>
    )
  }

  if (completed) {
    return (
      <div className="space-y-6 text-center py-8">
        <CheckCircle className="h-16 w-16 mx-auto text-green-500" />
        <div>
          <h3 className="text-lg font-semibold">Completed!</h3>
          <p className="text-muted-foreground">Redirecting to results...</p>
        </div>
        <div className="flex justify-center gap-4 text-sm">
          <div className="text-green-600">Matched: {stats.matched}</div>
          <div className="text-red-600">Unmatched: {stats.unmatched}</div>
          <div className="text-blue-600">Known: {stats.known}</div>
        </div>
        <Button onClick={() => setLocation(`/report/${sessionId}`)}>
          View Results
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6 py-4">
      {/* Current status */}
      <div className="flex items-center gap-3">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
        <span className="font-medium">{message}</span>
      </div>

      {/* Step list */}
      <div className="space-y-2">
        {STEPS.map((step) => {
          const isCompleted = completedSteps.has(step.id)
          const isActive = currentStep === step.id || currentStep === step.id.replace("ing", "ed")

          return (
            <div
              key={step.id}
              className={cn(
                "flex items-center gap-3 p-2 rounded",
                isCompleted && "text-green-600",
                isActive && !isCompleted && "text-primary bg-primary/5",
                !isCompleted && !isActive && "text-muted-foreground"
              )}
            >
              {isCompleted ? (
                <Check className="h-4 w-4" />
              ) : isActive ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <div className="h-4 w-4" />
              )}
              <span>{step.label}</span>
            </div>
          )
        })}
      </div>

      {/* Stats */}
      {(stats.transactions > 0 || stats.invoices > 0) && (
        <div className="bg-muted p-3 rounded-lg text-sm space-y-1">
          {stats.transactions > 0 && (
            <div>Transactions: {stats.transactions}</div>
          )}
          {stats.invoices > 0 && <div>Invoices: {stats.invoices}</div>}
          {stats.known > 0 && <div>Known: {stats.known}</div>}
          {stats.matched > 0 && <div>Matched: {stats.matched}</div>}
        </div>
      )}
    </div>
  )
}
