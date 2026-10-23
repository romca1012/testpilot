// Lot PT-00 (2026-10-13) — la nouvelle organisation « Paramètres de test » est-elle allumée sur cette installation ?
// Depuis le 2026-10-23 (porteur) : toujours. Des paramètres laissés vides ne sont simplement pas utilisés (A56).
//
// Un seul endroit pour le savoir : chaque écran concerné pose la même question, et un interrupteur lu de deux façons
// finirait par montrer la nouveauté à moitié.
import { computed } from 'vue'
import { useSettings } from './useSettings'

export const CLE_PARAMETRES_DE_TEST = 'parametres_de_test_enabled'

export function estAllume(valeur: string | undefined | null): boolean {
  return ['1', 'true', 'oui', 'on', 'yes'].includes(String(valeur ?? '').trim().toLowerCase())
}

export function useParametresDeTest() {
  const { loaded } = useSettings()
  // Porteur, 2026-10-23 : la case « Paramètres de test » des Paramètres du site est retirée — l'organisation est TOUJOURS
  // active (comptes, données de test, environnements dans chaque projet). La réponse reste posée ici, en un seul endroit.
  return { actifs: computed(() => true), connu: loaded }
}
