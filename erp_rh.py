#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ERP RH Burkina — lancement.

    python erp_rh.py                 démarre sur http://127.0.0.1:8650 (poste local uniquement)
    python erp_rh.py --demo          base de démonstration séparée (données fictives)
    python erp_rh.py --host 0.0.0.0 --cert cert.pem --key key.pem     accès réseau local en HTTPS
"""
import argparse, os, sys, webbrowser, threading

if sys.version_info < (3, 9):
    sys.exit("Python 3.9 ou plus récent est requis.")

ap = argparse.ArgumentParser(description="ERP RH Burkina")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8650)
ap.add_argument("--cert")
ap.add_argument("--key")
ap.add_argument("--demo", action="store_true", help="base de démonstration (dossier data_demo)")
ap.add_argument("--no-browser", action="store_true")
args = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
if args.demo:
    os.environ["ERP_RH_DATA"] = os.path.join(here, "data_demo")

from erp import core, schema, entites, rapports, vues  # noqa: E402  (l'ordre enregistre les routes)

schema.init_db()
if args.demo:
    from erp import demo
    demo.charger()
core.backup_if_needed()

if args.host not in ("127.0.0.1", "localhost") and not (args.cert and args.key):
    print("ATTENTION : accès réseau sans HTTPS. Les mots de passe et les salaires circuleraient en clair.\n"
          "            Fournissez --cert et --key (voir README) ou restez en 127.0.0.1.")
srv = core.serve(args.host, args.port, args.cert, args.key)
url = f"http{'s' if args.cert else ''}://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
print(f"ERP RH Burkina démarré : {url}\nDonnées : {core.DATA_DIR}\nCtrl+C pour arrêter.")
if not args.no_browser:
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    print("\nArrêt.")
