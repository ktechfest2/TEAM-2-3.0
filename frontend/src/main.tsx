import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { AppProviders } from '@/app/providers'
import { PwaUpdatePrompt } from '@/app/pwa-update-prompt'
import { routes } from '@/app/routes'
import '@/styles/index.css'

const router = createBrowserRouter(routes)

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Root element #root not found')

createRoot(rootElement).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
      <PwaUpdatePrompt />
    </AppProviders>
  </StrictMode>,
)
