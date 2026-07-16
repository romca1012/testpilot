"""Donne le rôle `group_expert_metier` au compte de test, DANS L'ENVIRONNEMENT Odoo.

Pourquoi ici et pas dans le scénario (arbitrage du porteur) : **un test ne doit pas fabriquer les
conditions de son propre succès**. Le rôle est une donnée d'ENVIRONNEMENT stable, comme les
produits ou les catégories ; un test qui se l'auto-attribue teste un monde qu'il a fabriqué —
et ne prouverait plus que l'accès fonctionne pour un vrai utilisateur habilité.

Contexte : les 5 scénarios du cas 5 (« Achat véhicule ») échouaient. Sonde
(`probe_achat_vehicule.py`) : l'application fonctionne PARFAITEMENT — module `custom_website`
installé, service 114 présent, route en 200 — mais le compte de test n'a pas le rôle exigé par la
spec, donc Odoo redirige vers `/home`, exactement comme documenté. Prérequis absent, ni bug
applicatif ni défaut de génération.

⚠️ Écrit dans la base Odoo de TEST (jamais la prod : `ODOO_ENV=prod` fait échouer le harnais).
Idempotent, et réversible (le rôle s'enlève par le même chemin).

Usage : PYTHONUTF8=1 python scripts/env_donner_role_expert_metier.py
"""

from urllib.parse import urlparse

import odoorpc

from testpilot import config
from testpilot.api.services.run_service import resolve_connection
from testpilot.store.db import get_initialized_db

CASE_ID = 5
FRONT_ROLE = "group_expert_metier"


def main() -> None:
    conn = get_initialized_db(config.DB_PATH)
    cx = resolve_connection(conn, CASE_ID)
    conn.close()

    p = urlparse(cx.get("ODOO_URL", "http://localhost:10017"))
    odoo = odoorpc.ODOO(p.hostname or "localhost", protocol="jsonrpc", port=p.port or 8069)
    odoo.login(cx.get("ODOO_DB"), cx.get("ODOO_USER"), cx.get("ODOO_PASSWORD"))

    roles = odoo.env["user.front.role"].search_read(
        [("front_role", "=", FRONT_ROLE)], ["name", "front_role"])
    if not roles:
        print(f"ÉCHEC : aucun rôle avec front_role={FRONT_ROLE!r} sur cette instance.")
        return
    role = roles[0]
    print(f"rôle cible : id={role['id']} {role['name']!r} ({role['front_role']})")

    user = odoo.env["res.users"].browse(odoo.env.uid)
    avant = [r.id for r in user.employee_front_role_ids]
    print("utilisateur :", user.login, f"(uid={odoo.env.uid})")
    print("rôles AVANT :", len(avant))

    if role["id"] in avant:
        print("déjà présent — rien à faire (idempotent).")
        return

    # (4, id) = lier un enregistrement existant, sans toucher aux autres rôles.
    user.write({"employee_front_role_ids": [(4, role["id"])]})

    apres = [r.id for r in odoo.env["res.users"].browse(odoo.env.uid).employee_front_role_ids]
    print("rôles APRÈS :", len(apres))
    ok = role["id"] in apres
    print(f"{FRONT_ROLE} accordé :", ok)
    if ok and set(avant).issubset(set(apres)):
        print("les rôles préexistants sont intacts.")


if __name__ == "__main__":
    main()
