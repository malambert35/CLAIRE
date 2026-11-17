# Configurer Immich MCP depuis CLAIRE

Connectez-vous avec un compte `family_admin`, ouvrez **Intégrations → Immich MCP**, puis :

1. Saisissez l’adresse réseau accessible depuis le conteneur CLAIRE, par exemple `http://192.168.1.20:5000/mcp`. Le port doit correspondre au port publié de votre serveur MCP. `localhost` et `127.0.0.1` ne désignent pas l’hôte Unraid depuis CLAIRE et sont refusés.
2. Si un proxy protège votre serveur MCP avec un jeton Bearer, saisissez ce jeton. Ce champ est facultatif : l’image `barryw/immichmcp` standard n’exige pas ce jeton. **Ce n’est pas la clé API Immich.**
3. Cochez **Activer la connexion Immich**, confirmez le serveur et l’accès à sa bibliothèque, puis **Enregistrer la connexion**.
4. Cliquez sur **Tester la connexion**. CLAIRE initialise une session MCP, découvre les outils et appelle `immich_ping` pour vérifier aussi la connexion entre MCP et Immich.
5. Consultez **Médias récents**, **Albums Immich**, ou recherchez un **nom de fichier**. Les premières lignes sont affichées, sans copier les originaux.

Le test est également disponible lorsque la connexion est désactivée. Les autres lectures exigent son activation. Après modification du formulaire, enregistrez avant de tester. Un champ jeton vide conserve le jeton enregistré ; la case **Supprimer le jeton enregistré** l’efface. Changer de serveur exige de remplacer ou d’effacer le jeton, pour ne pas transmettre involontairement le secret de l’ancien serveur.

## Compte Immich et confidentialité

Le [serveur barryw/ImmichMCP](https://github.com/barryw/ImmichMCP) utilise `IMMICH_BASE_URL` et `IMMICH_API_KEY` définis dans son propre conteneur. Son [gestionnaire d’authentification](https://github.com/barryw/ImmichMCP/blob/main/ImmichMCP/Client/ImmichAuthHandler.cs) emploie cette même clé pour ses appels Immich. Une connexion CLAIRE ne crée pas une identité Immich distincte et ne réduit pas les droits de cette clé.

**Dans cette version, seul l’administrateur qui configure la connexion peut la consulter et l’utiliser.** Un membre, un lecteur et les autres administrateurs n’y ont pas accès. Les résultats ne sont pas partagés avec la famille et sont accessibles dans le chat privé de cet administrateur. Deux connexions pointant vers un serveur MCP utilisant la même clé peuvent voir la même bibliothèque. L’accès des membres, les permissions par album et les références partagées nécessitent une étape distincte ; ne configurez pas une clé globale en supposant que CLAIRE filtre déjà les photos selon chaque compte Immich.

## Compatibilité et limites

- Transport pris en charge : **Streamable HTTP**, endpoint `/mcp`, réponses JSON et SSE, sessions MCP. Pas de lancement `stdio`, pas d’ancien transport HTTP+SSE, pas d’OAuth interactif.
- Modes **static** et **gateway** validés avec l’image réelle `ghcr.io/barryw/immichmcp`, digest `sha256:45acbcd7fb7ab766e1edad00cb5d3a2b849f1f6ecbadeb14771d1413bb241187`, sur une API Immich synthétique. Le tag `latest` peut évoluer ; le test de connexion indique les incompatibilités.
- Outils autorisés : `immich_ping`, `immich_assets_list`, `immich_albums_list`, `immich_search_metadata`, `immich_people_list`, `immich_people_assets`. Le mode gateway active uniquement ces noms après découverte. Aucune catégorie entière ni outil de modification, téléchargement, suppression ou partage n’est activé.
- Les listes sont bornées : 25 médias par requête, au plus 50 albums affichés. La recherche porte sur le nom du fichier, pas sur la reconnaissance d’images. Pas encore de miniatures distantes, de copie automatique, de navigation dans les albums ou d’utilisation par le LLM.
- Les descriptions d’outils ne sont jamais exécutées comme instructions. Les résultats sont réduits aux noms, identifiants, types et dates, puis affichés comme texte. Les URL retournées ne sont ni suivies ni intégrées dans la page.
- Les redirections sont refusées ; utilisez l’adresse finale. HTTP est réservé aux adresses privées. HTTPS public est accepté avec vérification normale du certificat. Les adresses loopback, link-local, multicast et réservées sont bloquées ; la résolution DNS est vérifiée puis fixée pour la connexion.

## Stockage, sauvegarde et mise à jour

La migration **0005** crée le catalogue de configuration protégé par les permissions PostgreSQL. Elle est appliquée au démarrage de l’image tout-en-un. Les déploiements séparés doivent exécuter les migrations et appliquer les droits de `infrastructure/docker/runtime-role.sql`.

Le jeton est chiffré avec Fernet en base. La clé persistante est dans `CLAIRE_DATA_DIR/.secrets/integrations.key` (donc `/data/archive/.secrets/integrations.key` dans l’image tout-en-un), avec permissions restreintes. Sauvegardez la base et cette clé ensemble dans une sauvegarde protégée. Les exports de souvenirs et de fichiers n’incluent pas cette clé. Une perte de clé impose de restaurer la clé ou de ressaisir le jeton. Ce chiffrement ne protège pas contre l’administrateur de l’hôte qui contrôle aussi les fichiers et les processus.

**Supprimer la connexion** efface sa configuration et son jeton en base sans modifier Immich. Les requêtes en cours revérifient la session et la configuration avant de rendre leurs résultats. Aucun port ni conteneur supplémentaire n’est nécessaire côté CLAIRE ; votre conteneur MCP existant reste utilisé.

Test de compatibilité reproductible : `python scripts/immich_compat_smoke.py --image claire:immich-test`, après construction de cette image. Le script crée et supprime son propre réseau et ses conteneurs de test, sans connecter de bibliothèque réelle.

## Chat Ollama

Avec la connexion active, demandez « Quels sont mes albums Immich ? » ou « Montre mes photos recentes ».
CLAIRE lit les albums ou les medias recents puis transmet au modele local au maximum 25 titres, types et dates.
La selection se fait par mots-cles dans le message courant, sans envoyer votre historique ou vos souvenirs au MCP.
Ce n'est ni un index complet ni une analyse visuelle : les images ne sont pas transmises au modele.
Les erreurs de connexion sont signalees dans le contexte du modele. Les reponses deja sauvegardees restent dans votre conversation privee apres deconnexion d'Immich.

### Photos par personne identifiee

Demandez **« Montre les photos de Camille »**, en utilisant le nom enregistre dans Immich.
CLAIRE consulte les personnes visibles, resout le nom (sans distinction de casse ou d'accents), puis lit jusqu'a 25 medias associes a cette personne.
Un prenom peut suffire s'il correspond a une seule personne ; en cas d'homonymes, le chat demande de preciser le nom complet. Les demandes avec plusieurs personnes ne calculent pas une intersection : elles demandent aussi une precision.
Le parcours est borne a 5 pages de 100 personnes. Si cette limite est atteinte, aucune personne n'est choisie automatiquement.
Les personnes masquees sont exclues. Une personne absente, une limite atteinte ou un outil MCP indisponible ne declenche jamais un remplacement par des photos recentes sans rapport.
Les identites proviennent des etiquettes Immich ; aucune reconnaissance faciale supplementaire ni verification d'identite n'est effectuee par Ollama.
La demande doit contenir le nom et un terme comme « photos de » ou « photos avec » ; les relances par pronom seul ne sont pas resolues.
