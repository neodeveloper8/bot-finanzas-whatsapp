import '@fontsource-variable/inter' // la fuente viaja con la app: sin pedirle nada a Google
import './index.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { ProveedorTema } from './lib/tema'

const clienteConsultas = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 30 s: cambiar de período y volver no repite la petición
      retry: (intentos, error) => error.status >= 500 && intentos < 2, // un 400/404 no mejora reintentando
      refetchOnWindowFocus: true, // vuelves a la pestaña (o al celular) y se actualiza solo
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={clienteConsultas}>
      <ProveedorTema>
        <App />
      </ProveedorTema>
    </QueryClientProvider>
  </StrictMode>,
)
