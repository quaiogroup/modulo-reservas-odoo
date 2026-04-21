-- 1. RENOMBRAR TABLAS
ALTER TABLE IF EXISTS spoot_office_booking           RENAME TO office_booking;
ALTER TABLE IF EXISTS spoot_office                   RENAME TO office_space;
ALTER TABLE IF EXISTS spoot_office_block             RENAME TO office_block;
ALTER TABLE IF EXISTS spoot_office_image             RENAME TO office_image;
ALTER TABLE IF EXISTS spoot_office_service           RENAME TO office_service;
ALTER TABLE IF EXISTS spoot_office_availability      RENAME TO office_availability;
ALTER TABLE IF EXISTS spoot_office_settings          RENAME TO office_settings;
ALTER TABLE IF EXISTS spoot_coworking_plan           RENAME TO office_plan;
ALTER TABLE IF EXISTS spoot_coworking_subscription   RENAME TO office_subscription;
ALTER TABLE IF EXISTS spoot_discount_code            RENAME TO office_discount;
ALTER TABLE IF EXISTS spoot_booking_quick_create_wizard RENAME TO office_booking_wizard;
ALTER TABLE IF EXISTS spoot_office_service_rel       RENAME TO office_space_service_rel;

-- 2. ACTUALIZAR NOMBRES DE MODELOS
UPDATE ir_model SET model = 'office.booking'       WHERE model = 'spoot.office.booking';
UPDATE ir_model SET model = 'office.space'          WHERE model = 'spoot.office';
UPDATE ir_model SET model = 'office.block'          WHERE model = 'spoot.office.block';
UPDATE ir_model SET model = 'office.image'          WHERE model = 'spoot.office.image';
UPDATE ir_model SET model = 'office.service'        WHERE model = 'spoot.office.service';
UPDATE ir_model SET model = 'office.availability'   WHERE model = 'spoot.office.availability';
UPDATE ir_model SET model = 'office.settings'       WHERE model = 'spoot.office.settings';
UPDATE ir_model SET model = 'office.plan'           WHERE model = 'spoot.coworking.plan';
UPDATE ir_model SET model = 'office.subscription'   WHERE model = 'spoot.coworking.subscription';
UPDATE ir_model SET model = 'office.discount'       WHERE model = 'spoot.discount.code';
UPDATE ir_model SET model = 'office.booking.wizard' WHERE model = 'spoot.booking.quick.create.wizard';

-- 3. ACTUALIZAR REFERENCIAS EN CAMPOS
UPDATE ir_model_fields SET relation = 'office.booking'      WHERE relation = 'spoot.office.booking';
UPDATE ir_model_fields SET relation = 'office.space'         WHERE relation = 'spoot.office';
UPDATE ir_model_fields SET relation = 'office.block'         WHERE relation = 'spoot.office.block';
UPDATE ir_model_fields SET relation = 'office.image'         WHERE relation = 'spoot.office.image';
UPDATE ir_model_fields SET relation = 'office.service'       WHERE relation = 'spoot.office.service';
UPDATE ir_model_fields SET relation = 'office.availability'  WHERE relation = 'spoot.office.availability';
UPDATE ir_model_fields SET relation = 'office.settings'      WHERE relation = 'spoot.office.settings';
UPDATE ir_model_fields SET relation = 'office.plan'          WHERE relation = 'spoot.coworking.plan';
UPDATE ir_model_fields SET relation = 'office.subscription'  WHERE relation = 'spoot.coworking.subscription';
UPDATE ir_model_fields SET relation = 'office.discount'      WHERE relation = 'spoot.discount.code';

-- 4. LIMPIAR DATOS DEL MODULO VIEJO
DELETE FROM ir_model_data WHERE module = 'spoot_office_booking';
DELETE FROM ir_ui_view    WHERE module = 'spoot_office_booking';

-- 5. ESTADO DEL MODULO
UPDATE ir_module_module SET state = 'uninstalled' WHERE name = 'spoot_office_booking';
UPDATE ir_module_module SET state = 'to install'  WHERE name = 'office_booking';

SELECT 'OK' AS resultado;
