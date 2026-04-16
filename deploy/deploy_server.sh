#!/usr/bin/env bash
set -euo pipefail

# =========================
# Configuração (ajuste se precisar)
# =========================
APP_DIR="${APP_DIR:-/opt/printflow}"
DOMAIN="${DOMAIN:-moscatel.ddns.net}"
SERVER_IP="${SERVER_IP:-18.220.171.193}"
BRANCH="${BRANCH:-main}"
RUN_USER="${RUN_USER:-ubuntu}"
REPO_URL="${REPO_URL:-}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"

if [[ -z "$REPO_URL" ]]; then
  echo "ERRO: defina REPO_URL para clonar/atualizar o projeto."
  echo "Exemplo:"
  echo "REPO_URL='https://github.com/seu-usuario/seu-repo.git' LETSENCRYPT_EMAIL='seu@email.com' bash deploy/deploy_server.sh"
  exit 1
fi

if [[ -z "$LETSENCRYPT_EMAIL" ]]; then
  echo "ERRO: defina LETSENCRYPT_EMAIL para gerar o certificado HTTPS."
  echo "Exemplo:"
  echo "REPO_URL='https://github.com/seu-usuario/seu-repo.git' LETSENCRYPT_EMAIL='seu@email.com' bash deploy/deploy_server.sh"
  exit 1
fi

echo "==> Atualizando pacotes..."
sudo apt update
sudo apt -y upgrade
sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git

echo "==> Preparando diretório do app em $APP_DIR ..."
sudo mkdir -p "$APP_DIR"
sudo chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "==> Clonando repositório..."
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> Atualizando código..."
cd "$APP_DIR"
git fetch --all
git checkout "$BRANCH"
git pull origin "$BRANCH"

echo "==> Configurando ambiente Python..."
if [[ ! -d "$APP_DIR/venv" ]]; then
  python3 -m venv "$APP_DIR/venv"
fi
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f "$APP_DIR/.env" ]]; then
  if [[ -f "$APP_DIR/.env.production.example" ]]; then
    cp "$APP_DIR/.env.production.example" "$APP_DIR/.env"
    echo "==> Arquivo .env criado a partir de .env.production.example"
    echo "ATENÇÃO: edite $APP_DIR/.env e ajuste senhas/chaves antes de continuar."
    echo "Depois execute o script novamente."
    exit 1
  else
    echo "ERRO: não encontrei .env nem .env.production.example em $APP_DIR"
    exit 1
  fi
fi

echo "==> Ajustando ALLOWED_HOSTS e CSRF no .env (se necessário)..."
if ! grep -q "^DJANGO_ALLOWED_HOSTS=" "$APP_DIR/.env"; then
  echo "DJANGO_ALLOWED_HOSTS=$DOMAIN,$SERVER_IP" >> "$APP_DIR/.env"
fi
if ! grep -q "^DJANGO_CSRF_TRUSTED_ORIGINS=" "$APP_DIR/.env"; then
  echo "DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN" >> "$APP_DIR/.env"
fi

echo "==> Migrações e estáticos..."
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check

echo "==> Instalando serviço do Gunicorn..."
if [[ ! -f "$APP_DIR/deploy/gunicorn-printflow.service" ]]; then
  echo "ERRO: arquivo deploy/gunicorn-printflow.service não encontrado no projeto."
  exit 1
fi
sudo cp "$APP_DIR/deploy/gunicorn-printflow.service" /etc/systemd/system/gunicorn-printflow.service
sudo sed -i "s/^User=.*/User=$RUN_USER/" /etc/systemd/system/gunicorn-printflow.service
sudo systemctl daemon-reload
sudo systemctl enable gunicorn-printflow
sudo systemctl restart gunicorn-printflow
sudo systemctl status gunicorn-printflow --no-pager || true

echo "==> Configurando Nginx (HTTP inicial)..."
if [[ ! -f "$APP_DIR/deploy/moscatel.ddns.net.conf" ]]; then
  echo "ERRO: arquivo deploy/moscatel.ddns.net.conf não encontrado no projeto."
  exit 1
fi
sudo cp "$APP_DIR/deploy/moscatel.ddns.net.conf" /etc/nginx/sites-available/"$DOMAIN"
sudo sed -i "s/moscatel.ddns.net/$DOMAIN/g" /etc/nginx/sites-available/"$DOMAIN"
sudo sed -i "s/18.220.171.193/$SERVER_IP/g" /etc/nginx/sites-available/"$DOMAIN"
sudo ln -sf /etc/nginx/sites-available/"$DOMAIN" /etc/nginx/sites-enabled/"$DOMAIN"
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "==> Gerando certificado HTTPS com Certbot..."
sudo certbot --nginx -d "$DOMAIN" --redirect -m "$LETSENCRYPT_EMAIL" --agree-tos -n

echo "==> Testando renovação automática..."
sudo certbot renew --dry-run

echo
echo "Deploy concluído com sucesso."
echo "Acesse: https://$DOMAIN"
