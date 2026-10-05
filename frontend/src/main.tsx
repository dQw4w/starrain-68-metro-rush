import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App'
import { installViewportHeightVar } from './lib/viewportHeight'

// Before first paint, so the app shell is sized to the visible viewport
// rather than iOS's larger toolbar-less one.
installViewportHeightVar()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
