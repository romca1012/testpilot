"""Application web locale à défauts injectables — cible du banc d'agents du connecteur web générique (lot Q2-b).

Pourquoi. Jusqu'ici seules des pages statiques de test existaient pour le connecteur `web` : impossible de mesurer
si un test GÉNÉRÉ par un agent détecte réellement un défaut (faux vert) sans accuser une application saine (faux
rouge). Cette petite boutique, en mémoire et sur loopback uniquement, a un comportement SAIN connu et six défauts
activables un par un (`defauts.py`). Lancement : `python -m banc.app_web.serveur --defauts total_faux`.
"""
