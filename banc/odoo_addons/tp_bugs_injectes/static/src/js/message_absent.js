/* Défaut `message_absent` (banc de mesure) : aucun message d'erreur n'est VISIBLE sur un champ requis vide.
 * N'agit que si le serveur déclare le défaut actif (`/tp_bugs/actifs`) — sinon l'interface est inchangée.
 * JS simple (pas de framework OWL) : identique sur 16.0, 17.0 et 18.0. */
(function () {
    "use strict";
    fetch("/tp_bugs/actifs", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {}}),
    }).then(function (r) { return r.json(); }).then(function (data) {
        if ((data.result || []).indexOf("message_absent") === -1) { return; }
        var style = document.createElement("style");
        style.textContent =
            ".o_notification.border-danger, .o_notification_manager .o_notification, " +
            ".o_field_invalid, .o_form_editable .o_field_invalid { display: none !important; }";
        document.head.appendChild(style);
    }).catch(function () { /* jamais bloquant */ });
})();
