import * as React from "react"
import { Upload, FileText, X, Loader2, Edit2 } from "lucide-react"
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
import { formatCurrency } from "@/lib/utils"
import type { Transaction } from "@/api/client"
import { useParsePdf, type ParsePdfResponse } from "@/api/client"

interface UploadPdfModalProps {
  transaction: Transaction | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (file: File, vendor?: string, invoiceDate?: string) => Promise<void>
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
  const [parsedData, setParsedData] = React.useState<ParsePdfResponse | null>(null)
  const [editedVendor, setEditedVendor] = React.useState("")
  const [editedDate, setEditedDate] = React.useState("")
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const parsePdf = useParsePdf()

  // Reset state when modal closes
  React.useEffect(() => {
    if (!open) {
      setSelectedFile(null)
      setParsedData(null)
      setEditedVendor("")
      setEditedDate("")
    }
  }, [open])

  // Parse PDF when file is selected
  const handleFileSelect = async (file: File) => {
    if (file && file.type === "application/pdf") {
      setSelectedFile(file)
      setParsedData(null)

      try {
        const result = await parsePdf.mutateAsync(file)
        setParsedData(result)
        setEditedVendor(result.vendor || "")
        setEditedDate(result.invoice_date || "")
      } catch (error) {
        console.error("Failed to parse PDF:", error)
      }
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFileSelect(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFileSelect(file)
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
      // Pass vendor/date only if edited (different from extracted)
      const vendorOverride = editedVendor !== parsedData?.vendor ? editedVendor : undefined
      const dateOverride = editedDate !== parsedData?.invoice_date ? editedDate : undefined
      await onSubmit(selectedFile, vendorOverride || editedVendor, dateOverride || editedDate)
    }
  }

  if (!transaction) return null

  const isParsing = parsePdf.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[550px]">
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
              border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
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
              onChange={handleInputChange}
              className="hidden"
            />

            {selectedFile ? (
              <div className="flex items-center justify-center gap-3">
                <FileText className="h-6 w-6 text-green-500" />
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
                    setParsedData(null)
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <>
                <Upload className="mx-auto h-8 w-8 text-muted-foreground" />
                <p className="mt-2 font-medium">Drop PDF here or click to browse</p>
                <p className="text-sm text-muted-foreground">Only PDF files are accepted</p>
              </>
            )}
          </div>

          {/* Parsing indicator */}
          {isParsing && (
            <div className="flex items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Parsing PDF...</span>
            </div>
          )}

          {/* Parsed data preview - editable */}
          {parsedData && !isParsing && (
            <div className="rounded-lg border p-4 space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Edit2 className="h-4 w-4" />
                Extracted Data (edit if needed)
              </div>

              <div className="grid gap-3">
                <div className="grid grid-cols-4 items-center gap-2">
                  <Label htmlFor="vendor" className="text-right text-sm">
                    Vendor:
                  </Label>
                  <Input
                    id="vendor"
                    value={editedVendor}
                    onChange={(e) => setEditedVendor(e.target.value)}
                    className="col-span-3 h-8"
                    placeholder="Company name"
                  />
                </div>

                <div className="grid grid-cols-4 items-center gap-2">
                  <Label htmlFor="date" className="text-right text-sm">
                    Date:
                  </Label>
                  <Input
                    id="date"
                    type="date"
                    value={editedDate}
                    onChange={(e) => setEditedDate(e.target.value)}
                    className="col-span-3 h-8"
                  />
                </div>

                <div className="grid grid-cols-4 items-center gap-2">
                  <Label className="text-right text-sm text-muted-foreground">
                    Amount:
                  </Label>
                  <span className="col-span-3 text-sm font-mono">
                    {parsedData.amount ? `${parsedData.amount} EUR` : "-"}
                  </span>
                </div>

                {parsedData.vs && (
                  <div className="grid grid-cols-4 items-center gap-2">
                    <Label className="text-right text-sm text-muted-foreground">
                      VS:
                    </Label>
                    <span className="col-span-3 text-sm font-mono">
                      {parsedData.vs}
                    </span>
                  </div>
                )}
              </div>

              {/* Filename preview */}
              {editedDate && editedVendor && (
                <div className="text-xs text-muted-foreground mt-2 pt-2 border-t">
                  Filename: <span className="font-mono">{editedDate}-001_{transaction.transaction_type}_{editedVendor.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '').slice(0, 20)}.pdf</span>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!selectedFile || !parsedData || isParsing || isLoading || !editedVendor || !editedDate}
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Upload & Match
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
