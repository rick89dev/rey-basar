# Despliegue de ReyBasar (servidor 157.245.243.226)

Mismo esquema que la caja: app en `/srv/reybasar/app` (usuario `reybasar`), puerto 8020,
configuración en `/etc/reybasar/reybasar.env`, datos en `/srv/reybasar/data`, fotos en `/srv/reybasar/media`.

## Actualizar (después de la primera vez)
    cd /srv/reybasar/app && sudo -u reybasar git pull && sudo -u reybasar .venv/bin/pip install -q -r requirements.txt && systemctl restart reybasar
