import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useGDriveStatus, useGDriveAuthUrl, useGDriveFolders } from "@/api/client"
import { Folder, ChevronRight, Loader2, ExternalLink, Check, Search, List } from "lucide-react"

interface GDriveSelectorProps {
  selectedFolderId: string | null
  selectedFolderName: string | null
  onFolderSelect: (folderId: string, folderName: string) => void
  onNext: () => void
  onSkip: () => void
}

export function GDriveSelector({
  selectedFolderId,
  selectedFolderName,
  onFolderSelect,
  onNext,
  onSkip,
}: GDriveSelectorProps) {
  const queryClient = useQueryClient()
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useGDriveStatus()
  const getAuthUrl = useGDriveAuthUrl()
  const [currentParentId, setCurrentParentId] = React.useState("root")
  const [showAll, setShowAll] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState("")
  const [breadcrumbs, setBreadcrumbs] = React.useState<Array<{ id: string; name: string }>>([
    { id: "root", name: "My Drive" },
  ])

  // Listen for message from OAuth popup
  React.useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === "gdrive-connected") {
        // Refresh status and folders
        refetchStatus()
        queryClient.invalidateQueries({ queryKey: ["gdrive-folders"] })
      }
    }
    window.addEventListener("message", handleMessage)
    return () => window.removeEventListener("message", handleMessage)
  }, [refetchStatus, queryClient])

  const { data: foldersData, isLoading: foldersLoading } = useGDriveFolders(
    status?.authenticated ? currentParentId : "",
    showAll
  )

  // Filter folders by search query
  const filteredFolders = React.useMemo(() => {
    if (!foldersData?.folders) return []
    if (!searchQuery.trim()) return foldersData.folders
    const query = searchQuery.toLowerCase()
    return foldersData.folders.filter((f) => f.name.toLowerCase().includes(query))
  }, [foldersData?.folders, searchQuery])

  const handleConnect = async () => {
    try {
      const result = await getAuthUrl.mutateAsync()
      // Open OAuth URL in new window
      window.open(result.auth_url, "_blank", "width=600,height=700")
    } catch (error) {
      console.error("Failed to get auth URL:", error)
    }
  }

  const handleFolderClick = (folderId: string, folderName: string) => {
    if (showAll) {
      // In "show all" mode, clicking navigates into folder and switches to browse mode
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
    onFolderSelect(folderId, folderName)
  }

  const toggleShowAll = () => {
    setShowAll(!showAll)
    setSearchQuery("")
    if (!showAll) {
      // Reset to root when switching to "show all"
      setBreadcrumbs([{ id: "root", name: "My Drive" }])
      setCurrentParentId("root")
    }
  }

  if (statusLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // GDrive not configured
  if (!status?.available) {
    return (
      <div className="space-y-6">
        <div className="text-center py-8 space-y-4">
          <div className="text-muted-foreground">
            <p>Google Drive integration is not configured.</p>
            <p className="text-sm mt-2">
              To enable it, add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={onSkip}>Skip - Use Local Directory</Button>
        </div>
      </div>
    )
  }

  // Not authenticated
  if (!status?.authenticated) {
    return (
      <div className="space-y-6">
        <div className="text-center py-8 space-y-4">
          <Folder className="h-16 w-16 mx-auto text-muted-foreground" />
          <div>
            <h3 className="text-lg font-semibold">Connect Google Drive</h3>
            <p className="text-muted-foreground">
              Allow access to select a folder containing your invoice PDFs
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
        <div className="flex justify-end">
          <Button variant="outline" onClick={onSkip}>
            Skip - Use Local Directory
          </Button>
        </div>
      </div>
    )
  }

  // Authenticated - show folder picker
  return (
    <div className="space-y-4">
      {/* Mode toggle and search */}
      <div className="flex gap-2">
        <Button
          variant={showAll ? "default" : "outline"}
          size="sm"
          onClick={toggleShowAll}
        >
          <List className="h-4 w-4 mr-1" />
          {showAll ? "Showing All" : "Show All Folders"}
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

      {/* Breadcrumbs (only in browse mode) */}
      {!showAll && (
        <div className="flex items-center gap-1 text-sm">
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
                  variant={selectedFolderId === folder.id ? "default" : "outline"}
                  onClick={() => handleSelectFolder(folder.id, folder.name)}
                >
                  {selectedFolderId === folder.id ? (
                    <>
                      <Check className="h-4 w-4 mr-1" />
                      Selected
                    </>
                  ) : (
                    "Select"
                  )}
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Selected folder */}
      {selectedFolderName && (
        <div className="bg-muted p-3 rounded-lg flex items-center gap-2">
          <Folder className="h-5 w-5 text-blue-500" />
          <span>Selected: <strong>{selectedFolderName}</strong></span>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between pt-4">
        <Button variant="outline" onClick={onSkip}>
          Use Local Directory Instead
        </Button>
        <Button onClick={onNext} disabled={!selectedFolderId}>
          Next
        </Button>
      </div>
    </div>
  )
}
