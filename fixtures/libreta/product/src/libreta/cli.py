"""Interfaz de línea de órdenes de la libreta."""
import argparse
import sys

from .storage import (
    NotaInexistente,
    anadir_nota,
    buscar_notas,
    eliminar_nota,
    listar_notas,
)


def construir_analizador():
    analizador = argparse.ArgumentParser(
        prog="libreta", description="Libreta de notas de línea de órdenes")
    analizador.add_argument(
        "--datos", default="datos",
        help="directorio del almacén de notas")
    sub = analizador.add_subparsers(dest="orden", required=True)

    alta = sub.add_parser("add", help="guarda una nota nueva")
    alta.add_argument("titulo")
    alta.add_argument("cuerpo")

    sub.add_parser("list", help="muestra las notas guardadas")

    busqueda = sub.add_parser("find", help="busca por título o cuerpo")
    busqueda.add_argument("texto")

    baja = sub.add_parser("delete", help="elimina una nota por identificador")
    baja.add_argument("id")

    return analizador


def main(argv=None):
    args = construir_analizador().parse_args(argv)
    if args.orden == "add":
        nota = anadir_nota(args.datos, args.titulo, args.cuerpo)
        print(f"nota {nota['id']} guardada")
        return 0
    if args.orden == "list":
        notas = listar_notas(args.datos)
        if not notas:
            print("no hay notas")
            return 0
        for nota in notas:
            print(f"{nota['id']}  {nota['titulo']}")
        return 0
    if args.orden == "find":
        for nota in buscar_notas(args.datos, args.texto):
            print(f"{nota['id']}  {nota['titulo']}")
        return 0
    if args.orden == "delete":
        try:
            eliminar_nota(args.datos, args.id)
        except NotaInexistente:
            print(f"no existe la nota {args.id}", file=sys.stderr)
            return 1
        print(f"nota {args.id} eliminada")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
