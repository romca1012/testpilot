"""Tests rapides du routage des outils PostgreSQL, sans serveur externe."""

from scripts.sauvegarder_postgresql import _pg_connection_env


def test_url_transmet_explicitement_la_base_aux_outils_postgresql():
    env, dbname = _pg_connection_env(
        "postgresql+psycopg://alice:secret@db.example:5433/autrebase"
    )

    assert dbname == "autrebase"
    assert env["PGDATABASE"] == "autrebase"
    assert env["PGHOST"] == "db.example"
    assert env["PGPORT"] == "5433"
    assert env["PGUSER"] == "alice"
    assert env["PGPASSWORD"] == "secret"
