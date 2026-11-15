from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import subprocess
import sys
import tempfile

base = Path("data/raw/gpm_monthly")
metadata = Path("data/metadata")
cookies = Path.home() / ".urs_cookies"

try:
    import h5py
except ImportError:
    h5py = None

vacios = sorted(
    p for p in base.glob("*.HDF5")
    if p.stat().st_size == 0
)

# Por seguridad, primero descarga solo un archivo.
archivos = vacios if "--all" in sys.argv else vacios[:1]

print("Archivos vacíos encontrados:", len(vacios))
print("Archivos a intentar:", len(archivos))
print("Verificación con h5py:", "Disponible" if h5py else "Pendiente")

recuperados = 0

for archivo in archivos:
    meta = metadata / f"gpm_monthly-{archivo.name}.json"

    if not meta.exists():
        print("SIN METADATOS:", archivo.name)
        continue

    info = json.loads(meta.read_text())
    url = info.get("url", "")

    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or parsed.hostname != "data.gesdisc.earthdata.nasa.gov"
    ):
        print("URL NO VÁLIDA:", archivo.name)
        continue

    fd, temporal = tempfile.mkstemp(
        prefix="gpm_",
        suffix=".part",
        dir=base
    )
    os.close(fd)

    print("\nDescargando:", archivo.name)

    try:
        comando = [
            "curl",
            "--location",
            "--fail",
            "--show-error",
            "--netrc",
            "--retry", "2",
            "--connect-timeout", "20",
            "--max-time", "900",
            "--cookie", str(cookies),
            "--cookie-jar", str(cookies),
            "--output", temporal,
            url,
        ]

        resultado = subprocess.run(comando)

        if resultado.returncode != 0:
            print("ERROR DE DESCARGA:", archivo.name)
            continue

        with open(temporal, "rb") as f:
            cabecera = f.read(8)

        if cabecera != b"\x89HDF\r\n\x1a\n":
            print("ERROR: no se recibió un HDF5 válido")
            continue

        if h5py is not None:
            with h5py.File(temporal, "r") as h:
                if "Grid/precipitation" not in h:
                    raise ValueError("Falta Grid/precipitation")

        if archivo.stat().st_size != 0:
            print("OMITIDO: el archivo original cambió")
            continue

        os.replace(temporal, archivo)
        recuperados += 1

        print("RECUPERADO:", archivo.name)
        print("Tamaño:", archivo.stat().st_size, "bytes")

    except Exception as e:
        print("ERROR:", archivo.name, e)

    finally:
        if os.path.exists(temporal):
            os.remove(temporal)

print("\n=== RESULTADO ===")
print("Recuperados en esta ejecución:", recuperados)
print("Vacíos restantes:", sum(
    p.stat().st_size == 0
    for p in base.glob("*.HDF5")
))
