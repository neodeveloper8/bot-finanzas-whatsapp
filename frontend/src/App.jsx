import { useRef, useState } from 'react'

import Aviso from './components/Aviso'
import FormularioMovimiento from './components/FormularioMovimiento'
import { BarraInferior, BarraLateral, CabeceraMovil } from './components/Navegacion'
import { EsqueletoResumen } from './components/Esqueleto'
import GraficoCategorias from './components/GraficoCategorias'
import GraficoDias from './components/GraficoDias'
import Movimientos from './components/Movimientos'
import Segmentado from './components/Segmentado'
import SelectorDia from './components/SelectorDia'
import Tarjetas, { TarjetaIngresoDiario } from './components/Tarjetas'
import { IconoAnterior, IconoMas, IconoSiguiente } from './components/Iconos'
import { useResumen } from './hooks/datos'
import { diasEntre, fechaISOLima, rangoLegible, sumarDias } from './lib/formato'

/**
 * Texto corto en el celular (< 640 px) y completo desde ahí.
 * El completo sigue en la página como "sr-only": el lector de pantalla dice
 * "Mes pasado" y no "Mes ant.", aunque a la vista solo quepa la abreviatura.
 */
function Etiqueta({ corta, larga }) {
  if (corta === larga) return larga
  return (
    <>
      <span aria-hidden="true" className="sm:hidden">
        {corta}
      </span>
      <span className="sr-only sm:not-sr-only">{larga}</span>
    </>
  )
}

const PERIODOS = [
  ['hoy', 'Hoy', 'Hoy'],
  ['semana', 'Semana', 'Semana'],
  ['mes', 'Mes', 'Este mes'],
  ['mes_pasado', 'Mes ant.', 'Mes pasado'],
  ['anio', 'Año', 'Este año'],
].map(([valor, corta, larga]) => ({ valor, etiqueta: <Etiqueta corta={corta} larga={larga} /> }))

/** Lo que Django inyecta en la página (ver app.html). En `npm run dev` no existe. */
function leerDatosIniciales() {
  try {
    return JSON.parse(document.getElementById('datos-panel')?.textContent ?? '{}')
  } catch {
    return {}
  }
}
const { nombre = '', es_demo: esDemo = false } = leerDatosIniciales()

/** Bajo el título de un día elegido: "Ayer", "Hace 3 días"... */
function haceCuanto(fecha, hoy) {
  const n = diasEntre(fecha, hoy)
  return n === 1 ? 'Ayer' : `Hace ${n} días`
}

const FLECHA =
  'flex size-9 cursor-pointer items-center justify-center rounded-md text-texto-medio hover:bg-fondo-hover disabled:cursor-default disabled:opacity-30'

export default function App() {
  const [periodo, setPeriodo] = useState('mes')
  const [fecha, setFecha] = useState(null) // solo con periodo "dia": "2026-11-19"
  const resumen = useResumen(periodo, fecha)
  const datos = resumen.data
  const hoy = fechaISOLima()
  const verUnDia = periodo === 'hoy' || periodo === 'dia'
  const diaActual = periodo === 'dia' ? fecha : hoy

  function elegirPeriodo(nuevo) {
    setPeriodo(nuevo)
    setFecha(null)
  }

  /** Ir a un día. Hoy (o algo posterior) no es un "día elegido": es el período "Hoy". */
  function irADia(iso) {
    if (iso >= hoy) return elegirPeriodo('hoy')
    setPeriodo('dia')
    setFecha(iso)
  }
  // null = cerrado; { mov: null } = crear; { mov } = editar ese movimiento
  const [formulario, setFormulario] = useState(null)
  const [aviso, setAviso] = useState(null)
  const timerAviso = useRef(null)

  // En la demo, sin "Agregar" ni editar (el backend responde 403 de todos modos)
  const agregar = esDemo ? null : () => setFormulario({ mov: null })
  const editar = (mov) => setFormulario({ mov })

  function guardado(texto) {
    setFormulario(null)
    clearTimeout(timerAviso.current)
    setAviso({ texto })
    timerAviso.current = setTimeout(() => setAviso(null), 4000)
  }

  return (
    <div className="flex min-h-dvh">
      <BarraLateral nombre={nombre} alAgregar={agregar} esDemo={esDemo} />

      <div className="min-w-0 flex-1">
        <CabeceraMovil nombre={nombre} />

        {esDemo && (
          <div role="note" className="border-b border-borde bg-fondo-suave px-4 py-2 text-center text-[13px] text-texto-medio">
            Estás viendo una demo con datos ficticios.
          </div>
        )}
        <main className="mx-auto flex max-w-[1080px] flex-col gap-7 px-4 pt-5 pb-28 md:px-12 md:pt-10 md:pb-16">
          <header id="resumen" className="flex scroll-mt-6 flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex items-center gap-2">
              {verUnDia && (
                <button
                  type="button"
                  onClick={() => irADia(sumarDias(diaActual, -1))}
                  aria-label="Día anterior"
                  className={FLECHA}
                >
                  <IconoAnterior tam={18} />
                </button>
              )}
              <div className="flex min-w-0 flex-col gap-1">
                <h1 className="text-[28px] font-bold tracking-tight md:text-[32px]">
                  {datos ? (periodo === 'hoy' ? 'Hoy' : periodo === 'semana' ? 'Esta semana' : datos.titulo) : ' '}
                </h1>
                <span className="text-[13px] text-texto-suave">
                  {!datos ? ' ' : periodo === 'dia' ? haceCuanto(fecha, hoy) : rangoLegible(datos.desde, datos.hasta)}
                </span>
              </div>
              {verUnDia && (
                <button
                  type="button"
                  onClick={() => irADia(sumarDias(diaActual, 1))}
                  disabled={periodo === 'hoy'} // no hay "mañana" que ver
                  aria-label="Día siguiente"
                  className={FLECHA}
                >
                  <IconoSiguiente tam={18} />
                </button>
              )}
            </div>
            <div className="flex items-center gap-3">
              {/* Celular (< 640 px): el período ocupa una fila entera, con los 5 botones a la
                  vista, y "Elegir día" baja a la fila siguiente. Desde 640 px, como antes:
                  una sola fila que se desplaza de lado si no entra. */}
              <div className="w-full min-w-0 flex-1 sm:-mx-4 sm:overflow-x-auto sm:px-4 sm:[scrollbar-width:none] lg:mx-0 lg:px-0">
                <div className="flex flex-col items-start gap-2 sm:w-max sm:flex-row sm:items-center">
                  <Segmentado opciones={PERIODOS} valor={periodo} alCambiar={elegirPeriodo} etiqueta="Período" lleno />
                  <SelectorDia fecha={fecha} activo={periodo === 'dia'} alElegir={irADia} />
                </div>
              </div>
              {/* En el celular el botón está en la barra inferior, al alcance del pulgar */}
              {agregar && (
                <button
                  type="button"
                  onClick={agregar}
                  className="hidden min-h-[40px] shrink-0 cursor-pointer items-center gap-1.5 rounded-lg bg-acento px-3.5 text-[13px] font-semibold text-white md:flex dark:text-[#191919]"
                >
                  <IconoMas tam={16} />
                  Agregar
                </button>
              )}
            </div>
          </header>

          {resumen.isPending ? (
            <EsqueletoResumen />
          ) : resumen.isError ? (
            <div className="rounded-xl border border-borde p-8 text-center text-[13px] text-texto-suave">
              No pude cargar el resumen.{' '}
              <button type="button" onClick={() => resumen.refetch()} className="cursor-pointer font-medium text-acento">
                Reintentar
              </button>
            </div>
          ) : (
            <div
              className={`flex flex-col gap-4 transition-opacity ${resumen.isFetching && resumen.isPlaceholderData ? 'opacity-60' : ''}`}
            >
              <Tarjetas datos={datos} />
              <TarjetaIngresoDiario datos={datos} anual={periodo === 'anio'} />
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <GraficoCategorias datos={datos} />
                <GraficoDias datos={datos} anual={periodo === 'anio'} alElegirDia={irADia} />
              </div>
            </div>
          )}

          <Movimientos periodo={periodo} fecha={fecha} alEditar={editar} soloLectura={esDemo} />
        </main>
      </div>

      <BarraInferior alAgregar={agregar} />

      {formulario && (
        <FormularioMovimiento mov={formulario.mov} alCerrar={() => setFormulario(null)} alGuardar={guardado} />
      )}
      <Aviso aviso={aviso} />
    </div>
  )
}
