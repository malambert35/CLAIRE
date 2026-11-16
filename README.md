# CLAIRE

**Continuous Learning AI for Remembrance and Evolution**

A family-owned knowledge preservation platform with a replaceable AI layer.

Installation : [Unraid tout-en-un](#unraid--mode-tout-en-un) · [Windows local](#windows-local-start) · [Compose multi-conteneurs](#déploiement-de-test-sur-unraid) · [Développement](#quick-development-start)

The memory workspace creates and edits real Markdown/JSON archives with UUID provenance, immutable revisions, private/family visibility, source attribution, revision history, recoverable deletion, title search and a date-sorted view. Owner-only history preserves previous private versions when the current story is shared. PostgreSQL row-level policies and application checks enforce access. An offline recovery command reconciles the catalogue after an interrupted write.

Owners can download a memory and all its revisions as a portable ZIP with Markdown, JSON, schema and checksum manifest. Verify it offline with `uv run python -m claire.portable path/to/memory.zip`. See the [export and recovery guide](docs/recovery.md).

Import a CLAIRE ZIP from the memory list with verification, preview and explicit confirmation. It creates a new private copy with revision history and origin references; it never overwrites an existing memory or restores old sharing grants.

**Status: 0.1.0 under development, not production-ready.** Identity, the memory workflow and streaming local Ollama chat are implemented and tested. Semantic retrieval, document ingestion, integrations, automated backup and succession are not yet available. No fake AI or persistence responses are provided.

## Windows local start

Stop a previous local server with Ctrl+C, then run from the repository:

```powershell
.\scripts\start-local.ps1
```

This migrates the existing `data/dev.db`, builds the interface and starts http://localhost:8000. Existing accounts remain intact. To create your first account, add `-Email you@example.test -FamilyName 'My family'`; do not pass `-Email` again for an existing account. The local script uses SQLite for evaluation; Docker uses PostgreSQL.

Local chat defaults to Ollama at `http://127.0.0.1:11434` with `qwen3:8b`. Start Ollama and install a model first. The interface lists installed local models. Conversations are private and saved. Live keyword retrieval supplies up to three authorized memory excerpts to local Ollama. See [chat setup and limits](docs/chat.md).

Read the [architecture and six-phase checklist](docs/architecture.md), [installation guide](docs/install.md), [security model](SECURITY.md), and [recovery plan](docs/recovery.md).

## Unraid — mode tout-en-un

**Un seul conteneur**, un port web et un dossier appdata : cette variante regroupe CLAIRE, PostgreSQL 18 avec pgvector et le worker. L'initialisation de la base, les migrations et les identifiants techniques sont automatiques. Ollama reste sur votre serveur existant.

Cette variante est disponible pour essais, construite localement ; aucune image AIO n'est encore publiée sur Docker Hub. Les tests Docker couvrent le démarrage, la persistance, le redémarrage après interruption et l'arrêt des services. Une installation sur votre Unraid reste à valider. Utilisez **un nouveau dossier dédié**, sans y copier une ancienne base PostgreSQL 17.

Depuis le dossier du dépôt sur Unraid :

```sh
cp .env.aio.example .env.aio
```

Modifiez `.env.aio` avec vos adresses (exemple HTTP local) :

```dotenv
CLAIRE_AIO_DATA_PATH=/mnt/user/appdata/claire-aio
CLAIRE_BIND_IP=192.168.1.50
CLAIRE_PORT=8000
CLAIRE_ORIGIN=http://192.168.1.50:8000
CLAIRE_SECURE_COOKIES=false
CLAIRE_LLM_BASE_URL=http://192.168.1.60:11434
CLAIRE_LLM_MODEL=qwen3:8b
```

`192.168.1.50` est ici l'adresse d'Unraid ; `192.168.1.60` celle d'Ollama. Ollama doit être joignable depuis Docker et avoir le modèle installé. Le port interne de CLAIRE reste `8000`. PostgreSQL écoute uniquement à l'intérieur du conteneur ; **ne publiez pas le port 5432**.

```sh
docker compose --env-file .env.aio -f docker-compose.aio.yml up -d --build
docker compose --env-file .env.aio -f docker-compose.aio.yml ps
docker logs --tail=100 claire-aio
```

Attendez l'état `healthy`, puis créez votre compte avec cette commande unique :

```sh
docker exec -it claire-aio python -m claire.aio create-user vous@example.ca --family-name 'Ma famille' --role family_admin
```

Entrez un mot de passe d'au moins 14 caractères, puis connectez-vous à `http://192.168.1.50:8000`. Il n'y a pas de compte par défaut. Conservez l'identifiant de famille affiché : pour un autre membre, utilisez `--family-id UUID` au lieu de créer une nouvelle famille.

**N'utilisez pas les étapes de création manuelle des secrets ou de PostgreSQL du guide multi-conteneurs ci-dessous pour le mode AIO.** N'appliquez pas non plus `PUID`, `PGID` ou un utilisateur forcé au conteneur AIO : son coordinateur initialise les permissions comme root, puis lance le serveur et le worker sous UID 10001, et PostgreSQL sous son propre utilisateur. Aucun mode `privileged` ni socket Docker n'est nécessaire.

Les données se trouvent dans le seul volume `/data` :

| Sous-dossier | Contenu |
| --- | --- |
| `archive/` | Textes Markdown, métadonnées et versions des souvenirs |
| `postgres/` | Comptes, conversations et catalogue PostgreSQL 18 |
| `secrets/` | Identifiant technique généré automatiquement, réservé au coordinateur |

Pour arrêter proprement : `docker stop --time 120 claire-aio`. Pour redémarrer : `docker start claire-aio`. Après changement de configuration ou mise à jour du code, relancez la commande Compose `up -d --build`. Sauvegardez **tout le dossier appdata, conteneur arrêté**, en préservant propriétaires et permissions ; protégez cette copie, car elle contient les données privées et le secret technique. Ne partagez pas ce dossier par SMB. L'import ZIP permet de récupérer des souvenirs comme nouvelles copies privées, pas de migrer automatiquement les comptes ou conversations de l'ancien mode.

Voir le [guide AIO détaillé](docs/all-in-one.md) pour les réglages Unraid manuels, les limites et le dépannage.

## Déploiement de test sur Unraid

Cette section décrit l'architecture **multi-conteneurs** historique. Pour le mode à un seul conteneur, utilisez la section précédente et `docker-compose.aio.yml` seul.

Les instructions ci-dessous utilisent **Docker Compose**, depuis le terminal Unraid. Docker et Compose v2 doivent être disponibles (`docker compose version`). L'installation complète sur Unraid et la restauration après perte du serveur restent à valider : conservez vos originaux ailleurs pendant les essais.

### Quels conteneurs sont nécessaires ?

PostgreSQL fonctionne **dans Docker, dans un conteneur séparé de CLAIRE**. Le fichier Compose crée et relie les services suivants :

| Service | Fonction | Port interne | Port à exposer sur Unraid |
| --- | --- | --- | --- |
| `claire-app` | Interface et API | TCP `8000` | `8000`, ou un autre port hôte libre |
| `claire-db` | PostgreSQL avec pgvector | TCP `5432` | Aucun : accès par le réseau Docker |
| `claire-worker` | Processus de fond | Aucun | Aucun |
| `migrate` | Initialisation/migration du schéma, puis arrêt | Aucun | Aucun |
| `claire-ollama` | Moteur IA facultatif | TCP `11434` | Aucun si utilisé dans ce Compose |

Vous n'avez pas à ajouter manuellement un conteneur PostgreSQL lorsque vous utilisez ce Compose. L'application contacte `claire-db:5432`. Un seul conteneur créé via « Add Container » dans Unraid ne remplace pas cet ensemble.

### 1. Récupérer et configurer le projet

Aucune image de version n'est encore publiée sur Docker Hub : construisez-la depuis le dépôt. Avec Git disponible, dans le terminal Unraid :

```sh
mkdir -p /mnt/user/appdata/claire
git clone https://github.com/malambert35/CLAIRE.git /mnt/user/appdata/claire/source
cd /mnt/user/appdata/claire/source
cp .env.example .env
```

Si le dépôt existe déjà, utilisez son dossier au lieu de le cloner de nouveau. Sans Git, téléchargez et extrayez le dépôt complet, puis ouvrez un terminal dans le dossier contenant `docker-compose.yml` et `Dockerfile`.

Exemple de `.env` pour un **essai HTTP sur le réseau local**, avec Unraid à `192.168.1.50` (remplacez cette adresse par la vôtre) :

```dotenv
CLAIRE_PORT=8000
CLAIRE_ORIGIN=http://192.168.1.50:8000
CLAIRE_SECURE_COOKIES=false

CLAIRE_DATA_PATH=/mnt/user/appdata/claire/archive
CLAIRE_DB_PATH=/mnt/user/appdata/claire/postgres
CLAIRE_MODELS_PATH=/mnt/user/appdata/claire/models
CLAIRE_SECRET_PATH=/mnt/user/appdata/claire/secrets

PUID=10001
PGID=10001

CLAIRE_LLM_BASE_URL=http://claire-ollama:11434
CLAIRE_LLM_MODEL=qwen3:8b
```

| Variable | Utilisation |
| --- | --- |
| `CLAIRE_PORT` | Port hôte de l'interface ; le port interne reste `8000` |
| `CLAIRE_ORIGIN` | Adresse exacte saisie dans le navigateur, protocole et port compris, sans `/` final |
| `CLAIRE_SECURE_COOKIES` | `false` pour cet essai HTTP local ; `true` avec HTTPS |
| `CLAIRE_DATA_PATH` | Archives Markdown/JSON, montées dans `/data` |
| `CLAIRE_DB_PATH` | Données PostgreSQL, montées dans `/var/lib/postgresql/data` |
| `CLAIRE_MODELS_PATH` | Modèles du service Ollama facultatif, montés dans `/root/.ollama` |
| `CLAIRE_SECRET_PATH` | Dossier des trois fichiers secrets décrits ci-dessous |
| `PUID`, `PGID` | Identité Linux de CLAIRE, du worker et des migrations ; ne modifie pas celle de PostgreSQL |
| `CLAIRE_LLM_BASE_URL` | Adresse d'Ollama accessible depuis le conteneur CLAIRE |
| `CLAIRE_LLM_MODEL` | Modèle installé à sélectionner par défaut |

Les variables `*_PATH`, `CLAIRE_PORT`, `PUID` et `PGID` servent à configurer Compose ; elles ne sont pas toutes des variables internes de l'application.

### 2. Autoriser l'accès depuis le réseau local

Par défaut, le Compose publie CLAIRE sur `127.0.0.1` uniquement. Pour cet essai sur le LAN, **remplacez** la ligne `ports` de `claire-app` dans `docker-compose.yml` par :

```yaml
    ports: ["192.168.1.50:${CLAIRE_PORT:-8000}:8000"]
```

Ne l'ajoutez pas comme une seconde ligne. Utilisez l'IP réelle d'Unraid. Ouvrez ensuite `http://192.168.1.50:8000`. Si vous choisissez un autre port hôte, adaptez aussi `CLAIRE_ORIGIN`. N'utilisez pas `docker-compose.dev.yml` pour cet exemple : il force l'origine à `http://localhost:8000`.

Pour un reverse proxy HTTPS, utilisez plutôt `CLAIRE_ORIGIN=https://claire.votre-domaine.ca` et `CLAIRE_SECURE_COOKIES=true`. Si le proxy est lui-même dans un conteneur, son `127.0.0.1` ne désigne pas Unraid : il doit pouvoir joindre le port publié ou partager un réseau Docker avec CLAIRE. Préservez les réponses en streaming, avec un délai suffisant pour l'inférence (180 secondes par défaut). Limitez les requêtes ordinaires à 16 Kio, et autorisez 34 Mio uniquement sur `/api/v1/memory-import/preview` et `/api/v1/memory-import/confirm`.

### 3. Préparer les volumes et les secrets

Exécutez ces commandes comme administrateur Unraid pour une nouvelle installation :

```sh
mkdir -p /mnt/user/appdata/claire/archive /mnt/user/appdata/claire/postgres /mnt/user/appdata/claire/models /mnt/user/appdata/claire/secrets
chown 10001:10001 /mnt/user/appdata/claire/archive
chmod 700 /mnt/user/appdata/claire/archive /mnt/user/appdata/claire/secrets
```

Adaptez le propriétaire d'`archive` si vous changez `PUID`/`PGID`. Ces variables ne corrigent pas automatiquement les permissions des fichiers existants. Ne changez pas récursivement le propriétaire du dossier PostgreSQL vers l'utilisateur CLAIRE. Placez la base sur un stockage local adapté, idéalement le pool/cache prévu pour appdata ; ne déplacez pas ses fichiers pendant qu'elle tourne.

Créez dans `secrets` les fichiers suivants, avec un éditeur local. Utilisez **deux mots de passe aléatoires différents**, pas les exemples :

| Fichier | Contenu sur une seule ligne |
| --- | --- |
| `db_password` | Mot de passe brut de `claire_owner` |
| `owner_database_url` | `postgresql+psycopg://claire_owner:MOT_DE_PASSE_OWNER_ENCODE@claire-db/claire` |
| `database_url` | `postgresql+psycopg://claire_runtime:MOT_DE_PASSE_RUNTIME_ENCODE@claire-db/claire` |

Dans les URL, encodez les caractères spéciaux des mots de passe au format URL ; `db_password` contient toujours la valeur brute correspondante. Compose monte uniquement les secrets nécessaires à chaque service. L'application et le worker utilisent `CLAIRE_DATABASE_URL_FILE=/run/secrets/database_url` ; les migrations utilisent `/run/secrets/owner_database_url`.

Avec les identifiants par défaut, réglez les permissions après création :

```sh
chown root:10001 /mnt/user/appdata/claire/secrets/database_url /mnt/user/appdata/claire/secrets/owner_database_url
chmod 440 /mnt/user/appdata/claire/secrets/database_url /mnt/user/appdata/claire/secrets/owner_database_url
chown root:root /mnt/user/appdata/claire/secrets/db_password
chmod 444 /mnt/user/appdata/claire/secrets/db_password
```

Le dossier parent `secrets` reste en `700`, réservé à l'administrateur sur l'hôte. Le mode de `db_password` permet au processus PostgreSQL de lire le fichier monté, quel que soit son UID dans l'image. Ne partagez pas ce dossier par SMB et ne commitez jamais ces fichiers.

### 4. Initialiser la base et le premier compte

Depuis le dossier du dépôt, avec `.env` et les secrets en place :

```sh
docker compose config --quiet
docker compose build
docker compose up -d claire-db
docker compose run --rm migrate
docker compose exec -T claire-db psql -v ON_ERROR_STOP=1 -U claire_owner -d claire < infrastructure/docker/runtime-role.sql
docker compose exec claire-db psql -U claire_owner -d claire
```

Dans `psql`, saisissez :

```text
\password claire_runtime
```

Entrez le mot de passe **brut** correspondant à `database_url`, confirmez-le, puis tapez `\q`. Le script `runtime-role.sql` est destiné à la première installation : il crée le rôle, ne le réexécutez pas à chaque démarrage. Modifier `db_password` après initialisation ne change pas automatiquement le mot de passe d'une base existante.

Créez ensuite le compte familial :

```sh
docker compose run --rm --entrypoint python migrate -m claire.cli vous@example.ca --family-name 'Ma famille' --role family_admin
docker compose up -d claire-app claire-worker
```

Le mot de passe du compte est demandé interactivement et doit contenir au moins 14 caractères. **Il n'existe aucun identifiant ou mot de passe par défaut.** Les comptes créés dans la base SQLite de Windows ne sont pas automatiquement transférés vers PostgreSQL. Pour ajouter une personne à la même famille, utilisez `--family-id UUID` avec l'identifiant donné lors de la création initiale ; sans cette option, une autre famille est créée.

### 5. Brancher Ollama

**Ollama intégré au Compose** : gardez `CLAIRE_LLM_BASE_URL=http://claire-ollama:11434`, puis lancez :

```sh
docker compose --profile local-ai up -d claire-ollama
docker compose exec claire-ollama ollama pull qwen3:8b
```

Le profil fourni utilise le CPU et une limite mémoire de 8 Gio pour Ollama ; adaptez les ressources au modèle. Le passthrough GPU Unraid n'est pas encore validé. Les modèles restent dans `CLAIRE_MODELS_PATH`.

**Ollama déjà installé ailleurs** : ne démarrez pas le service facultatif et configurez, par exemple :

```dotenv
CLAIRE_LLM_BASE_URL=http://192.168.1.60:11434
CLAIRE_LLM_MODEL=qwen3:8b
```

Le serveur Ollama doit écouter sur une adresse joignable depuis CLAIRE et autoriser cette connexion. `localhost` ou `127.0.0.1` dans CLAIRE désigne son propre conteneur, pas Unraid. Après modification du `.env`, recréez les services avec `docker compose up -d claire-app claire-worker`. Aucun port Ollama n'a besoin d'être exposé à Internet.

### 6. Vérifier, arrêter et mettre à jour

```sh
docker compose ps
docker compose logs --tail=100 claire-app claire-worker claire-db
curl --fail http://192.168.1.50:8000/healthz
curl --fail http://192.168.1.50:8000/readyz
```

Connectez-vous, créez un souvenir fictif, rechargez la page, vérifiez le chat Ollama et faites un export/import ZIP. La recherche du chat utilise actuellement des mots-clés ; mentionnez un nom ou un détail du souvenir.

Si la connexion échoue : vérifiez l'origine exacte, `CLAIRE_SECURE_COOKIES=false` pour HTTP local, les permissions des secrets, le mot de passe de `claire_runtime` et les journaux. Un port web inaccessible peut venir du binding `127.0.0.1` resté inchangé ou d'un port déjà occupé.

Pour arrêter : `docker compose stop`. Les données restent dans les dossiers montés. Avant une mise à jour, arrêtez les écritures et sauvegardez ensemble la base et les archives ; conservez les secrets séparément. Mettez ensuite le code à jour en préservant votre `.env` et votre adaptation du port, reconstruisez, migrez et redémarrez :

```sh
docker compose stop claire-app claire-worker
# Mettre à jour le code ici, après sauvegarde.
docker compose build
docker compose run --rm migrate
docker compose up -d claire-app claire-worker
```

Les ZIP préservent des souvenirs individuels, pas l'ensemble des comptes et conversations. Les sauvegardes automatiques et la restauration complète sur un nouvel hôte restent à développer/valider. Voir le [guide de préservation](docs/recovery.md).

## Quick development start

Requires Python 3.12+, uv, Node 22+, and Docker Compose v2 for PostgreSQL.

```sh
uv sync --frozen
cd apps/frontend
npm ci
npm run build
cd ../..
uv run pytest
uv run ruff check apps/backend tests
```

For a disposable local smoke test only, SQLite can run the identity foundation:

```sh
export CLAIRE_DATABASE_URL=sqlite:///./data/dev.db
export CLAIRE_ORIGIN=http://localhost:8000
export CLAIRE_SECURE_COOKIES=false
export CLAIRE_STATIC_DIR=apps/frontend/dist
mkdir -p data
uv run alembic upgrade head
uv run python -m claire.cli you@example.test --family-name 'Example family' --role family_admin
uv run uvicorn claire.main:create_app --factory --host 127.0.0.1
```

Open http://localhost:8000. SQLite is a test convenience, not the production database. Account passwords are entered interactively, never embedded in scripts. Add another family member with `--family-id UUID`; omission creates a separate household.

## API

OpenAPI JSON: `/openapi.json`. FastAPI documentation: `/docs` (the strict CSP currently blocks CDN Swagger assets; use the JSON specification with a local client).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Process health |
| GET | `/readyz` | Database and migration readiness |
| POST | `/api/v1/auth/login` | Opaque secure session |
| GET | `/api/v1/auth/me` | Current identity and CSRF token |
| POST | `/api/v1/auth/logout` | Revoke session |
| GET | `/api/v1/family/members` | Current household only |
| GET | `/api/v1/capabilities` | Implemented feature flags |
| GET/POST | `/api/v1/memories` | Authorized list/title search and confirmed creation |
| GET/PUT | `/api/v1/memories/{id}` | Read or revise; owner-only writes |
| GET | `/api/v1/memories/{id}/history` | Owner-only revision history |
| POST | `/api/v1/memories/{id}/delete` | Recoverable deletion |
| POST | `/api/v1/memories/{id}/restore` | Restore previous visibility |

Mutations require an exact configured Origin; authenticated mutations also require `X-CSRF-Token`. Session cookies are HttpOnly, Secure, SameSite=Strict by default. There is no public registration or default account.

## License and dependencies

Apache-2.0. Dependency versions are locked in `uv.lock` and `apps/frontend/package-lock.json`. See [third-party notices](docs/third-party.md). Deployment images are version-pinned; digest verification and vulnerability scans are release gates, not an assertion that old pins remain safe indefinitely.
