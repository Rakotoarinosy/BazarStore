# BazarStore

BazarStore est une boutique en ligne en français, pensée pour présenter un catalogue et permettre
aux clients de créer un compte. Le dépôt contient une application Angular pour la boutique et le
backoffice, ainsi qu’une API FastAPI pour l’authentification et la gestion des comptes.

## Fonctionnalités actuelles

- Boutique publique avec recherche, catégories, favoris et panier local.
- Prix de démonstration affichés en ariary (Ar).
- Inscription et connexion par e-mail et mot de passe.
- Connexion Google Identity, si OAuth est configuré.
- Gestion des utilisateurs côté API avec les rôles `customer`, `commercial` et `admin`.
- Les inscriptions publiques créent un compte `customer`. L’administrateur initial est créé au
  démarrage depuis la configuration du backend.
- Interface de backoffice basée sur le template Sakai.

Le catalogue et le panier sont actuellement des données d’exemple gérées côté frontend. La
validation des commandes, le paiement, l’enregistrement serveur du panier et la synchronisation
du catalogue avec une base ne sont pas encore connectés. L’API gère actuellement l’authentification
et les comptes, pas encore les commandes ou les produits.

## Technologies

- **Frontend :** Angular 21, TypeScript, PrimeNG et Sakai.
- **Backend :** Python 3.12+, FastAPI, SQLAlchemy 2 et Alembic.
- **Base locale par défaut :** SQLite.
- **Base cible possible :** PostgreSQL via `DATABASE_URL`.

## Prérequis

- Node.js et npm compatibles avec Angular 21.
- Python 3.12 ou plus récent.
- `make` et, au choix, `uv` ou `pip` pour installer le backend.
- Docker est facultatif.

## Lancer en développement

### 1. Démarrer l’API

Dans un terminal :

```bash
cd backend
make install
```

La commande crée `backend/.env` depuis `.env.example` si le fichier n’existe pas. Configure au
minimum le secret JWT et les identifiants de l’administrateur initial dans ce fichier, puis lance :

```bash
make migrate
make dev
```

L’API démarre sur <http://localhost:8000>. La documentation est disponible sur
<http://localhost:8000/docs> en environnement de développement.

### 2. Démarrer le frontend

Dans un second terminal :

```bash
cd frontend
npm install
npm start -- --port 4300
```

Ouvre <http://localhost:4300>. Le serveur Angular transmet les requêtes `/api/v1` à l’API locale
sur le port `8000` via `frontend/proxy.conf.json`.

## Configurer la connexion Google

1. Crée un client OAuth de type **Application Web** dans Google Cloud.
2. Ajoute `http://localhost:4300` aux origines JavaScript autorisées.
3. Dans `backend/.env`, renseigne `GOOGLE_CLIENT_ID` avec l’identifiant public du client.
4. Pour le développement local, crée `frontend/public/runtime-config.local.json` avec le même
   identifiant :

   ```json
   {
     "googleClientId": "TON_IDENTIFIANT_CLIENT.apps.googleusercontent.com"
   }
   ```

`runtime-config.json` est le fichier de base suivi par Git et garde un identifiant vide. Le fichier
`runtime-config.local.json` surcharge cette valeur en développement et est ignoré par Git. En
production, injecte la configuration remplie au déploiement sans la commiter. L’identifiant client
est public, mais le secret OAuth ne doit jamais être placé dans le frontend ni partagé dans une
capture d’écran. Les fichiers `.env` et `.sql` sont également ignorés par Git.

## Rôles des comptes

| Rôle | Utilisation |
|---|---|
| `customer` | Rôle par défaut des inscriptions publiques et des connexions Google nouvellement créées. |
| `commercial` | Accès de gestion au backoffice selon les routes protégées par le backend. |
| `admin` | Administration complète, y compris la gestion des comptes et des rôles. |

Le premier administrateur est créé au démarrage si aucun administrateur actif n’existe. Configure
`BOOTSTRAP_ADMIN_EMAIL` et `BOOTSTRAP_ADMIN_PASSWORD` dans `backend/.env`; retire ensuite le mot de
passe d’amorçage du fichier.

## Base de données et migrations

Le développement utilise SQLite par défaut. Alembic possède une migration initiale BazarStore qui
crée les tables `users` et `refresh_tokens` :

```bash
cd backend
make migrate
```

Pour PostgreSQL, configure `DATABASE_URL` dans `backend/.env`, par exemple :

```dotenv
DATABASE_URL=postgresql+psycopg://utilisateur:mot_de_passe@localhost:5432/bazarstore
```

Puis applique les migrations avec `make migrate`. Vérifie que la base cible est vide ou sauvegardée
avant d’initialiser son schéma. Les fichiers SQL locaux ne sont pas versionnés.

## Commandes utiles

Depuis `backend/` :

```bash
make help       # commandes disponibles
make test       # tests backend
make lint       # vérifications statiques
make revision m="description"  # créer une migration Alembic
```

Depuis `frontend/` :

```bash
npm start -- --port 4300  # serveur de développement
npm run build             # build de production
npm test                  # tests frontend
```

## Déploiement

Chaque push sur `main` est testé puis déployé automatiquement par GitHub Actions (Docker, VPS) :

- site : https://bazarstore.rakotoarinosy.com
- API : https://api.bazarstore.rakotoarinosy.com

Installation du serveur, secrets et exploitation : voir [deploy/README.md](deploy/README.md).

## Structure du dépôt

```text
.
├── backend/       # API FastAPI, authentification, utilisateurs et migrations
├── frontend/      # boutique Angular, pages d’authentification et backoffice
└── README.md      # guide général du projet
```

Pour les détails propres à chaque application, consulte [backend/README.md](backend/README.md) et
[frontend/README.md](frontend/README.md).
