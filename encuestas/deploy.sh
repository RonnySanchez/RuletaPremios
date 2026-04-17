#!/bin/bash

# Detener el script inmediatamente si algún comando falla
set -e

echo "========================================="
echo "Iniciando despliegue de la Ruleta..."
echo "========================================="

# 1. Navegar al directorio del proyecto
cd /home/codigos/public_html/rueda

# 2. Descargar los últimos cambios
echo "-> Descargando código desde Git..."
git pull origin main

# 3. Activar entorno virtual
echo "-> Activando entorno virtual..."
source venv/bin/activate

# 4. Aplicar migraciones
echo "-> Aplicando migraciones de base de datos..."
python manage.py migrate

# 5. Aplicar los cambios en la base de datos
echo "🗄️ Aplicando migraciones..."
python manage.py migrate

# 6. Recopilar archivos estáticos
echo "🎨 Actualizando archivos estáticos..."
python manage.py collectstatic --noinput --clear

# 7. Reiniciar el servicio de Gunicorn
echo "-> Reiniciando Gunicorn..."
sudo systemctl restart ruleta_gunicorn

# 8. Aplicar los cambios en la base de datos
echo "Saliendo entorno virtual"
deactivate

echo "========================================="
echo "¡Despliegue finalizado con éxito! 🚀"
echo "========================================="
