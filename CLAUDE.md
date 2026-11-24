# CLAUDE.md

Bot de finanzas personales por WhatsApp (Django) + panel web (React). Proyecto personal
de Gonzalo, en producción en un VPS compartido con otros sistemas. Ver README.md para
la descripción general.

## Cómo trabajar conmigo

- Háblame en castellano, tuteando.
- Explica el qué y el porqué de cada cambio, no solo el código. Estoy aprendiendo.
- Si ves una mala práctica, dímelo aunque no lo haya preguntado.
- En cambios grandes, propón un plan y espera mi confirmación antes de tocar archivos.
- No hagas commit ni push sin que te lo pida.

## Comandos

```bash
python manage.py test                       # siempre antes de dar algo por terminado
python manage.py test panel.test_api        # una app o módulo
python manage.py makemigrations --check     # verifica que no falten migraciones
cd frontend && npm run build                # verifica que el panel compile
python manage.py probar_interprete "texto"  # prueba la IA de texto (llama a la API real, cuesta)
```

## Arquitectura

- `whatsapp/`: `views.webhook` verifica la firma y encola; `tareas.atender_mensaje`
  corre en el worker de django-q2 y decide imagen / comando / texto libre.
- `comprobantes/`: llamadas a Claude con tool use; la salida se valida con los modelos
  Pydantic de `schemas.py`. El modelo está en `extractor.MODELO`.
- `finanzas/`: modelos y **toda la lógica de negocio en `servicios.py`**. Las vistas,
  tareas y la API llaman a servicios; no meten lógica propia.
  - `Categoria.tipo` (gasto/ingreso). Un movimiento solo lleva categoría de su tipo; lo
    valida `servicios._categoria_para` (la BD no puede). `categorias_disponibles(usuario, tipo)`
    filtra por tipo: la lista de WhatsApp tiene tope de 10 y es solo de gastos.
  - Fuentes: `yape`, `texto`, `voz`, `panel`. En un Yape no se editan monto, fecha ni tipo.
  - Solo los gastos con contraparte aprenden `ReglaCategoria`; los ingresos no.
- Demo pública: `panel/demo.py` (usuario `TELEFONO_DEMO = "demo-publico"` y datos ficticios),
  `seed_demo`, vista `panel.views.demo`. Se regenera cada hora con un `Schedule` de django-q2
  (`panel/tareas.py`, creado por la migración `panel/0002`): `botfin` no puede usar cron. La sesión demo es de solo lectura: lo impone
  `_requerir_sesion` en `panel/sesion.py` (403 `demo_solo_lectura`), no el frontend.
  **Si agregas una tarea que recorra usuarios** (resúmenes automáticos, recordatorios),
  excluye `telefono_wa=TELEFONO_DEMO` y agrega un test. Hoy no existe ninguna.
- `finanzas/resumenes.py`: rangos de fechas (`rango`, `rango_comparable`) y totales.
- `panel/`: enlace mágico (`servicios.py`), sesión propia sin `django.contrib.auth`
  (`sesion.py`), API JSON (`api.py`), una sola página React (`templates/panel/app.html`).
- `frontend/`: React. El build genera `panel.js`/`panel.css` con nombre fijo en
  `panel/static/panel/`; el hash lo pone `ManifestStaticFilesStorage` en collectstatic.

## Reglas del código

- **Toda consulta filtra por `usuario`.** Un id de otro usuario devuelve 404, no 403.
- Montos como `Decimal` en Python y como string (`"18.50"`) en JSON. Nunca float.
- Fechas en zona `America/Lima`. Para agrupar usa `TruncDate`/`TruncMonth` con `tzinfo`.
- La API del panel usa `@api_requerida` (401 JSON); las páginas, `@panel_requerido` (redirect).
- POST/DELETE del panel llevan CSRF. En tests de CSRF usa `Client(enforce_csrf_checks=True)`.
- Los tests nunca llaman a Anthropic ni a Meta. Mockea donde se usa, no donde se define
  (p. ej. `whatsapp.tareas.interpretar`, `whatsapp.tareas.enviar_texto`,
  `whatsapp.procesador.async_task`).
- Para fijar "hoy" en tests de la API del panel, parchea `panel.api._hoy` en `setUp`.
- Nombres de código en español, como el resto del proyecto.
- django-q2 con 1 worker a propósito: SQLite no aguanta escrituras concurrentes.

## Seguridad (no negociable)

- Nunca leas, muestres ni copies el contenido de `.env`. Si necesitas saber qué
  variables existen, mira `.env.example`.
- Nunca escribas en logs tokens, el enlace del panel ni datos de la API de Meta.
- Los tokens de enlace se guardan hasheados (sha256) y se canjean con un UPDATE atómico.
  No cambies ese flujo sin explicarme el porqué.
- No commitear: `.env`, `db.sqlite3*`, `.venv/`, `staticfiles/`, `muestras/`,
  `frontend/node_modules/`, `panel/static/panel/`, `*:Zone.Identifier`.

## Producción

- No tienes acceso al servidor y no debes intentarlo. Si un cambio necesita algo en el
  servidor, dame los comandos y los ejecuto yo.
- El servidor es compartido con otros sistemas: no se toca el Python ni el Node del
  sistema, ni nginx global, PM2 ni el firewall de los otros servicios.
- Despliegue: `deploy/actualizar.sh` como `botfin`. Si cambias ese script o `backup.sh`,
  conserva el bit de ejecución (`git ls-files -s deploy/` debe mostrar `100755`).
- Un cambio de modelo implica migración; el script la aplica sola al desplegar.
