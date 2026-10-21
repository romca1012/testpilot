"""Remise à zéro de l'Odoo du banc (étape 4 du plan unique, décision A71 du porteur, 2026-10-20).

`POST /__reset` : la base `banc` est recréée depuis la base modèle `banc_modele` (figée par `scripts/banc_init.*` juste après
l'installation), puis les défauts du banc ACTIFS avant la remise à zéro (`ir.config_parameter` `tp_bug.<code>`) sont
réappliqués — sans cela, un défaut activé pour une mesure disparaîtrait à la première remise à zéro, et le test sortirait
vert sur une application devenue saine (mesure faussée). Réponse : `{"remis_a_zero": true}` (A75), seulement si tout a
réussi ; sinon une erreur 500 et le test n'est pas joué.

Banc SEULEMENT : TestPilot ne touche jamais lui-même une base (A71). Ce service ne vit que dans `compose.banc.yml`, derrière
le relais `nginx` qui sert Odoo et cette adresse sur la MÊME origine (règle « même application » de l'adresse déclarée).
Aucune dépendance hors de la bibliothèque standard et de `psycopg2` (présent dans l'image Odoo).
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg2

BASE, MODELE = "banc", "banc_modele"
_VERROU = threading.Lock()
# Requêtes sans paramètre : psycopg2 n'y interprète pas « % ». L'antislash échappe « _ » (joker d'un LIKE).
_DEFAUTS = r"SELECT key, value FROM ir_config_parameter WHERE key LIKE 'tp\_bug.%'"
_SIGNALISATION = (r"SELECT sequence_name FROM information_schema.sequences WHERE sequence_name LIKE "
                  r"'base\_registry\_signaling%' OR sequence_name LIKE 'base\_cache\_signaling%'")


def _connexion(base: str):
    c = psycopg2.connect(host=os.environ.get("PGHOST", "db"), user=os.environ.get("PGUSER", "odoo"),
                         password=os.environ.get("PGPASSWORD", "odoo"), dbname=base)
    c.autocommit = True
    return c


def defauts_actifs() -> dict[str, str]:
    with closing(_connexion(BASE)) as c, c.cursor() as cur:
        cur.execute(_DEFAUTS)
        return dict(cur.fetchall())


def remettre_a_zero() -> dict[str, str]:
    """Recrée `banc` depuis `banc_modele` et réapplique les défauts actifs. Rend les défauts réappliqués."""
    with _VERROU:
        defauts = defauts_actifs()
        with closing(_connexion("postgres")) as c, c.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s "
                        "AND pid <> pg_backend_pid()", (BASE,))
            cur.execute(f'DROP DATABASE IF EXISTS "{BASE}"')
            cur.execute(f'CREATE DATABASE "{BASE}" TEMPLATE "{MODELE}"')
        with closing(_connexion(BASE)) as c, c.cursor() as cur:
            for cle, valeur in defauts.items():
                cur.execute("UPDATE ir_config_parameter SET value = %s WHERE key = %s", (valeur, cle))
                if cur.rowcount == 0:
                    cur.execute("INSERT INTO ir_config_parameter (key, value, create_date, write_date) "
                                "VALUES (%s, %s, now(), now())", (cle, valeur))
            # Odoo garde son registre et ses caches en mémoire : on lui signale qu'ils ont changé (séquences de
            # signalisation lues à chaque requête), sinon il servirait l'état d'avant la remise à zéro.
            cur.execute(_SIGNALISATION)
            for (sequence,) in cur.fetchall():
                cur.execute(f"SELECT nextval('\"{sequence}\"')")
        return defauts


class _Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code: int, corps: dict) -> None:
        brut = json.dumps(corps).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(brut)))
        self.end_headers()
        self.wfile.write(brut)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path != "/__reset":
            return self._json(404, {"erreur": "adresse inconnue"})
        try:
            defauts = remettre_a_zero()
        except Exception as exc:  # jamais « remis » sans preuve : le test ne sera pas joué
            return self._json(500, {"remis_a_zero": False, "erreur": f"{type(exc).__name__}: {exc}"[:300]})
        return self._json(200, {"remis_a_zero": True, "defauts_reappliques": sorted(defauts)})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8070"))), _Gestionnaire).serve_forever()
