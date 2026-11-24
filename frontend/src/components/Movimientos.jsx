import { useEffect, useRef, useState } from 'react'

import { useCambiarCategoria, useCategorias, useEliminar, useMovimientos } from '../hooks/datos'
import { useDiferido } from '../hooks/useDiferido'
import { colorCategoria } from '../lib/categorias'
import { fechaCorta, hora, soles } from '../lib/formato'
import { useTema } from '../lib/tema'
import Aviso from './Aviso'
import { Bloque } from './Esqueleto'
import {
  IconoAnterior,
  IconoBasura,
  IconoBuscar,
  IconoCelular,
  IconoFlechaAbajo,
  IconoLapiz,
  IconoMensaje,
  IconoPantalla,
  IconoSiguiente,
} from './Iconos'
import Segmentado from './Segmentado'

const ESPERA_DESHACER = 5000
const TIPOS = [
  { valor: '', etiqueta: 'Todos' },
  { valor: 'gasto', etiqueta: 'Gastos' },
  { valor: 'ingreso', etiqueta: 'Ingresos' },
]
const COLUMNAS = 'md:grid md:grid-cols-[72px_minmax(0,1fr)_88px_168px_112px_84px] md:gap-3'

/** Lo que se muestra como "detalle". Uno cargado a mano puede no tener descripción. */
const detalle = (mov) =>
  mov.contraparte || mov.descripcion || mov.categoria?.nombre || (mov.tipo === 'gasto' ? 'Gasto' : 'Ingreso')

// --------------------------------------------------------------------------- piezas

function EtiquetaCategoria({ mov, abierto, alTocar }) {
  const { oscuro } = useTema()
  const nombre = mov.categoria?.nombre ?? 'Sin categoría'
  const c = colorCategoria(mov.categoria?.nombre ?? null, oscuro)
  if (!alTocar) {
    // Solo lectura (demo): una etiqueta, no un botón
    return (
      <span
        className="inline-flex min-h-7 max-w-full items-center rounded px-2 text-[13px]"
        style={{ background: c.fondo, color: c.texto }}
      >
        <span className="truncate">{nombre}</span>
      </span>
    )
  }
  return (
    <button
      type="button"
      onClick={alTocar}
      aria-expanded={abierto}
      aria-label={`Categoría: ${nombre}. Cambiar`}
      className="inline-flex min-h-7 max-w-full cursor-pointer items-center gap-1 rounded px-2 text-[13px]"
      style={{ background: c.fondo, color: c.texto }}
    >
      <span className="truncate">{nombre}</span>
      <IconoFlechaAbajo tam={12} />
    </button>
  )
}

function Origen({ fuente, soloIcono = false }) {
  const Icono = { yape: IconoCelular, panel: IconoPantalla }[fuente] ?? IconoMensaje
  const texto = { yape: 'Yape', texto: 'Texto', voz: 'Voz', panel: 'Panel' }[fuente] ?? fuente
  return (
    <span className="flex items-center gap-1.5 text-[13px] text-texto-medio">
      <Icono tam={15} />
      {!soloIcono && texto}
    </span>
  )
}

function Monto({ mov }) {
  const gasto = mov.tipo === 'gasto'
  return (
    <span className={`text-right font-semibold whitespace-nowrap tabular-nums ${gasto ? '' : 'text-positivo'}`}>
      {gasto ? '−' : '+'}
      {soles(mov.monto)}
    </span>
  )
}

function BotonEditar({ mov, alEditar }) {
  return (
    <button
      type="button"
      onClick={alEditar}
      aria-label={`Editar: ${detalle(mov)}, ${soles(mov.monto)}`}
      className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-md text-texto-suave hover:bg-fondo-hover hover:text-texto"
    >
      <IconoLapiz tam={16} />
    </button>
  )
}

function BotonBorrar({ mov, alBorrar }) {
  const quien = detalle(mov)
  return (
    <button
      type="button"
      onClick={alBorrar}
      aria-label={`Eliminar: ${quien}, ${soles(mov.monto)}`}
      className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-md text-texto-suave hover:bg-fondo-hover hover:text-texto"
    >
      <IconoBasura tam={16} />
    </button>
  )
}

function SelectorCategoria({ mov, categorias, alElegir }) {
  const { oscuro } = useTema()
  return (
    <div className="flex flex-wrap items-center gap-1.5 bg-fondo-suave px-4 pt-1 pb-3.5 md:pl-[100px]">
      <span className="mr-1 text-xs text-texto-suave">Mover a</span>
      {/* Un gasto solo puede ir a categorías de gasto (el servidor también lo exige) */}
      {categorias.filter((cat) => cat.tipo === mov.tipo).map((cat) => {
        const c = colorCategoria(cat.nombre, oscuro)
        const actual = cat.id === mov.categoria?.id
        return (
          <button
            key={cat.id}
            type="button"
            aria-pressed={actual}
            onClick={() => alElegir(cat)}
            className="min-h-[30px] cursor-pointer rounded border px-2.5 text-[13px]"
            style={{ background: c.fondo, color: c.texto, borderColor: actual ? c.texto : 'transparent' }}
          >
            {cat.nombre}
          </button>
        )
      })}
      {mov.contraparte && mov.tipo === 'gasto' && (
        <span className="ml-1 text-xs text-texto-suave">
          Los próximos Yapes a {mov.contraparte} usarán esta categoría.
        </span>
      )}
    </div>
  )
}

function Fila({ mov, abierto, alTocarCategoria, alEditar, alBorrar, children }) {
  const quien = detalle(mov)
  return (
    <li className="border-b border-borde last:border-b-0">
      {/* Escritorio: una fila de tabla */}
      <div className={`hidden min-h-[52px] items-center px-4 py-2 ${COLUMNAS} ${abierto ? 'bg-fondo-suave' : ''}`}>
        <span className="text-[13px] text-texto-suave" title={hora(mov.fecha_hora)}>
          {fechaCorta(mov.fecha_hora)}
        </span>
        <span className="truncate font-medium">{quien}</span>
        <Origen fuente={mov.fuente} />
        <span className="min-w-0">
          <EtiquetaCategoria mov={mov} abierto={abierto} alTocar={alTocarCategoria} />
        </span>
        <Monto mov={mov} />
        <span className="flex justify-end">
          {alEditar && <BotonEditar mov={mov} alEditar={alEditar} />}
          {alBorrar && <BotonBorrar mov={mov} alBorrar={alBorrar} />}
        </span>
      </div>

      {/* Celular: tarjeta compacta, todo al alcance del pulgar */}
      <div className={`flex items-center gap-3 py-2.5 pr-1 pl-4 md:hidden ${abierto ? 'bg-fondo-suave' : ''}`}>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          {/* Tocar el nombre o el monto abre la edición: más fácil que un botón chico */}
          {alEditar ? (
            <button
              type="button"
              onClick={alEditar}
              aria-label={`Editar: ${quien}, ${soles(mov.monto)}`}
              className="flex cursor-pointer items-baseline justify-between gap-3 text-left"
            >
              <span className="truncate font-medium">{quien}</span>
              <Monto mov={mov} />
            </button>
          ) : (
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate font-medium">{quien}</span>
              <Monto mov={mov} />
            </div>
          )}
          <div className="flex items-center gap-2 text-xs text-texto-suave">
            <Origen fuente={mov.fuente} soloIcono />
            <span className="whitespace-nowrap">
              {fechaCorta(mov.fecha_hora)} · {hora(mov.fecha_hora)}
            </span>
            <span className="min-w-0">
              <EtiquetaCategoria mov={mov} abierto={abierto} alTocar={alTocarCategoria} />
            </span>
          </div>
        </div>
        {alBorrar && <BotonBorrar mov={mov} alBorrar={alBorrar} />}
      </div>
      {children}
    </li>
  )
}

// --------------------------------------------------------------------------- lista

/** `soloLectura` (demo): sin editar, borrar ni cambiar categoría. El backend igual lo impide. */
export default function Movimientos({ periodo, fecha, alEditar, soloLectura = false }) {
  const [q, setQ] = useState('')
  const [tipo, setTipo] = useState('')
  const [categoria, setCategoria] = useState('')
  const [pagina, setPagina] = useState(1)
  const [abierto, setAbierto] = useState(null)
  const [ocultos, setOcultos] = useState(() => new Set())
  const [aviso, setAviso] = useState(null)
  const pendiente = useRef(null) // { id, timer }: el borrado que espera los 5 segundos
  const timerAviso = useRef(null)

  const qDiferido = useDiferido(q)

  // Si cambia cualquier filtro, volvemos a la página 1. Se ajusta DURANTE el
  // render (patrón recomendado por React) en vez de un useEffect, que pintaría
  // primero la página vieja y luego corregiría.
  const firma = `${periodo}|${fecha}|${tipo}|${categoria}|${qDiferido}`
  const [firmaPrevia, setFirmaPrevia] = useState(firma)
  if (firma !== firmaPrevia) {
    setFirmaPrevia(firma)
    setPagina(1)
  }

  const lista = useMovimientos({ periodo, fecha, tipo, categoria, q: qDiferido, pagina })
  const { data: cats } = useCategorias()
  const cambiar = useCambiarCategoria()
  const eliminar = useEliminar()

  function mostrarAviso(nuevo, ms = 4000) {
    clearTimeout(timerAviso.current)
    setAviso(nuevo)
    if (ms) timerAviso.current = setTimeout(() => setAviso(null), ms)
  }

  function mostrar(id) {
    setOcultos((prev) => {
      const s = new Set(prev)
      s.delete(id)
      return s
    })
  }

  function confirmarBorrado() {
    const p = pendiente.current
    if (!p) return
    clearTimeout(p.timer)
    pendiente.current = null
    eliminar.mutate(p.id, {
      onError: () => {
        mostrar(p.id) // falló: la fila vuelve a aparecer
        mostrarAviso({ texto: 'No pude eliminarlo. Inténtalo de nuevo.' })
      },
    })
  }

  function borrar(mov) {
    confirmarBorrado() // si había otro esperando, ese se confirma ya
    setAbierto(null)
    setOcultos((prev) => new Set(prev).add(mov.id))
    const timer = setTimeout(() => {
      confirmarBorrado()
      setAviso(null)
    }, ESPERA_DESHACER)
    pendiente.current = { id: mov.id, timer }
    mostrarAviso(
      {
        texto: 'Movimiento eliminado',
        deshacer: () => {
          clearTimeout(timer)
          pendiente.current = null
          mostrar(mov.id)
          mostrarAviso(null, 0)
        },
      },
      0,
    )
  }

  // Si el componente se desmonta con un borrado esperando, NO lo enviamos:
  // ante la duda, preferimos conservar un dato a perderlo.
  useEffect(() => () => clearTimeout(pendiente.current?.timer), [])

  function elegirCategoria(mov, cat) {
    setAbierto(null)
    if (cat.id === mov.categoria?.id) return
    cambiar.mutate(
      { id: mov.id, categoriaId: cat.id },
      {
        onSuccess: (r) =>
          mostrarAviso({
            texto: r.regla_actualizada
              ? `Listo. Los próximos Yapes a ${mov.contraparte} irán a ${cat.nombre}.`
              : `Listo, quedó en ${cat.nombre}.`,
          }),
        onError: () => mostrarAviso({ texto: 'No pude cambiar la categoría.' }),
      },
    )
  }

  const datos = lista.data
  const visibles = datos?.resultados.filter((m) => !ocultos.has(m.id)) ?? []
  const desde = datos ? (datos.pagina - 1) * 20 + 1 : 0
  const hasta = datos ? desde + datos.resultados.length - 1 : 0

  return (
    <section id="movimientos" className="flex scroll-mt-6 flex-col gap-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold tracking-tight">Movimientos</h2>
        <div className="flex w-full flex-wrap items-center gap-2 md:w-auto">
          <label className="flex min-h-9 flex-1 items-center gap-1.5 rounded-md border border-borde-fuerte px-2.5 text-texto-suave md:flex-none">
            <IconoBuscar tam={16} />
            <span className="sr-only">Buscar movimientos</span>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar…"
              maxLength={50}
              className="w-full min-w-0 bg-transparent text-[13px] text-texto outline-none md:w-40"
            />
          </label>
          <label className="flex items-center gap-1.5 text-[13px] text-texto-suave">
            <span className="sr-only md:not-sr-only">Categoría</span>
            <select
              value={categoria}
              onChange={(e) => setCategoria(e.target.value)}
              className="min-h-9 rounded-md border border-borde-fuerte bg-fondo px-2 text-[13px] text-texto"
            >
              <option value="">Todas</option>
              {cats?.categorias.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
              <option value="sin">Sin categoría</option>
            </select>
          </label>
          <Segmentado opciones={TIPOS} valor={tipo} alCambiar={setTipo} etiqueta="Tipo de movimiento" chico />
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-borde">
        <div
          className={`hidden border-b border-borde px-4 py-2.5 text-xs font-medium text-texto-suave ${COLUMNAS}`}
          aria-hidden="true"
        >
          <span>Fecha</span>
          <span>Detalle</span>
          <span>Origen</span>
          <span>Categoría</span>
          <span className="text-right">Monto</span>
          <span />
        </div>

        {lista.isPending ? (
          <div className="flex flex-col gap-3 p-4" aria-busy="true">
            {[0, 1, 2, 3, 4].map((i) => (
              <Bloque key={i} className="h-9" />
            ))}
          </div>
        ) : lista.isError ? (
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-[13px] text-texto-suave">
            No pude cargar los movimientos.
            <button
              type="button"
              onClick={() => lista.refetch()}
              className="min-h-8 cursor-pointer rounded-md border border-borde-fuerte px-3 text-texto"
            >
              Reintentar
            </button>
          </div>
        ) : visibles.length === 0 ? (
          <p className="px-4 py-10 text-center text-[13px] text-texto-suave">
            {q || tipo || categoria ? 'No hay movimientos con esos filtros.' : 'No hay movimientos en este período.'}
          </p>
        ) : (
          <ul className={lista.isFetching ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
            {visibles.map((mov) => (
              <Fila
                key={mov.id}
                mov={mov}
                abierto={abierto === mov.id}
                alTocarCategoria={soloLectura ? null : () => setAbierto(abierto === mov.id ? null : mov.id)}
                alEditar={
                  soloLectura
                    ? null
                    : () => {
                        setAbierto(null)
                        alEditar(mov)
                      }
                }
                alBorrar={soloLectura ? null : () => borrar(mov)}
              >
                {abierto === mov.id && cats && (
                  <SelectorCategoria mov={mov} categorias={cats.categorias} alElegir={(c) => elegirCategoria(mov, c)} />
                )}
              </Fila>
            ))}
          </ul>
        )}

        {datos && datos.total > 0 && (
          <div className="flex items-center justify-between border-t border-borde px-4 py-2 text-[13px] text-texto-suave">
            <span>
              {desde}–{hasta} de {datos.total}
            </span>
            {datos.paginas > 1 && (
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={datos.pagina <= 1}
                  onClick={() => setPagina(datos.pagina - 1)}
                  aria-label="Página anterior"
                  className="flex size-9 cursor-pointer items-center justify-center rounded-md text-texto hover:bg-fondo-hover disabled:cursor-default disabled:opacity-30"
                >
                  <IconoAnterior tam={16} />
                </button>
                <button
                  type="button"
                  disabled={datos.pagina >= datos.paginas}
                  onClick={() => setPagina(datos.pagina + 1)}
                  aria-label="Página siguiente"
                  className="flex size-9 cursor-pointer items-center justify-center rounded-md text-texto hover:bg-fondo-hover disabled:cursor-default disabled:opacity-30"
                >
                  <IconoSiguiente tam={16} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <Aviso aviso={aviso} />
    </section>
  )
}
