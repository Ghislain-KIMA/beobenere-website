# BeoBenere

Site vitrine officiel de **BeoBenere**, entreprise de services informatiques
basée à Tenkodogo, Burkina Faso, et au service de clients à distance.

> ⚠️ **Dépôt à but de démonstration.** Ce code est rendu public à titre de
> portfolio professionnel. Voir [`LICENSE`](./LICENSE) — tous droits réservés,
> aucune réutilisation autorisée sans accord écrit préalable.

## À propos

BeoBenere accompagne les particuliers et petites entreprises, sur place à Tenkodogo et à distance, dans leurs besoins informatiques du quotidien : installation et formation bureautique, diagnostic et réparation matérielle, mais aussi création de sites et d'identité visuelle pour qui se lance ou veut se faire connaître. Une approche directe, sans jargon, centrée sur des solutions qui durent.

Quatre domaines de services :

- **Bureautique** — installation, configuration et formation aux outils courants (Word, Excel, PowerPoint...)
- **Maintenance & dépannage matériel** — diagnostic et réparation, jusqu'au remplacement de composants
- **Développement web & mobile sur mesure** — sites vitrines et applications adaptées à un besoin précis
- **Branding & design** — création de logo et charte graphique

## Fonctionnalités

- Page d'accueil, catalogue de services et coordonnées entièrement pilotés par la base de données (rien en dur dans le code)
- Catalogue de services filtrable par catégorie
- Formulaire de demande de devis, avec validation métier (email ou téléphone requis, adapté au contexte local)
- Formulaire de contact, avec coordonnées affichées dynamiquement (WhatsApp, horaires, zone d'intervention, réseaux sociaux)
- Mode sombre automatique, basé sur la préférence système du visiteur
- Menu mobile avec navigation adaptée aux petits écrans
- Interface d'administration Django pour la gestion courante du contenu
- Gestion du contenu de référence via un classeur Excel et des commandes d'import personnalisées, pour mettre à jour services et coordonnées sans toucher au code

## Stack technique

- **Backend** : Python / Django, organisé en plusieurs apps (homepage, company, service, devis, contact)
- **Base de données** : PostgreSQL
- **Frontend** : templates Django, CSS modulaire par app, sans framework JavaScript
- **Gestion de contenu** : fichiers Excel (openpyxl) et commandes de management Django dédiées

## Identité visuelle

Logo, palette de couleurs, typographie et règles d'usage sont documentés dans une charte graphique dédiée, construite à partir de mesures précises plutôt que d'estimations.

## Licence

Ce projet est protégé par tous droits réservés. Voir le fichier
[`LICENSE`](./LICENSE) pour le détail complet des restrictions d'usage.

## Documentation technique

Voir [`docs/`](./docs/README.md) pour la documentation détaillée (architecture, modèles de données, tests, décisions techniques).

## Contact

**BeoBenere** — Tenkodogo et à distance

- Email : [beobenere.business@gmail.com](mailto:beobenere.business@gmail.com)
- Téléphone / WhatsApp : +226 72 75 00 96
- Facebook : [https://www.facebook.com/BeoBenere](https://www.facebook.com/BeoBenere)
