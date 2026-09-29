"""La séquence de connexion confirmée d'un projet — sous-lot C du lot « Enregistrement assisté du
chemin de connexion ».

⚠️ **Une seule séquence ACTIVE par projet, jamais un historique.** Une nouvelle confirmation
remplace la précédente sans laisser de trace de l'ancienne — `project_id` est UNIQUE, l'écriture
est un UPSERT SQL (`ON CONFLICT(project_id) DO UPDATE`), pas un `DELETE` suivi d'un `INSERT` (qui
laisserait une fenêtre sans aucune séquence enregistrée entre les deux, visible d'une lecture
concurrente).
"""

from __future__ import annotations

import json

from testpilot.store.repositories import now_iso

Etape = dict[str, str]  # {"role": ..., "name": ...} — jamais un autre champ, jamais un secret.


def enregistrer(conn, *, project_id: int, etapes: list[Etape], recorded_by_user_id: int) -> None:
    """Remplace la séquence active du projet par `etapes` — c'est l'écriture de l'étape 6
    (confirmation explicite), jamais appelée avant que la personne n'ait validé ce qu'elle voit."""
    conn.execute(
        "INSERT INTO project_login_recording "
        "(project_id, steps_json, recorded_at, recorded_by_user_id) VALUES (?,?,?,?) "
        "ON CONFLICT(project_id) DO UPDATE SET "
        "steps_json=excluded.steps_json, recorded_at=excluded.recorded_at, "
        "recorded_by_user_id=excluded.recorded_by_user_id",
        (project_id, json.dumps(etapes, ensure_ascii=False), now_iso(), recorded_by_user_id))
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


def supprimer(conn, project_id: int) -> bool:
    """Retire la séquence active — la personne a annulé/recommencé APRÈS une confirmation
    antérieure, ou le porteur veut forcer un nouvel enregistrement. Rend `False` si rien n'existait
    déjà (idempotent, jamais une erreur sur un projet jamais enregistré)."""
    curseur = conn.execute("DELETE FROM project_login_recording WHERE project_id=?", (project_id,))
    conn.commit()
    return curseur.rowcount > 0
