"""Escritura segura de hojas que se reescriben completas (Personal, Proveedores, Ajustes, Historial_Planillas).

Antes: worksheet.clear() y luego update(). Si la segunda llamada fallaba (internet, cuota de Google), la hoja quedaba VACÍA.
Ahora: primero se escribe encima (una sola llamada atómica) y solo después se limpian las filas/columnas sobrantes.
Si cualquier paso falla, los datos anteriores siguen en la hoja.
"""


def a1(fila, columna):
    """(1, 1) → 'A1' · (10, 28) → 'AB10'."""
    letras = ""
    while columna > 0:
        columna, resto = divmod(columna - 1, 26)
        letras = chr(65 + resto) + letras
    return f"{letras}{fila}"


def reemplazar_contenido(ws, filas):
    """Deja en la hoja exactamente `filas` (lista de listas). Lanza la excepción de gspread si algo falla."""
    n_cols = max((len(f) for f in filas), default=1)
    filas = [list(f) + [""] * (n_cols - len(f)) for f in filas]
    n_filas = len(filas)
    if ws.col_count < n_cols:
        ws.add_cols(n_cols - ws.col_count)
    if ws.row_count < n_filas:
        ws.add_rows(n_filas - ws.row_count)
    ws.update(values=filas, range_name="A1")
    sobrantes = []
    if ws.row_count > n_filas:
        sobrantes.append(f"A{n_filas + 1}:{a1(ws.row_count, ws.col_count)}")
    if ws.col_count > n_cols and n_filas:
        sobrantes.append(f"{a1(1, n_cols + 1)}:{a1(n_filas, ws.col_count)}")
    if sobrantes:
        ws.batch_clear(sobrantes)
