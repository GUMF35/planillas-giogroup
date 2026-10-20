# Gio Group · Suite administrativa v5 — Informe técnico

Fecha: 20/10/2026 · Versión anterior auditada: v4.2 (`app.py`, 4 254 líneas).

## 0. Cómo se verificó

| Tipo de verificación | Qué se hizo |
|---|---|
| **Inspección estática** | Lectura completa de `app.py`; análisis con `pyflakes` (sin nombres indefinidos). |
| **Pruebas ejecutadas** | 49 pruebas automáticas con `pytest` en Python 3.12, Streamlit 1.66, pandas 3.0 y gspread 6.2 (las versiones que instala Streamlit Cloud). Todas pasan. |
| **Regresión con datos reales** | 60 reportes PDF reales procesados con la versión anterior y con la nueva: 60 idénticos (sueldo, comisión, ventas y servicios por colaborador), 0 diferencias, 0 errores. |
| **Revisión visual** | La app corriendo en el navegador integrado, en tamaño escritorio y teléfono (algunas páginas). |
| **NO verificado** | Conexión con **tu** Google Sheets real (no hay credenciales en este equipo: se usó una hoja simulada), envío por Gmail y comportamiento en Streamlit Cloud. Ver «Verificación después de publicar» (§8). |

---

## 1. Fase A — Auditoría

### 1.1 Inventario de funciones existentes

| Función | Clasificación (v4.2) |
|---|---|
| Lectura del PDF, cálculo de planilla, período/quincenas, cuadre contra el PDF | Funciona (verificado con 60 PDF reales) |
| Personal y sueldos, proveedores (alta/edición/baja), ajustes | Funciona y conectado a Sheets, pero con escritura riesgosa (H1, H2) |
| Autoguardado en `Historial_Planillas` | Funciona; reemplazaba períodos ya pagados sin dejar copia (H8) |
| Auditoría de documentos | Parcial: si Sheets fallaba, el registro se perdía sin aviso (H10) |
| Bonos, descuentos y notas del período | Solo en la sesión hasta el autoguardado; no se recuperaban al reiniciar (H9) |
| Ajustes de tema, reglas y salario mínimo | Solo en la sesión hasta pulsar «Guardar … en Google Sheets» (H13, sin cambio) |
| Recibos, memorándums, actas, planilla PDF, archivo Davivienda | Funcionan (archivos temporales de la sesión) |
| Envío por Gmail | Depende de `EMAIL_USER`/`EMAIL_PASS` (servicio externo; no probado aquí) |
| Pagos entregados, anticipos, préstamos, asistencia, horarios, caja, cuentas por pagar | **No existían** |
| Inicio de sesión y permisos | **No existía** (H4) |

### 1.2 Hallazgos

| # | Gravedad | Ubicación | Causa | Impacto | Solución | Estado |
|---|---|---|---|---|---|---|
| H1 | **Crítica** | `_escribir_hoja`, `guardar_historial_planilla` | Se hacía `clear()` y después `update()` | Si la segunda llamada fallaba, la hoja (Personal, Proveedores, Ajustes o Historial) quedaba **vacía** | `nucleo/hojas.py`: primero escribe encima y luego limpia solo lo sobrante | Corregido · probado con hoja simulada |
| H2 | **Crítica** | `cargar_empleados`, `cargar_proveedores`, `cargar_ajustes` | Si Sheets estaba configurado pero fallaba al abrir, se usaban datos de arranque | Cualquier guardado posterior **reemplazaba la hoja real** con esos datos | Estado de carga por hoja: si la lectura falló, se bloquea la escritura con un mensaje | Corregido · probado (`test_11_sheets_configurado_pero_caido…`) |
| H3 | **Alta** | `EMPLEADOS_POR_DEFECTO`, `CUENTAS_DAVIVIENDA`, `PROVEEDOR_EJEMPLO` | Cuentas bancarias y DUI de colaboradores (agregados en v4.2 a pedido) y datos bancarios de un proveedor dentro del código | Si el repositorio de GitHub es público, esos datos quedan expuestos (también en el historial de Git) | Retirados del código; se cargan a Sheets con «Importar cuentas desde el archivo de Davivienda» | Corregido · recomiendo repositorio **privado** |
| H4 | **Alta** | Toda la app | Sin inicio de sesión | Cualquiera con el enlace veía salarios, cuentas y préstamos | Inicio de sesión opcional con roles (contraseñas solo como hash PBKDF2 en Secrets) y aviso visible si está apagado | Corregido · probado |
| H5 | **Alta** | `aplicar_reporte` | Cada colaborador contaba sus servicios por separado | Si dos alias coincidían, **un mismo servicio se pagaba a dos personas** | Cada servicio se asigna a una sola persona | Corregido · 60 PDF sin cambios |
| H6 | Media | `coincide_alias` | Búsqueda por parte de palabra | «GIO» tomaba a «SERGIO», «LUIS» a «LUISA» | Palabra completa; si no hay, la búsqueda parcial anterior con aviso | Corregido |
| H7 | Media | `aplicar_reporte` | Comisiones sin redondear | El recibo podía diferir del total por $0.01 | Redondeo a centavos por colaborador | Corregido (efecto ≤ $0.01) |
| H8 | Media | `autoguardar_planilla` | Reemplazaba el período siempre | Una planilla ya pagada podía cambiar en silencio | Bloqueo cuando hay pagos, ajustes con motivo y copia en `Historial_Planillas_Versiones` | Corregido · probado |
| H9 | Media | Planillas | Bonos, descuentos y notas solo en la sesión | Se perdían al reiniciar | Se guardan en el historial y se recuperan al volver a subir el PDF del período | Corregido |
| H10 | Media | `_auditoria_a_sheets` | `except: pass` | Registros de auditoría perdidos sin aviso | Pasa por el almacén (cola de pendientes) y registra el usuario | Corregido |
| H11 | Media | Tabla rápida de personal | La búsqueda usaba el nombre nuevo | Renombrar a alguien borraba su cargo, banco, fecha de ingreso y bonos | Columna oculta con el nombre original | Corregido |
| H12 | Baja | Historial | Etiqueta «Total pagado» | Confundía lo calculado con lo pagado | «Total calculado» | Corregido |
| H13 | Baja | Configuración | Diseño | Tema y reglas se pierden si no se pulsa «Guardar» | — | Sin cambio (documentado) |
| H14 | Baja | `cargar_proveedores` | Proveedor de ejemplo cuando la hoja estaba vacía | «Preparar hoja» lo escribía como si fuera real | Lista vacía | Corregido |
| H15 | Observación | Fórmula de planilla | Regla definida por la gerencia | La renta del 10% se aplica solo al sueldo base; comisiones y bonos no tienen retención | **No se cambió.** Si el personal factura como servicios profesionales, valida con tu contador si la retención también aplica a comisiones | Pendiente de validar |
| H16 | Observación | Personal y Proveedores | Hojas que se reescriben completas | Si dos personas guardan a la vez, gana la última | Los módulos nuevos solo agregan filas (no tienen este problema) | Documentado |
| H17 | Info | PDF (fpdf2) | Parámetro `ln` obsoleto | Solo advertencias | — | Pendiente menor |

---

## 2. Fase B — Diseño

### 2.1 Arquitectura

```
app.py            interfaz existente + integración (Planillas, Configuración, menú, sesión)
nucleo/           lógica sin Streamlit (probada con pytest)
  util.py         fechas de El Salvador, montos, IDs, períodos
  almacen.py      guardado: solo agrega filas, idempotencia, cola de pendientes
  hojas.py        reescritura segura de hojas completas
  finanzas.py     pagos, anticipos, préstamos, ajustes, caja, cuentas por pagar, reportes
  asistencia.py   marcaciones, horarios versionados, incidencias
  personal.py     expediente, historial de cambios, alertas
  seguridad.py    hash de contraseñas, usuarios y permisos
vistas/           páginas nuevas (mismo diseño: tarjetas, chips, KPIs)
tests/            49 pruebas
```

### 2.2 Persistencia — ningún registro debe perderse

1. **Cada operación es una fila nueva** en su pestaña. Nunca se edita ni se borra una fila; las anulaciones y correcciones son filas nuevas que apuntan a la original (`Ref_ID`, `Corrige_ID`) y exigen motivo.
2. **Idempotencia:** cada operación tiene un `ID` único (y, cuando aplica, una `Clave_Unica`, p. ej. `DESC|<anticipo>|<período>`). Antes de escribir se relee la hoja: si ya existe, no se duplica (doble clic, reintento, sincronización).
3. **Confirmación real:** solo se muestra «guardado» si Google Sheets confirmó. Si falla, la operación queda **PENDIENTE** en una cola (archivo local `.datos_locales/pendientes.jsonl` + memoria) y se informa así, nunca como guardada.
4. **Sincronización:** botón «Sincronizar pendientes» en el menú lateral y en Configuración; descarta lo que ya llegó a la nube.
5. **Saldos con lectura fresca:** descuentos, abonos y pagos parciales releen la hoja antes de validar; si no hay conexión, la operación no se hace.
6. **Respaldo:** el JSON de Configuración incluye todos los módulos y los pendientes; `Historial_Planillas_Versiones` guarda cada versión reemplazada.

> En Streamlit Cloud el archivo local se borra al reiniciar el servidor: **solo Google Sheets es permanente.** Por eso la app avisa cuando hay pendientes.

### 2.3 Pestañas nuevas de Google Sheets

| Pestaña | Movimientos | Uso |
|---|---|---|
| `Pagos_Personal` | PAGO, ANULACION | Dinero entregado (sueldo, comisión, bono, extraordinario, reembolso, otro) |
| `Anticipos` | ENTREGA, DESCUENTO, DEVOLUCION, ANULACION | Saldo = entregado − descontado − devuelto |
| `Prestamos` | OTORGAMIENTO, ABONO, CUOTA_PLANILLA, REESTRUCTURACION, CANCELACION, ANULACION | Cuenta por cobrar con cuotas y vencimientos |
| `Ajustes_Planilla` | AJUSTE | Diferencias de planillas ya pagadas (con motivo) |
| `Asistencia` | MARCA, CORRECCION, ANULACION | Hora real (`Registrado`) y hora efectiva (`Fecha_Hora`) |
| `Horarios` | VERSION, ANULACION | Por colaborador, cargo o negocio, con vigencia |
| `Incidencias` | DECISION | Revisión de tardanzas, ausencias, horas extra |
| `Expediente` | REGISTRO, ESTADO, ANULACION | Permisos, vacaciones, incapacidades, contratos, documentos, observaciones, historial de cambios |
| `Caja` | MOVIMIENTO, ANULACION | Gastos e ingresos manuales |
| `Cuentas_por_Pagar` | FACTURA, PAGO, ANULACION | Proveedores, pagos parciales, vencimientos |
| `Ventas_Periodo` | VERSION | Ventas por e-commerce de cada PDF (para el panel) |
| `Historial_Planillas_Versiones` | — | Copia de cada planilla antes de reemplazarla |

Todas comparten `ID, Registrado, Usuario, Movimiento, Ref_ID`.

### 2.4 Reglas de negocio clave

- **Pago calculado ≠ pago entregado.** Planilla y recibos no marcan nada como pagado. Estados por colaborador y período: Calculado, Pendiente, Parcial, Completado, «Revisar: entregado de más». Estados de cada pago: Completado, Anulado, Corregido.
- **Neto a entregar = total de la planilla (fórmula original intacta) + ajustes − anticipos aplicados − cuotas aplicadas.** Sueldo, comisión y bono pagados cuentan contra la planilla; extraordinarios y reembolsos van aparte (no se suman dos veces).
- **Anticipo:** se descuenta una vez por período (`Clave_Unica`); recalcular la planilla no lo vuelve a restar; la devolución baja el saldo sin descuento salarial.
- **Préstamo:** separado de los anticipos y de los gastos (cuenta por cobrar). La cuota en planilla exige «autorizado por» y muestra saldo anterior → cuota → nuevo saldo. Sin saldos negativos ni cuotas duplicadas.
- **Planilla ya pagada:** queda bloqueada; los cambios se registran como ajustes con motivo.
- **Asistencia:** no permite dos entradas abiertas ni salida sin entrada. Las incidencias **nunca** descuentan dinero solas. No hay verificación biométrica ni de ubicación (se dice en pantalla).
- **Caja:** cada movimiento aparece una sola vez. Pagos, anticipos, préstamos y proveedores se registran en su módulo y la caja los muestra; sus categorías no se pueden registrar a mano.
- **Archivo Davivienda:** ahora usa lo **pendiente** por entregar. Descargarlo no marca nada; «Registrar como pagado» lo hace una sola vez por archivo.

### 2.5 Seguridad y roles

- **Administración:** todo.
- **Personal operativo:** solo «Mi asistencia» (marcar, su horario, sus jornadas, solicitar permisos). Sin salarios, cuentas, préstamos ni anticipos.
- Contraseñas: hash PBKDF2-SHA256 (260 000 iteraciones) en los Secrets; bloqueo de 60 s tras 5 intentos fallidos.
- Cada registro guarda el usuario. Las correcciones, anulaciones y cuotas guardan motivo y quién autorizó.
- Sin usuarios configurados la app funciona como antes, con un aviso visible.

---

## 3. Fase C — Migración (sin perder registros)

- **No se borra ninguna pestaña ni se limpia el historial.**
- Las columnas nuevas se agregan **al final**: `Personal` (+Negocio), `Historial_Planillas` (+Periodo_Clave, Negocio, Notas, Usuario), `Auditoria` (+Usuario, ID). Las filas existentes conservan sus valores.
- Las pestañas nuevas se crean solas al primer uso o con «Preparar hoja de cálculo».
- Cuentas y DUI: si la v4.2 ya corrió conectada a Sheets, ya están en la hoja «Personal». Si no, usa «Importar cuentas desde el archivo de Davivienda».
- **Volver atrás:** la v4.2 ignora las pestañas nuevas, pero vuelve a usar el «borrar y escribir» riesgoso (H1). No se recomienda.

---

## 4. Pruebas obligatorias (todas ejecutadas)

| # | Prueba | Dónde |
|---|---|---|
| 1 | Registrar y consultar un pago | `test_nucleo::test_01…`, `test_app_flujos::test_pago_manual` |
| 2 | Anticipo de $20 descontado una sola vez | `test_nucleo::test_02…`, `test_app::test_anticipo_se_descuenta…` |
| 3 | Préstamo $100, abono $25, saldo $75 | `test_nucleo::test_03…`, `test_app_flujos::test_prestamo_y_abono` |
| 4 | Repetir la operación no duplica el pago | `test_nucleo::test_04…`, `test_app_flujos::test_pago_manual` |
| 5 | Recalcular no descuenta dos veces el anticipo | `test_nucleo::test_05…`, `test_app::test_anticipo…` (botón Recalcular) |
| 6 | Pago completado no cambia sin ajuste | `test_nucleo::test_06…`, `test_app::test_06_planilla_pagada…` |
| 7 | Entrada y salida | `test_nucleo::test_07…`, `test_app::test_15_operativo…` |
| 8 | Marcación incompleta | `test_nucleo::test_08…` |
| 9 | Tardanza sin descuento automático | `test_nucleo::test_09…` |
| 10 | Gasto reflejado en reportes | `test_nucleo::test_10…`, `test_app_flujos::test_caja…` |
| 11 | Pérdida de conexión con Google Sheets | `test_nucleo::test_11…`, `test_sheets_simulado`, `test_app::test_11…` |
| 12 | Guardado fallido no aparece como exitoso | `test_nucleo::test_11_y_12…`, `test_app::test_12…` |
| 13 | Datos disponibles tras reiniciar | `test_nucleo::test_13…` (simulado) |
| 14 | Planillas y proveedores siguen operativos | `test_app::test_14_*` + regresión de 60 PDF |
| 15 | Permisos impiden ver información restringida | `test_nucleo::test_15…`, `test_app::test_15_*` |

Ejecutar en una PC con Python:

```bash
pip install -r requirements.txt pytest
python -m pytest
```

(La prueba con PDF real usa la variable `GIO_PDF_PRUEBA` con la ruta del reporte; los PDF no se suben al repositorio.)

---

## 5. Instalación y despliegue (Streamlit Cloud)

1. **Sube a GitHub** (reemplaza o agrega): `app.py`, `requirements.txt`, `pytest.ini`, `.gitignore`, las carpetas `nucleo/`, `vistas/` y `tests/`, y `.streamlit/config.toml` y `.streamlit/secrets.toml.ejemplo`. **No subas** `secrets.toml`, `.datos_locales/`, archivos JSON ni PDF.
2. **Haz el repositorio privado** (GitHub → Settings → Change visibility). Si fue público con la v4.2, las cuentas quedaron en el historial. Un número de cuenta no permite retirar dinero, pero es dato personal.
3. Streamlit Cloud se actualiza solo. Si no, usa «Reboot app».
4. En la app: **Configuración → Respaldo y conexión → Reintentar conexión → Preparar hoja de cálculo** (crea las pestañas nuevas; no borra nada).
5. **Configuración → Personal y sueldos → Importar cuentas desde el archivo de Davivienda**: pega tus líneas `cuenta,monto,nombre` y guarda.
6. **Configuración → Seguridad y usuarios → Crear un usuario**: genera un bloque por persona, pégalo en *Settings → Secrets* y guarda. Al reiniciar, la app pide iniciar sesión.
7. (Opcional) En Streamlit Cloud: *Settings → Sharing → Only specific people*.

## 6. Decisiones tomadas (opción más segura)

- **Google Sheets se mantiene** como base de datos: alcanza para el volumen actual. Si en el futuro hay muchas personas editando a la vez o cientos de miles de filas, conviene PostgreSQL (p. ej. Supabase, con plan gratuito). El almacén está separado en `nucleo/almacen.py`: se agregaría otro backend sin tocar las páginas, exportando cada pestaña a CSV para migrar.
- **Comprobantes:** se guarda número o enlace (p. ej. a Google Drive). Subir archivos desde la app requiere una unidad compartida de Google Workspace (las cuentas de servicio no tienen espacio propio); no se implementó.
- **Inicio de sesión opcional** para no bloquear la app el día de la actualización. Se recomienda activarlo de inmediato.
- **Reglas laborales** (tolerancia, jornada de 8 h diarias y 44 h semanales, umbral de horas extra) son valores configurables de referencia. Verifícalos con el Código de Trabajo o tu asesor. Ninguna incidencia descuenta dinero sola.

## 7. Limitaciones conocidas

- La cola de pendientes vive en el servidor: en la nube se pierde si Streamlit reinicia antes de sincronizar. La app lo advierte y permite descargarla.
- «Personal activo» cuenta a todos los registrados (no hay estado activo/inactivo; quien se va se elimina como antes y queda como «Baja» en el expediente).
- Advertencias de `fpdf2` por un parámetro obsoleto (no afectan).

## 8. Verificación después de publicar (5 minutos)

1. Configuración → Respaldo y conexión: todo en ✅ y «Preparar hoja de cálculo».
2. Anticipos: registra un anticipo de $1 a ti mismo. Debe decir «guardado» y aparecer en la pestaña `Anticipos` de tu hoja.
3. Anúlalo con motivo «prueba» y confirma que aparece la fila ANULACION.
4. Sube el PDF de una quincena y confirma que la planilla da los mismos totales de siempre.
5. Asistencia: marca entrada y salida de prueba y anúlalas con motivo.
