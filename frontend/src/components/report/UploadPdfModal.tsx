import * as React from "react"
import { Upload, FileText, X, Loader2 } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { formatCurrency } from "@/lib/utils"
import type { Transaction } from "@/api/client"

interface UploadPdfModalProps {
  transaction: Transaction | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (file: File) => Promise<void>
  isLoading?: boolean
}

export function UploadPdfModal({
  transaction,
  open,
  onOpenChange,
  onSubmit,
  isLoading,
}: UploadPdfModalProps) {
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null)
  const [dragOver, setDragOver] = React.useState(false)
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  // Reset file when modal closes
  React.useEffect(() => {
    if (!open) {
      setSelectedFile(null)
    }
  }, [open])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && file.type === "application/pdf") {
      setSelectedFile(file)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file && file.type === "application/pdf") {
      setSelectedFile(file)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = () => {
    setDragOver(false)
  }

  const handleSubmit = async () => {
    if (selectedFile) {
      await onSubmit(selectedFile)
    }
  }

  if (!transaction) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Upload Invoice PDF</DialogTitle>
          <DialogDescription>
            Upload the invoice PDF that matches this transaction
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Transaction info */}
          <div className="rounded-lg bg-muted p-3 text-sm">
            <div className="font-medium">Transaction Details</div>
            <div className="mt-1 grid grid-cols-2 gap-1 text-muted-foreground">
              <span>Date:</span>
              <span>{transaction.date}</span>
              <span>Amount:</span>
              <span className="font-mono">
                {formatCurrency(transaction.amount, transaction.currency)}
              </span>
              <span>Note:</span>
              <span className="truncate">{transaction.note || "-"}</span>
            </div>
          </div>

          {/* Drop zone */}
          <div
            className={`
              border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
              transition-colors
              ${dragOver ? "border-primary bg-primary/5" : "border-muted-foreground/25"}
              ${selectedFile ? "border-green-500 bg-green-500/5" : ""}
            `}
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileSelect}
              className="hidden"
            />

            {selectedFile ? (
              <div className="flex items-center justify-center gap-3">
                <FileText className="h-8 w-8 text-green-500" />
                <div className="text-left">
                  <p className="font-medium">{selectedFile.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="ml-2"
                  onClick={(e) => {
                    e.stopPropagation()
                    setSelectedFile(null)
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <>
                <Upload className="mx-auto h-10 w-10 text-muted-foreground" />
                <p className="mt-2 font-medium">Drop PDF here or click to browse</p>
                <p className="text-sm text-muted-foreground">Only PDF files are accepted</p>
              </>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!selectedFile || isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Upload & Match
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
