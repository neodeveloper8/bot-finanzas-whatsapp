# Bot Finanzas

Bot de finanzas personales por WhatsApp. Le mandas una captura de Yape o un mensaje
como *"almuerzo 18.50"* y lo registra solo, con categoría. Tiene un panel web para
ver todo con gráficos.

## Qué hace

- **Capturas de Yape** → Claude (visión) extrae monto, contraparte, fecha y tipo.
- **Texto libre** → Claude interpreta uno o varios gastos/ingresos en un mensaje, cada uno
  con su categoría: *"ayer hice 45 en indrive y gasté 20 en gasolina"* → un ingreso
  (InDrive) y un gasto (Transporte).
- **Categorías de gasto y de ingreso** (Sueldo, InDrive, Otros ingresos). Un movimiento
  solo puede llevar una categoría de su mismo tipo.
- **Categorías que aprenden**: si corriges la categoría de un gasto a una contraparte, la
  próxima vez la usa sola (los ingresos no aprenden reglas).
- **Resúmenes** por WhatsApp: `hoy`, `semana`, `mes`.
- **Panel web** (`panel`): el bot te manda un enlace mágico. Desde ahí:
  - **agregas** gastos e ingresos a mano (el formulario recuerda tu última categoría);
  - **editas** cualquier movimiento (en un Yape, solo categoría y descripción: monto,
    fecha y tipo vienen del comprobante) o lo **borras**;
  - eliges el período (hoy, semana, mes, mes pasado, año) o **un día cualquiera**: con el
    calendario, con las flechas ‹ › o tocando su barra en el gráfico por día;
  - ves totales con comparación al período anterior, una dona de gastos o ingresos por
    categoría y un gráfico por día de gastos, ingresos (apilados por categoría) o balance;
  - una tarjeta del ingreso diario (la categoría de ingreso con más días en el período,
    hoy InDrive): total, días trabajados, promedio por día trabajado y mejor día.
- **`salir`** cierra la sesión del panel en todos tus dispositivos.
- **Demo pública** (`/panel/demo/`, apagada por defecto): un usuario ficticio con ~90 días de
  datos inventados, en solo lectura. Ver [Demo pública](#demo-pública).

## Stack

| Parte | Tecnología |
|---|---|
| Backend | Django 6, SQLite (WAL) |
| Cola de tareas | django-q2 usando la propia BD (sin Redis) |
| IA | API de Anthropic (`claude-haiku-5-5`) con tool use + Pydantic |
| Mensajería | WhatsApp Cloud API (Meta) |
| Panel | React 19 + Vite 8 + Tailwind 4 + Recharts + TanStack Query, servido por Django |
| Producción | gunicorn + PM2 + nginx en un VPS, HTTPS con DuckDNS |

## Estructura

```
config/        settings, urls, wsgi
whatsapp/      webhook, cliente de la API de Meta, procesamiento de mensajes y comandos
comprobantes/  extracción con IA: capturas (extractor.py) y texto (interprete.py)
finanzas/      modelos (Usuario, Categoria, Transaccion, ReglaCategoria), servicios y resúmenes
panel/         enlace mágico, sesión, vistas y API JSON del panel
frontend/      app React del panel (el build sale a panel/static/panel/)
deploy/        actualizar.sh, backup.sh, PM2 y nginx
```

## Flujo de un mensaje

```
WhatsApp → POST /whatsapp/webhook/ (firma verificada) → se encola en django-q2
        → worker: imagen → extractor | texto → comando o intérprete
        → finanzas.servicios registra → respuesta por WhatsApp
```

El webhook responde rápido y el trabajo pesado (IA, descarga de imágenes) se hace en el
worker, porque Meta reintenta si no recibe un 200 en pocos segundos.

## Desarrollo local

Requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node ≥ 20.19 (o ≥ 22.12).

```bash
uv venv && uv pip install -r requirements.txt
cp .env.example .env          # y completa los valores
python manage.py migrate
python manage.py runserver    # terminal 1
python manage.py qcluster     # terminal 2 (worker)
```

Clave secreta para `.env`:

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Para recibir mensajes reales en local necesitas exponer el puerto con un túnel (ngrok)
y apuntar el webhook de Meta a `https://<tunel>/whatsapp/webhook/`.

### Panel en modo desarrollo

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxy a Django en :8000)
```

Para entrar, escríbele `panel` al bot y abre el enlace en `localhost:8000`; la cookie de
sesión sirve también en `:5173` (las cookies son por host, no por puerto).

Sin WhatsApp (sin túnel ni webhook), genera el enlace desde la terminal. Vence en 10
minutos y sirve una sola vez; no lo pegues en ningún lado, lleva el token:

```bash
python manage.py shell -c "from panel.servicios import crear_enlace; from finanzas.models import Usuario; print(crear_enlace(Usuario.objects.first()))"
```

### Probar la IA sin WhatsApp

```bash
python manage.py probar_extractor ruta/a/captura.jpg
python manage.py probar_interprete "almuerzo 18.50 y pasaje 2"
```

## Tests

```bash
python manage.py test
```

Los tests no llaman a la API de Anthropic ni a Meta (todo está mockeado).

## Producción

Corre como el usuario `botfin` en el VPS: gunicorn en `127.0.0.1:8010` detrás de nginx,
y el worker como segundo proceso de PM2. La BD vive fuera del repo
(`/home/botfin/datos/db.sqlite3`) y se respalda a diario con `deploy/backup.sh`.

Para desplegar después de hacer `git push`:

```bash
ssh <servidor>
sudo -iu botfin
~/bot-finanzas/deploy/actualizar.sh
```

El script hace pull, instala dependencias, migra, compila el panel con el Node propio de
`botfin` (`~/.local/node`), ejecuta `collectstatic` y recarga PM2.

## Demo pública

`/panel/demo/` entra al panel como un usuario ficticio (`telefono_wa="demo-publico"`,
nombre de `PANEL_DEMO_NOMBRE`, por defecto "Carlos"):

- Solo funciona con `PANEL_DEMO_ACTIVO=True` en el `.env`; si no, da 404.
- **Solo lectura en el backend**: con una sesión demo, todo POST/PATCH/DELETE de la API
  responde 403 `{"error": "demo_solo_lectura"}`. El frontend además oculta los botones.
- La sesión demo dura 2 horas fijas y no reemplaza una sesión real ya abierta en ese
  navegador (para verla siendo tú, usa una ventana de incógnito).
- No se indexa: `<meta name="robots" content="noindex">` y cabecera `X-Robots-Tag`.

Los datos los genera `python manage.py seed_demo [--reset]`, sin llamar a ninguna API. Son
determinísticos **por fecha** (semilla `SEMILLA-fecha`) y relativos a hoy: cada reset inserta
los movimientos de hoy que ya "pasaron".

En producción se regeneran solos: el worker de django-q2 corre dos tareas programadas
(`panel/tareas.py`), creadas por la migración `panel/0002`, así que `actualizar.sh` las deja
listas. No se usa cron porque en el servidor `botfin` no tiene permiso para usarlo.

- `regenerar_demo`, cada hora en punto (no hace nada si `PANEL_DEMO_ACTIVO` está apagado).
- `limpiar_sesiones` (`clearsessions`), cada día a las 4:30 a. m. de Lima: cada visita a la
  demo crea una sesión en la BD.

Se ven (y se pueden pausar) en el admin, en *Django Q → Scheduled tasks*. Sus mensajes
salen en el log de `botfin-worker` (`pm2 logs botfin-worker`).

## Variables de entorno

Ver `.env.example`. Las de producción (`DJANGO_DB_PATH`, `DJANGO_ADMIN_URL`,
`DJANGO_CSRF_TRUSTED_ORIGINS`, `PANEL_URL_BASE`) se dejan vacías en local.
Nunca se commitea `.env`.
