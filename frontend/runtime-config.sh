#!/bin/sh
# Génère la configuration du navigateur au démarrage du conteneur (image nginx officielle :
# les scripts de /docker-entrypoint.d/ s'exécutent avant nginx).
set -eu
cat > /usr/share/nginx/html/runtime-config.json <<JSON
{ "googleClientId": "${GOOGLE_CLIENT_ID:-}" }
JSON
if [ -n "${GOOGLE_CLIENT_ID:-}" ]; then
    echo "runtime-config.json généré (connexion Google configurée)"
else
    echo "runtime-config.json généré (GOOGLE_CLIENT_ID vide : connexion Google masquée)"
fi
