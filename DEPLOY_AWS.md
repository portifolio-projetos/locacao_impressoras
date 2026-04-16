# Deploy AWS EC2 (Gunicorn + Nginx + HTTPS)

Este guia assume Ubuntu 22.04/24.04 em EC2, domínio `moscatel.ddns.net` apontando para `18.220.171.193`, e projeto em `/opt/printflow`.

## 1) Preparar servidor

```bash
sudo apt update && sudo apt -y upgrade
sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git
```

## 2) Segurança AWS

- Security Group da instância:
  - `22/tcp` (seu IP)
  - `80/tcp` (0.0.0.0/0)
  - `443/tcp` (0.0.0.0/0)

## 3) Subir projeto

```bash
cd /opt
sudo git clone <URL_DO_SEU_REPOSITORIO> printflow
sudo chown -R ubuntu:ubuntu /opt/printflow
cd /opt/printflow
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4) Configurar `.env` de produção

```bash
cp .env.production.example .env
nano .env
```

Ajuste pelo menos:
- `DJANGO_SECRET_KEY`
- `DATABASE_URL` (ou `POSTGRES_*`)
- `DJANGO_ALLOWED_HOSTS=moscatel.ddns.net,18.220.171.193`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://moscatel.ddns.net`

## 5) Migrar banco e coletar estáticos

```bash
source /opt/printflow/venv/bin/activate
cd /opt/printflow
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

## 6) Gunicorn (systemd)

```bash
sudo cp /opt/printflow/deploy/gunicorn-printflow.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gunicorn-printflow
sudo systemctl start gunicorn-printflow
sudo systemctl status gunicorn-printflow --no-pager
```

## 7) Nginx (HTTP inicial)

```bash
sudo cp /opt/printflow/deploy/moscatel.ddns.net.conf /etc/nginx/sites-available/moscatel.ddns.net
sudo ln -sf /etc/nginx/sites-available/moscatel.ddns.net /etc/nginx/sites-enabled/moscatel.ddns.net
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

Teste HTTP:

```bash
curl -I http://moscatel.ddns.net
```

## 8) HTTPS com Let's Encrypt

```bash
sudo certbot --nginx -d moscatel.ddns.net --redirect -m seu-email@dominio.com --agree-tos -n
```

Teste renovação:

```bash
sudo certbot renew --dry-run
```

## 9) Pós-HTTPS (opcional fixar config SSL manual)

Se quiser usar configuração SSL fixa do projeto:

```bash
sudo cp /opt/printflow/deploy/moscatel.ddns.net-ssl.conf /etc/nginx/sites-available/moscatel.ddns.net
sudo nginx -t
sudo systemctl reload nginx
```

## 10) Comandos úteis

```bash
sudo journalctl -u gunicorn-printflow -f
sudo tail -f /var/log/nginx/error.log
sudo systemctl restart gunicorn-printflow
sudo systemctl reload nginx
```
