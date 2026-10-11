# Intégration BazarStore × Odoo 19

Référence métier : cahier des charges « BazarStore × Odoo 19 » v1.0 (identifiants BZ, OD, IN, FI,
NF). Ce document décrit ce qui est **réellement implémenté**, les décisions prises et les limites.

## Principe

BazarStore reste une application e-commerce indépendante. Odoo 19 (édition Community) est l'ERP.

```
Odoo 19 ──(JSON-2, HTTPS, clé API)──► BazarStore API ──► catalogue Angular
           pull, délai max, retry       journal integration_sync_runs
```

BazarStore **lit** Odoo. Aucun point d'entrée public n'est exposé à Odoo pour ce flux. Si Odoo est
indisponible, le catalogue déjà publié reste servi depuis la base BazarStore (NF-02).

## Lot 1 : catalogue Odoo → BazarStore (implémenté)

### Source de vérité

| Donnée | Maître | Règle |
|---|---|---|
| Référence (`code` = `default_code`), nom, prix, statut, catégorie | Odoo | Écrasés à chaque synchronisation. **Verrouillés** dans le back-office BazarStore (409) pour un produit lié. |
| Stock publié | Odoo | `free_qty` Odoo **moins** les quantités des commandes BazarStore ouvertes (`confirmed`, `processing`, `shipped`) déjà décomptées. |
| Description | Odoo si renseignée | Une description de vente Odoo vide ne remplace pas la description BazarStore. |
| Image | BazarStore | Non synchronisée pour ce lot. |
| Prix des commandes passées | BazarStore | Figé dans `order_items.unit_price`, jamais modifié par la synchronisation (IN-05). |

**Convention de prix.** `lst_price` Odoo est un prix **TTC** en ariary : configurer la taxe de vente
Odoo à 20 % avec « Prix incluant la taxe ». Le prix est arrondi à l'ariary.

### Correspondance des identifiants

- `products.odoo_product_id` (unique) ↔ `product.product.id` (la variante).
- `product_categories.odoo_category_id` (unique) ↔ `product.category.id`.
- **Rapprochement initial :** un produit Odoo non lié est rattaché au produit BazarStore de même
  référence (`code` = `default_code`). Une catégorie est rattachée par son slug (par exemple,
  « High-tech & électronique » correspond à `high-tech-electronique`). À défaut, elle est créée.
- Odoo n'impose pas l'unicité de `default_code` : un second produit Odoo avec une référence déjà
  liée est **rejeté**, et non fusionné.

### Produits lus

Le flux lit les produits Odoo **actifs**, **vendables** (`sale_ok`) et de type **bien**
(`consu`). Il relit aussi les produits déjà liés, même archivés, pour les retirer de la vente
(IN-04).

Un produit lié disparu d'Odoo est désactivé. Cela n'arrive qu'après un **passage complet
réussi** : une panne en cours de route ne vide jamais le catalogue.

Chaque passage relit tout le catalogue, par pages de 200 produits. Une synchronisation
incrémentale sur `write_date` ne suffirait pas : un mouvement de stock ne modifie pas le
`write_date` du produit.

### Fiabilité

| Exigence | Mise en œuvre |
|---|---|
| FI-01, FI-02 | Clé API d'un utilisateur Odoo dédié (`Authorization: bearer`). `https://` obligatoire en production (vérifié au démarrage). |
| FI-04 | Chaque enregistrement est validé (`src/domain/integration/odoo_catalog.py`). Un enregistrement invalide est rejeté avec un motif, les autres sont appliqués. |
| FI-05 | `ODOO_TIMEOUT_SECONDS` par appel. |
| FI-06 | Nouvelles tentatives sur délai dépassé, erreur de connexion, 429 et 5xx, avec backoff exponentiel. Aucune nouvelle tentative sur 401, 403 ou 4xx. |
| FI-07, IN-03 | Mise à jour idempotente : un rejeu ne crée aucun doublon. Une seule synchronisation s'exécute à la fois. |
| FI-09 | `correlation_id` (UUID) sur chaque exécution, envoyé à Odoo (`X-Correlation-ID`) et présent dans les logs BazarStore. Odoo ne le journalise pas nativement. |
| FI-10 | Table `integration_sync_runs` : type, déclencheur, statut, durée, compteurs, motifs de rejet, erreur. |
| FI-13, FI-14, FI-15, IN-08 | Resynchronisation d'un produit ou du catalogue complet, à la demande. |

### Utilisation

Endpoints réservés aux administrateurs. Ils répondent 503 si `ODOO_SYNC_ENABLED=false`.

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/api/v1/integration/odoo/catalog/sync` | Catalogue complet (synchronisation initiale comprise) |
| `POST` | `/api/v1/integration/odoo/products/{odoo_product_id}/sync` | Un produit précis |
| `GET` | `/api/v1/integration/odoo/runs?limit=20` | Journal des exécutions |

Ligne de commande, à planifier par cron, par exemple toutes les 5 minutes :

```bash
uv run python -m scripts.sync_odoo_catalog              # catalogue
uv run python -m scripts.sync_odoo_catalog --product 42 # un produit
# Codes de sortie : 0 succès · 1 produits rejetés · 2 échec ou intégration coupée
```

Variables d'environnement : voir `ODOO_*` dans [`.env.example`](../.env.example).

## Environnement Odoo de développement

Utiliser la source Odoo 19 Community locale, avec une **base dédiée** `bazarstore_odoo`, séparée
d'AndaoHiasa. Le chemin des addons est passé en ligne de commande, et le module AndaoHiasa n'est
pas chargé.

```bash
cd ~/Documents/dev/learning/odoo/odoo
# 1. Création de la base (une fois)
.venv/bin/python odoo-bin server -c odoo.conf --addons-path=addons,odoo/addons \
  -d bazarstore_odoo -i sale_management,stock,sale_stock,purchase \
  --load-language=fr_FR --stop-after-init
# 2. Démarrage, en écoute locale uniquement
.venv/bin/python odoo-bin server -c odoo.conf --addons-path=addons,odoo/addons \
  -d bazarstore_odoo --db-filter='^bazarstore_odoo$' --http-interface=127.0.0.1
```

Ensuite, dans Odoo :

1. Créer un utilisateur « Intégration BazarStore » avec les droits Ventes / Utilisateur et
   Inventaire / Utilisateur.
2. Générer sa clé API (Préférences → Sécurité du compte → Clés API).
3. La placer dans `backend/.env`.
4. Configurer la taxe de vente « 20 %, prix incluant la taxe ».

## Tests

```bash
uv run pytest tests/unit/test_odoo_catalog.py tests/unit/test_odoo_client.py \
  tests/integration/test_odoo_catalog_sync.py tests/e2e/api/test_odoo_integration_api.py
```

Les tests n'ouvrent aucune connexion réseau : `httpx.MockTransport` simule Odoo pour le client,
et `tests/fakes_odoo.py` simule le catalogue pour la synchronisation.

Les scénarios du §12 « Nouveau produit » et « Changement de prix » sont couverts. Les cas suivants
le sont aussi : rejeu sans doublon, archivage, suppression, panne en cours de route, rejet d'un
enregistrement invalide, doublon de SKU, réservations de stock et droits d'accès.

## Limites connues et lots suivants

- **Stock** : jusqu'au lot 3, Odoo ignore les ventes web. Après livraison d'une commande BazarStore,
  le stock Odoo doit être ajusté manuellement.
- **Non synchronisés** : images, variantes (IN-07) et listes de prix ou promotions (OD-02). Chaque
  variante apparaît comme un produit distinct.
- **Délai** : il dépend de la fréquence du cron (polling). Un webhook Odoo (module CUS) est prévu
  au lot 4 pour le quasi temps réel.
- **Exécution synchrone** : la synchronisation tourne dans la requête HTTP, ce qui convient à un
  petit catalogue. Un catalogue volumineux demandera une tâche de fond.
- **Supervision** : pas encore d'écran dans Angular (FI-11) ni d'alertes (FI-12).

| Lot | Contenu |
|---|---|
| 2 | Clients BazarStore → Odoo. Prérequis : profil et adresses côté BazarStore. |
| 3 | Commandes → Odoo via une outbox, avec un module `bazarstore_connector` (référence BazarStore unique côté Odoo), puis arrêt de la facturation et du décompte de stock locaux. |
| 4 | Retours de statut, livraison et facture Odoo → BazarStore. |
| 5 | Supervision. |
