"""Lógica de negocio de la Suite administrativa de GIO GROUP (sin Streamlit, para poder probarla).

- util:        fechas de El Salvador, montos, identificadores y textos.
- almacen:     guardado permanente en Google Sheets (solo agrega filas), idempotencia y cola de pendientes.
- finanzas:    pagos al personal, anticipos, préstamos, caja, cuentas por pagar y reportes.
- asistencia:  marcaciones, horarios versionados e incidencias.
- personal:    expediente del colaborador y alertas.
- seguridad:   contraseñas (hash PBKDF2), usuarios y permisos por rol.
"""
