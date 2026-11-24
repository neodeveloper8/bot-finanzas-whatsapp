import { cambioPorcentual, fechaCorta, soles } from '../lib/formato'

/** "↓ 11% menos que ayer". Gastar menos es BUENO (verde) aunque la flecha baje. */
function Cambio({ actual, anterior, etiqueta, menosEsBueno }) {
  const pct = cambioPorcentual(actual, anterior)
  if (pct === null) {
    const texto = actual === '0.00' ? `Igual que ${etiqueta}` : `Nada registrado ${etiqueta}`
    return <span className="text-xs text-texto-suave">{texto}</span>
  }
  if (pct === 0) return <span className="text-xs text-texto-suave">Igual que {etiqueta}</span>

  const sube = pct > 0
  const bueno = menosEsBueno ? !sube : sube
  return (
    <span className={`text-xs font-medium ${bueno ? 'text-positivo' : 'text-alerta'}`}>
      {sube ? '↑' : '↓'} {Math.abs(pct)}% {sube ? 'más' : 'menos'} que {etiqueta}
    </span>
  )
}

function Tarjeta({ titulo, children, destacada = false }) {
  return (
    <div
      className={`flex flex-col gap-1.5 rounded-xl border border-borde px-5 py-4 ${destacada ? 'bg-fondo-suave' : ''}`}
    >
      <span className="text-[13px] font-medium text-texto-suave">{titulo}</span>
      {children}
    </div>
  )
}

const MONTO = 'text-[26px] font-bold tracking-tight tabular-nums'

export default function Tarjetas({ datos }) {
  const { totales: t, comparacion: c } = datos
  const positivo = !t.balance.startsWith('-')
  return (
    <section aria-label="Totales del período" className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
      <Tarjeta titulo="Gastos">
        <span className={MONTO}>{soles(t.gastos)}</span>
        <Cambio actual={t.gastos} anterior={c.gastos} etiqueta={c.etiqueta} menosEsBueno />
      </Tarjeta>
      <Tarjeta titulo="Ingresos">
        <span className={MONTO}>{soles(t.ingresos)}</span>
        <Cambio actual={t.ingresos} anterior={c.ingresos} etiqueta={c.etiqueta} />
      </Tarjeta>
      <Tarjeta titulo="Balance" destacada>
        <span className={`${MONTO} ${positivo ? 'text-positivo' : 'text-alerta'}`}>
          {soles(t.balance, { signo: true })}
        </span>
        <span className="text-xs text-texto-suave">
          {t.movimientos} {t.movimientos === 1 ? 'movimiento' : 'movimientos'}
        </span>
      </Tarjeta>
    </section>
  )
}

/**
 * La tarjeta del ingreso que entra casi a diario (hoy: InDrive).
 *
 * No busca "InDrive" por nombre: elige la categoría de ingreso con MÁS días
 * distintos en el período. El sueldo entra un día al mes; la que se repite
 * día tras día es la diaria. Si mañana haces delivery, la tarjeta lo detecta sola.
 */
export function TarjetaIngresoDiario({ datos, anual }) {
  const candidatas = datos.por_categoria_ingresos.filter((c) => c.id !== null && c.dias >= 2)
  if (candidatas.length === 0) return null // con 1 día no hay promedio que mostrar
  const c = candidatas.reduce((a, b) => (b.dias > a.dias ? b : a))
  const mejor = fechaCorta(`${c.mejor_dia.fecha}T12:00:00-05:00`)

  return (
    <section
      aria-label={`Ingresos de ${c.nombre}`}
      className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl border border-borde px-5 py-4 sm:grid-cols-4"
    >
      <Dato titulo={`${c.emoji} ${c.nombre}`.trim()} destacado>
        {soles(c.total)}
      </Dato>
      <Dato titulo={anual ? 'Días con ingreso' : 'Días trabajados'}>{c.dias}</Dato>
      {/* Entre los días que trabajaste, no entre todos: un día libre no baja el promedio */}
      <Dato titulo="Promedio por día trabajado">{soles(c.promedio_por_dia)}</Dato>
      <Dato titulo={`Mejor día · ${mejor}`}>{soles(c.mejor_dia.total)}</Dato>
    </section>
  )
}

function Dato({ titulo, children, destacado = false }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="truncate text-[13px] font-medium text-texto-suave">{titulo}</span>
      <span className={`font-bold tracking-tight tabular-nums ${destacado ? 'text-[22px] text-positivo' : 'text-lg'}`}>
        {children}
      </span>
    </div>
  )
}
