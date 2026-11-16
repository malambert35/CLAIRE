# CLAIRE AIO — un seul conteneur pour Unraid

Le mode AIO combine le serveur web, PostgreSQL 18/pgvector et le worker. Le Compose à un seul service est `docker-compose.aio.yml`. Il ne faut pas le fusionner avec `docker-compose.yml`. Le démarrage rapide se trouve dans le [README](../README.md#unraid--mode-tout-en-un).

## Installation sans Compose

L'image de test linux/amd64 est publiée sur Docker Hub. Dans Unraid, utilisez **`malambert35/claire:aio`** dans le champ Repository. Pour la télécharger depuis un terminal :

```sh
docker pull malambert35/claire:aio
```

Pour une configuration manuelle dans Unraid, utilisez ces réglages :

| Champ | Valeur |
| --- | --- |
| Nom du conteneur | `claire-aio` |
| Repository | `malambert35/claire:aio` |
| Réseau | Bridge |
| Port conteneur | `8000` TCP |
| Port hôte | `8000`, ou un port libre correspondant à l'origine |
| Chemin conteneur | `/data` |
| Chemin hôte | `/mnt/user/appdata/claire-aio`, dossier neuf et dédié |
| `CLAIRE_ORIGIN` | URL exacte du navigateur, par exemple `http://192.168.1.50:8000` |
| `CLAIRE_SECURE_COOKIES` | `false` pour cet essai HTTP local ; `true` pour HTTPS |
| `CLAIRE_LLM_BASE_URL` | URL de votre Ollama existant, par exemple `http://192.168.1.60:11434` |
| `CLAIRE_LLM_MODEL` | Modèle installé, par exemple `qwen3:8b` |

Paramètres Docker supplémentaires correspondant au Compose :

```text
--stop-timeout=120 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=128m --tmpfs /run:rw,noexec,nosuid,size=32m --security-opt no-new-privileges --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --cap-add SETUID --cap-add SETGID --cap-add KILL
```

Ne forcez pas l'utilisateur du conteneur et n'activez pas le mode privilégié. Les processus applicatifs restent non-root ; le coordinateur root prépare les permissions, initialise la base et supervise les utilisateurs séparés. La base n'est accessible que sur loopback et son socket interne. Le compte applicatif n'est ni superutilisateur, ni propriétaire du schéma, et ne contourne pas RLS. Un compte PostgreSQL d'administration par authentification locale peer est réservé aux opérations internes.

Ne publiez pas `5432`. N'ajoutez pas les variables `CLAIRE_DATABASE_URL` ou `CLAIRE_DATABASE_URL_FILE` : le mode AIO gère et impose sa propre connexion. Les chemins `CLAIRE_AIO_DATA_PATH`, `CLAIRE_BIND_IP` et `CLAIRE_PORT` servent au fichier Compose, pas à l'application dans l'interface Docker manuelle.

## Premier compte et autres membres

Une fois le conteneur sain :

```sh
docker exec -it claire-aio python -m claire.aio create-user vous@example.ca --family-name 'Ma famille' --role family_admin
docker exec -it claire-aio python -m claire.aio create-user membre@example.ca --family-id UUID_AFFICHE --role member
```

La première commande est à exécuter une seule fois pour ce compte. Les mots de passe sont saisis interactivement, jamais intégrés dans l'image ou prédéfinis.

## Persistance, arrêt et récupération

- Gardez le même dossier `/data` lors du remplacement du conteneur. Les sous-dossiers sont initialisés automatiquement ; ne les attribuez pas tous au même UID et n'appliquez pas une correction récursive des permissions Unraid.
- Accordez 120 secondes à l'arrêt. Le coordinateur arrête d'abord le serveur web et le worker, puis demande un arrêt PostgreSQL propre. Une défaillance d'un processus provoque l'arrêt de l'ensemble, afin que la politique Docker de redémarrage puisse repartir dans un état cohérent.
- Un verrou exclusif refuse deux conteneurs AIO sur le même dossier. N'exécutez jamais un serveur PostgreSQL séparé sur ces fichiers.
- Une base PostgreSQL d'une autre version majeure est refusée. L'ancien mode Compose utilise PostgreSQL 17 : changer simplement son montage vers AIO n'est pas une migration. Le transfert complet de cette installation demande une procédure explicite de dump/restore et de reprise des identités, non fournie à ce stade.
- Si `initdb` a été interrompu, un dossier non vide sans `PG_VERSION` est refusé. Préservez les fichiers et examinez les journaux ; ne supprimez pas aveuglément le dossier.
- Les migrations sont automatiques au démarrage. Sauvegardez avant de mettre à jour. Le retour à une image antérieure après migration n'est pas une procédure de rollback validée.

Pour une copie cohérente du volume : arrêtez le conteneur, copiez l'intégralité du dossier appdata en préservant propriétaires et permissions, puis redémarrez. Ne copiez pas les fichiers PostgreSQL à chaud. Stockez les sauvegardes de façon protégée/chiffrée : elles contiennent les données privées et le secret technique. Les sauvegardes planifiées, la restauration sur un nouvel hôte Unraid et les mises à jour majeures PostgreSQL restent des travaux séparés.

## Vérifications et limites

```sh
docker inspect --format '{{.State.Health.Status}}' claire-aio
docker logs --tail=100 claire-aio
docker exec claire-aio python -m claire.aio health
```

Le test `scripts/aio_smoke.py --image claire:aio` crée un volume jetable distinct et vérifie l'initialisation, la création de comptes, l'isolation entre familles, les privilèges SQL, les permissions de fichiers, pgvector, le remplacement du conteneur, la récupération après arrêt brutal et l'arrêt de l'ensemble après panne du worker. Il ne doit pas être utilisé comme preuve d'une restauration complète sur Unraid. La CI construit et scanne cette variante séparément de l'image standard.

Ollama, ses modèles et son éventuel GPU restent externes. Aucun mécanisme de sauvegarde automatique ou assistant web de premier compte n'est inclus dans ce jalon. L'image standard construite sans `--target aio` reste distincte. La publication AIO est une préversion linux/amd64, pas une version stable multi-architecture.

Le workflow manuel **Publish AIO preview to Docker Hub** construit, teste et scanne la même image avant de la pousser. Il utilise les secrets GitHub `DOCKERHUB_USERNAME` et `DOCKERHUB_TOKEN` ; le jeton doit disposer de Read & Write sur le dépôt. Il publie le tag mobile `aio` et un tag `aio-<12 premiers caractères du commit>`. La première publication est `aio-7586e3136408`. Pour une construction locale indépendante : `docker build --target aio -t claire:aio-local .`.
