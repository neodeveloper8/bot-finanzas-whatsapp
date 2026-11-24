import { useEffect, useRef, useState } from 'react'

import { useCategorias, useGuardarMovimiento } from '../hooks/datos'
import { colorCategoria } from '../lib/categorias'
import { ayerISOLima, fechaISOLima, soles } from '../lib/formato'
import { useTema } from '../lib/tema'
import Segmentado from './Segmentado'

const TIPOS = [
  { valor: 'gasto', etiqueta: 'Gasto' },
  { valor: 'ingreso', etiqueta: 'Ingreso' },
]

// Hasta 8 enteros y 2 decimales: lo mismo que acepta la BD (max_digits=10).
// Acepta coma o punto: en el celular el teclado peruano suele traer coma.
const MONTO_VALIDO = /^\d{1,8}([.,]\d{1,2})?$/

const MENSAJES = {
  monto: 'Escribe un monto mayor a 0, con hasta 2 decimales.',
  fecha: 'Elige una fecha de hoy o de antes.',
  descripcion: 'La descripción es demasiado larga.',
  tipo_no_editable: 'Viene del comprobante de Yape: no se puede cambiar.',
  monto_no_editable: 'Viene del comprobante de Yape: no se puede cambiar.',
  fecha_no_editable: 'Viene del comprobante de Yape: no se puede cambiar.',
}

// --------------------------------------------------------------------------- memoria

// "Lo último que usaste" vive en ESTE navegador (localStorage). Si el navegador
// lo bloquea (modo privado), el formulario funciona igual, solo sin recordar.
const CLAVE = 'panel.ultimo'

function leerUltimo() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE)) ?? {}
  } catch {
    return {}
  }
}

function guardarUltimo(tipo, categoriaId) {
  try {
    const previo = leerUltimo()
    localStorage.setItem(CLAVE, JSON.stringify({ ...previo, tipo, [tipo]: categoriaId }))
  } catch {
    /* sin almacenamiento: no pasa nada */
  }
}

// --------------------------------------------------------------------------- piezas

function Campo({ etiqueta, error, children, ayuda }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[13px] font-medium text-texto-medio">{etiqueta}</span>
      {children}
      {error ? (
        <span className="text-xs text-alerta">{error}</span>
      ) : (
        ayuda && <span className="text-xs text-texto-suave">{ayuda}</span>
      )}
    </div>
  )
}

const ENTRADA =
  'min-h-11 w-full rounded-md border border-borde-fuerte bg-fondo px-3 text-[15px] text-texto outline-none focus:border-acento disabled:bg-fondo-suave disabled:text-texto-suave'

function Chip({ activo, alTocar, children, estilo }) {
  return (
    <button
      type="button"
      aria-pressed={activo}
      onClick={alTocar}
      className="min-h-9 cursor-pointer rounded-md border px-3 text-[13px]"
      style={estilo ?? { borderColor: activo ? 'var(--acento)' : 'var(--borde-fuerte)' }}
    >
      {children}
    </button>
  )
}

// --------------------------------------------------------------------------- formulario

/**
 * Crear (mov = null) o editar (mov = el movimiento) en una ventana modal.
 *
 * Usa <dialog> nativo con showModal(): el navegador ya resuelve lo difícil de
 * un modal (atrapar el foco del teclado, cerrar con Esc, el fondo oscuro, que
 * los lectores de pantalla ignoren lo de atrás). Escribirlo a mano es fácil de hacer mal.
 */
export default function FormularioMovimiento({ mov = null, alCerrar, alGuardar }) {
  const { oscuro } = useTema()
  const dialogo = useRef(null)
  const { data: cats } = useCategorias()
  const guardar = useGuardarMovimiento()

  const editando = mov !== null
  const esYape = mov?.fuente === 'yape' // monto, fecha y tipo vienen del comprobante
  const hoy = fechaISOLima()

  // Valores iniciales: los del movimiento, o lo último que usaste al crear
  const [inicial] = useState(() => {
    if (editando) {
      return {
        tipo: mov.tipo,
        monto: mov.monto,
        fecha: mov.fecha_hora.slice(0, 10), // la API manda la hora de Lima: "2026-11-20T..."
        categoriaId: mov.categoria?.id ?? null,
        descripcion: mov.descripcion,
      }
    }
    const ultimo = leerUltimo()
    const tipo = ultimo.tipo === 'ingreso' ? 'ingreso' : 'gasto'
    return { tipo, monto: '', fecha: hoy, categoriaId: ultimo[tipo] ?? null, descripcion: '' }
  })
  const [tipo, setTipo] = useState(inicial.tipo)
  const [monto, setMonto] = useState(inicial.monto)
  const [fecha, setFecha] = useState(inicial.fecha)
  const [categoriaId, setCategoriaId] = useState(inicial.categoriaId)
  const [descripcion, setDescripcion] = useState(inicial.descripcion)
  const [errores, setErrores] = useState({})

  // Sin cleanup que llame a close(): al desmontarse, el <dialog> sale del DOM y el
  // navegador lo cierra solo. Un close() aquí dispararía onClose en el doble
  // montaje de StrictMode (desarrollo) y la ventana se cerraría apenas abre.
  useEffect(() => {
    if (!dialogo.current.open) dialogo.current.showModal()
  }, [])

  const categorias = cats?.categorias.filter((c) => c.tipo === tipo) ?? []
  // Si la categoría recordada ya no existe (o es de otro tipo), se ignora
  const categoriaValida = categorias.some((c) => c.id === categoriaId) ? categoriaId : null

  function cambiarTipo(nuevo) {
    if (nuevo === tipo) return
    setTipo(nuevo)
    // "Comida" no sirve para un ingreso: pasamos a la última que usaste de ese tipo
    setCategoriaId(editando ? null : (leerUltimo()[nuevo] ?? null))
  }

  function armarDatos() {
    const todo = {
      tipo,
      monto: monto.trim().replace(',', '.'),
      fecha,
      categoria_id: categoriaValida,
      descripcion: descripcion.trim(),
    }
    if (!editando) return todo
    // Al editar mandamos SOLO lo que cambió (PATCH). En un Yape, además, el
    // servidor no deja tocar monto/fecha/tipo: ni los ofrecemos.
    const antes = {
      tipo: inicial.tipo,
      monto: inicial.monto,
      fecha: inicial.fecha,
      categoria_id: inicial.categoriaId,
      descripcion: inicial.descripcion,
    }
    return Object.fromEntries(Object.entries(todo).filter(([k, v]) => v !== antes[k]))
  }

  function enviar(e) {
    e.preventDefault()
    // Validación rápida aquí para no esperar al servidor. La que manda es la del servidor.
    const nuevos = {}
    if (!esYape && (!MONTO_VALIDO.test(monto.trim()) || Number(monto.replace(',', '.')) <= 0)) {
      nuevos.monto = MENSAJES.monto
    }
    if (!esYape && (!fecha || fecha > hoy)) nuevos.fecha = MENSAJES.fecha
    setErrores(nuevos)
    if (Object.keys(nuevos).length) return

    const datos = armarDatos()
    if (editando && Object.keys(datos).length === 0) return alCerrar() // nada cambió

    guardar.mutate(
      { id: mov?.id, datos },
      {
        onSuccess: ({ movimiento: m }) => {
          if (!editando) guardarUltimo(m.tipo, m.categoria?.id ?? null)
          const signo = m.tipo === 'gasto' ? 'Gasto' : 'Ingreso'
          alGuardar(editando ? 'Cambios guardados.' : `${signo} de ${soles(m.monto)} anotado.`)
        },
        onError: (err) => {
          if (err.campo) {
            const campo = err.campo.replace('_no_editable', '')
            setErrores({ [campo]: MENSAJES[err.campo] ?? 'Revisa este dato.' })
          } else if (err.status === 404) {
            setErrores({
              general: editando
                ? 'Ya no encuentro este movimiento. Puede que lo hayas borrado.'
                : 'Esa categoría ya no está disponible. Elige otra.',
            })
          } else {
            setErrores({ general: 'No pude guardarlo. Revisa tu conexión e inténtalo de nuevo.' })
          }
        },
      },
    )
  }

  const titulo = editando ? 'Editar movimiento' : 'Agregar movimiento'

  return (
    <dialog
      ref={dialogo}
      onClose={alCerrar} // Esc o dialog.close(): avisamos a App para que lo desmonte
      onClick={(e) => e.target === dialogo.current && alCerrar()} // clic en el fondo oscuro
      aria-label={titulo}
      className={[
        'bg-fondo text-texto backdrop:bg-black/40',
        // Celular: hoja que sube desde abajo, a todo el ancho y al alcance del pulgar
        'mx-0 mt-auto mb-0 max-h-[92dvh] w-full max-w-none rounded-t-2xl',
        // Escritorio: ventana centrada
        'md:m-auto md:max-w-[440px] md:rounded-xl md:shadow-xl',
      ].join(' ')}
    >
      <form
        onSubmit={enviar}
        noValidate // los mensajes los ponemos nosotros, en castellano y en su sitio
        className="flex flex-col gap-5 px-5 pt-5 pb-[max(env(safe-area-inset-bottom),20px)]"
      >
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold tracking-tight">{titulo}</h2>
          <Segmentado
            opciones={esYape ? TIPOS.filter((t) => t.valor === tipo) : TIPOS}
            valor={tipo}
            alCambiar={cambiarTipo}
            etiqueta="Tipo de movimiento"
            chico
          />
        </div>

        {esYape && (
          <p className="rounded-md bg-fondo-suave px-3 py-2 text-xs text-texto-suave">
            El monto y la fecha vienen del comprobante de Yape. Si están mal, borra el movimiento y
            vuelve a mandar la captura al bot.
          </p>
        )}

        <Campo etiqueta="Monto" error={errores.monto}>
          <div className="relative">
            <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[15px] text-texto-suave">
              S/
            </span>
            <input
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
              inputMode="decimal" // teclado numérico en el celular
              autoComplete="off"
              placeholder="0.00"
              disabled={esYape}
              autoFocus={!editando}
              aria-invalid={Boolean(errores.monto)}
              className={`${ENTRADA} pl-9 text-lg font-semibold tabular-nums`}
            />
          </div>
        </Campo>

        <Campo etiqueta="Fecha" error={errores.fecha}>
          <div className="flex flex-wrap items-center gap-2">
            {!esYape && (
              <>
                <Chip activo={fecha === hoy} alTocar={() => setFecha(hoy)}>
                  Hoy
                </Chip>
                <Chip activo={fecha === ayerISOLima()} alTocar={() => setFecha(ayerISOLima())}>
                  Ayer
                </Chip>
              </>
            )}
            <input
              type="date"
              value={fecha}
              max={hoy}
              onChange={(e) => setFecha(e.target.value)}
              disabled={esYape}
              aria-label="Fecha"
              aria-invalid={Boolean(errores.fecha)}
              className={`${ENTRADA} w-auto flex-1`}
            />
          </div>
        </Campo>

        <Campo
          etiqueta="Categoría"
          error={errores.categoria_id}
          ayuda={esYape && tipo === 'gasto' && mov.contraparte ? `Los próximos Yapes a ${mov.contraparte} usarán esta categoría.` : null}
        >
          <div className="flex flex-wrap gap-1.5">
            {categorias.map((c) => {
              const color = colorCategoria(c.nombre, oscuro)
              const activa = c.id === categoriaValida
              return (
                <Chip
                  key={c.id}
                  activo={activa}
                  alTocar={() => setCategoriaId(activa ? null : c.id)} // tocar la elegida la quita
                  estilo={{ background: color.fondo, color: color.texto, borderColor: activa ? color.texto : 'transparent' }}
                >
                  {c.emoji} {c.nombre}
                </Chip>
              )
            })}
          </div>
        </Campo>

        <Campo etiqueta="Descripción (opcional)" error={errores.descripcion}>
          <input
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
            maxLength={255}
            placeholder={tipo === 'ingreso' ? 'Ej.: viajes de la noche' : 'Ej.: almuerzo'}
            className={ENTRADA}
          />
        </Campo>

        {errores.general && (
          <p role="alert" className="text-[13px] text-alerta">
            {errores.general}
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={alCerrar}
            className="min-h-11 flex-1 cursor-pointer rounded-md border border-borde-fuerte text-[15px] font-medium hover:bg-fondo-hover"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={guardar.isPending}
            className="min-h-11 flex-1 cursor-pointer rounded-md bg-acento text-[15px] font-semibold text-white disabled:opacity-60 dark:text-[#191919]"
          >
            {guardar.isPending ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
