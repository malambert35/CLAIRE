# PDF, photos et médias

Dans **Documents et archives**, choisissez **Fichiers PDF**. Dans **Photos et médias**, importez JPEG, PNG, WebP, MP3, WAV ou MP4. Chaque fichier doit être non vide et ne pas dépasser **25 Mio**. Les extensions et signatures sont contrôlées ; ce contrôle ne constitue pas un antivirus ni une validation complète du format.

Cliquez sur **Importer un fichier**, sélectionnez l’original, donnez-lui un titre et une description, puis vérifiez la visibilité. Cochez la confirmation et enregistrez. Le fichier est privé par défaut. Le partage familial autorise les membres de votre famille à le consulter, à le télécharger et à l’exporter. Seul son propriétaire peut modifier le partage, le mettre à la corbeille ou le restaurer. Un administrateur familial n’accède pas aux fichiers privés d’un autre propriétaire.

Les images s’affichent dans une galerie. Les fichiers audio et vidéo disposent d’un lecteur ; la lecture dépend des codecs pris en charge par le navigateur. Le serveur accepte les requêtes de plages d’octets pour la lecture et le déplacement dans le média. Les PDF sont téléchargés comme originaux, sans exécution intégrée dans CLAIRE.

La recherche porte sur le titre, le nom du fichier et la description. **Elle ne recherche pas dans le contenu du PDF ou du média.** Pas d’OCR, transcription, reconnaissance faciale, classement automatique ou analyse par Ollama à cette étape. Les fichiers conservent leurs métadonnées embarquées, y compris une éventuelle position GPS ; celles-ci sont donc accessibles aux personnes autorisées à télécharger l’original.

**Télécharger l’original** restitue les octets importés. **Exporter avec les métadonnées (.zip)** ajoute un `metadata.json` contenant le titre, la description, le propriétaire, la visibilité, la date, la taille et l’empreinte SHA-256. Ce ZIP est un export de fichier, distinct du format ZIP des souvenirs ; son réimport automatique n’est pas encore pris en charge. Les originaux sont immuables : importer une autre version crée un nouveau fichier. La corbeille masque le fichier aux autres membres et permet sa restauration par le propriétaire ; elle ne libère pas l’espace disque.

## Déploiement et conservation

La migration **0004** ajoute le catalogue des fichiers et ses règles d’accès PostgreSQL. L’image tout-en-un applique cette migration au démarrage. Pour un déploiement séparé, exécutez `alembic upgrade head` avec le compte de migration et appliquez les droits de `infrastructure/docker/runtime-role.sql` avant de démarrer le nouveau backend.

Les fichiers sont stockés dans `CLAIRE_DATA_DIR/files/<famille>/<propriétaire>/<identifiant>/original`, à côté d’un `import.json` qui décrit l’import initial. Ce dernier ne reflète pas les changements de partage ultérieurs : **PostgreSQL est la référence des droits actuels**. Sauvegardez ensemble la base PostgreSQL et le répertoire d’archives ; dans l’image tout-en-un, les deux se trouvent dans le volume `/data` existant. Aucun port ou volume supplémentaire n’est nécessaire.

Une empreinte est vérifiée avant de servir un original. Un original absent ou altéré est signalé comme indisponible. Un import interrompu avant validation en base peut laisser un répertoire non référencé ; il n’est jamais servi par l’API. Il n’y a pas encore de quota global, de nettoyage automatique de ces répertoires, de miniatures précalculées ou de suppression définitive. Surveillez l’espace disponible. Le retrait d’un partage ne retire pas les copies déjà téléchargées.
