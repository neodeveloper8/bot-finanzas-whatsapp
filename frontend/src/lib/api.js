// Única puerta de React hacia Django. Si algo cambia en cómo hablamos con el
// backend (cabeceras, errores, sesión), se cambia AQUÍ y en ningún otro lado.

export class ErrorApi extends Error {
  /** `campo`: en un 400 de datos inválidos, cuál falló ("monto", "fecha"...). */
  constructor(status, codigo, campo = null) {
    super(codigo)
    this.status = status
    this.codigo = codigo
    this.campo = campo
  }
}

export function leerCookie(nombre) {
  const fila = document.cookie.split('; ').find((c) => c.startsWith(`${nombre}=`))
  return fila ? decodeURIComponent(fila.split('=')[1]) : ''
}

async function pedir(url, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (method !== 'GET') {
    // Django exige el token CSRF en todo lo que modifica datos. Lo dejó en la
    // cookie "csrftoken" al cargar la página; aquí lo devolvemos en una cabecera.
    // Un sitio malicioso no puede leer NUESTRAS cookies, así que no puede imitarlo.
    headers['X-CSRFToken'] = leerCookie('csrftoken')
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const r = await fetch(url, {
    method,
    headers,
    signal,
    credentials: 'same-origin', // manda la cookie de sesión (mismo sitio)
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (r.status === 401) {
    // Sesión vencida o cerrada con "salir" desde WhatsApp
    window.location.assign('/panel/acceso/')
    throw new ErrorApi(401, 'sin_sesion')
  }
  if (!r.ok) {
    let datos = {}
    try {
      datos = await r.json()
    } catch {
      /* la respuesta no era JSON (ej.: 500 de nginx) */
    }
    throw new ErrorApi(r.status, datos.error ?? 'error', datos.campo ?? null)
  }
  return r.status === 204 ? null : r.json()
}

function query(params) {
  // Quita los filtros vacíos: ?tipo=&q= ensucia la URL y la caché
  const limpios = Object.entries(params).filter(([, v]) => v !== '' && v != null)
  return new URLSearchParams(limpios).toString()
}

export const api = {
  // `fecha` solo va con periodo="dia" (query() quita el null del resto)
  resumen: (periodo, fecha, { signal } = {}) =>
    pedir(`/panel/api/resumen/?${query({ periodo, fecha })}`, { signal }),
  movimientos: (filtros, { signal } = {}) =>
    pedir(`/panel/api/movimientos/?${query(filtros)}`, { signal }),
  categorias: ({ signal } = {}) => pedir('/panel/api/categorias/', { signal }),
  cambiarCategoria: (id, categoriaId) =>
    pedir(`/panel/api/movimientos/${id}/categoria/`, { method: 'POST', body: { categoria_id: categoriaId } }),
  crear: (datos) => pedir('/panel/api/movimientos/', { method: 'POST', body: datos }),
  // PATCH: solo viajan los campos que cambiaron
  editar: (id, cambios) => pedir(`/panel/api/movimientos/${id}/`, { method: 'PATCH', body: cambios }),
  eliminar: (id) => pedir(`/panel/api/movimientos/${id}/`, { method: 'DELETE' }),
}
