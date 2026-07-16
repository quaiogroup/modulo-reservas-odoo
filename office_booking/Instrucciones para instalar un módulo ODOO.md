1. Ingresar mediante Putty al servidor
2. Validar que el docker esté en ejecución el comando es:
   `docker exec -it odoo-app bash`
3. Traer desde el repositorio la versión del módulo actualizada:

`sudo git clone https://github.com/quaiogroup/modulo-reservas-odoo.git -b 19.0`
tuvimos que extraer office_booking
sudo mv modulo-reservas-odoo/office_booking .

5. Se ingresa al contenedor mediante el comando
   `docker exec -it [nombre_contenedor] bash`
   Para nuestro caso
   `docker exec -it odoo-app bash`
6. Se instala el módulo:
   `odoo -i office_booking -d sppot.co --db_host=db --db_user=xxx --db_password=xxx --no-http --stop-after-init`
