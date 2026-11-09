# Notifications des demandes de devis et des messages de contact

Chaque nouvelle demande de devis et chaque nouveau message de contact envoyés depuis le site déclenchent un e-mail d'alerte, avec un lien direct vers la demande ou le message dans l'admin. Les deux formulaires suivent exactement le même fonctionnement : l'envoi ne se fait **pas** pendant la requête du visiteur, il est confié à une commande lancée chaque minute par `cron`, qui renvoie automatiquement les notifications en échec.

## Fonctionnement

```
Visiteur ──▶ formulaire /devis/ ou /contact/ ──▶ vue
                                                  │ enregistre la demande (notified_at = vide)
                                                  └─▶ page de succès, immédiatement

cron (chaque minute) ──▶ manage.py send_devis_notifications
                     ──▶ manage.py send_contact_notifications
                            │ cherchent les lignes avec notified_at vide
                            │ pour chacune : envoie l'e-mail via Gmail (SMTP)
                            │   ├─ succès → notified_at = maintenant
                            │   └─ échec  → notified_at reste vide, erreur journalisée,
                            │               nouvel essai au passage suivant
```

Le champ `notified_at`, présent sur `Devis` et sur `ContactMessage`, sert de file d'attente :

| Valeur | Signification |
|---|---|
| vide (`NULL`) | notification pas encore envoyée, ou dernier envoi en échec |
| date | notification envoyée à cette date |

### Pourquoi ce choix

- **La page du visiteur n'attend pas l'envoi.** Un envoi Gmail prend 1 à 3 secondes, jusqu'à 10 (`EMAIL_TIMEOUT`) si Gmail ne répond pas.
- **Aucun envoi n'est perdu.** Un échec (coupure réseau, panne Gmail) laisse la demande en attente, et elle est retentée à la minute suivante.
- **Pas d'infrastructure supplémentaire.** Une file de tâches classique (Celery + Redis) demanderait deux services de plus à installer et surveiller. La base de données et `cron` suffisent pour le volume de demandes du site.

Contrepartie : la notification arrive dans la minute qui suit la demande, et non instantanément.

Une demande de devis **saisie à la main dans l'admin** (client qui a appelé, écrit sur WhatsApp…) ne déclenche pas d'alerte : l'admin remplit `notified_at` au moment de l'ajout (voir la section Administration de `architecture.md`).

Le code des deux apps est volontairement dupliqué plutôt que factorisé : avec seulement deux cas, une abstraction commune risquerait de ne pas convenir à un troisième. La partie commune sera regroupée si un troisième formulaire apparaît.

## Fichiers concernés

### Demandes de devis (app `devis`)

| Fichier | Rôle |
|---|---|
| `apps/devis/models.py` | champ `notified_at` sur `Devis` |
| `apps/devis/migrations/0005_devis_notified_at.py` | ajoute le champ et marque les devis existants comme déjà notifiés (`RunPython`, `notified_at = created_at`) |
| `apps/devis/views.py` | `devis_create()` enregistre seulement le devis |
| `apps/devis/notifications.py` | `send_devis_notification()` (un envoi, lève une exception en cas d'échec) et `send_pending_notifications()` (parcourt les devis en attente, renvoie `(envoyées, échecs)`) |
| `apps/devis/management/commands/send_devis_notifications.py` | commande lancée par `cron` ; silencieuse quand il n'y a rien à envoyer |
| `apps/devis/tests/test_notifications.py` | tests de l'envoi, de la non-répétition, du renvoi après échec et de la commande |

### Messages de contact (app `contact`)

| Fichier | Rôle |
|---|---|
| `apps/contact/models.py` | champ `notified_at` sur `ContactMessage` |
| `apps/contact/migrations/0004_contactmessage_notified_at.py` | ajoute le champ et marque les messages existants comme déjà notifiés |
| `apps/contact/views.py` | `contact_page()` enregistre seulement le message |
| `apps/contact/notifications.py` | `send_contact_notification()` et `send_pending_notifications()`, sur le même modèle que pour les devis |
| `apps/contact/management/commands/send_contact_notifications.py` | commande lancée par `cron` |
| `apps/contact/tests/test_notifications.py` | mêmes tests que pour les devis |

Les deux alertes se distinguent par leur sujet : « Nouvelle demande de devis — *nom* » et « Nouveau message de contact — *nom* ».

## Configuration

Les réglages sont dans `beobenere/settings.py` et lisent leurs valeurs dans `.env` (chargé par `python-dotenv`, ignoré par Git).

| Variable `.env` | Exemple | Rôle |
|---|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | envoi réel ; sans cette variable, les e-mails s'affichent dans le terminal (backend console) |
| `EMAIL_HOST_USER` | `beobenere.business@gmail.com` | compte Gmail expéditeur |
| `EMAIL_HOST_PASSWORD` | *(16 caractères, sans espaces)* | mot de passe d'application Google, **jamais** dans le code ni dans Git |
| `DEVIS_NOTIFICATION_EMAIL` | `ghiskima@gmail.com` | adresse qui reçoit les alertes des demandes de devis |
| `CONTACT_NOTIFICATION_EMAIL` | *(facultative)* | adresse qui reçoit les alertes des messages de contact ; reprend `DEVIS_NOTIFICATION_EMAIL` si elle n'est pas définie |
| `SITE_URL` | `http://100.116.252.58:8000` | base du lien « Voir la demande » ; doit être joignable depuis l'appareil où l'e-mail est lu |

Réglages fixes dans `settings.py` : `EMAIL_HOST = smtp.gmail.com`, `EMAIL_PORT = 587`, `EMAIL_USE_TLS = True`, `EMAIL_TIMEOUT = 10`, `DEFAULT_FROM_EMAIL = "BeoBenere <beobenere.business@gmail.com>"`.

Les alertes partent vers une **autre** adresse que l'expéditeur : une messagerie ne notifie généralement pas sur le téléphone un message dont on est soi-même l'expéditeur.

## Programmation avec cron

`crontab -e`, puis une seule ligne :

```
* * * * * cd /chemin/vers/beobenere-website && /usr/bin/flock -n /tmp/beobenere-notifications.lock sh -c '/chemin/vers/python manage.py send_devis_notifications; /chemin/vers/python manage.py send_contact_notifications' >> logs/cron.log 2>&1
```

| Élément | Rôle |
|---|---|
| `* * * * *` | chaque minute (passer à `*/5 * * * *` pour toutes les 5 minutes) |
| `cd …` | se placer dans le projet, pour trouver `manage.py` et `.env` |
| `flock -n …lock` | empêche deux exécutions simultanées (sinon, pendant une panne Gmail, une exécution lente pourrait chevaucher la suivante et envoyer deux fois la même notification) |
| `sh -c '…; …'` | `flock` ne lance qu'une seule commande : `sh -c` permet d'en regrouper deux sous le même verrou |
| chemin complet vers Python | `cron` ne charge pas l'environnement (conda, venv) |
| `>> logs/cron.log 2>&1` | garde la sortie et les erreurs des commandes |

Les deux commandes sont séparées par `;` et non par `&&`, pour que la seconde s'exécute même si la première plante.

Chaque ligne de `cron.log` commence par la date et `Devis :` ou `Contact :` :

```
2026-10-05 17:53 Devis : 2 notification(s) envoyée(s), 0 échec(s).
2026-10-05 17:53 Contact : 1 notification(s) envoyée(s), 0 échec(s).
```

Pour ne voir que ces résumés, sans les traces d'erreur : `grep -E "Devis|Contact" logs/cron.log | tail`.

Coût : une exécution sans rien à envoyer prend environ une seconde par commande (essentiellement le chargement de Django), soit quelques pour cent d'un cœur sur une journée.

## Journalisation

Les échecs d'envoi sont écrits par les loggers `devis.notifications` et `contact.notifications` dans `logs/django.log`, avec date, gravité et origine :

```
2026-10-05 09:16:18,805 ERROR devis.notifications : Échec de l'envoi de la notification pour le devis 9
```

`LOGGING` envoie le logger racine vers ce fichier : toute erreur journalisée par le code des apps y est donc enregistrée, pas seulement celles de Django. Les traces apparaissent aussi dans `cron.log`, le gestionnaire `console` écrivant sur la sortie d'erreur que la ligne `cron` redirige.

## Tests

```bash
python manage.py test devis contact
```

`mail.outbox` remplace l'envoi réel pendant les tests ; `mock.patch("devis.notifications.send_mail")` (ou `contact.notifications.send_mail`) simule une panne pour vérifier que la demande reste en attente.

## Dépannage

| Symptôme | Cause probable | Vérification |
|---|---|---|
| Aucune alerte reçue | `cron` non installé, ou machine éteinte | `crontab -l`, `grep -E "Devis\|Contact" logs/cron.log \| tail` |
| `Temporary failure in name resolution` dans le journal | coupure réseau ou DNS passagère | `getent hosts smtp.gmail.com` ; le renvoi automatique s'en charge |
| `Network is unreachable` dans le journal | connexion coupée, ou réseau sans IPv6 (Python essaie alors l'IPv4 ensuite : l'erreur n'est bloquante que si l'IPv4 échoue aussi) | `nc -zv -w 10 -4 smtp.gmail.com 587` ; le renvoi automatique s'en charge au retour du réseau |
| `Username and Password not accepted` | mot de passe d'application révoqué ou erroné | en créer un nouveau (voir ci-dessous) |
| Le lien de l'e-mail ne s'ouvre pas | `SITE_URL` injoignable depuis l'appareil | vérifier `SITE_URL` et l'adresse d'écoute du serveur |
| Une demande jamais notifiée | échecs répétés | `grep "Échec de l'envoi" logs/django.log` ; la ligne a `notified_at` vide dans l'admin |

### Recréer le mot de passe d'application Google

1. Se connecter au compte `beobenere.business@gmail.com` sur `myaccount.google.com`.
2. Vérifier que la validation en deux étapes est activée (obligatoire).
3. Ouvrir `https://myaccount.google.com/apppasswords`, révoquer l'ancien mot de passe « Site BeoBenere » s'il existe, en créer un nouveau.
4. Copier les 16 caractères **sans espaces** dans `EMAIL_HOST_PASSWORD` du `.env`.
5. Aucun redémarrage nécessaire pour `cron` (chaque exécution relit `.env`) ; redémarrer `runserver` s'il tourne.

## Au déploiement

- [ ] Créer `.env` sur le serveur avec les variables ci-dessus, `SITE_URL` pointant vers le nom de domaine.
- [ ] Installer la ligne `cron` avec les chemins du serveur.
- [ ] Envoyer une demande de devis et un message de contact de test, puis vérifier `logs/cron.log` et la réception des deux alertes.
