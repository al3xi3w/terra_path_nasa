"""Build the offline farmer app's data file from the engine outputs.

    python scripts/build_app.py

Writes app/data/app_data.js. Open app/index.html in a browser, or serve the folder
(python -m http.server -d app) to enable offline caching with the service worker.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.app_export import write

if __name__ == '__main__':
    out, data = write()
    print(out)
    for p in data['pilots']:
        print(f"{p['id']:<11} {p['status']:<18} rutas {len(p['routes'])}  montaña {p['terrain']['mountain_warning']}  "
              f"primera helada {p['first_frost']}")
