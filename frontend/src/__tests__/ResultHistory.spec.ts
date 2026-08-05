/**
 * L'historique des résultats d'un cas dans une campagne — pièces jointes (2026-08-05).
 *
 * ⚠️ Ce que ce fichier garde : les pièces jointes ne sont affichées QUE si elles existent, un
 * résultat sans fichier n'affiche rien de plus qu'avant (elle est TOUJOURS optionnelle), et le
 * lien de téléchargement pointe vers la route par IDENTIFIANTS NUMÉRIQUES du serveur, jamais
 * vers un nom de fichier — c'est la garde que le backend applique, l'écran ne doit rien inventer
 * qui la contourne.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ResultHistory from '../components/ResultHistory.vue'

const RESULTAT_SANS_PIECE = {
  id: 1, mode: 'automatique', statut: 'passed', statut_manuel: '', comment: '',
  created_by: 'TestPilot', created_at: '2026-08-03T12:54:00+00:00',
  execution_id: 119, execution_status: 'success', functional_status: 'conforme',
  attachments: [],
}

const RESULTAT_AVEC_PIECES = {
  id: 2, mode: 'manuelle', statut: 'blocked', statut_manuel: 'blocked',
  comment: 'environnement indisponible', created_by: 'Romaric',
  created_at: '2026-08-05T09:00:00+00:00',
  execution_id: null, execution_status: null, functional_status: null,
  attachments: [
    { id: 5, filename: 'capture-écran.png', content_type: 'image/png', size_bytes: 204800 },
    { id: 6, filename: 'journal.log', content_type: 'text/plain', size_bytes: 512 },
  ],
}

describe('ResultHistory — les pièces jointes d\'un résultat', () => {
  it('n\'affiche rien de plus quand il n\'y a aucune pièce jointe', () => {
    const w = mount(ResultHistory, { props: { results: [RESULTAT_SANS_PIECE] } })
    expect(w.find('a[href*="/attachments/"]').exists()).toBe(false)
  })

  it('liste chaque pièce jointe avec son nom et sa taille', () => {
    const w = mount(ResultHistory, { props: { results: [RESULTAT_AVEC_PIECES] } })

    expect(w.text()).toContain('capture-écran.png')
    expect(w.text()).toContain('journal.log')
    expect(w.text()).toContain('Ko')   // 204 800 octets → un affichage en Ko, pas en octets bruts
  })

  it('pointe vers la route par IDENTIFIANTS, jamais vers un nom de fichier', () => {
    const w = mount(ResultHistory, { props: { results: [RESULTAT_AVEC_PIECES] } })

    // ⚠️ `API_BASE` vaut `http://localhost:8000` sous Vitest (`import.meta.env.DEV`) : on ne
    // teste donc pas une égalité stricte d'URL, mais que le CHEMIN attendu y figure.
    const liens = w.findAll('a').map((a) => a.attributes('href') || '')
    expect(liens.some((h) => h.endsWith('/api/results/2/attachments/5'))).toBe(true)
    expect(liens.some((h) => h.endsWith('/api/results/2/attachments/6'))).toBe(true)
    expect(liens.some((h) => h.includes('capture-écran.png'))).toBe(false)
  })

  it('ne casse rien sur un résultat qui ne porte pas encore de champ attachments', () => {
    // Défaut réel rencontré en développant cette fonctionnalité : des fixtures de test plus
    // anciennes ne portent pas `attachments`, et `r.attachments.length` (sans `?.`) y plantait.
    const { attachments, ...sansChamp } = RESULTAT_SANS_PIECE
    expect(() => mount(ResultHistory, { props: { results: [sansChamp as any] } })).not.toThrow()
  })
})
