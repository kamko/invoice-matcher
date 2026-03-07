import { useState, useEffect, useCallback } from 'react'
import { useSettings, useSetSetting, useGDriveStatus, useGDriveAuthUrl, useGDriveFolders, useAppConfig, showSuccess, showApiError } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../components/ui/dialog'
import { Loader2, Save, Eye, EyeOff, Cloud, CloudOff, LogOut, FolderOpen, ChevronRight, ArrowLeft } from 'lucide-react'

const FIO_TOKEN_KEY = 'fio_token'

export function SettingsPage() {
  const { data: settings, isLoading, refetch } = useSettings()
  const setSetting = useSetSetting()
  const { data: gdriveStatus, refetch: refetchGDrive } = useGDriveStatus()
  const getAuthUrl = useGDriveAuthUrl()
  const { data: appConfig } = useAppConfig()

  const [fioToken, setFioToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [invoiceFolder, setInvoiceFolder] = useState('')
  const [invoiceFolderName, setInvoiceFolderName] = useState('')
  const [initialized, setInitialized] = useState(false)
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [currentFolderId, setCurrentFolderId] = useState('root')
  const [folderPath, setFolderPath] = useState<Array<{ id: string; name: string }>>([{ id: 'root', name: 'My Drive' }])

  const { data: foldersData, isLoading: foldersLoading } = useGDriveFolders(
    showFolderPicker ? currentFolderId : ''
  )

  // Listen for GDrive OAuth callback
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'gdrive-connected') {
        refetchGDrive()
        showSuccess('Google Drive connected successfully')
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [refetchGDrive])

  const handleConnectGDrive = useCallback(async () => {
    try {
      const { auth_url } = await getAuthUrl.mutateAsync()
      // Open OAuth popup
      const width = 600
      const height = 700
      const left = window.screenX + (window.outerWidth - width) / 2
      const top = window.screenY + (window.outerHeight - height) / 2
      window.open(
        auth_url,
        'gdrive-oauth',
        `width=${width},height=${height},left=${left},top=${top}`
      )
    } catch (error) {
      showApiError(error, 'Connect to Google Drive')
    }
  }, [getAuthUrl])

  const handleDisconnectGDrive = useCallback(async () => {
    try {
      await fetch('/api/gdrive/disconnect', { method: 'POST' })
      refetchGDrive()
      showSuccess('Disconnected from Google Drive')
    } catch (error) {
      showApiError(error, 'Disconnect from Google Drive')
    }
  }, [refetchGDrive])

  // Initialize form values from localStorage and settings
  useEffect(() => {
    if (!initialized) {
      // Load Fio token from localStorage first (backward compatibility)
      const storedToken = localStorage.getItem(FIO_TOKEN_KEY)
      if (storedToken) {
        setFioToken(storedToken)
      }

      if (settings) {
        setInvoiceFolder(settings.invoice_parent_folder_id || '')
        setInvoiceFolderName(settings.invoice_parent_folder_name || '')
      }

      setInitialized(true)
    }
  }, [settings, initialized])

  const handleSaveFioToken = () => {
    localStorage.setItem(FIO_TOKEN_KEY, fioToken)
    showSuccess('Fio token saved to browser storage')
  }

  const handleSaveInvoiceFolder = async () => {
    try {
      await setSetting.mutateAsync({ key: 'invoice_parent_folder_id', value: invoiceFolder })
      if (invoiceFolderName) {
        await setSetting.mutateAsync({ key: 'invoice_parent_folder_name', value: invoiceFolderName })
      }
      showSuccess('Invoice folder saved')
      refetch()
    } catch (error) {
      showApiError(error, 'Save invoice folder')
    }
  }

  const openFolderPicker = () => {
    setCurrentFolderId('root')
    setFolderPath([{ id: 'root', name: 'My Drive' }])
    setShowFolderPicker(true)
  }

  const navigateToFolder = (folderId: string, folderName: string) => {
    setCurrentFolderId(folderId)
    setFolderPath([...folderPath, { id: folderId, name: folderName }])
  }

  const navigateBack = () => {
    if (folderPath.length > 1) {
      const newPath = folderPath.slice(0, -1)
      setFolderPath(newPath)
      setCurrentFolderId(newPath[newPath.length - 1].id)
    }
  }

  const selectFolder = (folderId: string, folderName: string) => {
    setInvoiceFolder(folderId)
    setInvoiceFolderName(folderName)
    setShowFolderPicker(false)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground">
          Configure API tokens and integrations
        </p>
      </div>

      <div className="grid gap-6">
        {/* Fio Bank Settings */}
        <Card>
          <CardHeader>
            <CardTitle>Fio Bank API</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>API Token</Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    type={showToken ? 'text' : 'password'}
                    value={fioToken}
                    onChange={(e) => setFioToken(e.target.value)}
                    placeholder="Enter your Fio API token"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-2 top-1/2 -translate-y-1/2 h-7 w-7"
                    onClick={() => setShowToken(!showToken)}
                  >
                    {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
                <Button onClick={handleSaveFioToken} disabled={setSetting.isPending}>
                  <Save className="h-4 w-4 mr-2" />
                  Save
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Get your token from Fio Internetbanking &gt; Settings &gt; API
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Google Drive Settings */}
        <Card>
          <CardHeader>
            <CardTitle>Google Drive</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Connection Status */}
            <div className="space-y-2">
              <Label>Connection Status</Label>
              <div className="flex items-center gap-3">
                {gdriveStatus?.available ? (
                  gdriveStatus.authenticated ? (
                    <>
                      <div className="flex items-center gap-2 text-green-600">
                        <Cloud className="h-5 w-5" />
                        <span className="font-medium">Connected</span>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleDisconnectGDrive}
                      >
                        <LogOut className="h-4 w-4 mr-2" />
                        Disconnect
                      </Button>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <CloudOff className="h-5 w-5" />
                        <span>Not connected</span>
                      </div>
                      <Button
                        onClick={handleConnectGDrive}
                        disabled={getAuthUrl.isPending}
                      >
                        <Cloud className="h-4 w-4 mr-2" />
                        Connect Google Drive
                      </Button>
                    </>
                  )
                ) : (
                  <div className="text-muted-foreground text-sm">
                    Google Drive integration not configured on server
                  </div>
                )}
              </div>
            </div>

            <div className="border-t pt-4 space-y-2">
              <Label>Invoice Parent Folder</Label>
              <div className="flex gap-2">
                <Input
                  value={invoiceFolderName || invoiceFolder}
                  readOnly
                  placeholder="Select a folder..."
                  className="flex-1"
                />
                {gdriveStatus?.authenticated && (
                  <Button variant="outline" onClick={openFolderPicker}>
                    <FolderOpen className="h-4 w-4 mr-2" />
                    Browse
                  </Button>
                )}
                <Button onClick={handleSaveInvoiceFolder} disabled={setSetting.isPending || !invoiceFolder}>
                  <Save className="h-4 w-4 mr-2" />
                  Save
                </Button>
              </div>
              {invoiceFolder && (
                <p className="text-xs text-muted-foreground">ID: {invoiceFolder}</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* LLM Settings */}
        <Card>
          <CardHeader>
            <CardTitle>LLM (Invoice Parsing)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Current Model</Label>
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm bg-muted px-2 py-1 rounded">
                  {appConfig?.llm_model || 'Not configured'}
                </span>
                {appConfig?.llm_enabled ? (
                  <span className="text-green-600 text-sm">Enabled</span>
                ) : (
                  <span className="text-muted-foreground text-sm">Disabled (no API key)</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env to configure
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Current Settings */}
        <Card>
          <CardHeader>
            <CardTitle>Current Settings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              {settings && Object.entries(settings).map(([key, value]) => (
                <div key={key} className="flex justify-between py-1 border-b last:border-0">
                  <span className="font-medium">{key}</span>
                  <span className="text-muted-foreground truncate max-w-xs">
                    {key.includes('token') ? '***hidden***' : (value || '-')}
                  </span>
                </div>
              ))}
              {(!settings || Object.keys(settings).length === 0) && (
                <p className="text-muted-foreground">No settings configured</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Folder Picker Modal */}
      <Dialog open={showFolderPicker} onOpenChange={setShowFolderPicker}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Select Invoice Folder</DialogTitle>
          </DialogHeader>

          {/* Breadcrumb */}
          <div className="flex items-center gap-1 text-sm text-muted-foreground overflow-x-auto pb-2">
            {folderPath.map((folder, index) => (
              <span key={folder.id} className="flex items-center">
                {index > 0 && <ChevronRight className="h-4 w-4 mx-1" />}
                <button
                  className="hover:text-foreground hover:underline"
                  onClick={() => {
                    const newPath = folderPath.slice(0, index + 1)
                    setFolderPath(newPath)
                    setCurrentFolderId(folder.id)
                  }}
                >
                  {folder.name}
                </button>
              </span>
            ))}
          </div>

          {/* Folder List */}
          <div className="border rounded-lg max-h-64 overflow-y-auto">
            {folderPath.length > 1 && (
              <button
                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted text-left border-b"
                onClick={navigateBack}
              >
                <ArrowLeft className="h-4 w-4" />
                <span>..</span>
              </button>
            )}

            {foldersLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : foldersData?.folders.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                No subfolders
              </div>
            ) : (
              foldersData?.folders.map((folder) => (
                <div
                  key={folder.id}
                  className="flex items-center justify-between px-3 py-2 hover:bg-muted border-b last:border-0"
                >
                  <button
                    className="flex items-center gap-2 flex-1 text-left"
                    onClick={() => navigateToFolder(folder.id, folder.name)}
                  >
                    <FolderOpen className="h-4 w-4 text-amber-500" />
                    <span>{folder.name}</span>
                  </button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => selectFolder(folder.id, folder.name)}
                  >
                    Select
                  </Button>
                </div>
              ))
            )}
          </div>

          <DialogFooter>
            {currentFolderId !== 'root' && (
              <Button
                variant="default"
                onClick={() => selectFolder(currentFolderId, folderPath[folderPath.length - 1].name)}
              >
                Select Current Folder
              </Button>
            )}
            <Button variant="outline" onClick={() => setShowFolderPicker(false)}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
