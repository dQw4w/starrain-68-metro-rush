import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * Catches render/runtime errors anywhere below it so a single broken
 * component doesn't blank the whole app during a live event. Shows the
 * error + a recovery button instead.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface in console for on-site debugging
    console.error('App crashed:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center gap-5 px-6 text-center">
          <p className="text-white font-black text-xl">糟糕，出了一點問題</p>
          <pre className="text-red-300/70 text-xs max-w-full overflow-auto bg-black/30 rounded-xl p-3 max-h-40">
            {this.state.error.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="bg-orange-500 text-white font-bold px-8 py-3 rounded-full"
          >
            重新整理
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
