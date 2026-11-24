import { useEffect, useState } from 'react'

/** Devuelve `valor` recién cuando deja de cambiar por `ms`. Para la búsqueda:
 *  sin esto, escribir "supermercado" dispararía 12 peticiones (una por letra). */
export function useDiferido(valor, ms = 300) {
  const [diferido, setDiferido] = useState(valor)
  useEffect(() => {
    const t = setTimeout(() => setDiferido(valor), ms)
    return () => clearTimeout(t)
  }, [valor, ms])
  return diferido
}
