import ipaddress


def get_client_ip(request):
    """Adresse IP réelle du visiteur, utilisée par django-axes pour compter les mots de passe faux.

    Derrière Nginx, Django voit toutes les requêtes venir de 127.0.0.1 : la vraie adresse est dans
    l'en-tête X-Real-IP, que Nginx écrit lui-même (proxy_set_header X-Real-IP $remote_addr). On ne
    fait confiance à cet en-tête que si la requête vient de la machine elle-même : un visiteur qui
    écrirait cet en-tête dans sa propre requête n'a donc aucun effet.
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")
    try:
        from_local_proxy = ipaddress.ip_address(remote_addr).is_loopback
    except ValueError:
        from_local_proxy = False

    if from_local_proxy:
        real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()
        try:
            return str(ipaddress.ip_address(real_ip))
        except ValueError:
            pass
    return remote_addr
