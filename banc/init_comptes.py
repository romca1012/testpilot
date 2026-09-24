# -*- coding: utf-8 -*-
"""Exécuté par `odoo shell` (banc_init) : deux comptes de test, langue `fr_FR` pour tous.

  banc_commercial : Ventes / Utilisateur (ses documents)
  banc_manager    : Ventes / Administrateur + Stock / Administrateur + Facturation / Conseiller

Mots de passe JETABLES, valables sur le banc seulement (jamais sur une instance client).
"""
LANG = "fr_FR"
env["res.lang"]._activate_lang(LANG)  # noqa: F821  (env fourni par `odoo shell`)


def groupes(*xmlids):
    return [(4, env.ref(x).id) for x in xmlids]  # noqa: F821


COMPTES = [
    ("banc_commercial", "Commercial banc", "banc-commercial",
     groupes("base.group_user", "sales_team.group_sale_salesman")),
    ("banc_manager", "Manager banc", "banc-manager",
     groupes("base.group_user", "sales_team.group_sale_manager", "stock.group_stock_manager",
             "account.group_account_manager")),
]
for login, nom, mot_de_passe, groups in COMPTES:
    utilisateur = env["res.users"].with_context(no_reset_password=True).search(  # noqa: F821
        [("login", "=", login)], limit=1)
    valeurs = {"name": nom, "login": login, "password": mot_de_passe, "lang": LANG, "groups_id": groups}
    if utilisateur:
        utilisateur.write(valeurs)
    else:
        env["res.users"].with_context(no_reset_password=True).create(valeurs)  # noqa: F821

# Langue fr_FR aussi pour l'administrateur (les libellés de menu que TestPilot explore sont en français).
env.ref("base.user_admin").write({"lang": LANG})  # noqa: F821
env.cr.commit()  # noqa: F821
print("banc_init_comptes: OK")
