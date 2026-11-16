# Documents texte et Markdown

Dans **Documents et archives**, cliquez sur **Importer un document**. Choisissez un fichier UTF-8 `.txt`, `.md` ou `.markdown` de 8 Kio et 6 000 caractères maximum. Vérifiez le texte, le titre et la visibilité avant de confirmer l’enregistrement. Le fichier est lu dans le navigateur ; aucun contenu n’est envoyé au serveur avant confirmation.

Les documents sont privés par défaut. Le partage familial donne accès à la version courante aux membres de votre famille ; les documents privés des autres membres restent inaccessibles, y compris à un administrateur familial. L’import conserve le texte original et enregistre le nom du fichier et son empreinte SHA-256 comme provenance. Cela ne vérifie pas les affirmations : le statut initial est « Information incertaine ».

Les documents utilisent les archives versionnées existantes : modification, historique, corbeille, restauration et export ZIP. La provenance originale reste dans la première version, même si elle est modifiée ensuite. La page Documents filtre les documents ; la page Souvenirs permet aussi de les retrouver avec le reste des archives.

La recherche de la bibliothèque trouve une chaîne dans le titre ou le contenu, sans distinguer majuscules et minuscules. Elle lit les versions autorisées avant pagination ; elle ne repose pas encore sur un index plein texte et peut ralentir avec une grande bibliothèque.

Le chat peut utiliser immédiatement les documents autorisés parmi les 200 archives les plus récemment modifiées, avec au maximum trois extraits. Pour les textes longs, il choisit des passages correspondant aux mots de la question au lieu de ne transmettre que le début. Mentionnez un nom ou un détail précis. Il n’y a ni entraînement du modèle ni recherche sémantique à cette étape.

L’onglet **Fichiers PDF** conserve et télécharge les PDF originaux jusqu’à 25 Mio. Leur texte n’est pas extrait ni transmis au chat. Les photos, sons et vidéos disposent du module **Photos et médias**. Voir [le guide des fichiers](files.md).

Word, OCR, import de dossiers et gros fichiers ne sont pas encore pris en charge. Aucun service cloud n’est utilisé pour l’import.
