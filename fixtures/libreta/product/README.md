# Libreta

Libreta de notas de línea de órdenes, escrita en Python solo con la biblioteca
estándar. Cada nota tiene un identificador, un título, un cuerpo y la fecha de
creación; el almacén es un archivo JSON dentro del directorio de datos que se
indique, nunca fuera de él.

## Órdenes

- `libreta add "Título" "Cuerpo"` guarda una nota nueva.
- `libreta list` muestra todas las notas guardadas.
- `libreta find "texto"` busca por título o cuerpo.
- `libreta delete ID` elimina la nota con ese identificador.

El directorio de datos se elige con `--datos` (por defecto `datos`).

## Estructura

- `src/libreta/storage.py`: almacén de notas y sus operaciones.
- `src/libreta/cli.py`: interfaz de línea de órdenes.
- `tests/test_libreta.py`: pruebas del almacén con unittest.

Las pruebas se ejecutan con `python3 -B tests/test_libreta.py` desde la raíz
del producto.
