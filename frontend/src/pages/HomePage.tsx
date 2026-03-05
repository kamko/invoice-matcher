import * as React from "react"
import { Link, useLocation } from "wouter"
import { Calendar, ChevronRight, Loader2, Settings, RefreshCw, FolderOpen, ExternalLink, CheckCircle2, Download, Layers } from "lucide-react"
import { useMonths, useGDriveStatus, useGDriveAuthUrl, useSetting, useSetSetting, useAppConfig } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { FolderPickerDialog } from "@/components/FolderPickerDialog"
import { Checkbox } from "@/components/ui/checkbox"
import { useSync } from "@/context/SyncContext"

export function HomePage() {
  const [, setLocation] = useLocation()
  const { data: months, isLoading, refetch: refetchMonths } = useMonths()
  const { data: gdriveStatus, refetch: refetchGdriveStatus } = useGDriveStatus()
  const getAuthUrl = useGDriveAuthUrl()
  const { data: parentFolderSetting } = useSetting("invoice_parent_folder_id")
  const { data: parentFolderNameSetting } = useSetting("invoice_parent_folder_name")
  const { data: appConfig } = useAppConfig()
  const setSettingMutation = useSetSetting()

  // Listen for OAuth popup message
  React.useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === "gdrive-connected") {
        refetchGdriveStatus()
      }
    }
    window.addEventListener("message", handleMessage)
    return () => window.removeEventListener("message", handleMessage)
  }, [refetchGdriveStatus])

  const handleGDriveConnect = async () => {
    try {
      const result = await getAuthUrl.mutateAsync()
      window.open(result.auth_url, "_blank", "width=600,height=700")
    } catch (error) {
      console.error("Failed to get auth URL:", error)
    }
  }

  const [fioToken, setFioToken] = React.useState(() => localStorage.getItem("fio_token") || "")
  const [showSettings, setShowSettings] = React.useState(false)
  const [selectedMonth, setSelectedMonth] = React.useState(() => {
    // Default to current month
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`
  })
  const [showFolderPicker, setShowFolderPicker] = React.useState(false)
  const [downloadingMonth, setDownloadingMonth] = React.useState<string | null>(null)
  const [selectedBatchMonths, setSelectedBatchMonths] = React.useState<Set<string>>(new Set())
  const { startSync, startBatchSync } = useSync()

  const parentFolderId = parentFolderSetting?.value
  const parentFolderName = parentFolderNameSetting?.value

  const handleDownloadInvoices = async (yearMonth: string) => {
    setDownloadingMonth(yearMonth)
    try {
      const response = await fetch(`/api/months/${yearMonth}/download-invoices`)
      if (!response.ok) {
        const err = await response.json()
        alert(err.detail || "Failed to download")
        return
      }
      // Create blob and download
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `invoices-${yearMonth}.zip`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      alert("Failed to download invoices")
    } finally {
      setDownloadingMonth(null)
    }
  }

  // Generate last 12 months for selection
  const monthOptions = React.useMemo(() => {
    const options: string[] = []
    const now = new Date()
    for (let i = 0; i < 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      options.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`)
    }
    return options
  }, [])

  const formatYearMonth = (ym: string) => {
    const [year, mon] = ym.split("-")
    const date = new Date(parseInt(year), parseInt(mon) - 1)
    return date.toLocaleDateString("en-US", { month: "long", year: "numeric" })
  }

  const handleSaveSettings = () => {
    localStorage.setItem("fio_token", fioToken)
    setShowSettings(false)
  }

  const handleParentFolderSelect = async (folderId: string, folderName: string) => {
    await setSettingMutation.mutateAsync({ key: "invoice_parent_folder_id", value: folderId })
    await setSettingMutation.mutateAsync({ key: "invoice_parent_folder_name", value: folderName })
  }

  const handleSync = (yearMonth: string) => {
    if (!fioToken) {
      setShowSettings(true)
      return
    }

    // No need to pass folder IDs - backend auto-resolves from parent folder
    startSync({
      yearMonth,
      fioToken,
      onComplete: () => {
        refetchMonths()
        setLocation(`/month/${yearMonth}`)
      },
    })
  }

  const handleBatchSync = () => {
    if (!fioToken) {
      setShowSettings(true)
      return
    }

    if (selectedBatchMonths.size === 0) {
      return
    }

    // Sort months chronologically
    const sortedMonths = Array.from(selectedBatchMonths).sort()

    startBatchSync({
      months: sortedMonths,
      fioToken,
      onComplete: () => {
        refetchMonths()
        setSelectedBatchMonths(new Set())
      },
    })
  }

  const toggleBatchMonth = (ym: string) => {
    setSelectedBatchMonths((prev) => {
      const next = new Set(prev)
      if (next.has(ym)) {
        next.delete(ym)
      } else {
        next.add(ym)
      }
      return next
    })
  }

  const hasToken = !!fioToken

  return (
    <div className="container mx-auto py-8 max-w-4xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold">Invoice Reconciliation</h1>
          <p className="text-muted-foreground">Manage your monthly reconciliations</p>
        </div>
        <Button variant="outline" onClick={() => setShowSettings(!showSettings)}>
          <Settings className="h-4 w-4 mr-2" />
          Settings
        </Button>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Settings</CardTitle>
            <CardDescription>Configure your Fio Bank API token and invoice folder</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="fio-token">Fio Bank API Token</Label>
              <Input
                id="fio-token"
                type="password"
                value={fioToken}
                onChange={(e) => setFioToken(e.target.value)}
                placeholder="Your Fio API token"
              />
              <p className="text-xs text-muted-foreground">
                Token is stored locally in your browser
              </p>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Google Drive:</span>
                {gdriveStatus?.authenticated ? (
                  <span className="text-sm text-green-600">Connected</span>
                ) : (
                  <>
                    <span className="text-sm text-amber-600">Not connected</span>
                    {gdriveStatus?.available && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={handleGDriveConnect}
                        disabled={getAuthUrl.isPending}
                      >
                        {getAuthUrl.isPending ? (
                          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        ) : (
                          <ExternalLink className="h-3 w-3 mr-1" />
                        )}
                        Connect
                      </Button>
                    )}
                  </>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">LLM Model:</span>
                {appConfig?.llm_enabled ? (
                  <span className="text-sm font-mono">{appConfig.llm_model}</span>
                ) : (
                  <span className="text-sm text-amber-600">Not configured (set OPENROUTER_API_KEY)</span>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <Label>Invoice Parent Folder</Label>
              <p className="text-xs text-muted-foreground mb-2">
                Select the folder containing monthly subfolders (YYYYMM format, e.g., 202602)
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1 justify-start"
                  onClick={() => setShowFolderPicker(true)}
                  disabled={!gdriveStatus?.authenticated}
                >
                  <FolderOpen className="h-4 w-4 mr-2" />
                  {parentFolderName || "Select parent folder..."}
                </Button>
                {parentFolderId && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => {
                      await setSettingMutation.mutateAsync({ key: "invoice_parent_folder_id", value: "" })
                      await setSettingMutation.mutateAsync({ key: "invoice_parent_folder_name", value: "" })
                    }}
                  >
                    Clear
                  </Button>
                )}
              </div>
            </div>
            <Button onClick={handleSaveSettings}>Save Settings</Button>
          </CardContent>
        </Card>
      )}

      {/* Quick Sync */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Sync Month</CardTitle>
          <CardDescription>
            {hasToken
              ? parentFolderId
                ? "Select a month to sync - folders auto-detected from parent"
                : "Configure invoice parent folder in settings first"
              : "Configure your Fio token in settings first"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4 items-end">
            <div className="flex-1 space-y-2">
              <Label htmlFor="month-select">Month</Label>
              <select
                id="month-select"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {monthOptions.map((ym) => (
                  <option key={ym} value={ym}>
                    {formatYearMonth(ym)}
                  </option>
                ))}
              </select>
            </div>
            <Button
              onClick={() => handleSync(selectedMonth)}
              disabled={!hasToken}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Sync {formatYearMonth(selectedMonth)}
            </Button>
          </div>
          {parentFolderId && (
            <p className="text-xs text-muted-foreground">
              Using folder: {parentFolderName} / {selectedMonth.replace("-", "")}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Batch Sync */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5" />
            Batch Sync
          </CardTitle>
          <CardDescription>
            Sync multiple months at once - fetches all transactions in one API call
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
            {monthOptions.map((ym) => {
              const [year, mon] = ym.split("-")
              const date = new Date(parseInt(year), parseInt(mon) - 1)
              const shortLabel = date.toLocaleDateString("en-US", { month: "short", year: "2-digit" })
              const isSelected = selectedBatchMonths.has(ym)

              return (
                <div
                  key={ym}
                  className={`flex items-center gap-2 p-2 rounded border cursor-pointer transition-colors ${
                    isSelected ? "bg-primary/10 border-primary" : "hover:bg-muted"
                  }`}
                  onClick={() => toggleBatchMonth(ym)}
                >
                  <Checkbox
                    checked={isSelected}
                    onCheckedChange={() => toggleBatchMonth(ym)}
                  />
                  <span className="text-sm">{shortLabel}</span>
                </div>
              )
            })}
          </div>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {selectedBatchMonths.size} month{selectedBatchMonths.size !== 1 ? "s" : ""} selected
            </p>
            <Button
              onClick={handleBatchSync}
              disabled={!hasToken || selectedBatchMonths.size === 0}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Sync {selectedBatchMonths.size} Month{selectedBatchMonths.size !== 1 ? "s" : ""}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Existing Months */}
      <Card>
        <CardHeader>
          <CardTitle>Monthly Reports</CardTitle>
          <CardDescription>View and manage your reconciliation history</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : !months || months.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Calendar className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No reconciliations yet</p>
              <p className="text-sm">Sync a month above to get started</p>
            </div>
          ) : (
            <div className="space-y-2">
              {months.map((m) => (
                <Link key={m.year_month} href={`/month/${m.year_month}`}>
                  <div className="flex items-center justify-between p-4 rounded-lg border hover:bg-accent cursor-pointer">
                    <div className="flex items-center gap-4">
                      <Calendar className="h-5 w-5 text-muted-foreground" />
                      <div>
                        <div className="font-medium">{formatYearMonth(m.year_month)}</div>
                        <div className="text-sm text-muted-foreground">
                          {m.last_synced_at
                            ? `Last synced: ${new Date(m.last_synced_at).toLocaleDateString()}`
                            : "Not synced yet"}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right text-sm">
                        <div className="text-green-600">{m.matched_count} matched</div>
                        {m.unmatched_count > 0 ? (
                          <div className="text-amber-600">{m.unmatched_count} unmatched</div>
                        ) : (
                          <div className="text-green-600 flex items-center gap-1 justify-end">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            All matched
                          </div>
                        )}
                      </div>
                      <Badge
                        variant={
                          m.status === "completed" && m.unmatched_count === 0
                            ? "success"
                            : m.status === "completed"
                            ? "outline"
                            : m.status === "processing"
                            ? "secondary"
                            : m.status === "failed"
                            ? "destructive"
                            : "outline"
                        }
                      >
                        {m.status === "completed" && m.unmatched_count === 0 ? "complete" : m.status}
                      </Badge>
                      {m.gdrive_folder_id && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          title="Download all invoices from folder (for VAT)"
                          disabled={downloadingMonth === m.year_month}
                          onClick={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                            handleDownloadInvoices(m.year_month)
                          }}
                        >
                          {downloadingMonth === m.year_month ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Download className="h-4 w-4" />
                          )}
                        </Button>
                      )}
                      <ChevronRight className="h-5 w-5 text-muted-foreground" />
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Folder Picker Dialog */}
      <FolderPickerDialog
        open={showFolderPicker}
        onOpenChange={setShowFolderPicker}
        onSelect={handleParentFolderSelect}
        title="Select Invoice Parent Folder"
        description="Choose the folder containing monthly subfolders (YYYYMM format)"
      />
    </div>
  )
}
