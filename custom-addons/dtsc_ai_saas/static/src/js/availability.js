/* Hide an already open assistant when the SaaS control plane disables it. */
(function () {
    'use strict';
    let checking = false;
    async function refresh() {
        if (checking || document.hidden || !document.querySelector('.o_dtsc_ai_assistant')) return;
        checking = true;
        try {
            const response = await fetch('/dtsc/ai_assistant/access', {cache: 'no-store'});
            const data = response.ok ? await response.json() : null;
            if (data && data.success === true && data.allowed === false) {
                document.querySelectorAll('.o_dtsc_ai_assistant').forEach(function (element) { element.remove(); });
            }
        } catch (error) {
            // A transient network error must not discard the user's open chat.
        } finally {
            checking = false;
        }
    }
    window.setInterval(refresh, 5000);
    document.addEventListener('visibilitychange', refresh);
}());
