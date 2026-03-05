import * as React from "react"
import { Loader2, Upload, Calendar } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface UploadInvoiceModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (file: File, invoiceDate: string) => Promise<void>
  isLoading: boolean
  yearMonth: string
}

export function UploadInvoiceModal({
  open,
  onOpenChange,
  onSubmit,
  isLoading,
  yearMonth,
}: UploadInvoiceModalProps) {
  const [file, setFile] = React.useState<File | null>(null)
  const [invoiceDate, setInvoiceDate] = React.useState(() => {
    // Default to last day of the month
    const [year, month] = yearMonth.split("-").map(Number)
    const lastDay = new Date(year, month, 0).getDate()
    return `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`
  })
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  // Update default date when yearMonth changes
  React.useEffect(() => {
    const [year, month] = yearMonth.split("-").map(Number)
    const lastDay = new Date(year, month, 0).getDate()
    setInvoiceDate(`${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`)
  }, [yearMonth])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile && selectedFile.type === "application/pdf") {
      setFile(selectedFile)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile && droppedFile.type === "application/pdf") {
      setFile(droppedFile)
    }
  }

  const handleSubmit = async () => {
    if (!file || !invoiceDate) return
    await onSubmit(file, invoiceDate)
    setFile(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleClose = (open: boolean) => {
    if (!open) {
      setFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
    onOpenChange(open)
  }

  const formatYearMonth = (ym: string) => {
    const [year, mon] = ym.split("-")
    const date = new Date(parseInt(year), parseInt(mon) - 1)
    return date.toLocaleDateString("en-US", { month: "long", year: "numeric" })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Upload Invoice</DialogTitle>
          <DialogDescription>
            Add a new invoice to {formatYearMonth(yearMonth)}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Invoice Date */}
          <div className="space-y-2">
            <Label htmlFor="invoice-date" className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              Invoice Date (VAT Date)
            </Label>
            <Input
              id="invoice-date"
              type="date"
              value={invoiceDate}
              onChange={(e) => setInvoiceDate(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              This date will be used as the filename prefix (YYYY-MM-DD_filename.pdf)
            </p>
          </div>

          {/* File Upload */}
          <div className="space-y-2">
            <Label>PDF File</Label>
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                file ? "border-green-500 bg-green-50" : "border-muted-foreground/25 hover:border-primary"
              }`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                onChange={handleFileChange}
                className="hidden"
              />
              {file ? (
                <div className="space-y-1">
                  <Upload className="h-8 w-8 mx-auto text-green-600" />
                  <p className="font-medium text-green-700">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    Drop a PDF here or click to select
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!file || !invoiceDate || isLoading}>
            {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Upload Invoice
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
