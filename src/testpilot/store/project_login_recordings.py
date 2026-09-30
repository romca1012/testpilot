"""La séquence de connexion confirmée d'un projet — sous-lot C du lot « Enregistrement assisté du
chemin de connexion », étendu (2026-09-30) au descripteur du formulaire de connexion lui-même
(champ identifiant, champ mot de passe, bouton de soumission) — motivé par un échec réel en
production de la détection générique (`tenter_connexion_generique` devine le champ identifiant par
premier match DOM et soumet à l'aveugle via la touche Entrée, ce qui a raté sur une application
réelle malgré des identifiants valides).

⚠️ **Une seule séquence ACTIVE par projet, jamais un historique.** Une nouvelle confirmation
remplace la précédente sans laisser de trace de l'ancienne — `project_id` est UNIQUE, l'écriture
est un UPSERT SQL (`ON CONFLICT(project_id) DO UPDATE`), pas un `DELETE` suivi d'un `INSERT` (qui
laisserait une fenêtre sans aucune séquence enregistrée entre les deux, visible d'une lecture
concurrente). `login_form` suit la MÊME règle que `etapes` : une confirmation qui n'a pas atteint
les 3 clics guidés du formulaire REMPLACE un descripteur précédemment enregistré par « aucun »,
jamais un mélange ancien/nouveau — une session confirmée est un tout, jamais rafistolée avec des
morceaux d'une session antérieure.
"""

from __future__ import annotations

import json

from testpilot.store.repositories import now_iso

Etape = dict[str, str]  # {"role": ..., "name": ...} — jamais un autre champ, jamais un secret.

# Descripteur du formulaire de connexion, capturé par 3 clics guidés (jamais un secret, jamais une
# valeur — seulement rôle/nom, comme `Etape`). Les 3 clés sont TOUJOURS toutes les trois présentes
# quand le descripteur existe : un formulaire partiellement identifié ne serait pas rejouable et
# ne doit jamais être stocké à moitié (voir `live_session_service.py::_traiter_clic_formulaire`).
LoginForm = dict[str, Etape]  # {"champ_identifiant": ..., "champ_mdp": ..., "bouton_soumission": ...}


def enregistrer(conn, *, project_id: int, etapes: list[Etape], recorded_by_user_id: int,
                 login_form: LoginForm | None = None) -> None:
    """Remplace la séquence active du projet par `etapes` (et son `login_form`, ou aucun) —
    c'est l'écriture de l'étape 6 (confirmation explicite), jamais appelée avant que la personne
    n'ait validé ce qu'elle voit."""
    conn.execute(
        "INSERT INTO project_login_recording "
        "(project_id, steps_json, recorded_at, recorded_by_user_id, login_form_json) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(project_id) DO UPDATE SET "
        "steps_json=excluded.steps_json, recorded_at=excluded.recorded_at, "
        "recorded_by_user_id=excluded.recorded_by_user_id, "
        "login_form_json=excluded.login_form_json",
        (project_id, json.dumps(etapes, ensure_ascii=False), now_iso(), recorded_by_user_id,
         json.dumps(login_form, ensure_ascii=False) if login_form else ""))
    conn.commit()


def lire(conn, project_id: int) -> list[Etape] | None:
    """La séquence active du projet, ou `None` si aucune n'a jamais été confirmée — jamais une
    liste vide pour « pas de séquence », qui serait indiscernable d'une séquence enregistrée sans
    aucune étape."""
    ligne = conn.execute(
        "SELECT steps_json FROM project_login_recording WHERE project_id=?", (project_id,)
    ).fetchone()
    if ligne is None:
        return None
    return json.loads(ligne["steps_json"])


def lire_formulaire(conn, project_id: int) -> LoginForm | None:
    """Le descripteur du formulaire de connexion du projet, ou `None` si aucun n'a jamais été
    capturé (projet jamais passé par les 3 clics guidés, ou enregistré avant cette extension) —
    l'appelant (`generic_web.py`) retombe alors sur `tenter_connexion_generique`, comportement
    inchangé."""
    ligne = conn.execute(
        "SELECT login_form_json FROM project_login_recording WHERE project_id=?", (project_id,)
    ).fetchone()
    if ligne is None or not ligne["login_form_json"]:
        return None
    return json.loads(ligne["login_form_json"])


def supprimer(conn, project_id: int) -> bool:
    """Retire la séquence active — la personne a annulé/recommencé APRÈS une confirmation
    antérieure, ou le porteur veut forcer un nouvel enregistrement. Rend `False` si rien n'existait
    déjà (idempotent, jamais une erreur sur un projet jamais enregistré)."""
    curseur = conn.execute("DELETE FROM project_login_recording WHERE project_id=?", (project_id,))
    conn.commit()
    return curseur.rowcount > 0
