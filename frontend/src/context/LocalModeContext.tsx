import * as React from "react"

interface LocalModeContextValue {
  isLocalMode: boolean
  setLocalMode: (value: boolean) => void
}

const LocalModeContext = React.createContext<LocalModeContextValue>({
  isLocalMode: false,
  setLocalMode: () => {},
})

export function useLocalMode() {
  return React.useContext(LocalModeContext)
}

export function LocalModeProvider({ children }: { children: React.ReactNode }) {
  const [isLocalMode, setLocalModeState] = React.useState(() => {
    // Initialize from localStorage
    const stored = localStorage.getItem("local_mode")
    return stored === "true"
  })

  const setLocalMode = React.useCallback((value: boolean) => {
    setLocalModeState(value)
    localStorage.setItem("local_mode", value ? "true" : "false")
  }, [])

  const value = React.useMemo(
    () => ({ isLocalMode, setLocalMode }),
    [isLocalMode, setLocalMode]
  )

  return (
    <LocalModeContext.Provider value={value}>
      {children}
    </LocalModeContext.Provider>
  )
}
