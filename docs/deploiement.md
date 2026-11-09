# Déploiement en production

Procédure complète pour installer le site sur un serveur Ubuntu : Gunicorn derrière Nginx, PostgreSQL, notifications par `cron`, sauvegardes, pare-feu. Elle a été rodée le 9 octobre 2026 sur le serveur d'entraînement (portable Ubuntu 26.04, accès par Tailscale) et sert de modèle pour le VPS.

Chaque étape se termine par une **vérification** : ne passer à la suivante que si le résultat attendu est obtenu.

## Vue d'ensemble

```
Visiteur ──▶ Nginx :80/:443 ──┬─▶ /static/…  → fichiers de /srv/beobenere/staticfiles/
                              └─▶ le reste   → Gunicorn 127.0.0.1:8000 → Django → PostgreSQL

cron (chaque minute)   ──▶ send_devis_notifications + send_contact_notifications ──▶ Gmail
cron (chaque nuit)     ──▶ pg_dump ──▶ /var/backups/beobenere/
PC (chaque heure)      ──▶ rsync (clé limitée en lecture) ──▶ ~/sauvegardes/beobenere/
```

| Élément | Emplacement |
|---|---|
| Code | `/srv/beobenere` (clone Git) |
| Environnement Python | `/srv/beobenere/.venv` |
| Réglages secrets | `/srv/beobenere/.env` (droits `600`, jamais dans Git) |
| Fichiers statiques collectés | `/srv/beobenere/staticfiles/` |
| Journaux Django et cron | `/srv/beobenere/logs/` |
| Service Gunicorn | `/etc/systemd/system/beobenere.service` |
| Site Nginx | `/etc/nginx/sites-available/beobenere` |
| Sauvegardes | `/var/backups/beobenere/` (droits `700`) |

Dans ce guide, `<utilisateur>` est le compte Linux qui fait tourner le site (sur le serveur d'entraînement : `ghislain-kima`), et `<adresse>` l'adresse du serveur (IP ou nom de domaine).

---

## 1. Paquets système

```bash
sudo apt update && sudo apt upgrade
sudo apt install git python3-venv postgresql nginx rsync
python3 --version
```

**Vérification :** Python **3.12 ou plus** (Django 6.1). Le serveur d'entraînement a Python 3.14.

> Si `apt` affiche *« dpkg was interrupted »* (coupure de courant pendant une installation) : `sudo dpkg --configure -a`, puis relancer.

## 2. Base PostgreSQL

Générer un mot de passe solide et le noter à l'abri :

```bash
openssl rand -hex 24
```

Créer l'utilisateur et la base :

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE beobenere LOGIN PASSWORD '<mot de passe généré>';
CREATE DATABASE beobenere OWNER beobenere;
\q
```

**Vérification :** `psql -h localhost -U beobenere -d beobenere` demande le mot de passe puis ouvre une invite `beobenere=>` (`\q` pour sortir).

## 3. Récupérer le code

```bash
sudo mkdir -p /srv/beobenere
sudo chown <utilisateur>:<utilisateur> /srv/beobenere
git clone https://github.com/Ghislain-KIMA/beobenere-website.git /srv/beobenere
cd /srv/beobenere
git log --oneline -1
```

**Vérification :** le dernier commit est celui attendu, et le dossier `logs/` existe (grâce à `logs/.gitkeep`).

## 4. Environnement virtuel et dépendances

```bash
cd /srv/beobenere
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn
```

**Vérification :**

```bash
pip list | grep -iE "django|gunicorn|psycopg"   # Django, gunicorn, psycopg2-binary
git status                                        # « working tree clean » : .venv est ignoré
```

> Si `python3 -m venv` affiche *« ensurepip is not available »* : `sudo apt install python3-venv`.

## 5. Le fichier `.env`

Générer une clé secrète **propre à ce serveur** (ne jamais réutiliser celle du développement) :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Partir du modèle versionné, puis remplir :

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

| Variable | Valeur |
|---|---|
| `SECRET_KEY` | la clé générée ci-dessus |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | noms et IP du serveur, séparés par des virgules, sans espace (ex. `beobenere.com,www.beobenere.com`) |
| `USE_HTTPS` | `False` tant que le certificat n'est pas installé (étape 14), puis `True` |
| `DB_NAME`, `DB_USER` | `beobenere` |
| `DB_PASSWORD` | le mot de passe de l'étape 2 |
| `DB_HOST`, `DB_PORT` | `localhost`, `5432` |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` (ligne absente = e-mails affichés dans la console) |
| `EMAIL_HOST_USER` | `beobenere.business@gmail.com` |
| `EMAIL_HOST_PASSWORD` | un **mot de passe d'application Gmail dédié à ce serveur** (voir ci-dessous) |
| `DEVIS_NOTIFICATION_EMAIL`, `CONTACT_NOTIFICATION_EMAIL` | `beobenere.business@gmail.com` |
| `SITE_URL` | adresse publique complète, utilisée dans les liens des e-mails (ex. `https://beobenere.com`) |
| `ADMINS` | adresse(s) qui reçoivent les erreurs 500, séparées par des virgules |

**Deux pièges du `.env` :**

- **Une variable en double : c'est la dernière ligne qui gagne.** Un modèle vide collé en bas du fichier écrase toutes les vraies valeurs au-dessus.
- **Une ligne vide n'est pas une ligne absente.** `DEVIS_NOTIFICATION_EMAIL=` vaut `""` : la valeur par défaut de `settings.py` ne s'applique **que** si la ligne n'existe pas du tout. Remplir la ligne ou la supprimer, jamais la laisser vide.

**Mot de passe d'application Gmail :** sur le compte beobenere.business@gmail.com, activer la validation en deux étapes (myaccount.google.com/security), puis créer un code sur myaccount.google.com/apppasswords. Le recopier **sans espaces**. Un code par machine : si un serveur est compromis, on supprime son seul code.

**Vérification :** `python manage.py check` → *« System check identified no issues »*.

## 6. Base de données et contenu

```bash
python manage.py migrate
python manage.py showmigrations | grep "\[ \]"    # ne doit rien afficher
python manage.py createsuperuser                  # mot de passe différent du développement
python manage.py import_company data/services-beobenere.xlsx
python manage.py import_services data/services-beobenere.xlsx
```

**Vérification :** `migrate` termine par des `OK`, `import_company` affiche *« Entreprise créée. »*, `import_services` le nombre de catégories et de services créés, sans avertissement.

## 7. Fichiers statiques

```bash
python manage.py collectstatic
git status --short     # ne doit rien afficher : staticfiles/ est ignoré
```

**Vérification :** *« … static files copied to '/srv/beobenere/staticfiles' »*.

## 8. Tester Gunicorn à la main

```bash
gunicorn --bind 127.0.0.1:8000 beobenere.wsgi
```

Dans une autre fenêtre (tmux : `Ctrl+B` puis `C`) :

```bash
curl -I http://127.0.0.1:8000/
```

**Vérification :** `HTTP/1.1 200 OK` avec `Server: gunicorn`. Arrêter ensuite Gunicorn avec `Ctrl+C` (sinon le port 8000 reste occupé). Les CSS ne sont pas servis à ce stade : c'est normal avec `DEBUG=False`, ce sera le rôle de Nginx.

## 9. Service systemd pour Gunicorn

```bash
sudo nano /etc/systemd/system/beobenere.service
```

```ini
[Unit]
Description=BeoBenere - Django via Gunicorn
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=<utilisateur>
Group=<utilisateur>
WorkingDirectory=/srv/beobenere
ExecStart=/srv/beobenere/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 --access-logfile - beobenere.wsgi
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

- `User` : le propriétaire de `/srv/beobenere`, qui peut donc écrire dans `logs/`.
- `--workers 2` : suffisant pour un petit serveur ; la règle courante est `2 × nombre de cœurs + 1` si la mémoire le permet.
- `127.0.0.1` : Gunicorn n'est joignable que depuis le serveur, Nginx est la seule porte d'entrée.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now beobenere
```

**Vérification**, après quelques secondes (pas immédiatement : les workers mettent un instant à démarrer) :

```bash
sudo systemctl status beobenere --no-pager   # active (running), 3 processus gunicorn
curl -I http://127.0.0.1:8000/               # 200 OK
```

Journaux du service : `journalctl -u beobenere -n 50`.

## 10. Nginx

```bash
sudo nano /etc/nginx/sites-available/beobenere
```

```nginx
server {
    listen 80;
    server_name <adresse>;

    client_max_body_size 2M;

    location /static/ {
        alias /srv/beobenere/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

- `server_name` : les mêmes noms que `ALLOWED_HOSTS`, séparés par des **espaces**.
- `alias` : le `/` final est indispensable.
- `X-Forwarded-Proto` : indispensable pour `USE_HTTPS` (étape 14).

```bash
sudo ln -s /etc/nginx/sites-available/beobenere /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Masquer la version de Nginx : dans `/etc/nginx/nginx.conf`, mettre `server_tokens off;` (Ubuntu 26.04 livre `server_tokens build;`), puis `sudo nginx -t && sudo systemctl reload nginx`.

**Vérification :**

```bash
curl -I http://127.0.0.1/static/images/favicon-beobenere-green.svg
```

→ `200 OK`, `Server: nginx` (sans numéro de version), `Content-Type: image/svg+xml`. Puis ouvrir le site dans un navigateur : il doit s'afficher **avec son style**. Parcourir toutes les pages.

> `403 Forbidden` sur les fichiers statiques = Nginx (`www-data`) ne peut pas lire un des dossiers. Diagnostic : `namei -l /srv/beobenere/staticfiles/images` — chaque ligne doit finir par `r-x` pour « les autres ».

## 11. Tester les formulaires

1. Envoyer une demande de devis **depuis la carte d'un service** (le service doit être présélectionné).
2. Envoyer un message de contact.
3. Dans `/admin/`, les deux doivent apparaître, avec une croix rouge dans « Notifié » (le cron n'existe pas encore).

Une erreur **403 CSRF** à cette étape indique en général un `ALLOWED_HOSTS` ou un en-tête `Host` incorrect, ou des cookies sécurisés activés alors que le site est encore en HTTP (`USE_HTTPS=True` trop tôt).

## 12. Notifications par cron

Tester d'abord à la main :

```bash
python manage.py sendtestemail beobenere.business@gmail.com   # l'e-mail de test doit arriver
python manage.py send_devis_notifications                     # « 1 notification(s) envoyée(s), 0 échec(s) »
```

Puis programmer (`crontab -e`) :

```cron
* * * * * cd /srv/beobenere && /usr/bin/flock -n /tmp/beobenere-notifications.lock sh -c '.venv/bin/python manage.py send_devis_notifications; .venv/bin/python manage.py send_contact_notifications' >> logs/cron.log 2>&1
```

Le détail de cette ligne (`flock`, `sh -c`) est expliqué dans [`notifications.md`](./notifications.md).

**Vérification :** une minute après l'envoi du formulaire de contact, `cat logs/cron.log` montre *« Contact : 1 notification(s) envoyée(s) »*, l'e-mail arrive, son lien « Voir le message » ouvre l'admin, et la coche est verte.

> En mode console (pas d'`EMAIL_BACKEND` SMTP), l'e-mail est écrit dans `logs/cron.log` au lieu d'être envoyé. Les `=C3=A9` qu'on y voit sont l'encodage normal des accents dans un e-mail.

## 13. Sauvegardes automatiques

> **Sur le serveur d'entraînement**, cette étape et la suivante ne sont pas utilisées : les sauvegardes y sont assurées par le script `sauvegarde-serveur` (timer systemd `sauvegarde-serveur.timer`, tous les jours à 3 h 30). Il lance `pg_dump -Fc` en tant qu'utilisateur `postgres` (donc sans `~/.pgpass`), garde 3 jours de copies dans `/var/backups/serveur/beobenere/`, puis le PC les récupère et les archive avec restic. Les étapes 13 et 14 décrivent la méthode autonome, à utiliser sur un VPS qui n'a pas cette infrastructure. BeoBenere n'a aucun fichier téléversé : la base PostgreSQL est la seule chose à sauvegarder (le fichier `.env`, qui contient des secrets, ne l'est volontairement pas).

**Connexion sans mot de passe pour `pg_dump`** — fichier `~/.pgpass` :

```
localhost:5432:beobenere:beobenere:<mot de passe PostgreSQL>
```

```bash
chmod 600 ~/.pgpass      # obligatoire : sinon PostgreSQL ignore le fichier
psql -h localhost -U beobenere -d beobenere -c "SELECT count(*) FROM devis;"
```

> Les tables portent les noms fixés par `db_table` dans les modèles : `devis`, `contact_message`, `service`, `category`, `company` (et non `devis_devis`…).

**Dossier des sauvegardes**, hors du code et lisible par le seul propriétaire :

```bash
sudo mkdir -p /var/backups/beobenere
sudo chown <utilisateur>:<utilisateur> /var/backups/beobenere
chmod 700 /var/backups/beobenere
```

**Script** `~/bin/sauvegarde-beobenere.sh` (`chmod 700`) :

```sh
#!/bin/sh
set -eu
umask 077

DEST=/var/backups/beobenere
FICHIER="$DEST/beobenere-$(date +%Y-%m-%d_%H%M).dump"

pg_dump -h localhost -U beobenere -Fc beobenere -f "$FICHIER.tmp"
mv "$FICHIER.tmp" "$FICHIER"

find "$DEST" -name 'beobenere-*.dump' -mtime +14 -delete

echo "$(date '+%F %T') Sauvegarde OK : $FICHIER"
```

- `-Fc` : format compressé, permet de restaurer une seule table.
- `.tmp` puis `mv` : une sauvegarde interrompue ne ressemble jamais à une sauvegarde valide.
- Les sauvegardes de plus de 14 jours sont supprimées sur le serveur.

**Vérification :** lancer le script à la main, puis

```bash
pg_restore -l /var/backups/beobenere/beobenere-*.dump | grep "TABLE DATA"
```

→ une ligne par table (`devis`, `contact_message`, `auth_user`…).

**Programmation** (`crontab -e`), chaque nuit à 3 h 17 :

```cron
17 3 * * * $HOME/bin/sauvegarde-beobenere.sh >> /var/backups/beobenere/sauvegarde.log 2>&1
```

### Restaurer une sauvegarde

À essayer au moins une fois, sur une base de test, avant d'en avoir besoin :

```bash
sudo -u postgres createdb -O beobenere beobenere_restauration
pg_restore -h localhost -U beobenere -d beobenere_restauration --no-owner /var/backups/beobenere/<fichier>.dump
psql -h localhost -U beobenere -d beobenere_restauration -c "SELECT count(*) FROM devis;"
sudo -u postgres dropdb beobenere_restauration
```

## 14. Copie des sauvegardes hors du serveur

Une sauvegarde sur le même disque ne protège ni d'une panne de disque ni d'un vol. C'est le **PC qui vient chercher** les fichiers : le serveur n'a aucun accès au PC.

**Sur le PC**, une clé dédiée, sans phrase secrète (le script tourne seul) :

```bash
ssh-keygen -t ed25519 -f ~/.ssh/beobenere_sauvegarde -N "" -C "sauvegarde-beobenere"
cat ~/.ssh/beobenere_sauvegarde.pub
```

**Sur le serveur**, autoriser cette clé **uniquement** en lecture du dossier des sauvegardes, grâce à `rrsync` (fourni avec `rsync`). Dans `~/.ssh/authorized_keys` (dossier `700`, fichier `600`), sur une seule ligne :

```
command="/usr/bin/rrsync -ro /var/backups/beobenere/",restrict ssh-ed25519 AAAA… sauvegarde-beobenere
```

**Vérification, depuis le PC :**

```bash
ssh -i ~/.ssh/beobenere_sauvegarde <utilisateur>@<adresse> "ls /"
# → refusé : « rrsync error: SSH_ORIGINAL_COMMAND does not run rsync »
rsync -e "ssh -i ~/.ssh/beobenere_sauvegarde" <utilisateur>@<adresse>:/
# → liste le contenu de /var/backups/beobenere/ et rien d'autre
```

**Script sur le PC** `~/bin/recuperer-sauvegardes-beobenere.sh` (`chmod 700`) :

```sh
#!/bin/sh
set -eu
umask 077

DEST="$HOME/sauvegardes/beobenere"
mkdir -p "$DEST"

rsync -a \
  -e "ssh -i $HOME/.ssh/beobenere_sauvegarde -o BatchMode=yes -o ConnectTimeout=20" \
  <utilisateur>@<adresse>:/ "$DEST/"

echo "$(date '+%F %T') Récupération OK"
```

Pas de `--delete` : le PC garde tout l'historique, même après le nettoyage des 14 jours sur le serveur. Le dossier de destination ne doit **pas** être un dossier synchronisé avec un cloud tant que les fichiers ne sont pas chiffrés (ils contiennent les données des clients).

**Programmation sur le PC** (`crontab -e`), chaque heure, puisque le PC n'est pas toujours allumé :

```cron
23 * * * * $HOME/bin/recuperer-sauvegardes-beobenere.sh >> $HOME/sauvegardes/recuperation.log 2>&1
```

## 15. Pare-feu (ufw)

**Attention :** une mauvaise règle peut couper l'accès SSH. Écrire toutes les règles **avant** `ufw enable`, et vérifier par où l'on est connecté : `echo $SSH_CONNECTION`.

**Serveur d'entraînement** (tout passe par Tailscale) :

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow in on tailscale0
sudo ufw allow 41641/udp          # liaison directe Tailscale
sudo ufw show added               # relire avant d'activer
sudo ufw enable
sudo ufw status verbose
```

**VPS** (site public) : mêmes règles par défaut, plus le web ouvert à tous et SSH :

```bash
sudo ufw allow 'Nginx Full'       # ports 80 et 443
sudo ufw allow OpenSSH            # ou seulement « allow in on tailscale0 » si Tailscale est installé sur le VPS
```

**Vérification :** le site répond par le chemin autorisé, et **ne répond pas** par un chemin interdit (sur le serveur d'entraînement : `http://<IP locale>` depuis un appareil sans Tailscale doit échouer par délai dépassé).

## 16. HTTPS (VPS uniquement)

Prérequis : le nom de domaine pointe vers l'IP du VPS, et `server_name` / `ALLOWED_HOSTS` contiennent ce domaine.

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d <domaine> -d www.<domaine>
sudo certbot renew --dry-run       # le renouvellement automatique doit fonctionner
```

Puis, **seulement une fois le site accessible en `https://`**, dans `.env` :

```ini
USE_HTTPS=True
SITE_URL=https://<domaine>
```

```bash
sudo systemctl restart beobenere
python manage.py check --deploy
```

`USE_HTTPS=True` active d'un coup `SECURE_PROXY_SSL_HEADER`, la redirection HTTP → HTTPS, les cookies sécurisés et HSTS (1 heure au départ). **Vérification :** `check --deploy` ne signale plus W004, W008, W012, W016. Restent volontairement W005 (HSTS sur les sous-domaines) et W021 (preload), à n'activer qu'après plusieurs semaines de HTTPS sans problème : ce sont des choix difficiles à annuler.

## 17. Test du redémarrage

Le serveur doit tout reprendre seul (coupure de courant, mise à jour du noyau) :

```bash
sudo reboot
```

Après une à deux minutes, sans se reconnecter, ouvrir le site. Puis :

```bash
systemctl is-active beobenere nginx postgresql cron     # (+ tailscaled si utilisé) : tout « active »
timedatectl                                             # « System clock synchronized: yes »
```

L'heure doit être juste : le cron, les dates des devis et les noms des sauvegardes en dépendent. Sans pile ni batterie, l'horloge est corrigée par NTP dès que la connexion Internet revient.

---

## Mettre à jour le site

Après chaque `git push` depuis le poste de développement, sur le serveur.

**Avant tout, une sauvegarde instantanée de la base** (indispensable quand la mise à jour contient une migration). Sur le serveur d'entraînement :

```bash
umask 077
sudo runuser -u postgres -- pg_dump -Fc beobenere > ~/beobenere-avant-maj.dump
pg_restore -l ~/beobenere-avant-maj.dump | grep "TABLE DATA"   # une ligne par table
```

Sur un serveur configuré avec les étapes 13 et 14, lancer simplement `~/bin/sauvegarde-beobenere.sh`. Une fois la mise à jour vérifiée, supprimer ce fichier : il contient les données des clients.

Puis la mise à jour :

```bash
cd /srv/beobenere
source .venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py check
python manage.py migrate --plan      # voir les migrations à venir, sans les appliquer
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart beobenere
```

**Vérification :** `git log --oneline -1` montre le nouveau commit, `systemctl status beobenere` une heure de démarrage récente, `python manage.py showmigrations | grep "\[ \]"` n'affiche rien, `curl -I http://127.0.0.1:8000/` répond `200 OK`. Le cron n'a pas besoin d'être redémarré : il relance Python à chaque passage.

## Contrôles réguliers

| Quoi | Commande | Attendu |
|---|---|---|
| Sauvegarde de la nuit | `tail -3 /var/backups/beobenere/sauvegarde.log` | « Sauvegarde OK » daté du jour |
| Copie sur le PC | `tail -3 ~/sauvegardes/recuperation.log` | « Récupération OK » récent |
| Notifications | `tail -5 /srv/beobenere/logs/cron.log` | « 0 échec(s) » |
| Erreurs Django | `tail -20 /srv/beobenere/logs/django.log` | rien d'anormal |
| Service | `systemctl status beobenere --no-pager` | active (running) |
| Espace disque | `df -h /` | moins de 80 % utilisé |

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `role "<utilisateur>" does not exist`, `Please supply the NAME` | les variables `DB_*` ne sont pas lues : `.env` absent, mal placé, ou écrasé par des lignes vides plus bas |
| Notifications envoyées à personne | `DEVIS_NOTIFICATION_EMAIL=` présent mais vide |
| `SMTPAuthenticationError` | mot de passe d'application mal recopié (avec espaces) ou supprimé |
| Site sans style | `collectstatic` oublié, ou `alias` Nginx sans `/` final |
| `403` sur `/static/` | droits de lecture manquants pour `www-data` (`namei -l`) |
| `400 Bad Request` | l'adresse utilisée n'est pas dans `ALLOWED_HOSTS` |
| `502 Bad Gateway` | Gunicorn arrêté : `journalctl -u beobenere -n 50` |
| Redirections en boucle après `USE_HTTPS=True` | `X-Forwarded-Proto` absent de la configuration Nginx |
| `Host key verification failed` / `Permission denied (publickey)` | commande lancée sur la mauvaise machine (regarder l'invite : `@ubuntu` = PC, `@ubuntu-server` = serveur), ou clé non autorisée |
| `pg_dump` demande un mot de passe | `~/.pgpass` absent ou pas en `600` |
| Dates bizarres dans l'admin ou les journaux | horloge non synchronisée : `timedatectl` |
