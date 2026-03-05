import * as React from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { FolderInvoice } from "@/api/client"

interface RenameInvoiceModalProps {
  invoice: FolderInvoice | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onRename: (fileId: string, newFilename: string) => Promise<void>
  isLoading?: boolean
}

export function RenameInvoiceModal({
  invoice,
  open,
  onOpenChange,
  onRename,
  isLoading,
}: RenameInvoiceModalProps) {
  const [newFilename, setNewFilename] = React.useState("")

  React.useEffect(() => {
    if (invoice) {
      setNewFilename(invoice.filename)
    }
  }, [invoice])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!invoice || !newFilename.trim()) return

    await onRename(invoice.gdrive_file_id, newFilename.trim())
    onOpenChange(false)
  }

  // Extract payment type from filename for quick fix buttons
  const getPaymentType = (filename: string): string | null => {
    const match = filename.match(/^\d{4}-\d{2}-\d{2}-\d+_([a-zA-Z0-9-]+)_/)
    return match ? match[1] : null
  }

  const replacePaymentType = (filename: string, newType: string): string => {
    return filename.replace(
      /^(\d{4}-\d{2}-\d{2}-\d+)_[a-zA-Z0-9-]+_/,
      `$1_${newType}_`
    )
  }

  if (!invoice) return null

  // Use newFilename for current selection (updates as user clicks buttons)
  const selectedType = getPaymentType(newFilename)
  // Check if invoice follows the naming pattern (for showing quick fix buttons)
  const hasPaymentType = getPaymentType(invoice.filename) !== null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Rename Invoice</DialogTitle>
          <DialogDescription>
            Change the filename of this invoice in Google Drive.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="filename">Filename</Label>
            <Input
              id="filename"
              value={newFilename}
              onChange={(e) => setNewFilename(e.target.value)}
              placeholder="2025-10-03-001_card_vendor.pdf"
            />
          </div>

          {/* Quick fix buttons for payment type */}
          {hasPaymentType && (
            <div className="space-y-2">
              <Label>Quick fix payment type:</Label>
              <div className="flex gap-2 flex-wrap">
                {["card", "wire", "sepa-debit", "cash"].map((type) => (
                  <Button
                    key={type}
                    type="button"
                    variant={selectedType === type ? "default" : "outline"}
                    size="sm"
                    onClick={() => setNewFilename(replacePaymentType(newFilename, type))}
                  >
                    {type}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!newFilename.trim() || newFilename === invoice.filename || isLoading}
            >
              {isLoading ? "Renaming..." : "Rename"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
