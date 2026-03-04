import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useGDriveStatus, useGDriveAuthUrl, useGDriveFolders } from "@/api/client"
import { Folder, ChevronRight, Loader2, ExternalLink, Check, Search, List } from "lucide-react"

interface FolderPickerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (folderId: string, folderName: string) => void
  title?: string
  description?: string
}

export function FolderPickerDialog({
  open,
  onOpenChange,
  onSelect,
  title = "Select Invoice Folder",
  description = "Choose the Google Drive folder containing invoices for this month",
}: FolderPickerDialogProps) {
  const queryClient = useQueryClient()
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useGDriveStatus()
  const getAuthUrl = useGDriveAuthUrl()
  const [currentParentId, setCurrentParentId] = React.useState("root")
  const [showAll, setShowAll] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState("")
  const [breadcrumbs, setBreadcrumbs] = React.useState<Array<{ id: string; name: string }>>([
    { id: "root", name: "My Drive" },
  ])

  // Reset state when dialog opens
  React.useEffect(() => {
    if (open) {
      setCurrentParentId("root")
      setShowAll(false)
      setSearchQuery("")
      setBreadcrumbs([{ id: "root", name: "My Drive" }])
    }
  }, [open])

  // Listen for message from OAuth popup
  React.useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === "gdrive-connected") {
        refetchStatus()
        queryClient.invalidateQueries({ queryKey: ["gdrive-folders"] })
      }
    }
    window.addEventListener("message", handleMessage)
    return () => window.removeEventListener("message", handleMessage)
  }, [refetchStatus, queryClient])

  const { data: foldersData, isLoading: foldersLoading } = useGDriveFolders(
    status?.authenticated && open ? currentParentId : "",
    showAll
  )

  const filteredFolders = React.useMemo(() => {
    if (!foldersData?.folders) return []
    if (!searchQuery.trim()) return foldersData.folders
    const query = searchQuery.toLowerCase()
    return foldersData.folders.filter((f) => f.name.toLowerCase().includes(query))
  }, [foldersData?.folders, searchQuery])

  const handleConnect = async () => {
    try {
      const result = await getAuthUrl.mutateAsync()
      window.open(result.auth_url, "_blank", "width=600,height=700")
    } catch (error) {
      console.error("Failed to get auth URL:", error)
    }
  }

  const handleFolderClick = (folderId: string, folderName: string) => {
    if (showAll) {
      setShowAll(false)
      setSearchQuery("")
    }
    setBreadcrumbs((prev) => [...prev, { id: folderId, name: folderName }])
    setCurrentParentId(folderId)
  }

  const handleBreadcrumbClick = (index: number) => {
    const newBreadcrumbs = breadcrumbs.slice(0, index + 1)
    setBreadcrumbs(newBreadcrumbs)
    setCurrentParentId(newBreadcrumbs[newBreadcrumbs.length - 1].id)
  }

  const handleSelectFolder = (folderId: string, folderName: string) => {
    onSelect(folderId, folderName)
    onOpenChange(false)
  }

  const toggleShowAll = () => {
    setShowAll(!showAll)
    setSearchQuery("")
    if (!showAll) {
      setBreadcrumbs([{ id: "root", name: "My Drive" }])
      setCurrentParentId("root")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {statusLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : !status?.available ? (
          <div className="text-center py-8 space-y-4">
            <div className="text-muted-foreground">
              <p>Google Drive integration is not configured.</p>
              <p className="text-sm mt-2">
                Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file.
              </p>
            </div>
          </div>
        ) : !status?.authenticated ? (
          <div className="text-center py-8 space-y-4">
            <Folder className="h-16 w-16 mx-auto text-muted-foreground" />
            <div>
              <h3 className="text-lg font-semibold">Connect Google Drive</h3>
              <p className="text-muted-foreground">
                Allow access to browse your invoice folders
              </p>
            </div>
            <Button onClick={handleConnect} disabled={getAuthUrl.isPending}>
              {getAuthUrl.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <ExternalLink className="h-4 w-4 mr-2" />
              )}
              Connect to Google Drive
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Mode toggle and search */}
            <div className="flex gap-2">
              <Button
                variant={showAll ? "default" : "outline"}
                size="sm"
                onClick={toggleShowAll}
              >
                <List className="h-4 w-4 mr-1" />
                {showAll ? "Showing All" : "Show All"}
              </Button>
              {showAll && (
                <div className="relative flex-1">
                  <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search folders..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-8"
                  />
                </div>
              )}
            </div>

            {/* Breadcrumbs */}
            {!showAll && (
              <div className="flex items-center gap-1 text-sm flex-wrap">
                {breadcrumbs.map((crumb, index) => (
                  <React.Fragment key={crumb.id}>
                    {index > 0 && <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                    <button
                      onClick={() => handleBreadcrumbClick(index)}
                      className="hover:text-primary hover:underline"
                    >
                      {crumb.name}
                    </button>
                  </React.Fragment>
                ))}
              </div>
            )}

            {/* Folder list */}
            <div className="border rounded-lg max-h-64 overflow-y-auto">
              {foldersLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : !filteredFolders.length ? (
                <div className="text-center py-8 text-muted-foreground">
                  {searchQuery ? "No folders match your search" : "No folders found"}
                </div>
              ) : (
                <div className="divide-y">
                  {filteredFolders.map((folder) => (
                    <div
                      key={folder.id}
                      className="flex items-center justify-between p-3 hover:bg-muted"
                    >
                      <button
                        onClick={() => handleFolderClick(folder.id, folder.name)}
                        className="flex items-center gap-2 flex-1 text-left"
                      >
                        <Folder className="h-5 w-5 text-blue-500" />
                        <span>{folder.name}</span>
                      </button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleSelectFolder(folder.id, folder.name)}
                      >
                        <Check className="h-4 w-4 mr-1" />
                        Select
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
