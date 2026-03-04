import * as React from "react"
import { WizardLayout } from "@/components/wizard/WizardLayout"
import { DateRangePicker } from "@/components/wizard/DateRangePicker"
import { FioTokenInput } from "@/components/wizard/FioTokenInput"
import { InvoiceDirInput } from "@/components/wizard/InvoiceDirInput"
import { GDriveSelector } from "@/components/wizard/GDriveSelector"
import { ProcessingStep } from "@/components/wizard/ProcessingStep"

const STEPS = [
  { id: "dates", title: "Date Range", description: "Select the period for reconciliation" },
  { id: "gdrive", title: "Google Drive", description: "Select folder with invoice PDFs" },
  { id: "token", title: "Bank Token", description: "Enter your Fio Bank API token" },
  { id: "processing", title: "Processing", description: "Running reconciliation" },
]

const STEPS_LOCAL = [
  { id: "dates", title: "Date Range", description: "Select the period for reconciliation" },
  { id: "invoices", title: "Invoices", description: "Specify local invoice directory" },
  { id: "token", title: "Bank Token", description: "Enter your Fio Bank API token" },
  { id: "processing", title: "Processing", description: "Running reconciliation" },
]

export function WizardPage() {
  const [currentStep, setCurrentStep] = React.useState(0)
  const [useLocalDir, setUseLocalDir] = React.useState(false)

  // Form state
  const [fromDate, setFromDate] = React.useState("")
  const [toDate, setToDate] = React.useState("")
  const [gdriveFolderId, setGdriveFolderId] = React.useState<string | null>(null)
  const [gdriveFolderName, setGdriveFolderName] = React.useState<string | null>(null)
  const [invoiceDir, setInvoiceDir] = React.useState("")
  const [fioToken, setFioToken] = React.useState("")

  const steps = useLocalDir ? STEPS_LOCAL : STEPS

  const handleStartReconciliation = () => {
    setCurrentStep(3) // Move to processing step (SSE handles the rest)
  }

  const handleGDriveFolderSelect = (folderId: string, folderName: string) => {
    setGdriveFolderId(folderId)
    setGdriveFolderName(folderName)
  }

  const handleSkipGDrive = () => {
    setUseLocalDir(true)
    // Stay on step 1 but switch to local dir input
  }

  const handleBackToGDrive = () => {
    setUseLocalDir(false)
  }

  // Set default dates on mount (current month: 1st to last day)
  React.useEffect(() => {
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth(), 1)
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0)
    // Format as YYYY-MM-DD using local time (not UTC)
    const formatDate = (d: Date) => {
      const year = d.getFullYear()
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${year}-${month}-${day}`
    }
    setFromDate(formatDate(start))
    setToDate(formatDate(end))
  }, [])

  // Check for gdrive=connected query param (OAuth callback)
  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get("gdrive") === "connected") {
      // Clean up URL
      window.history.replaceState({}, "", window.location.pathname)
    }
  }, [])

  return (
    <WizardLayout steps={steps} currentStep={currentStep}>
      {currentStep === 0 && (
        <DateRangePicker
          fromDate={fromDate}
          toDate={toDate}
          onFromDateChange={setFromDate}
          onToDateChange={setToDate}
          onNext={() => setCurrentStep(1)}
        />
      )}

      {currentStep === 1 && !useLocalDir && (
        <GDriveSelector
          selectedFolderId={gdriveFolderId}
          selectedFolderName={gdriveFolderName}
          onFolderSelect={handleGDriveFolderSelect}
          onNext={() => setCurrentStep(2)}
          onSkip={handleSkipGDrive}
        />
      )}

      {currentStep === 1 && useLocalDir && (
        <InvoiceDirInput
          invoiceDir={invoiceDir}
          onInvoiceDirChange={setInvoiceDir}
          onNext={() => setCurrentStep(2)}
          onBack={handleBackToGDrive}
        />
      )}

      {currentStep === 2 && (
        <FioTokenInput
          token={fioToken}
          onTokenChange={setFioToken}
          onNext={handleStartReconciliation}
          onBack={() => setCurrentStep(1)}
        />
      )}

      {currentStep === 3 && (
        <ProcessingStep
          fromDate={fromDate}
          toDate={toDate}
          fioToken={fioToken}
          gdriveFolderId={useLocalDir ? null : gdriveFolderId}
          invoiceDir={useLocalDir ? invoiceDir : ""}
        />
      )}
    </WizardLayout>
  )
}
