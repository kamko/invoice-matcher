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
import { Select } from "@/components/ui/select"
import { formatCurrency, formatDate } from "@/lib/utils"
import type { Transaction } from "@/api/client"

export interface MarkKnownData {
  transaction_id: string
  rule_type: "exact" | "pattern" | "vendor" | "note" | "account"
  reason: string
  vendor_pattern?: string
  note_pattern?: string
  amount?: string
  counter_account?: string
}

interface MarkKnownModalProps {
  transaction: Transaction | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: MarkKnownData) => void | Promise<void>
  isLoading?: boolean
}

export function MarkKnownModal({
  transaction,
  open,
  onOpenChange,
  onSubmit,
  isLoading,
}: MarkKnownModalProps) {
  const [ruleType, setRuleType] = React.useState<"exact" | "pattern" | "vendor" | "note" | "account">("note")
  const [reason, setReason] = React.useState("")
  const [vendorPattern, setVendorPattern] = React.useState("")
  const [notePattern, setNotePattern] = React.useState("")
  const [accountPattern, setAccountPattern] = React.useState("")

  React.useEffect(() => {
    if (transaction) {
      // Pre-fill patterns from transaction
      setVendorPattern(transaction.counter_name || "")
      setAccountPattern(transaction.counter_account || "")
      // Extract keywords from note for pattern suggestion
      const note = transaction.note || ""
      // Take first significant word as pattern suggestion
      const words = note.split(/[\s|:,]+/).filter(w => w.length > 3)
      if (words.length > 0) {
        setNotePattern(words[0])
      }
    }
  }, [transaction])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!transaction) return

    onSubmit({
      transaction_id: transaction.id,
      rule_type: ruleType,
      reason,
      vendor_pattern: (ruleType === "pattern" || ruleType === "vendor") ? vendorPattern : undefined,
      note_pattern: ruleType === "note" ? notePattern : undefined,
      amount: ruleType === "exact" ? transaction.amount : undefined,
      counter_account: (ruleType === "exact" || ruleType === "account") ? accountPattern : undefined,
    })
  }

  if (!transaction) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Mark as Known Transaction</DialogTitle>
          <DialogDescription>
            Create a rule to recognize this type of transaction in the future.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Transaction details */}
          <div className="bg-muted p-4 rounded-md space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Date:</span>
              <span>{formatDate(transaction.date)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Amount:</span>
              <span className="font-mono">
                {formatCurrency(transaction.amount, transaction.currency)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Counter Party:</span>
              <span className="truncate max-w-[200px]">
                {transaction.counter_name || "-"}
              </span>
            </div>
            {transaction.counter_account && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Account/IBAN:</span>
                <span className="font-mono text-xs truncate max-w-[200px]">
                  {transaction.counter_account}
                </span>
              </div>
            )}
            {transaction.note && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Note:</span>
                <span className="truncate max-w-[200px]">{transaction.note}</span>
              </div>
            )}
          </div>

          {/* Rule type */}
          <div className="space-y-2">
            <Label htmlFor="rule-type">Match Type</Label>
            <Select
              id="rule-type"
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value as typeof ruleType)}
              options={[
                { value: "note", label: "Note - Match by note pattern (recommended)" },
                { value: "account", label: "Account - Match by IBAN/account number" },
                { value: "exact", label: "Exact - Match exact amount + account" },
                { value: "pattern", label: "Pattern - Match by text pattern" },
                { value: "vendor", label: "Vendor - Match by vendor name" },
              ]}
            />
          </div>

          {/* Note pattern (for note type) */}
          {ruleType === "note" && (
            <div className="space-y-2">
              <Label htmlFor="note-pattern">Note Pattern (regex)</Label>
              <Input
                id="note-pattern"
                value={notePattern}
                onChange={(e) => setNotePattern(e.target.value)}
                placeholder="e.g., Pozicka or OPENAI|ChatGPT"
              />
              <p className="text-xs text-muted-foreground">
                Regex pattern to match against transaction note. Use | for OR.
              </p>
              {transaction?.note && (
                <p className="text-xs text-muted-foreground bg-muted p-2 rounded">
                  Note: {transaction.note}
                </p>
              )}
            </div>
          )}

          {/* Vendor pattern (for pattern/vendor types) */}
          {(ruleType === "pattern" || ruleType === "vendor") && (
            <div className="space-y-2">
              <Label htmlFor="vendor-pattern">Vendor Pattern</Label>
              <Input
                id="vendor-pattern"
                value={vendorPattern}
                onChange={(e) => setVendorPattern(e.target.value)}
                placeholder="e.g., Netflix or ^NETFLIX.*"
              />
              <p className="text-xs text-muted-foreground">
                Regex pattern to match against vendor name or transaction note
              </p>
            </div>
          )}

          {/* Account pattern (for account type) */}
          {ruleType === "account" && (
            <div className="space-y-2">
              <Label htmlFor="account-pattern">Account/IBAN</Label>
              <Input
                id="account-pattern"
                value={accountPattern}
                onChange={(e) => setAccountPattern(e.target.value)}
                placeholder="e.g., SK1234567890 or CZ65..."
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Match transactions going to this account number or IBAN
              </p>
              {transaction?.counter_account && (
                <p className="text-xs text-muted-foreground bg-muted p-2 rounded font-mono">
                  Transaction IBAN: {transaction.counter_account}
                </p>
              )}
            </div>
          )}

          {/* Reason */}
          <div className="space-y-2">
            <Label htmlFor="reason">Reason *</Label>
            <Input
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g., Monthly Netflix subscription"
              required
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!reason.trim() || isLoading}>
              {isLoading ? "Creating..." : "Create Rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
