# Déploiement de BazarStore (Docker + GitHub Actions)

| | |
|---|---|
| Site | https://bazarstore.rakotoarinosy.com (le site relaie `/api/v1` vers l'API) |
| API | https://api.bazarstore.rakotoarinosy.com (webhook Stripe, accès direct) |
| Serveur | VPS BazarStore (217.76.49.226), dossier `/srv/BazarStore` |
| Images | `ghcr.io/rakotoarinosy/bazarstore-backend` et `-frontend` (privées) |
| Stockage des images produit | MinIO du VPS AndaoHiasa (port 9000 filtré sur l'IP du VPS BazarStore) |

## Comment ça marche

```
git push main ──► GitHub Actions
                   ├─ backend : ruff + pytest
                   ├─ frontend : ng build --configuration production
                   ├─ images Docker → GHCR (tag = commit + latest)
                   └─ SSH sur le VPS : copie de docker-compose.yml, pull, up -d, vérification HTTPS

VPS BazarStore
  nginx (HTTPS, certbot) ──► 127.0.0.1:4270  conteneur web  (Angular + relais /api/ → api)
                         └─► 127.0.0.1:8070  conteneur api  (FastAPI, migrations au démarrage)
                                               └─► conteneur db (PostgreSQL 16, volume)
                                               └─► MinIO du VPS AndaoHiasa :9000
```

Une pull request lance seulement les tests et le build : rien n'est déployé.

---

## Installation (une seule fois)

### 1. DNS

Créer deux enregistrements **A** vers l'IP du VPS BazarStore :

```
bazarstore.rakotoarinosy.com       A   <IP_VPS_BAZARSTORE>
api.bazarstore.rakotoarinosy.com   A   <IP_VPS_BAZARSTORE>
```

### 2. VPS BazarStore : Docker, nginx, certbot

```bash
# Docker (si absent)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"          # puis se reconnecter

# nginx + certbot
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

### 3. Utilisateur et clé SSH de déploiement

Sur ta machine, générer une clé **dédiée** au déploiement :

```bash
ssh-keygen -t ed25519 -C "github-actions-bazarstore" -f ~/.ssh/bazarstore_deploy -N ""
ssh-copy-id -i ~/.ssh/bazarstore_deploy.pub <utilisateur>@<IP_VPS_BAZARSTORE>
```

L'utilisateur doit faire partie du groupe `docker`. Si tu réutilises la clé de l'action AndaoHiasa, ajoute seulement sa clé publique dans `~/.ssh/authorized_keys` du VPS BazarStore.

### 4. Dossier de l'application et `backend/.env`

Sur le serveur, il n'y a **qu'un seul fichier à remplir** : `backend/.env`.

```
/srv/BazarStore/
├── docker-compose.yml   copié par la CI (celui de la racine du dépôt)
├── backend/.env         variables de production : à remplir (chmod 600)
└── .env                 généré par la CI à chaque déploiement : ne pas modifier
```

Depuis ta machine, envoyer le modèle :

```bash
ssh fehizoro@217.76.49.226 "mkdir -p /srv/BazarStore/backend"
scp deploy/.env.production.example fehizoro@217.76.49.226:/srv/BazarStore/backend/.env
```

Puis, sur le serveur, générer les secrets sans qu'ils quittent le VPS :

```bash
cd /srv/BazarStore
SECRET=$(openssl rand -hex 32); PG=$(openssl rand -hex 24)
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|; s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PG|; s|MOT_DE_PASSE_POSTGRES|$PG|" backend/.env
chmod 600 backend/.env
nano backend/.env    # admin, Google, MinIO, Stripe…
```

`GOOGLE_CLIENT_ID` sert aussi au site : son conteneur génère `runtime-config.json` au démarrage.

### 5. nginx + HTTPS

```bash
sudo cp bazarstore.conf /etc/nginx/sites-available/bazarstore.conf   # fichier deploy/nginx/bazarstore.conf
sudo ln -s /etc/nginx/sites-available/bazarstore.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d bazarstore.rakotoarinosy.com -d api.bazarstore.rakotoarinosy.com
```

Certbot ajoute le HTTPS, la redirection HTTP → HTTPS et le renouvellement automatique. Si `WEB_PORT` ou `API_PORT` changent dans `backend/.env`, il faut aussi les changer dans ce fichier.

### 6. MinIO sur le VPS AndaoHiasa

Ces commandes se lancent **sur le VPS AndaoHiasa**.

**a) Une clé MinIO dédiée à BazarStore**, limitée à son bucket. On ne réutilise pas la clé root.

```bash
docker exec -it andaohiasa-minio sh -c '
  mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" &&
  mc mb --ignore-existing local/bazarstore-products &&
  cat > /tmp/bazarstore-rw.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::bazarstore-products"] },
    { "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::bazarstore-products/*"] }
  ]
}
EOF
  mc admin policy create local bazarstore-rw /tmp/bazarstore-rw.json &&
  mc admin user add local bazarstore "CHOISIR_UN_SECRET_LONG" &&
  mc admin policy attach local bazarstore-rw --user bazarstore'
```

Dans `backend/.env` de BazarStore : `MINIO_ACCESS_KEY=bazarstore`, `MINIO_SECRET_KEY=<le secret choisi>` et `MINIO_ENDPOINT=<IP_VPS_ANDAOHIASA>:9000`.

**b) Filtrer le port 9000 sur l'IP du VPS BazarStore.**

> ⚠️ Les ports publiés par Docker **contournent UFW**. Le filtrage doit se faire dans la chaîne `DOCKER-USER` d'iptables.

```bash
BAZAR_IP=<IP_VPS_BAZARSTORE>
EXT_IF=$(ip route show default | awk '{print $5; exit}')   # interface publique (ex. eth0)

# Refuser le port 9000 depuis Internet sauf pour le VPS BazarStore.
# Les conteneurs AndaoHiasa passent par le réseau Docker interne : non concernés.
sudo iptables -I DOCKER-USER -i "$EXT_IF" -p tcp --dport 9000 ! -s "$BAZAR_IP" -j DROP
# Console MinIO (9001) : pas besoin d'accès public non plus.
sudo iptables -I DOCKER-USER -i "$EXT_IF" -p tcp --dport 9001 -j DROP

# Rendre les règles permanentes
sudo apt install -y iptables-persistent && sudo netfilter-persistent save
```

Vérification depuis le VPS BazarStore : `curl -s -o /dev/null -w "%{http_code}\n" http://<IP_VPS_ANDAOHIASA>:9000/minio/health/live` doit répondre `200`. Depuis une autre machine, la même commande doit expirer.

Ce choix (port en HTTP filtré par IP) fait circuler les images produit en clair entre les deux VPS. Pour chiffrer ce trafic plus tard, on peut passer MinIO derrière un sous-domaine HTTPS (`MINIO_ENDPOINT=https://s3.…`) : le code BazarStore le gère déjà.

### 7. Secrets GitHub

Dans le dépôt, aller dans **Settings → Secrets and variables → Actions → New repository secret** :

| Secret | Valeur |
|---|---|
| `VPS_HOST` | IP ou nom du VPS BazarStore |
| `VPS_USER` | utilisateur SSH (membre du groupe docker) |
| `VPS_PRIVATE_KEY` | contenu de `~/.ssh/bazarstore_deploy` (clé **privée**) |
| `VPS_PORT` | facultatif, si SSH n'écoute pas sur le port 22 |

Les images GHCR sont privées, mais **rien à configurer sur le VPS** : le déploiement utilise le jeton GitHub éphémère du workflow (`docker login`, `pull`, puis `docker logout`).

### 8. Services externes

- **Stripe** (dashboard → Developers → Webhooks) : endpoint `https://api.bazarstore.rakotoarinosy.com/api/v1/orders/payments/stripe/webhook`, événement `checkout.session.completed`. Mettre le `whsec_…` dans `STRIPE_WEBHOOK_SECRET`.
- **Google Cloud** (client OAuth) : ajouter `https://bazarstore.rakotoarinosy.com` dans les « Origines JavaScript autorisées ».

### 9. Premier déploiement

Pousser sur `main`, ou lancer le workflow **CI/CD** à la main (onglet Actions → Run workflow). Au premier démarrage :

- les migrations créent les tables ;
- l'administrateur `BOOTSTRAP_ADMIN_EMAIL` est créé. **Retirer ensuite `BOOTSTRAP_ADMIN_PASSWORD` de `backend/.env`** ;
- le catalogue est vide : créer les catégories et les produits depuis le backoffice. Leurs images partent dans MinIO.

---

## Exploitation

```bash
cd /srv/BazarStore
docker compose ps                   # état des conteneurs
docker compose logs -f api          # journaux de l'API (JSON)
docker compose up -d                # après une modification de backend/.env (recrée les conteneurs)
```

**Revenir à une version précédente** : mettre le commit voulu dans `IMAGE_TAG=` du `.env` de la racine (la CI y écrit le commit déployé), puis :

```bash
echo "<jeton GitHub read:packages>" | docker login ghcr.io -u Rakotoarinosy --password-stdin
docker compose pull && docker compose up -d
docker logout ghcr.io
```

Si la version la plus récente a appliqué une migration, il faut d'abord la défaire : `docker compose exec api alembic downgrade -1`.

**Sauvegarde de la base** (par exemple une tâche cron quotidienne) :

```bash
docker compose -f /srv/BazarStore/docker-compose.yml exec -T db \
  pg_dump -U bazarstore bazarstore | gzip > /srv/BazarStore/backups/bazarstore-$(date +%F).sql.gz
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `.github/workflows/ci-cd.yml` | Tests, build, images, déploiement, vérification HTTPS |
| `docker-compose.yml` (racine) | Conteneurs db, api, web (copié sur le VPS par la CI) |
| `deploy/.env.production.example` | Modèle de `backend/.env` en production |
| `deploy/nginx/bazarstore.conf` | Site nginx de l'hôte (avant certbot) |
| `backend/Dockerfile` | Image de l'API (dépendances figées, migrations au démarrage) |
| `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/runtime-config.sh` | Image du site (build Angular, relais `/api/`, configuration Google générée au démarrage) |
