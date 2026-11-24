// Toda la comunicación con la API pasa por TanStack Query. Nos da gratis:
//  - caché: volver a "Este mes" no repite la petición si los datos son recientes
//  - cancelación: si cambias de período rápido, aborta la petición vieja (signal)
//  - estados: isPending / isError / isFetching sin escribir useState a mano
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../lib/api'

export function useResumen(periodo, fecha) {
  return useQuery({
    queryKey: ['resumen', periodo, fecha],
    queryFn: ({ signal }) => api.resumen(periodo, fecha, { signal }),
    placeholderData: keepPreviousData, // mientras carga el nuevo período, deja ver el anterior
  })
}

export function useMovimientos(filtros) {
  return useQuery({
    queryKey: ['movimientos', filtros],
    queryFn: ({ signal }) => api.movimientos(filtros, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useCategorias() {
  return useQuery({
    queryKey: ['categorias'],
    queryFn: ({ signal }) => api.categorias({ signal }),
    staleTime: Infinity, // casi nunca cambian
  })
}

/** Después de modificar algo, marca como viejos el resumen y la lista para que se recarguen. */
function useRefrescarTodo() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['resumen'] })
    qc.invalidateQueries({ queryKey: ['movimientos'] })
  }
}

export function useCambiarCategoria() {
  const refrescar = useRefrescarTodo()
  return useMutation({
    mutationFn: ({ id, categoriaId }) => api.cambiarCategoria(id, categoriaId),
    onSuccess: refrescar,
  })
}

/** Crea (sin id) o edita (con id) un movimiento desde el formulario. */
export function useGuardarMovimiento() {
  const refrescar = useRefrescarTodo()
  return useMutation({
    mutationFn: ({ id, datos }) => (id ? api.editar(id, datos) : api.crear(datos)),
    onSuccess: refrescar,
  })
}

export function useEliminar() {
  const refrescar = useRefrescarTodo()
  return useMutation({
    mutationFn: (id) => api.eliminar(id),
    onSettled: refrescar, // también si falló: así la fila "oculta" reaparece
  })
}
