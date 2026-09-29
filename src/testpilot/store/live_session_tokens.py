"""Jeton d'accès à usage unique d'une session live — sous-lot B du lot « Enregistrement assisté
du chemin de connexion ».

⚠️ **Jamais le jeton en clair en base.** Seul son hash (SHA-256 — entropie déjà suffisante pour un
jeton aléatoire de 32 octets, contrairement à un mot de passe choisi par un humain ; pas besoin
d'un hash lent). Le jeton en clair n'existe qu'une fois, dans la valeur de retour de `creer()`.

⚠️ **Consommation ATOMIQUE, en une seule écriture conditionnelle.** Une lecture (« est-il valide ? »)
suivie d'une écriture séparée (« marque-le utilisé ») ouvrirait une fenêtre de course : deux
connexions WebSocket simultanées avec le même jeton pourraient toutes les deux le lire comme
valide avant qu'aucune ne l'ait marqué consommé. `UPDATE ... WHERE used_at='' AND expires_at>?`
ferme cette fenêtre : au plus UNE des deux tentatives peut affecter une ligne.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from testpilot.store.repositories import now_iso

DUREE_VIE_SECONDES = 300  # 5 minutes — court, comme un lien de réinitialisation de mot de passe.


def _hash(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def creer(conn, *, project_id: int, created_by_user_id: int,
          duree_vie_secondes: int = DUREE_VIE_SECONDES) -> tuple[str, str]:
    """Crée un jeton, rend `(jeton_en_clair, expires_at)` — le jeton en clair n'est JAMAIS relisible
    depuis la base ensuite, c'est la seule fois qu'il existe sous cette forme."""
    jeton = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=duree_vie_secondes)).isoformat()
    conn.execute(
        "INSERT INTO live_session_token "
        "(project_id, created_by_user_id, token_hash, created_at, expires_at) VALUES (?,?,?,?,?)",
        (project_id, created_by_user_id, _hash(jeton), now_iso(), expires_at))
    conn.commit()
    return jeton, expires_at


def consommer(conn, jeton: str) -> dict | None:
    """Consomme le jeton s'il est valide (existe, jamais utilisé, non expiré) — `None` sinon, pour
    N'IMPORTE laquelle de ces raisons : la distinction n'a aucune valeur pour l'appelant, qui
    refuse dans les trois cas, jamais un indice qui aiderait à deviner un jeton valide par
    tâtonnement (jeton inconnu, jeton mal formé : `_hash` d'une chaîne quelconque ne correspond
    simplement à aucune ligne — aucune validation de forme séparée n'est nécessaire)."""
    maintenant = now_iso()
    empreinte = _hash(jeton)
    curseur = conn.execute(
        "UPDATE live_session_token SET used_at=? "
        "WHERE token_hash=? AND used_at='' AND expires_at > ?",
        (maintenant, empreinte, maintenant))
    conn.commit()
    if curseur.rowcount != 1:
        return None
    ligne = conn.execute(
        "SELECT project_id, created_by_user_id FROM live_session_token WHERE token_hash=?",
        (empreinte,)).fetchone()
    return dict(ligne) if ligne else None
