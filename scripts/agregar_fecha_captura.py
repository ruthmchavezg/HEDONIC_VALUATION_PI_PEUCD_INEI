"""Agrega la columna fecha_captura a un CSV de Urbania (el adaptador la lee si existe).

Uso:
    python scripts/agregar_fecha_captura.py ENTRADA.csv AAAA-MM-DD [SALIDA.csv]

No modifica el original: por defecto escribe ENTRADA_con_fecha.csv junto al archivo.
Se corre una vez por cada CSV de Urbania, con la fecha real en que se hizo ese scrapeo.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    entrada = Path(sys.argv[1])
    fecha = sys.argv[2]
    date.fromisoformat(fecha)  # falla si no es AAAA-MM-DD
    salida = Path(sys.argv[3]) if len(sys.argv) > 3 else entrada.with_name(entrada.stem + "_con_fecha.csv")

    df = pd.read_csv(entrada, encoding="utf-8-sig", dtype=str, keep_default_na=False, na_values=[""])
    df["fecha_captura"] = fecha
    df.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"{len(df)} filas -> {salida}")


if __name__ == "__main__":
    main()
