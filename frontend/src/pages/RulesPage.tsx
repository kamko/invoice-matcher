import * as React from "react"
import { Plus, Pencil, Trash2, Loader2 } from "lucide-react"
import {
  useKnownTransactions,
  useCreateKnownTransaction,
  useUpdateKnownTransaction,
  useDeleteKnownTransaction,
  type KnownTransaction,
} from "../api/client"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table"
import { Button } from "../components/ui/button"
import { Badge } from "../components/ui/badge"
import { Input } from "../components/ui/input"
import { Label } from "../components/ui/label"
import { Select } from "../components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../components/ui/dialog"

function formatCurrency(amount: string) {
  const num = parseFloat(amount)
  return new Intl.NumberFormat('cs-CZ', {
    style: 'currency',
    currency: 'CZK',
  }).format(num)
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('cs-CZ')
}

export function RulesPage() {
  const { data: rules, isLoading } = useKnownTransactions()
  const createRule = useCreateKnownTransaction()
  const updateRule = useUpdateKnownTransaction()
  const deleteRule = useDeleteKnownTransaction()

  const [editingRule, setEditingRule] = React.useState<KnownTransaction | null>(null)
  const [isCreateOpen, setIsCreateOpen] = React.useState(false)

  // Form state
  const [formData, setFormData] = React.useState({
    rule_type: "vendor" as "exact" | "pattern" | "vendor" | "note" | "account",
    vendor_pattern: "",
    note_pattern: "",
    amount: "",
    amount_min: "",
    amount_max: "",
    vs_pattern: "",
    counter_account: "",
    reason: "",
    is_active: true,
  })

  const resetForm = () => {
    setFormData({
      rule_type: "vendor",
      vendor_pattern: "",
      note_pattern: "",
      amount: "",
      amount_min: "",
      amount_max: "",
      vs_pattern: "",
      counter_account: "",
      reason: "",
      is_active: true,
    })
  }

  const openCreate = () => {
    resetForm()
    setIsCreateOpen(true)
  }

  const openEdit = (rule: KnownTransaction) => {
    setFormData({
      rule_type: rule.rule_type,
      vendor_pattern: rule.vendor_pattern || "",
      note_pattern: rule.note_pattern || "",
      amount: rule.amount || "",
      amount_min: rule.amount_min || "",
      amount_max: rule.amount_max || "",
      vs_pattern: rule.vs_pattern || "",
      counter_account: rule.counter_account || "",
      reason: rule.reason,
      is_active: rule.is_active,
    })
    setEditingRule(rule)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const data = {
      rule_type: formData.rule_type,
      vendor_pattern: formData.vendor_pattern || undefined,
      note_pattern: formData.note_pattern || undefined,
      amount: formData.amount || undefined,
      amount_min: formData.amount_min || undefined,
      amount_max: formData.amount_max || undefined,
      vs_pattern: formData.vs_pattern || undefined,
      counter_account: formData.counter_account || undefined,
      reason: formData.reason,
      is_active: formData.is_active,
    }

    if (editingRule) {
      await updateRule.mutateAsync({ id: editingRule.id, ...data })
      setEditingRule(null)
    } else {
      await createRule.mutateAsync(data)
      setIsCreateOpen(false)
    }
    resetForm()
  }

  const handleDelete = async (id: number) => {
    if (window.confirm("Are you sure you want to delete this rule?")) {
      await deleteRule.mutateAsync(id)
    }
  }

  const ruleTypeOptions = [
    { value: 'vendor', label: 'Vendor Match' },
    { value: 'exact', label: 'Exact Amount' },
    { value: 'pattern', label: 'Pattern Match' },
    { value: 'note', label: 'Note Match' },
    { value: 'account', label: 'Account Match' },
  ]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Known Transaction Rules</h1>
          <p className="text-muted-foreground">
            Manage rules for automatically recognizing transactions (fees, recurring payments, etc.)
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Add Rule
        </Button>
      </div>

      <div className="border rounded-lg">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Type</TableHead>
              <TableHead>Pattern / Amount</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!rules?.length ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No rules defined yet
                </TableCell>
              </TableRow>
            ) : (
              rules.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <Badge variant="outline">{rule.rule_type}</Badge>
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate">
                    {rule.vendor_pattern ||
                      rule.note_pattern ||
                      (rule.amount && formatCurrency(rule.amount)) ||
                      rule.counter_account ||
                      "-"}
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate">
                    {rule.reason}
                  </TableCell>
                  <TableCell>
                    <Badge className={rule.is_active ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-800"}>
                      {rule.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell>{formatDate(rule.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(rule)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(rule.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog
        open={isCreateOpen || editingRule !== null}
        onOpenChange={(open) => {
          if (!open) {
            setIsCreateOpen(false)
            setEditingRule(null)
            resetForm()
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingRule ? "Edit Rule" : "Create Rule"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>Rule Type</Label>
              <Select
                value={formData.rule_type}
                onChange={(e) =>
                  setFormData({ ...formData, rule_type: e.target.value as typeof formData.rule_type })
                }
                options={ruleTypeOptions}
              />
            </div>

            {(formData.rule_type === "vendor" || formData.rule_type === "pattern") && (
              <div className="space-y-2">
                <Label>Vendor Pattern (regex)</Label>
                <Input
                  value={formData.vendor_pattern}
                  onChange={(e) =>
                    setFormData({ ...formData, vendor_pattern: e.target.value })
                  }
                  placeholder="e.g., Fio banka|bank fee"
                />
              </div>
            )}

            {formData.rule_type === "note" && (
              <div className="space-y-2">
                <Label>Note Pattern (regex)</Label>
                <Input
                  value={formData.note_pattern}
                  onChange={(e) =>
                    setFormData({ ...formData, note_pattern: e.target.value })
                  }
                  placeholder="e.g., Monthly fee"
                />
              </div>
            )}

            {formData.rule_type === "exact" && (
              <>
                <div className="space-y-2">
                  <Label>Amount</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={formData.amount}
                    onChange={(e) =>
                      setFormData({ ...formData, amount: e.target.value })
                    }
                    placeholder="Exact amount (negative for expenses)"
                  />
                </div>
              </>
            )}

            {formData.rule_type === "account" && (
              <div className="space-y-2">
                <Label>Counter Account</Label>
                <Input
                  value={formData.counter_account}
                  onChange={(e) =>
                    setFormData({ ...formData, counter_account: e.target.value })
                  }
                  placeholder="Account number or IBAN"
                />
              </div>
            )}

            {formData.rule_type === "pattern" && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Amount Min</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={formData.amount_min}
                    onChange={(e) =>
                      setFormData({ ...formData, amount_min: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Amount Max</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={formData.amount_max}
                    onChange={(e) =>
                      setFormData({ ...formData, amount_max: e.target.value })
                    }
                  />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>Reason / Description *</Label>
              <Input
                value={formData.reason}
                onChange={(e) =>
                  setFormData({ ...formData, reason: e.target.value })
                }
                placeholder="e.g., Bank fees, Monthly subscription"
                required
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active"
                checked={formData.is_active}
                onChange={(e) =>
                  setFormData({ ...formData, is_active: e.target.checked })
                }
              />
              <Label htmlFor="is_active">Active</Label>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setIsCreateOpen(false)
                  setEditingRule(null)
                  resetForm()
                }}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  !formData.reason.trim() ||
                  createRule.isPending ||
                  updateRule.isPending
                }
              >
                {editingRule ? "Update" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
