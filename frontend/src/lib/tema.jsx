import { createContext, useCallback, useContext, useEffect, useState } from 'react'

const TemaContexto = createContext(null)
const consulta = () => window.matchMedia('(prefers-color-scheme: dark)')

function leerPreferencia() {
  try {
    return localStorage.getItem('tema') ?? 'sistema'
  } catch {
    return 'sistema'
  }
}

export function ProveedorTema({ children }) {
  const [preferencia, setPreferencia] = useState(leerPreferencia) // 'claro' | 'oscuro' | 'sistema'
  const [sistemaOscuro, setSistemaOscuro] = useState(() => consulta().matches)

  // Si eliges "sistema" y el celular pasa a modo oscuro de noche, lo seguimos
  useEffect(() => {
    const mq = consulta()
    const alCambiar = (e) => setSistemaOscuro(e.matches)
    mq.addEventListener('change', alCambiar)
    return () => mq.removeEventListener('change', alCambiar)
  }, [])

  const oscuro = preferencia === 'sistema' ? sistemaOscuro : preferencia === 'oscuro'

  useEffect(() => {
    document.documentElement.classList.toggle('dark', oscuro)
  }, [oscuro])

  const elegir = useCallback((valor) => {
    setPreferencia(valor)
    try {
      if (valor === 'sistema') localStorage.removeItem('tema')
      else localStorage.setItem('tema', valor)
    } catch {
      /* sin localStorage: el tema dura solo esta visita */
    }
  }, [])

  return (
    <TemaContexto.Provider value={{ preferencia, oscuro, elegir }}>{children}</TemaContexto.Provider>
  )
}

export const useTema = () => useContext(TemaContexto)
