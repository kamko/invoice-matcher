import { useEffect, useRef } from 'react'
import { toast } from 'sonner'

interface SSEEvent {
  type: 'connected' | 'progress' | 'info' | 'error' | 'success'
  timestamp?: string
  operation?: string
  message?: string
  current?: number
  total?: number
  percent?: number
}

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const toastIdsRef = useRef<Map<string, string | number>>(new Map())

  useEffect(() => {
    // Connect to SSE endpoint
    const eventSource = new EventSource('/api/sse/events')
    eventSourceRef.current = eventSource

    eventSource.onmessage = (event) => {
      try {
        const data: SSEEvent = JSON.parse(event.data)

        switch (data.type) {
          case 'connected':
            // Silent connection
            break

          case 'progress': {
            const toastId = `progress-${data.operation}`
            const existingToastId = toastIdsRef.current.get(toastId)

            if (existingToastId) {
              toast.loading(`${data.message} (${data.percent}%)`, {
                id: existingToastId,
              })
            } else {
              const newId = toast.loading(`${data.message} (${data.percent}%)`)
              toastIdsRef.current.set(toastId, newId)
            }
            break
          }

          case 'info':
            toast.info(data.message)
            break

          case 'error': {
            // Dismiss any progress toast for this operation
            const errorProgressKey = `progress-${data.operation}`
            const errorProgressId = toastIdsRef.current.get(errorProgressKey)
            if (errorProgressId) {
              // Update the existing progress toast to error instead of creating new one
              toast.error(data.message, { id: errorProgressId })
              toastIdsRef.current.delete(errorProgressKey)
            } else {
              toast.error(data.message)
            }
            break
          }

          case 'success': {
            // Dismiss any progress toast for this operation
            const progressKey = `progress-${data.operation}`
            const successProgressId = toastIdsRef.current.get(progressKey)
            if (successProgressId) {
              // Update the existing progress toast to success instead of creating new one
              toast.success(data.message, { id: successProgressId })
              toastIdsRef.current.delete(progressKey)
            } else {
              toast.success(data.message)
            }
            break
          }
        }
      } catch (e) {
        console.error('Failed to parse SSE event:', e)
      }
    }

    eventSource.onerror = () => {
      // Silently reconnect - EventSource auto-reconnects
    }

    return () => {
      eventSource.close()
    }
  }, [])
}
