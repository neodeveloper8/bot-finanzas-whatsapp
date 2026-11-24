import { useState } from 'react'
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { colorCategoria } from '../lib/categorias'
import { centimos, fechaCorta, soles } from '../lib/formato'
import { useTema } from '../lib/tema'
import Segmentado from './Segmentado'

const VISTAS = [
  { valor: 'gastos', etiqueta: 'Gastos' },
  { valor: 'ingresos', etiqueta: 'Ingresos' },
  { valor: 'balance', etiqueta: 'Balance' },
]

// Las categorías que ocultas en la leyenda (ej.: Sueldo) se recuerdan en este navegador
const CLAVE_OCULTAS = 'panel.ingresosOcultos'
function leerOcultas() {
  try {
    return new Set(JSON.parse(localStorage.getItem(CLAVE_OCULTAS)) ?? [])
  } catch {
    return new Set()
  }
}
function guardarOcultas(ocultas) {
  try {
    localStorage.setItem(CLAVE_OCULTAS, JSON.stringify([...ocultas]))
  } catch {
    /* sin almacenamiento: solo dura mientras la página esté abierta */
  }
}

/** Céntimos enteros -> "1234.50", para reutilizar soles() sin pasar por float. */
const aTexto = (c) => `${c < 0 ? '-' : ''}${Math.floor(Math.abs(c) / 100)}.${String(Math.abs(c) % 100).padStart(2, '0')}`

const claveDe = (categoria) => (categoria.id === null ? 'sin' : String(categoria.id))

function Burbuja({ active, payload, vista, categorias }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  let detalle = null
  if (p.futuro) {
    detalle = <span className="ml-2 font-semibold">—</span>
  } else if (vista === 'ingresos') {
    const filas = categorias.filter((c) => p[`c_${c.clave}`] > 0)
    detalle = (
      <div className="mt-1 flex flex-col gap-0.5">
        {filas.length === 0 && <span className="text-texto-suave">Sin ingresos</span>}
        {filas.map((c) => (
          <span key={c.clave} className="flex items-center gap-1.5">
            <span className="size-2 rounded-[2px]" style={{ background: c.color }} />
            <span className="flex-1">{c.nombre}</span>
            <span className="ml-3 font-semibold tabular-nums">{soles(aTexto(p[`c_${c.clave}`]))}</span>
          </span>
        ))}
      </div>
    )
  } else {
    detalle = (
      <span className="ml-2 font-semibold tabular-nums">
        {soles(aTexto(p.valor), { signo: vista === 'balance' })}
      </span>
    )
  }
  return (
    <div className="rounded-md border border-borde bg-fondo px-2.5 py-1.5 text-xs shadow-md">
      <span className="text-texto-suave">{p.titulo}</span>
      {detalle}
    </div>
  )
}

export default function GraficoDias({ datos, anual, alElegirDia }) {
  const { oscuro } = useTema()
  const [vista, setVista] = useState('gastos')
  const [ocultas, setOcultas] = useState(leerOcultas)

  // Una serie por categoría de ingreso, para apilarlas en la misma barra
  const categorias = datos.por_categoria_ingresos.map((c) => ({
    clave: claveDe(c),
    nombre: c.nombre,
    color: colorCategoria(c.id === null ? null : c.nombre, oscuro).punto,
  }))
  const visibles = categorias.filter((c) => !ocultas.has(c.clave))

  const serie = datos.serie.map((p) => {
    const gastos = p.futuro ? 0 : centimos(p.gastos)
    const ingresos = p.futuro ? 0 : centimos(p.ingresos)
    const fila = {
      ...p,
      // T12:00-05:00: una fecha "pura" a mediodía de Lima nunca se corre de día
      titulo: anual ? p.etiqueta : fechaCorta(`${p.fecha}T12:00:00-05:00`),
      valor: vista === 'balance' ? ingresos - gastos : gastos,
    }
    for (const c of categorias) {
      fila[`c_${c.clave}`] = p.futuro ? 0 : centimos(p.ingresos_por_categoria[c.clave] ?? '0')
    }
    return fila
  })

  // Promedio diario de gasto: total del período / días YA transcurridos de ese período
  const dias = serie.filter((p) => p.en_periodo && !p.futuro).length
  const total = centimos(datos.totales.gastos)
  const promedio =
    vista === 'gastos' && !anual && dias > 1 && total > 0 ? soles((total / dias / 100).toFixed(2)) : null

  // Etiquetas del eje: en un mes, solo 1, 5, 10, 15... para que no se amontonen
  const mostrarEtiqueta = (i) => anual || i === 0 || (i + 1) % 5 === 0

  function alternar(clave) {
    const nuevas = new Set(ocultas)
    if (nuevas.has(clave)) nuevas.delete(clave)
    else nuevas.add(clave)
    setOcultas(nuevas)
    guardarOcultas(nuevas)
  }

  const colorSimple = (p) => {
    if (p.futuro) return 'var(--fondo-hover)'
    if (p.valor === 0) return 'var(--borde-fuerte)'
    if (vista === 'balance') return p.valor > 0 ? 'var(--positivo)' : 'var(--alerta)'
    return p.en_periodo ? 'var(--acento)' : 'var(--borde-fuerte)'
  }

  const unidad = anual ? 'mes' : 'día'

  /** Tocar una barra (o el espacio sobre ella) abre ese día. En el año, las barras son meses. */
  function tocar(estado) {
    const p = serie[Number(estado?.activeTooltipIndex)]
    if (!anual && p && !p.futuro) alElegirDia(p.fecha)
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-borde p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">Por {unidad}</h2>
        <Segmentado opciones={VISTAS} valor={vista} alCambiar={setVista} etiqueta="Qué mostrar" chico />
      </div>

      <div
        className={`h-[170px] ${anual ? '' : 'cursor-pointer'}`}
        role="img"
        aria-label={`Gráfico de ${vista} por ${unidad}`}
      >
        <ResponsiveContainer>
          <BarChart
            data={serie}
            margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
            barCategoryGap="18%"
            onClick={tocar}
          >
            <XAxis
              dataKey="etiqueta"
              tickLine={false}
              axisLine={{ stroke: 'var(--borde)' }}
              interval={0}
              tick={({ x, y, payload, index }) =>
                mostrarEtiqueta(index) ? (
                  <text x={x} y={y + 12} textAnchor="middle" fontSize={11} fill="var(--texto-suave)">
                    {payload.value}
                  </text>
                ) : null
              }
            />
            {/* Oculto. Su rango siempre incluye el 0: así las barras nacen del piso
                y un balance negativo baja de la línea del 0 */}
            <YAxis hide domain={[(min) => Math.min(0, min), (max) => Math.max(0, max)]} />
            <Tooltip
              content={<Burbuja vista={vista} categorias={visibles} />}
              cursor={{ fill: 'var(--fondo-hover)' }}
            />
            {vista === 'balance' && <ReferenceLine y={0} stroke="var(--borde-fuerte)" />}

            {vista === 'ingresos' ? (
              visibles.map((c, i) => (
                <Bar
                  key={c.clave}
                  dataKey={`c_${c.clave}`}
                  stackId="ingresos"
                  fill={c.color}
                  radius={i === visibles.length - 1 ? [3, 3, 0, 0] : 0}
                  isAnimationActive={false}
                >
                  {serie.map((p) => (
                    <Cell key={p.fecha} fillOpacity={p.en_periodo ? 1 : 0.35} />
                  ))}
                </Bar>
              ))
            ) : (
              <Bar dataKey="valor" radius={[3, 3, 0, 0]} minPointSize={3} isAnimationActive={false}>
                {serie.map((p) => (
                  <Cell key={p.fecha} fill={colorSimple(p)} />
                ))}
              </Bar>
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {vista === 'gastos' && (promedio || !anual) && (
        <span className="text-xs text-texto-suave">
          {promedio && `Promedio ${promedio} / día`}
          {promedio && !anual && ' · '}
          {!anual && 'Toca una barra para ver ese día'}
        </span>
      )}
      {vista === 'ingresos' &&
        (categorias.length === 0 ? (
          <span className="text-xs text-texto-suave">Sin ingresos en este período.</span>
        ) : (
          // Leyenda que también filtra: ocultar "Sueldo" deja ver a escala los ingresos diarios
          <div className="flex flex-wrap items-center gap-1.5">
            {categorias.map((c) => {
              const oculta = ocultas.has(c.clave)
              return (
                <button
                  key={c.clave}
                  type="button"
                  aria-pressed={!oculta}
                  onClick={() => alternar(c.clave)}
                  title={oculta ? `Mostrar ${c.nombre}` : `Ocultar ${c.nombre}`}
                  className={`flex min-h-7 cursor-pointer items-center gap-1.5 rounded-md border border-borde px-2 text-xs ${oculta ? 'text-texto-suave line-through opacity-60' : ''}`}
                >
                  <span className="size-2 rounded-[2px]" style={{ background: c.color }} />
                  {c.nombre}
                </button>
              )
            })}
          </div>
        ))}
      {vista === 'balance' && (
        <span className="text-xs text-texto-suave">Verde: ingresaste más de lo que gastaste ese {unidad}.</span>
      )}
    </div>
  )
}
