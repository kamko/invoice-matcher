import { useState, useEffect, useCallback } from 'react'
import { authFetch, useSettings, useSetSetting, useGDriveStatus, useGDriveFolders, useGDriveFolderInfo, useAppConfig, useImportGDrive, useImportSubfolders, useFioVault, useSaveFioVault, useDeleteFioVault, useMailjetSenderStatus, useVehicles, useCreateVehicle, useUpdateVehicle, showSuccess, showApiError } from '../api/client'
import type { Vehicle } from '../api/client'
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
import { Loader2, Save, Eye, EyeOff, Cloud, CloudOff, FolderOpen, ChevronRight, ArrowLeft, Search, Download, Check, Mail, Car, Pencil } from 'lucide-react'
import { clearLegacyFioToken, clearRememberedVaultPassword, encryptSecret, getLegacyFioToken, hasPersistentVaultPassword, rememberVaultPassword } from '../lib/crypto'

const DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE = `Posielam doklady za obdobie {period}.

{comments}`
const DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE = '{company_name} - Doklady za obdobie {period}'
const DEFAULT_MAILJET_SENDER_NAME = 'Invoice Matcher'

export function SettingsPage() {
  const auth = useAuth()
  const { data: settings, isLoading, refetch } = useSettings()
  const setSetting = useSetSetting()
  const { data: gdriveStatus, refetch: refetchGDrive } = useGDriveStatus()
  const { data: fioVault, isLoading: fioVaultLoading } = useFioVault()
  const saveFioVault = useSaveFioVault()
  const deleteFioVault = useDeleteFioVault()
  const { data: appConfig } = useAppConfig()
  const { data: vehicles = [], isLoading: vehiclesLoading } = useVehicles(false)
  const createVehicle = useCreateVehicle()
  const updateVehicle = useUpdateVehicle()
  const savedMailjetSenderEmail = settings?.mailjet_sender_email || ''
  const { data: mailjetSenderStatus, isLoading: mailjetSenderStatusLoading, isError: mailjetSenderStatusError } = useMailjetSenderStatus(
    savedMailjetSenderEmail,
    Boolean(appConfig?.mailjet_enabled)
  )
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
  const [companyName, setCompanyName] = useState('')
  const [accountantEmail, setAccountantEmail] = useState('')
  const [mailjetSenderName, setMailjetSenderName] = useState(DEFAULT_MAILJET_SENDER_NAME)
  const [mailjetSenderEmail, setMailjetSenderEmail] = useState('')
  const [accountantEmailSubjectTemplate, setAccountantEmailSubjectTemplate] = useState(DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE)
  const [accountantEmailTemplate, setAccountantEmailTemplate] = useState(DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE)
  const [initialized, setInitialized] = useState(false)
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [folderPickerTarget, setFolderPickerTarget] = useState<'invoice' | 'accountant'>('invoice')
  const [currentFolderId, setCurrentFolderId] = useState('root')
  const [folderPath, setFolderPath] = useState<Array<{ id: string; name: string }>>([{ id: 'root', name: 'My Drive' }])
  const [folderSearch, setFolderSearch] = useState('')
  const [newVehicleName, setNewVehicleName] = useState('')
  const [newVehicleRegistration, setNewVehicleRegistration] = useState('')
  const [editingVehicleId, setEditingVehicleId] = useState<number | null>(null)
  const [editingVehicleName, setEditingVehicleName] = useState('')
  const [editingVehicleRegistration, setEditingVehicleRegistration] = useState('')

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
    if (initialized || isLoading || fioVaultLoading || !settings) {
      return
    }

    const legacyToken = getLegacyFioToken()
    if (legacyToken && !fioVault?.configured) {
      setFioToken(legacyToken)
      setHasLegacyToken(true)
    }

    setInvoiceFolder(settings.invoice_parent_folder_id || '')
    setInvoiceFolderName(settings.invoice_parent_folder_name || '')
    setAccountantFolder(settings.accountant_folder_id || '')
    setAccountantFolderName(settings.accountant_folder_name || '')
    setCompanyName(settings.company_name || '')
    setAccountantEmail(settings.accountant_email || '')
    setMailjetSenderName(settings.mailjet_sender_name || DEFAULT_MAILJET_SENDER_NAME)
    setMailjetSenderEmail(settings.mailjet_sender_email || '')
    setAccountantEmailSubjectTemplate(settings.accountant_email_subject_template || DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE)
    setAccountantEmailTemplate(settings.accountant_email_template || DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE)
    setInitialized(true)
  }, [settings, fioVault, fioVaultLoading, initialized, isLoading])

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
      rememberVaultPassword(vaultPassword, persistVaultPassword, payload)
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

  const handleSaveAccountantEmail = async () => {
    const recipient = accountantEmail.trim()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient)) {
      showApiError(new Error('Enter a valid email address'), 'Save accountant email')
      return
    }

    try {
      await setSetting.mutateAsync({ key: 'accountant_email', value: recipient })
      setAccountantEmail(recipient)
      showSuccess('Accountant email saved')
      refetch()
    } catch (error) {
      showApiError(error, 'Save accountant email')
    }
  }

  const handleSaveCompanyName = async () => {
    const normalizedCompanyName = companyName.trim()
    if (!normalizedCompanyName) {
      showApiError(new Error('Enter a company name'), 'Save company name')
      return
    }

    try {
      await setSetting.mutateAsync({ key: 'company_name', value: normalizedCompanyName })
      setCompanyName(normalizedCompanyName)
      showSuccess('Company name saved')
      refetch()
    } catch (error) {
      showApiError(error, 'Save company name')
    }
  }

  const handleSaveMailjetSender = async () => {
    const senderName = mailjetSenderName.trim()
    const senderEmail = mailjetSenderEmail.trim()
    if (!senderName) {
      showApiError(new Error('Enter a sender name'), 'Save Mailjet sender')
      return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(senderEmail)) {
      showApiError(new Error('Enter a valid sender email address'), 'Save Mailjet sender')
      return
    }

    try {
      await setSetting.mutateAsync({ key: 'mailjet_sender_name', value: senderName })
      await setSetting.mutateAsync({ key: 'mailjet_sender_email', value: senderEmail })
      setMailjetSenderName(senderName)
      setMailjetSenderEmail(senderEmail)
      showSuccess('Mailjet sender saved')
      refetch()
    } catch (error) {
      showApiError(error, 'Save Mailjet sender')
    }
  }

  const handleSaveAccountantEmailSubjectTemplate = async () => {
    const template = accountantEmailSubjectTemplate.trim()
    if (!template.includes('{company_name}') || !template.includes('{period}')) {
      showApiError(
        new Error('Subject template must contain {company_name} and {period}'),
        'Save subject template'
      )
      return
    }

    try {
      await setSetting.mutateAsync({ key: 'accountant_email_subject_template', value: template })
      setAccountantEmailSubjectTemplate(template)
      showSuccess('Subject template saved')
      refetch()
    } catch (error) {
      showApiError(error, 'Save subject template')
    }
  }

  const handleSaveAccountantEmailTemplate = async () => {
    const template = accountantEmailTemplate.trim()
    if (!template) {
      showApiError(new Error('Email template cannot be empty'), 'Save email template')
      return
    }

    try {
      await setSetting.mutateAsync({ key: 'accountant_email_template', value: template })
      setAccountantEmailTemplate(template)
      showSuccess('Summary email template saved')
      refetch()
    } catch (error) {
      showApiError(error, 'Save email template')
    }
  }

  const normalizeRegistration = (value: string) => value.replace(/[\s-]/g, '').toUpperCase()

  const validateVehicle = (name: string, registration: string) => {
    if (!name.trim()) {
      throw new Error('Enter a vehicle name')
    }
    if (!/^[A-Z]{2}\d{3}[A-Z]{2}$/.test(normalizeRegistration(registration))) {
      throw new Error('Use the registration format KE885HH')
    }
  }

  const handleCreateVehicle = async () => {
    try {
      validateVehicle(newVehicleName, newVehicleRegistration)
      await createVehicle.mutateAsync({
        name: newVehicleName.trim(),
        registration: normalizeRegistration(newVehicleRegistration),
      })
      setNewVehicleName('')
      setNewVehicleRegistration('')
      showSuccess('Vehicle added')
    } catch (error) {
      showApiError(error, 'Add vehicle')
    }
  }

  const startEditingVehicle = (vehicle: Vehicle) => {
    setEditingVehicleId(vehicle.id)
    setEditingVehicleName(vehicle.name)
    setEditingVehicleRegistration(vehicle.registration)
  }

  const handleUpdateVehicle = async () => {
    if (!editingVehicleId) return
    try {
      validateVehicle(editingVehicleName, editingVehicleRegistration)
      await updateVehicle.mutateAsync({
        vehicleId: editingVehicleId,
        name: editingVehicleName.trim(),
        registration: normalizeRegistration(editingVehicleRegistration),
      })
      setEditingVehicleId(null)
      showSuccess('Vehicle updated')
    } catch (error) {
      showApiError(error, 'Update vehicle')
    }
  }

  const handleToggleVehicle = async (vehicle: Vehicle) => {
    try {
      await updateVehicle.mutateAsync({
        vehicleId: vehicle.id,
        is_active: !vehicle.is_active,
      })
      showSuccess(vehicle.is_active ? 'Vehicle deactivated' : 'Vehicle activated')
    } catch (error) {
      showApiError(error, vehicle.is_active ? 'Deactivate vehicle' : 'Activate vehicle')
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
            <div className="flex flex-col gap-1 rounded-lg border px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
              <span className="text-muted-foreground">Encrypted vault status</span>
              <span className={fioVault?.configured ? 'text-green-600 font-medium' : 'text-muted-foreground'}>
                {fioVault?.configured ? 'Configured' : 'Not configured'}
              </span>
            </div>
            <div className="space-y-2">
              <Label>API Token</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
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
                <Button className="w-full sm:w-auto" onClick={handleSaveFioToken} disabled={saveFioVault.isPending}>
                  <Save className="h-4 w-4 mr-2" />
                  {fioVault?.configured ? 'Update' : 'Save'}
                </Button>
                {fioVault?.configured && (
                  <Button className="w-full sm:w-auto" variant="outline" onClick={handleDeleteFioToken} disabled={deleteFioVault.isPending}>
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
              <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
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
              <div className="flex flex-col gap-2 sm:flex-row">
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
                <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-col sm:gap-1">
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
                    className="w-full sm:w-auto"
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
              <div className="flex flex-col gap-2 sm:flex-row">
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
                <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-col sm:gap-1">
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

              <div className="pt-3 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">Summary Email</span>
                  <span className={appConfig?.mailjet_enabled ? 'text-xs font-medium text-green-700' : 'text-xs font-medium text-orange-700'}>
                    {appConfig?.mailjet_enabled ? 'Mailjet API ready' : 'Mailjet API not configured'}
                  </span>
                </div>

                <Label htmlFor="company-name">Company Name</Label>
                <div className="flex gap-2">
                  <Input
                    id="company-name"
                    value={companyName}
                    onChange={(event) => setCompanyName(event.target.value)}
                    maxLength={255}
                    placeholder="Your organization"
                  />
                  <Button
                    size="sm"
                    onClick={handleSaveCompanyName}
                    disabled={setSetting.isPending || !companyName.trim()}
                  >
                    <Save className="h-4 w-4 mr-1" />
                    Save
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Used wherever the subject template contains <code>{'{company_name}'}</code>.
                </p>

                <Label htmlFor="accountant-email-subject-template">Subject Template</Label>
                <div className="flex gap-2">
                  <Input
                    id="accountant-email-subject-template"
                    value={accountantEmailSubjectTemplate}
                    onChange={(event) => setAccountantEmailSubjectTemplate(event.target.value)}
                    maxLength={255}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleSaveAccountantEmailSubjectTemplate}
                    disabled={setSetting.isPending || !accountantEmailSubjectTemplate.trim()}
                  >
                    Save Subject
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Required tokens: <code>{'{company_name}'}</code> and <code>{'{period}'}</code>.
                </p>

                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="mailjet-sender-name">Sender Name</Label>
                    <Input
                      id="mailjet-sender-name"
                      value={mailjetSenderName}
                      onChange={(event) => setMailjetSenderName(event.target.value)}
                      maxLength={255}
                      placeholder="Invoice Matcher"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="mailjet-sender-email">Sender Email</Label>
                    <Input
                      id="mailjet-sender-email"
                      type="email"
                      value={mailjetSenderEmail}
                      onChange={(event) => setMailjetSenderEmail(event.target.value)}
                      placeholder="invoices@example.com"
                    />
                  </div>
                </div>
                <div className="flex items-start justify-between gap-4">
                  <div className="text-xs">
                    {mailjetSenderEmail.trim() !== savedMailjetSenderEmail ? (
                      <span className="text-muted-foreground">Save the sender to check it in Mailjet.</span>
                    ) : mailjetSenderStatusLoading ? (
                      <span className="text-muted-foreground">Checking sender in Mailjet...</span>
                    ) : mailjetSenderStatusError ? (
                      <span className="font-medium text-orange-700">Could not check the sender with Mailjet.</span>
                    ) : mailjetSenderStatus?.active ? (
                      <span className="font-medium text-green-700">
                        {mailjetSenderStatus.scope === 'domain' ? 'Verified domain' : 'Verified address'}
                        {mailjetSenderStatus.matched_sender ? ` (${mailjetSenderStatus.matched_sender})` : ''}
                      </span>
                    ) : savedMailjetSenderEmail && appConfig?.mailjet_enabled ? (
                      <span className="font-medium text-orange-700">Address or domain is not active in Mailjet.</span>
                    ) : (
                      <span className="text-muted-foreground">An active sender address or domain is required.</span>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleSaveMailjetSender}
                    disabled={setSetting.isPending || !mailjetSenderName.trim() || !mailjetSenderEmail.trim()}
                  >
                    Save Sender
                  </Button>
                </div>

                <Label htmlFor="accountant-email">Accountant Email</Label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="accountant-email"
                      type="email"
                      value={accountantEmail}
                      onChange={(event) => setAccountantEmail(event.target.value)}
                      placeholder="accountant@example.com"
                      className="pl-9"
                    />
                  </div>
                  <Button
                    size="sm"
                    onClick={handleSaveAccountantEmail}
                    disabled={setSetting.isPending || !accountantEmail.trim()}
                  >
                    <Save className="h-4 w-4 mr-1" />
                    Save
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  After a Drive export, the app sends a short period summary and any document comments to this address.
                </p>

                <div className="pt-2 space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <Label htmlFor="accountant-email-template">Message Template</Label>
                    <span className="text-xs text-muted-foreground">{accountantEmailTemplate.length}/1000</span>
                  </div>
                  <textarea
                    id="accountant-email-template"
                    value={accountantEmailTemplate}
                    onChange={(event) => setAccountantEmailTemplate(event.target.value)}
                    maxLength={1000}
                    rows={5}
                    className="flex w-full resize-y rounded-md border border-input bg-background px-3 py-2 font-mono text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                  <div className="flex items-start justify-between gap-4">
                    <p className="text-xs text-muted-foreground">
                      Available tokens: <code>{'{company_name}'}</code>, <code>{'{period}'}</code>, and <code>{'{comments}'}</code>.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleSaveAccountantEmailTemplate}
                      disabled={setSetting.isPending || !accountantEmailTemplate.trim()}
                    >
                      Save Template
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Vehicles */}
        <Card>
          <CardHeader>
            <CardTitle>Vehicles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,12rem)_auto] sm:items-end">
              <div className="space-y-2">
                <Label htmlFor="new-vehicle-name">Vehicle name</Label>
                <Input
                  id="new-vehicle-name"
                  value={newVehicleName}
                  onChange={(event) => setNewVehicleName(event.target.value)}
                  placeholder="e.g. Toyota Corolla"
                  maxLength={100}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-vehicle-registration">Registration (ŠPZ)</Label>
                <Input
                  id="new-vehicle-registration"
                  value={newVehicleRegistration}
                  onChange={(event) => setNewVehicleRegistration(event.target.value.toUpperCase())}
                  placeholder="KE885HH"
                  maxLength={9}
                  autoComplete="off"
                />
              </div>
              <Button
                onClick={handleCreateVehicle}
                disabled={createVehicle.isPending || !newVehicleName.trim() || !newVehicleRegistration.trim()}
              >
                <Car className="mr-1 h-4 w-4" />
                Add vehicle
              </Button>
            </div>

            <p className="text-xs text-muted-foreground">
              Active vehicles appear in the expense upload dropdown. Existing PDFs keep their stored registration.
            </p>

            {vehiclesLoading ? (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading vehicles...
              </div>
            ) : vehicles.length === 0 ? (
              <div className="rounded-md border border-dashed px-4 py-6 text-center">
                <Car className="mx-auto mb-2 h-5 w-5 text-muted-foreground" />
                <p className="text-sm font-medium">No vehicles configured</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Add your first vehicle to classify fuel and other car expenses.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-md border">
                {vehicles.map((vehicle) => (
                  <div key={vehicle.id} className="border-b p-3 last:border-b-0">
                    {editingVehicleId === vehicle.id ? (
                      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,12rem)_auto] sm:items-end">
                        <div className="space-y-2">
                          <Label htmlFor={`vehicle-name-${vehicle.id}`}>Vehicle name</Label>
                          <Input
                            id={`vehicle-name-${vehicle.id}`}
                            value={editingVehicleName}
                            onChange={(event) => setEditingVehicleName(event.target.value)}
                            maxLength={100}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor={`vehicle-registration-${vehicle.id}`}>Registration</Label>
                          <Input
                            id={`vehicle-registration-${vehicle.id}`}
                            value={editingVehicleRegistration}
                            onChange={(event) => setEditingVehicleRegistration(event.target.value.toUpperCase())}
                            maxLength={9}
                          />
                        </div>
                        <div className="flex gap-2">
                          <Button size="sm" onClick={handleUpdateVehicle} disabled={updateVehicle.isPending}>
                            Save
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setEditingVehicleId(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{vehicle.name}</span>
                            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{vehicle.registration}</code>
                            {!vehicle.is_active && <span className="text-xs text-muted-foreground">Inactive</span>}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => startEditingVehicle(vehicle)}>
                            <Pencil className="mr-1 h-3.5 w-3.5" /> Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleToggleVehicle(vehicle)}
                            disabled={updateVehicle.isPending}
                          >
                            {vehicle.is_active ? 'Deactivate' : 'Activate'}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
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
                <div key={key} className="flex flex-col gap-1 border-b py-1 last:border-0 sm:flex-row sm:justify-between">
                  <span className="break-all font-medium">{key}</span>
                  <span className="break-all text-muted-foreground sm:max-w-xs sm:truncate">
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
