# ReyBasar

Catálogo de ropa y juguetes **nuevos y seminuevos** (FastAPI + SQLite). Base de datos propia, separada de Winclub/caja.

## Demo local

```bash
cd ~/Sites/reybasar
./iniciar.sh                 # crea .venv la primera vez y arranca en http://localhost:8020
.venv/bin/
.venv/bin/
```

- Tienda: http://localhost:8020
- Cuentas: http://localhost:8020/cuenta/registro — **el primer usuario que se registra queda como administrador**.
  Los demás nacen clientes; un admin los puede hacer admin en Admin › Usuarios.
  En producción conviene fijar `REYBASAR_ADMINS=correo1,correo2` (solo esos nacen admin).
- Admin: http://localhost:8020/admin (entra con tu cuenta de administrador)
- Productos de ejemplo: `iniciar.sh` carga una vez la categoría **Demo** (fotos de Unsplash).
  Quitarlos: `.venv/bin/python -m app.demo --borrar`

## Imágenes del sitio
Banners, mosaicos de categoría, favicon e imagen para compartir se generan con `python diseno/generar.py`
(usa los patrones y el conejo de la marca; sin fotos de producto). Edita textos ahí y vuelve a correrlo.
Las fotos de los mosaicos de categoría son de Unsplash (licencia libre) y se cargan desde su CDN;
para servirlas desde el sitio corre `bash diseno/descargar_fotos.sh` en tu Mac.

## Páginas
- `/` portada como el diseño original: carrusel, mosaico de categorías, beneficios, Destacados, banda Quiero vender, Descuentos, Nuevos y Seminuevos.
- `/categoria/{dama|caballero|ninas|ninos|juguetes|otros}` con filtro Nuevo/Seminuevo y orden.
- `/nuevos`, `/usados`, `/descuentos`, `/buscar?q=`, `/producto/{slug}`.
- `/carrito`: se guarda en el navegador; para pedir hay que iniciar sesión. El pedido aparta las piezas
  (son únicas) y se manda por WhatsApp. Entregas solo en Cuernavaca
  (`REYBASAR_ENTREGA_CIUDAD`); el punto y la hora se acuerdan con el admin por WhatsApp.
- `/cuenta`: mis datos y mis pedidos. Admin › Pedidos: Nuevo → Confirmado → Entregado (marca vendidas) / Cancelado (las libera).
- `/quiero-vender`: consignación vs. compra directa, calculadora y formulario a WhatsApp.
- `/preguntas-frecuentes`.

## Admin
Alta/edición de productos con varias fotos (la principal se elige), precio, precio anterior (descuento), costo privado, talla, marca, nuevo/seminuevo, origen propio/consignación (con vendedor), destacado, visible, vendido, eliminar. Resumen: en venta, vendidos, a consignación y valor del inventario.

## API para el bot de WhatsApp
Con `REYBASAR_BOT_TOKEN` definido, `Authorization: Bearer <token>`:
- `POST /api/productos` (multipart: nombre, categoria, precio, condicion, talla, descripcion, origen, costo, fotos[])
- `GET /api/productos?q=`
- `POST /api/productos/{id}/estado` (vendido, visible)

## Configuración (variables de entorno)
`REYBASAR_DATABASE_URL`, `REYBASAR_MEDIA_DIR`, `REYBASAR_SECRET_KEY`, `REYBASAR_ADMINS`, `REYBASAR_DEMO`, `REYBASAR_BOT_TOKEN`, `REYBASAR_WHATSAPP` (52777…), `OPENAI_API_KEY` (IA del admin), `REYBASAR_ENTREGA_CIUDAD`, `REYBASAR_ENTREGA_COSTO` (0 = se confirma por WhatsApp), `REYBASAR_ENTREGA_GRATIS_DESDE`, `REYBASAR_COMPRA_PCT_MIN`/`MAX` (20/25), `REYBASAR_INE_DESDE` (1000), `REYBASAR_PRIVADO_DIR`.
