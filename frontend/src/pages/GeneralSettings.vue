<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import Button from '../components/ui/Button.vue'
import { api, type SettingOut, type TimezoneOption } from '../lib/api'
import { useSession } from '../lib/useSession'
import { useSettings } from '../lib/useSettings'

const { session } = useSession()
const { ensureLoaded } = useSettings()
const estAdmin = computed(() => session.value?.role === 'admin')
const loading = ref(true)
const saving = ref(false)
const erreur = ref('')
const succes = ref('')
const initial = ref<Record<string, string>>({})
const form = reactive({
  instance_name: 'TestPilot',
  instance_timezone: 'Europe/Paris',
  date_format: 'DD/MM/YYYY',
})

const formats = [
  { value: 'DD/MM/YYYY', label: 'Jour / Mois / Année', example: '25/08/2026' },
  { value: 'YYYY-MM-DD', label: 'Année-Mois-Jour', example: '2026-08-25' },
  { value: 'MM/DD/YYYY', label: 'Mois / Jour / Année', example: '08/25/2026' },
]
const fuseaux = ref<TimezoneOption[]>([])
const modifie = computed(() => Object.entries(form).some(([k, v]) => initial.value[k] !== v))
const nomValide = computed(() => form.instance_name.trim().length >= 2 && form.instance_name.trim().length <= 80)

function appliquer(reglages: SettingOut[]) {
  const valeurs = Object.fromEntries(reglages.map((r) => [r.key, r.value]))
  form.instance_name = valeurs.instance_name || 'TestPilot'
  form.instance_timezone = valeurs.instance_timezone || 'Europe/Paris'
  form.date_format = valeurs.date_format || 'DD/MM/YYYY'
  initial.value = { ...form }
}

async function charger() {
  loading.value = true
  erreur.value = ''
  try {
    const [reglages, options] = await Promise.all([api.listSettings(), api.listTimezoneOptions()])
    fuseaux.value = options
    appliquer(reglages)
    if (!fuseaux.value.some((f) => f.value === form.instance_timezone)) {
      form.instance_timezone = fuseaux.value[0]?.value || 'Europe/Paris'
    }
  }
  catch (e: any) { erreur.value = e?.message || 'Impossible de charger les paramètres généraux.' }
  finally { loading.value = false }
}

function annuler() {
  Object.assign(form, initial.value)
  erreur.value = ''
  succes.value = ''
}

async function enregistrer() {
  if (!estAdmin.value || !nomValide.value || !modifie.value) return
  saving.value = true
  erreur.value = ''
  succes.value = ''
  try {
    await Promise.all(Object.entries(form).map(([cle, valeur]) => api.setSetting(cle, valeur.trim())))
    appliquer(await api.listSettings())
    await ensureLoaded(true)
    succes.value = 'Paramètres généraux enregistrés.'
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally { saving.value = false }
}

onMounted(charger)
</script>

<template>
  <div class="mx-auto max-w-4xl px-4 py-6 sm:px-6 md:py-8">
    <header class="max-w-3xl">
      <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Administration</div>
      <h1 class="mt-1 text-2xl font-semibold tracking-tight">Paramètres généraux</h1>
      <p class="mt-2 text-sm leading-6 text-muted-foreground">
        Ces valeurs s’appliquent à toute l’instance et servent de référence à tous les projets.
      </p>
    </header>

    <p v-if="!estAdmin" role="alert" class="mt-5 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">
      Consultation uniquement : seul un administrateur peut modifier ces paramètres.
    </p>
    <p v-if="erreur" role="alert" class="mt-5 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{{ erreur }}</p>
    <p v-if="succes" role="status" class="mt-5 rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">{{ succes }}</p>
    <p v-if="loading" class="mt-6 text-sm text-muted-foreground" aria-live="polite">Chargement…</p>

    <form v-else class="mt-6 rounded-xl border border-border bg-surface-raised shadow-sm" @submit.prevent="enregistrer">
      <div class="space-y-6 p-4 sm:p-6">
        <label class="block max-w-xl">
          <span class="text-sm font-medium">Nom de l’instance</span>
          <input v-model="form.instance_name" :disabled="!estAdmin" maxlength="80" required
                 aria-describedby="instance-name-help instance-name-error"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:cursor-not-allowed disabled:opacity-60" />
          <span id="instance-name-help" class="mt-1.5 block text-xs text-muted-foreground">Affiché dans l’administration et le titre du navigateur. 2 à 80 caractères.</span>
          <span v-if="!nomValide" id="instance-name-error" class="mt-1 block text-xs text-destructive">Saisissez entre 2 et 80 caractères.</span>
        </label>

        <div class="grid gap-5 sm:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium">Fuseau horaire</span>
            <select v-model="form.instance_timezone" :disabled="!estAdmin" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:opacity-60">
              <option v-for="f in fuseaux" :key="f.value" :value="f.value">{{ f.label }} — {{ f.value }}</option>
            </select>
            <span class="mt-1.5 block text-xs text-muted-foreground">Les dates restent stockées en UTC puis sont affichées dans ce fuseau.</span>
          </label>
          <div class="rounded-lg border border-border bg-surface px-4 py-3">
            <div class="text-sm font-medium">Langue de l’interface</div>
            <div class="mt-1 text-sm">Français</div>
            <p class="mt-1.5 text-xs text-muted-foreground">L’anglais sera proposé lorsqu’une traduction complète sera disponible.</p>
          </div>
        </div>

        <label class="block max-w-xl">
          <span class="text-sm font-medium">Format de date</span>
          <select v-model="form.date_format" :disabled="!estAdmin" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:opacity-60">
            <option v-for="f in formats" :key="f.value" :value="f.value">{{ f.label }} — {{ f.example }}</option>
          </select>
          <span class="mt-1.5 block text-xs text-muted-foreground">Aperçu : {{ formats.find((f) => f.value === form.date_format)?.example }} à 14:35</span>
        </label>
      </div>

      <div class="flex flex-col-reverse gap-3 border-t border-border bg-surface px-4 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-6">
        <Button type="button" variant="secondary" size="lg" :disabled="!modifie || saving" @click="annuler">Annuler</Button>
        <Button type="submit" variant="primary" size="lg" :loading="saving" :disabled="!estAdmin || !modifie || !nomValide">Enregistrer</Button>
      </div>
    </form>
  </div>
</template>
