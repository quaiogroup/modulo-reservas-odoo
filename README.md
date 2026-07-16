# Office Booking (Sppot) — Instalación y Actualización

Módulo de Odoo 19 para reserva de oficinas y coworking: sitio web público, portal
de cliente, pagos con Bold, planes/suscripciones y notificaciones por correo.

- **Nombre técnico del módulo:** `office_booking`
- **Versión actual:** `19.0.1.1.0`
- **Repositorio:** `https://github.com/quaiogroup/modulo-reservas-odoo.git` (rama `19.0`)
- **Depende de:** `base`, `contacts`, `mail`, `website`, `portal`, `calendar` (todos estándar de Odoo)

> ⚠️ El repositorio se llama `modulo-reservas-odoo`, pero el módulo instalable es la
> carpeta **`office_booking`** que está dentro. Odoo debe ver esa carpeta en su
> *addons path*.

---

## 1. Requisitos

- Odoo **19.0** en Docker
- PostgreSQL (contenedor aparte)
- Acceso al *addons path* del contenedor de Odoo (bind mount o volumen)

Datos por entorno:

| | Desarrollo (local) | Producción |
|---|---|---|
| Contenedor Odoo | `odoo19` | `odoo-app` |
| Contenedor Postgres | `odoo-postgres` | (servicio `db`) |
| Base de datos | `reservas` | `sppot.co` |
| `--db_host` | `odoo-postgres` | `db` |
| `--db_user` / `--db_password` | `odoo` / `odoo` | `xxx` / `xxx` (ver credenciales del servidor) |
| Addons path (dentro del contenedor) | `/mnt/extra-addons` | `/mnt/extra-addons` |
| URL | http://localhost:8069 | https://sppot.co |

---

## 2. Instalación (primera vez)

### 2.1 Producción (servidor con Docker)

1. Conéctate al servidor por **Putty (SSH)** y confirma que el contenedor corre:
   ```bash
   docker exec -it odoo-app bash   # o: docker ps
   ```

2. Clona el repo (rama `19.0`) y extrae la carpeta `office_booking`.
   > Ejecuta esto en la carpeta que Odoo lee como *addons* (la que está montada
   > en `odoo-app`); ahí es donde debe quedar `office_booking`.
   ```bash
   sudo git clone https://github.com/quaiogroup/modulo-reservas-odoo.git -b 19.0
   sudo mv modulo-reservas-odoo/office_booking .
   ```

3. Instala el módulo dentro del contenedor `odoo-app`:
   ```bash
   docker exec -it odoo-app odoo -i office_booking -d sppot.co \
     --db_host=db --db_user=xxx --db_password=xxx --no-http --stop-after-init
   ```

4. Reinicia Odoo:
   ```bash
   docker restart odoo-app
   ```

5. Verifica en https://sppot.co que el módulo aparece instalado y el sitio carga.

> **Nota:** `--db_user=xxx --db_password=xxx` son placeholders (igual que en el
> doc original). Las credenciales reales están en el `odoo.conf` / variables de
> entorno del contenedor `odoo-app`; no se guardan en el repo por seguridad.

### 2.2 Desarrollo (local)

La carpeta del repo ya está montada en `/mnt/extra-addons`. Para instalar:

```bash
docker exec odoo19 odoo -i office_booking -d reservas \
  --db_host=odoo-postgres --db_user=odoo --db_password=odoo --stop-after-init
docker restart odoo19
```

---

## 3. Actualización (nueva versión del módulo)

> La actualización usa la bandera **`-u`** (update). Odoo detecta cualquier
> cambio de código, vistas, datos y **ejecuta automáticamente los scripts de
> migración** si la versión del `__manifest__.py` subió. No hay que correr SQL a mano.

### 3.1 Producción

1. **Backup de la base de datos** (obligatorio antes de cualquier migración de esquema):
   ```bash
   docker exec db pg_dump -U xxx sppot.co > sppot_backup_$(date +%F_%H%M).sql
   ```

2. Trae la última versión y reemplaza `office_booking` (mismo proceso que la
   instalación). Ejecútalo en la carpeta donde vive `office_booking`:
   ```bash
   sudo rm -rf modulo-reservas-odoo office_booking       # limpia lo anterior
   sudo git clone https://github.com/quaiogroup/modulo-reservas-odoo.git -b 19.0
   sudo mv modulo-reservas-odoo/office_booking .
   ```

3. Actualiza el módulo (esto dispara la migración automática):
   ```bash
   docker exec -it odoo-app odoo -u office_booking -d sppot.co \
     --db_host=db --db_user=xxx --db_password=xxx --no-http --stop-after-init
   ```

4. Reinicia Odoo:
   ```bash
   docker restart odoo-app
   ```

5. Revisa que en el log aparezca la migración (si la versión cambió), sin errores:
   ```
   INFO ... odoo.modules.migration: module office_booking: Running migration ...
   INFO ... Module office_booking loaded ...
   ```

### 3.2 Desarrollo (local)

Como la carpeta ya está montada, basta con actualizar y reiniciar:

```bash
docker exec odoo19 odoo -u office_booking -d reservas \
  --db_host=odoo-postgres --db_user=odoo --db_password=odoo --stop-after-init
docker restart odoo19
```

---

## 4. Cómo funcionan las migraciones

Cuando se sube la versión en `__manifest__.py` (ej. `19.0.1.0.0` → `19.0.1.1.0`),
Odoo ejecuta automáticamente los scripts de:

```
office_booking/migrations/<version>/pre-migrate.py    # antes de cargar el módulo (renombra columnas, etc.)
office_booking/migrations/<version>/post-migrate.py   # después de cargar (limpieza)
```

Los scripts son **idempotentes** (se pueden re-ejecutar sin romper nada) y corren
igual en local y en producción con el mismo comando `-u`. Por eso una migración
que preserva datos (ej. renombrar una columna sin perder su contenido) queda
resuelta sola en ambos entornos.

> **Regla al hacer cambios que tocan la base de datos** (renombrar/eliminar campos,
> mover datos): sube la versión del manifest y agrega un script en
> `migrations/<nueva_version>/`. Si solo cambias vistas, textos, CSS o lógica
> Python sin tocar el esquema, no hace falta migración — basta con `-u`.

---

## 5. Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| `-u` no aplica cambios de vistas | Falta reiniciar: `docker restart <contenedor>` |
| Plantillas de correo no se actualizan | Registro con `noupdate=1` guardado en `ir_model_data`. Forzar: `UPDATE ir_model_data SET noupdate=false WHERE module='office_booking' AND model='mail.template';` y volver a correr `-u` |
| `column ... does not exist` tras cambiar un campo | Faltó el script de migración con `ALTER TABLE ... RENAME COLUMN`. Ver sección 4 |
| La migración no corre | La versión del `__manifest__.py` no cambió respecto a la instalada |
| Vista personalizada (Studio/editor web) rota tras renombrar campos | Esas vistas viven en la BD (COW), no en el código; requieren arreglo en `ir_ui_view.arch_db` dentro del script de migración |

---

## 6. Comandos rápidos (chuleta)

**Local — actualizar + reiniciar:**
```bash
docker exec odoo19 odoo -u office_booking -d reservas --db_host=odoo-postgres --db_user=odoo --db_password=odoo --stop-after-init && docker restart odoo19
```

**Producción — backup + actualizar + reiniciar:**
```bash
docker exec db pg_dump -U xxx sppot.co > sppot_backup_$(date +%F_%H%M).sql
docker exec -it odoo-app odoo -u office_booking -d sppot.co --db_host=db --db_user=xxx --db_password=xxx --no-http --stop-after-init
docker restart odoo-app
```
