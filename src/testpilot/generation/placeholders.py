"""Valeurs de remplacement partagées entre le harnais de qualification (qui MASQUE) et les outils d'écriture
(qui REFUSENT) : une seule définition, pour que les deux ne divergent jamais."""

# Ce que le harnais de qualification met à la place d'un secret du projet dans tout ce que voit l'IA
# (`QualificationLLM._redact`). Ce n'est JAMAIS une valeur saisissable : un test qui la contient a recopié le
# masque au lieu d'une vraie valeur.
SECRET_MASQUE = "[secret]"
