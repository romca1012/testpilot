// Quelles routes s'affichent SANS le shell de projet.
//
// ⚠️ **Ce n'est pas un réglage d'apparence.** Le shell (`CasesShell`) construit tous ses liens
// avec le `pid` lu dans l'URL. Une route hors de `/projects/:pid` qui l'utilise quand même fait
// lever à vue-router « Missing required param "pid" » PENDANT le rendu : la page reste
// **entièrement blanche**, sans message à l'écran, l'erreur n'existant que dans la console.
// Constaté le 2026-08-04 sur l'écran Réglages, et gardé par un test qui compare cette liste aux
// routes réellement déclarées.
export const ROUTES_SANS_SHELL = ['home', 'projects', 'admin-projects', 'settings', 'settings-general', 'settings-security', 'utilisateurs', 'utilisateur-detail', 'role-detail']
