import * as React from "react"
import { Link, useLocation } from "wouter"
import { Calendar, ChevronRight, Loader2, Settings, RefreshCw, FolderOpen, ExternalLink, CheckCircle2, Download } from "lucide-react"
import { useMonths, useGDriveStatus, useGDriveAuthUrl } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { FolderPickerDialog } from "@/components/FolderPickerDialog"
import { useSync } from "@/context/SyncContext"

interface MonthFolderInfo {
  id: string
  name: string
}

// Helper to get folder info for a month from localStorage
function getMonthFolder(yearMonth: string): MonthFolderInfo | null {
  const folders = JSON.parse(localStorage.getItem("month_folders") || "{}")
  return folders[yearMonth] || null
}

// Helper to set folder info for a month
function setMonthFolder(yearMonth: string, folderId: string, folderName: string) {
  const folders = JSON.parse(localStorage.getItem("month_folders") || "{}")
  folders[yearMonth] = { id: folderId, name: folderName }
  localStorage.setItem("month_folders", JSON.stringify(folders))
}

export function HomePage() {
  const [, setLocation] = useLocation()
  const { data: months, isLoading, refetch: refetchMonths } = useMonths()
  const { data: gdriveStatus, refetch: refetchGdriveStatus } = useGDriveStatus()
  const getAuthUrl = useGDriveAuthUrl()

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
  const [selectedFolder, setSelectedFolder] = React.useState<MonthFolderInfo | null>(() => getMonthFolder(selectedMonth))
  const [showFolderPicker, setShowFolderPicker] = React.useState(false)
  const { startSync } = useSync()

  // Update folder when month changes
  React.useEffect(() => {
    setSelectedFolder(getMonthFolder(selectedMonth))
  }, [selectedMonth])

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

  const handleFolderSelect = (folderId: string, folderName: string) => {
    setSelectedFolder({ id: folderId, name: folderName })
    setMonthFolder(selectedMonth, folderId, folderName)
  }

  // Calculate previous month
  const getPrevMonth = (ym: string): string => {
    const [year, mon] = ym.split("-").map(Number)
    const prevDate = new Date(year, mon - 2, 1) // mon-1 is current, mon-2 is previous
    return `${prevDate.getFullYear()}-${String(prevDate.getMonth() + 1).padStart(2, "0")}`
  }

  const handleSync = (yearMonth: string) => {
    if (!fioToken) {
      setShowSettings(true)
      return
    }

    const folderForMonth = getMonthFolder(yearMonth)
    const prevMonth = getPrevMonth(yearMonth)
    const prevMonthFolder = getMonthFolder(prevMonth)

    startSync({
      yearMonth,
      fioToken,
      gdriveFolderId: folderForMonth?.id,
      prevMonthGdriveFolderId: prevMonthFolder?.id,
      onComplete: () => {
        refetchMonths()
        setLocation(`/month/${yearMonth}`)
      },
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
            <CardDescription>Configure your Fio Bank API token</CardDescription>
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
            <Button onClick={handleSaveSettings}>Save Settings</Button>
          </CardContent>
        </Card>
      )}

      {/* Quick Sync */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Sync Month</CardTitle>
          <CardDescription>
            {hasToken ? "Select a month and invoice folder to sync" : "Configure your Fio token in settings first"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
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
            <div className="space-y-2">
              <Label>Invoice Folder for {formatYearMonth(selectedMonth)}</Label>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1 justify-start"
                  onClick={() => setShowFolderPicker(true)}
                >
                  <FolderOpen className="h-4 w-4 mr-2" />
                  {selectedFolder ? selectedFolder.name : "Select folder..."}
                </Button>
                {selectedFolder && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setSelectedFolder(null)
                      setMonthFolder(selectedMonth, "", "")
                    }}
                  >
                    Clear
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {selectedFolder ? `Folder: ${selectedFolder.name}` : "No folder - will skip invoice matching"}
                {" | "}
                Prev month ({formatYearMonth(getPrevMonth(selectedMonth))}): {getMonthFolder(getPrevMonth(selectedMonth))?.name || "not set"}
              </p>
            </div>
          </div>
          <div className="flex justify-end">
            <Button
              onClick={() => handleSync(selectedMonth)}
              disabled={!hasToken}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Sync {formatYearMonth(selectedMonth)}
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
                      {m.matched_count > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          title="Download matched invoices"
                          onClick={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                            window.open(`/api/months/${m.year_month}/download-invoices`, "_blank")
                          }}
                        >
                          <Download className="h-4 w-4" />
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
        onSelect={handleFolderSelect}
        title={`Select Folder for ${formatYearMonth(selectedMonth)}`}
        description="Choose the Google Drive folder containing invoices for this month"
      />
    </div>
  )
}
