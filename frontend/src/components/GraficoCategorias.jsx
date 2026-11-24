import { useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

import { colorCategoria } from '../lib/categorias'
import { centimos, soles } from '../lib/formato'
import { useTema } from '../lib/tema'
import Segmentado from './Segmentado'

const VISTAS = [
  { valor: 'gastos', etiqueta: 'Gastos' },
  { valor: 'ingresos', etiqueta: 'Ingresos' },
]
const TEXTOS = {
  gastos: { titulo: '¿En qué se fue el dinero?', vacio: 'Sin gastos en este período.' },
  ingresos: { titulo: '¿De dónde vino el dinero?', vacio: 'Sin ingresos en este período.' },
}

export default function GraficoCategorias({ datos }) {
  const { oscuro } = useTema()
  const [vista, setVista] = useState('gastos')
  const lista = vista === 'gastos' ? datos.por_categoria : datos.por_categoria_ingresos
  const filas = lista.map((c) => ({
    ...c,
    valor: centimos(c.total), // Recharts necesita números: céntimos enteros, sin errores de float
    color: colorCategoria(c.id === null ? null : c.nombre, oscuro).punto,
  }))

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-borde p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">{TEXTOS[vista].titulo}</h2>
        <Segmentado opciones={VISTAS} valor={vista} alCambiar={setVista} etiqueta="Qué mostrar" chico />
      </div>

      {filas.length === 0 ? (
        <p className="py-10 text-center text-[13px] text-texto-suave">{TEXTOS[vista].vacio}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-6">
          <div className="relative size-[168px] shrink-0">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={filas}
                  dataKey="valor"
                  nameKey="nombre"
                  innerRadius={58}
                  outerRadius={84}
                  paddingAngle={filas.length > 1 ? 1.5 : 0}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {filas.map((f) => (
                    <Cell key={f.id ?? 'sin'} fill={f.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[11px] text-texto-suave">Total</span>
              <span className="text-[15px] font-bold tabular-nums">{soles(datos.totales[vista])}</span>
            </div>
          </div>

          {/* La lista ES la información; el gráfico solo la acompaña (lectores de pantalla incluidos) */}
          <ul className="flex min-w-40 flex-1 flex-col gap-2">
            {filas.map((f) => (
              <li key={f.id ?? 'sin'} className="flex items-center gap-2 text-[13px]">
                <span aria-hidden="true" className="size-2.5 shrink-0 rounded-[3px]" style={{ background: f.color }} />
                <span className="min-w-0 flex-1 truncate">{f.nombre}</span>
                <span className="text-texto-suave tabular-nums">{f.porcentaje}%</span>
                <span className="min-w-20 text-right font-semibold tabular-nums">{soles(f.total)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
