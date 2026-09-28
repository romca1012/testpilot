"""Profil d'instance SAPIAN, volet ODOO (touche `context.odoo`) — lot 06 (D6, F6).

Sort du socle commun (`behave_runtime/environment.py`) la restauration du champ
`employee_front_role_ids`, propre à Sapian — un rôle temporairement accordé par un step Sapian (via
`context._roles_to_restore`, jamais posé par le socle commun) doit être retiré en fin de scénario,
sur le même principe que le teardown générique (best-effort, jamais fatal).

⚠️ **Orphelin de tout step à ce jour** : aucun step de la bibliothèque ne pose
`context._roles_to_restore` (recherché dans tout `behave_runtime/`, aucune occurrence hors la
restauration elle-même — voir le rapport du lot). Conservé plutôt que supprimé : c'était déjà le
comportement du socle avant ce lot, silencieusement inactif faute d'un step qui l'alimente ; le
sortir du socle ne change rien à son (in)activité, seulement à SON EMPLACEMENT.

Copié par le runner sous `steps/_profil_connecteur.py` (nom CANONIQUE) SEULEMENT quand le projet
déclare `profil_instance = "sapian"` (`BehaveRunner._profil_files`) ; `environment.py` importe
`apres_scenario` de ce nom canonique, jamais du nom original de ce fichier.
"""


def apres_scenario(context) -> None:
    """Appelé par `environment.after_scenario`, APRÈS le teardown générique — restaure tout rôle
    temporairement accordé par un step Sapian (`context._roles_to_restore`, absent par défaut)."""
    odoo = getattr(context, "odoo", None)
    if odoo is None:
        return
    for user_id, role_id in getattr(context, "_roles_to_restore", []):
        try:
            odoo.env["res.users"].browse(user_id).write({"employee_front_role_ids": [(3, role_id)]})
        except Exception as exc:  # teardown best-effort : ne jamais masquer le verdict
            print(f"[profil sapian] rôle {role_id} non retiré de l'user {user_id} : {exc}")
