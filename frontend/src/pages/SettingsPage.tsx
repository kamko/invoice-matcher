import { useState, useEffect, useCallback } from 'react'
import { authFetch, useSettings, useSetSetting, useGDriveStatus, useGDriveFolders, useGDriveFolderInfo, useAppConfig, useImportGDrive, useImportSubfolders, useFioVault, useSaveFioVault, useDeleteFioVault, showSuccess, showApiError } from '../api/client'
import { useAuth } from '../auth'
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
import { Checkbox } from '../components/ui/checkbox'
import { Loader2, Save, Eye, EyeOff, Cloud, CloudOff, FolderOpen, ChevronRight, ArrowLeft, Search, Download, Check } from 'lucide-react'
import { clearLegacyFioToken, clearRememberedVaultPassword, encryptSecret, getLegacyFioToken, hasPersistentVaultPassword, rememberVaultPassword } from '../lib/crypto'

export function SettingsPage() {
  const auth = useAuth()
  const { data: settings, isLoading, refetch } = useSettings()
  const setSetting = useSetSetting()
  const { data: gdriveStatus, refetch: refetchGDrive } = useGDriveStatus()
  const { data: fioVault } = useFioVault()
  const saveFioVault = useSaveFioVault()
  const deleteFioVault = useDeleteFioVault()
  const { data: appConfig } = useAppConfig()
  const importGDrive = useImportGDrive()
  const getFolderInfo = useGDriveFolderInfo()
  const [isImporting, setIsImporting] = useState(false)
  const [showImportWizard, setShowImportWizard] = useState(false)
  const [selectedImportFolders, setSelectedImportFolders] = useState<string[]>([])
  const [importProgress, setImportProgress] = useState<{ current: number; total: number; results: Array<{ folder: string; imported: number; skipped: number }> } | null>(null)

  const [fioToken, setFioToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [vaultPassword, setVaultPassword] = useState('')
  const [showVaultPassword, setShowVaultPassword] = useState(false)
  const [persistVaultPassword, setPersistVaultPassword] = useState(hasPersistentVaultPassword())
  const [hasLegacyToken, setHasLegacyToken] = useState(false)
  const [invoiceFolder, setInvoiceFolder] = useState('')
  const [invoiceFolderName, setInvoiceFolderName] = useState('')
  const [accountantFolder, setAccountantFolder] = useState('')
  const [accountantFolderName, setAccountantFolderName] = useState('')
  const [initialized, setInitialized] = useState(false)
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [folderPickerTarget, setFolderPickerTarget] = useState<'invoice' | 'accountant'>('invoice')
  const [currentFolderId, setCurrentFolderId] = useState('root')
  const [folderPath, setFolderPath] = useState<Array<{ id: string; name: string }>>([{ id: 'root', name: 'My Drive' }])
  const [folderSearch, setFolderSearch] = useState('')

  const { data: foldersData, isLoading: foldersLoading } = useGDriveFolders(
    showFolderPicker ? currentFolderId : '',
    {
      search: folderSearch || undefined,
      showAll: !!folderSearch,
    }
  )

  // Fetch subfolders when import wizard is open
  const { data: importSubfolders, isLoading: subfoldersLoading } = useImportSubfolders(
    showImportWizard ? invoiceFolder : ''
  )

  // Refresh Drive state when the combined Google sign-in flow completes
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'auth-complete') {
        refetchGDrive()
        showSuccess('Google access refreshed successfully')
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [refetchGDrive])

  const handleDisconnectGDrive = useCallback(async () => {
    try {
      const response = await authFetch('/gdrive/disconnect', { method: 'POST' })
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(error.detail || `HTTP ${response.status}`)
      }
      refetchGDrive()
      showSuccess('Disconnected from Google Drive')
    } catch (error) {
      showApiError(error, 'Disconnect from Google Drive')
    }
  }, [refetchGDrive])

  // Initialize form values from localStorage and settings
  useEffect(() => {
    if (!initialized) {
      const legacyToken = getLegacyFioToken()
      if (legacyToken && !fioVault?.configured) {
        setFioToken(legacyToken)
        setHasLegacyToken(true)
      }

      if (settings) {
        setInvoiceFolder(settings.invoice_parent_folder_id || '')
        setInvoiceFolderName(settings.invoice_parent_folder_name || '')
        setAccountantFolder(settings.accountant_folder_id || '')
        setAccountantFolderName(settings.accountant_folder_name || '')
      }

      setInitialized(true)
    }
  }, [settings, fioVault, initialized])

  const handleSaveFioToken = async () => {
    if (!fioToken.trim()) {
      showApiError(new Error('Enter a Fio token first'), 'Save encrypted Fio token')
      return
    }

    if (!vaultPassword) {
      showApiError(new Error('Enter a vault password first'), 'Save encrypted Fio token')
      return
    }

    try {
      const payload = await encryptSecret(fioToken.trim(), vaultPassword)
      await saveFioVault.mutateAsync(payload)
      rememberVaultPassword(vaultPassword, persistVaultPassword)
      clearLegacyFioToken()
      setHasLegacyToken(false)
      setFioToken('')
      showSuccess('Encrypted Fio token saved')
    } catch (error) {
      showApiError(error, 'Save encrypted Fio token')
    }
  }

  const handleDeleteFioToken = async () => {
    try {
      await deleteFioVault.mutateAsync()
      clearLegacyFioToken()
      clearRememberedVaultPassword()
      setFioToken('')
      setVaultPassword('')
      setHasLegacyToken(false)
      showSuccess('Encrypted Fio token deleted')
    } catch (error) {
      showApiError(error, 'Delete encrypted Fio token')
    }
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

  const handleSaveAccountantFolder = async () => {
    try {
      await setSetting.mutateAsync({ key: 'accountant_folder_id', value: accountantFolder })
      if (accountantFolderName) {
        await setSetting.mutateAsync({ key: 'accountant_folder_name', value: accountantFolderName })
      }
      showSuccess('Accountant folder saved')
      refetch()
    } catch (error) {
      showApiError(error, 'Save accountant folder')
    }
  }

  const lookupFolderName = async (folderId: string, target: 'invoice' | 'accountant') => {
    if (!folderId || folderId.length < 10) return
    try {
      const info = await getFolderInfo.mutateAsync(folderId)
      if (target === 'invoice') {
        setInvoiceFolderName(info.name)
      } else {
        setAccountantFolderName(info.name)
      }
    } catch {
      // Folder not found or error - leave name empty
    }
  }

  const openFolderPicker = (target: 'invoice' | 'accountant') => {
    setFolderPickerTarget(target)
    setCurrentFolderId('root')
    setFolderPath([{ id: 'root', name: 'My Drive' }])
    setFolderSearch('')
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
    if (folderPickerTarget === 'invoice') {
      setInvoiceFolder(folderId)
      setInvoiceFolderName(folderName)
    } else {
      setAccountantFolder(folderId)
      setAccountantFolderName(folderName)
    }
    setShowFolderPicker(false)
  }

  const handleImportSelected = async () => {
    if (selectedImportFolders.length === 0) {
      showApiError(new Error('Select at least one folder'), 'Import')
      return
    }

    setIsImporting(true)
    setImportProgress({ current: 0, total: selectedImportFolders.length, results: [] })

    const results: Array<{ folder: string; imported: number; skipped: number }> = []

    for (let i = 0; i < selectedImportFolders.length; i++) {
      const folderId = selectedImportFolders[i]
      const folderName = importSubfolders?.folders.find(f => f.id === folderId)?.name || folderId

      setImportProgress(prev => prev ? { ...prev, current: i + 1 } : null)

      try {
        const result = await importGDrive.mutateAsync({ folder_id: folderId })
        results.push({ folder: folderName, imported: result.imported, skipped: result.skipped })
      } catch (error) {
        results.push({ folder: folderName, imported: 0, skipped: 0 })
      }
    }

    setImportProgress(prev => prev ? { ...prev, results } : null)
    setIsImporting(false)

    const totalImported = results.reduce((sum, r) => sum + r.imported, 0)
    showSuccess(`Imported ${totalImported} invoices from ${selectedImportFolders.length} folders`)
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
            <div className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
              <span className="text-muted-foreground">Encrypted vault status</span>
              <span className={fioVault?.configured ? 'text-green-600 font-medium' : 'text-muted-foreground'}>
                {fioVault?.configured ? 'Configured' : 'Not configured'}
              </span>
            </div>
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
                <Button onClick={handleSaveFioToken} disabled={saveFioVault.isPending}>
                  <Save className="h-4 w-4 mr-2" />
                  {fioVault?.configured ? 'Update' : 'Save'}
                </Button>
                {fioVault?.configured && (
                  <Button variant="outline" onClick={handleDeleteFioToken} disabled={deleteFioVault.isPending}>
                    Delete
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {hasLegacyToken
                  ? 'Legacy browser-stored token detected and ready to migrate into the encrypted vault.'
                  : 'The server stores only the encrypted token blob.'}
              </p>
              <p className="text-xs text-muted-foreground">
                Get your token from Fio Internetbanking &gt; Settings &gt; API
              </p>
            </div>

            <div className="space-y-2">
              <Label>Vault Password</Label>
              <div className="relative">
                <Input
                  type={showVaultPassword ? 'text' : 'password'}
                  value={vaultPassword}
                  onChange={(e) => setVaultPassword(e.target.value)}
                  placeholder="Used only in your browser to encrypt/decrypt the token"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-2 top-1/2 -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowVaultPassword(!showVaultPassword)}
                >
                  {showVaultPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={persistVaultPassword}
                  onCheckedChange={(checked) => setPersistVaultPassword(checked === true)}
                />
                <span>Remember password on this device (less secure)</span>
              </label>
              <p className="text-xs text-muted-foreground">
                If unchecked, the password is remembered only for the current browser tab.
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
                        <span className="font-medium">Connected through Google sign-in</span>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={auth.login}
                      >
                        <Cloud className="h-4 w-4 mr-2" />
                        Refresh Google Access
                      </Button>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <CloudOff className="h-5 w-5" />
                        <span>Google Drive access is missing</span>
                      </div>
                      <Button
                        onClick={auth.login}
                      >
                        <Cloud className="h-4 w-4 mr-2" />
                        Sign In Again
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleDisconnectGDrive}
                      >
                        Clear Stored Access
                      </Button>
                    </>
                  )
                ) : (
                  <div className="text-muted-foreground text-sm">
                    Google Drive integration not configured on server
                  </div>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                App access and Google Drive access are granted together in one Google sign-in flow.
              </p>
            </div>

            <div className="border-t pt-4 space-y-2">
              <Label>Invoice Parent Folder</Label>
              <div className="flex gap-2">
                <div className="flex-1 space-y-1">
                  <Input
                    value={invoiceFolderName || (invoiceFolder ? '(loading...)' : '')}
                    readOnly
                    placeholder="Folder name"
                    className={invoiceFolderName ? '' : 'text-muted-foreground'}
                  />
                  <Input
                    value={invoiceFolder}
                    onChange={(e) => {
                      setInvoiceFolder(e.target.value)
                      setInvoiceFolderName('')
                    }}
                    onBlur={() => lookupFolderName(invoiceFolder, 'invoice')}
                    placeholder="Paste folder ID..."
                    className="font-mono text-xs h-7"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  {gdriveStatus?.authenticated && (
                    <Button variant="outline" size="sm" onClick={() => openFolderPicker('invoice')}>
                      <FolderOpen className="h-4 w-4 mr-1" />
                      Browse
                    </Button>
                  )}
                  <Button size="sm" onClick={handleSaveInvoiceFolder} disabled={setSetting.isPending || !invoiceFolder}>
                    <Save className="h-4 w-4 mr-1" />
                    Save
                  </Button>
                </div>
              </div>
              {invoiceFolder && gdriveStatus?.authenticated && (
                <div className="pt-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSelectedImportFolders([])
                      setImportProgress(null)
                      setShowImportWizard(true)
                    }}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Import Existing Invoices from GDrive
                  </Button>
                  <p className="text-xs text-muted-foreground mt-1">
                    Select subfolders (YYYYMM) to import from
                  </p>
                </div>
              )}
            </div>

            {/* Accountant Export Root */}
            <div className="border-t pt-4 space-y-2">
              <Label>Accountant Shared Root Folder</Label>
              <div className="flex gap-2">
                <div className="flex-1 space-y-1">
                  <Input
                    value={accountantFolderName || (accountantFolder ? '(loading...)' : '')}
                    readOnly
                    placeholder="Folder name"
                    className={accountantFolderName ? '' : 'text-muted-foreground'}
                  />
                  <Input
                    value={accountantFolder}
                    onChange={(e) => {
                      setAccountantFolder(e.target.value)
                      setAccountantFolderName('')
                    }}
                    onBlur={() => lookupFolderName(accountantFolder, 'accountant')}
                    placeholder="Paste folder ID..."
                    className="font-mono text-xs h-7"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  {gdriveStatus?.authenticated && (
                    <Button variant="outline" size="sm" onClick={() => openFolderPicker('accountant')}>
                      <FolderOpen className="h-4 w-4 mr-1" />
                      Browse
                    </Button>
                  )}
                  <Button size="sm" onClick={handleSaveAccountantFolder} disabled={setSetting.isPending || !accountantFolder}>
                    <Save className="h-4 w-4 mr-1" />
                    Save
                  </Button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Shared root folder used for accountant offload. The app routes files into
                `POKLADNICNE_DOKLADY`, `DOSLE_FAKTURY`, or `OSTATNE`.
              </p>
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
            <DialogTitle>
              {folderPickerTarget === 'invoice' ? 'Select Invoice Folder' : 'Select Accountant Folder'}
            </DialogTitle>
          </DialogHeader>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={folderSearch}
              onChange={(e) => setFolderSearch(e.target.value)}
              placeholder="Search folders..."
              className="pl-8"
            />
          </div>

          {/* Breadcrumb - hidden during search */}
          {!folderSearch && (
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
          )}

          {/* Folder List */}
          <div className="border rounded-lg max-h-64 overflow-y-auto">
            {folderPath.length > 1 && !folderSearch && (
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
                {folderSearch ? 'No folders found' : 'No subfolders'}
              </div>
            ) : (
              foldersData?.folders.map((folder) => (
                <div
                  key={folder.id}
                  className="flex items-center justify-between px-3 py-2 hover:bg-muted border-b last:border-0"
                >
                  <button
                    className="flex items-center gap-2 flex-1 text-left"
                    onClick={() => {
                      if (folderSearch) {
                        // When clicking from search results, select directly
                        selectFolder(folder.id, folder.name)
                      } else {
                        navigateToFolder(folder.id, folder.name)
                      }
                    }}
                  >
                    <FolderOpen className={`h-4 w-4 ${folder.shared ? 'text-blue-500' : 'text-amber-500'}`} />
                    <span>{folder.name}</span>
                    {folder.shared && (
                      <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">shared</span>
                    )}
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
            {currentFolderId !== 'root' && !folderSearch && (
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

      {/* Import Wizard Modal */}
      <Dialog open={showImportWizard} onOpenChange={setShowImportWizard}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Import Invoices from GDrive</DialogTitle>
          </DialogHeader>

          {!importProgress ? (
            <>
              <p className="text-sm text-muted-foreground">
                Select the month folders (YYYYMM) to import:
              </p>

              <div className="border rounded-lg max-h-64 overflow-y-auto">
                {subfoldersLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin" />
                  </div>
                ) : !importSubfolders?.folders.length ? (
                  <div className="py-8 text-center text-muted-foreground">
                    No subfolders found
                  </div>
                ) : (
                  importSubfolders.folders
                    .sort((a, b) => b.name.localeCompare(a.name))
                    .map((folder) => (
                      <label
                        key={folder.id}
                        className="flex items-center gap-3 px-3 py-2 hover:bg-muted cursor-pointer border-b last:border-0"
                      >
                        <Checkbox
                          checked={selectedImportFolders.includes(folder.id)}
                          onCheckedChange={(checked) => {
                            if (checked) {
                              setSelectedImportFolders([...selectedImportFolders, folder.id])
                            } else {
                              setSelectedImportFolders(selectedImportFolders.filter(id => id !== folder.id))
                            }
                          }}
                        />
                        <FolderOpen className="h-4 w-4 text-amber-500" />
                        <span className="font-mono">{folder.name}</span>
                      </label>
                    ))
                )}
              </div>

              <div className="flex justify-between text-sm">
                <Button
                  variant="link"
                  size="sm"
                  className="p-0 h-auto"
                  onClick={() => setSelectedImportFolders(importSubfolders?.folders.map(f => f.id) || [])}
                >
                  Select All
                </Button>
                <span className="text-muted-foreground">
                  {selectedImportFolders.length} selected
                </span>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setShowImportWizard(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={handleImportSelected}
                  disabled={selectedImportFolders.length === 0 || isImporting}
                >
                  {isImporting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    <>
                      <Download className="h-4 w-4 mr-2" />
                      Import Selected
                    </>
                  )}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              {/* Progress view */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  {isImporting ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <Check className="h-5 w-5 text-green-600" />
                  )}
                  <span>
                    {isImporting
                      ? `Importing folder ${importProgress.current} of ${importProgress.total}...`
                      : 'Import complete!'}
                  </span>
                </div>

                {importProgress.results.length > 0 && (
                  <div className="border rounded-lg max-h-48 overflow-y-auto">
                    {importProgress.results.map((r, i) => (
                      <div key={i} className="flex justify-between px-3 py-2 border-b last:border-0 text-sm">
                        <span className="font-mono">{r.folder}</span>
                        <span className="text-muted-foreground">
                          {r.imported} imported, {r.skipped} skipped
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <DialogFooter>
                <Button onClick={() => setShowImportWizard(false)} disabled={isImporting}>
                  Close
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
