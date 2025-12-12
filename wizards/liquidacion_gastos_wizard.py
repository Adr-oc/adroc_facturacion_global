# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LiquidacionGastosWizardAttachmentLine(models.TransientModel):
    _name = 'liquidacion.gastos.wizard.attachment.line'
    _description = 'Línea de adjunto para wizard de liquidación'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'liquidacion.gastos.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Adjunto',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    name = fields.Char(related='attachment_id.name', string='Nombre')
    mimetype = fields.Char(related='attachment_id.mimetype', string='Tipo')
    file_size = fields.Integer(related='attachment_id.file_size', string='Tamaño')
    include = fields.Boolean(string='Incluir', default=True)

    # Campos para mostrar origen del adjunto
    origin_type = fields.Char(string='Tipo', compute='_compute_origin_info')
    origin_name = fields.Char(string='Registro', compute='_compute_origin_info')
    shipment_name = fields.Char(string='Embarque', compute='_compute_origin_info')

    @api.depends('attachment_id')
    def _compute_origin_info(self):
        for line in self:
            att = line.attachment_id
            origin_type = ''
            origin_name = ''
            shipment_name = ''

            if att.res_model == 'mrdc.shipment':
                origin_type = 'Embarque'
                shipment = self.env['mrdc.shipment'].browse(att.res_id)
                if shipment.exists():
                    origin_name = shipment.name or ''
                    shipment_name = shipment.name or ''

            elif att.res_model == 'account.move':
                origin_type = 'Factura'
                invoice = self.env['account.move'].browse(att.res_id)
                if invoice.exists():
                    origin_name = invoice.name or ''
                    if invoice.mrdc_shipment_id:
                        shipment_name = invoice.mrdc_shipment_id.name or ''

            elif att.res_model == 'mrdc.external.account':
                origin_type = 'Cuenta Ajena'
                external = self.env['mrdc.external.account'].browse(att.res_id)
                if external.exists():
                    origin_name = external.name or ''
                    if hasattr(external, 'shipment_id') and external.shipment_id:
                        shipment_name = external.shipment_id.name or ''

            else:
                origin_type = att.res_model or 'Otro'
                origin_name = str(att.res_id) if att.res_id else ''

            line.origin_type = origin_type
            line.origin_name = origin_name
            line.shipment_name = shipment_name


class LiquidacionGastosWizard(models.TransientModel):
    _name = 'liquidacion.gastos.wizard'
    _description = 'Wizard para seleccionar adjuntos de Liquidación de Gastos'

    report_type = fields.Selection([
        ('normal', 'Normal'),
        ('assukargo', 'Assukargo'),
    ], string='Formato de Reporte', default='normal', required=True)

    invoice_ids = fields.Many2many(
        'account.move',
        'liquidacion_gastos_wizard_invoice_rel',
        'wizard_id',
        'invoice_id',
        string='Facturas',
    )

    shipment_ids = fields.Many2many(
        'mrdc.shipment',
        'liquidacion_gastos_wizard_shipment_rel',
        'wizard_id',
        'shipment_id',
        string='Embarques',
        compute='_compute_shipments',
        store=True,
    )

    attachment_line_ids = fields.One2many(
        'liquidacion.gastos.wizard.attachment.line',
        'wizard_id',
        string='Adjuntos',
    )

    # Campo legacy para compatibilidad (computado desde las líneas)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Adjuntos seleccionados',
        compute='_compute_attachment_ids',
    )

    available_attachment_ids = fields.Many2many(
        'ir.attachment',
        'liquidacion_gastos_wizard_available_attachment_rel',
        'wizard_id',
        'attachment_id',
        string='Adjuntos disponibles',
        compute='_compute_available_attachments',
    )

    @api.depends('attachment_line_ids', 'attachment_line_ids.include')
    def _compute_attachment_ids(self):
        for wizard in self:
            wizard.attachment_ids = wizard.attachment_line_ids.filtered(
                lambda l: l.include
            ).mapped('attachment_id')

    @api.depends('invoice_ids')
    def _compute_shipments(self):
        for wizard in self:
            shipments = wizard.invoice_ids.mapped('mrdc_shipment_id')
            wizard.shipment_ids = shipments.filtered(lambda s: s)

    @api.depends('invoice_ids', 'shipment_ids')
    def _compute_available_attachments(self):
        Attachment = self.env['ir.attachment']
        for wizard in self:
            # Adjuntos de embarques
            shipment_attachments = Attachment.search([
                ('res_model', '=', 'mrdc.shipment'),
                ('res_id', 'in', wizard.shipment_ids.ids),
            ]) if wizard.shipment_ids else Attachment

            # Adjuntos de facturas
            invoice_attachments = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', 'in', wizard.invoice_ids.ids),
            ])

            wizard.available_attachment_ids = shipment_attachments | invoice_attachments

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids', [])
        active_model = self._context.get('active_model')

        if active_model != 'account.move' or not active_ids:
            raise UserError(_('Debe seleccionar al menos una factura.'))

        invoices = self.env['account.move'].browse(active_ids)

        # Filtrar solo facturas de cliente
        customer_invoices = invoices.filtered(
            lambda inv: inv.move_type in ('out_invoice', 'out_refund')
        )

        if not customer_invoices:
            raise UserError(_('Debe seleccionar facturas de cliente.'))

        res['invoice_ids'] = [(6, 0, customer_invoices.ids)]

        # Obtener todos los adjuntos disponibles
        Attachment = self.env['ir.attachment']
        shipments = customer_invoices.mapped('mrdc_shipment_id').filtered(lambda s: s)

        # Adjuntos de embarques
        shipment_attachments = Attachment.search([
            ('res_model', '=', 'mrdc.shipment'),
            ('res_id', 'in', shipments.ids),
        ]) if shipments else Attachment

        # Adjuntos de facturas
        invoice_attachments = Attachment.search([
            ('res_model', '=', 'account.move'),
            ('res_id', 'in', customer_invoices.ids),
        ])

        all_attachments = shipment_attachments | invoice_attachments

        # Crear líneas de adjuntos con secuencia
        if all_attachments:
            attachment_lines = []
            for seq, attachment in enumerate(all_attachments, start=10):
                attachment_lines.append((0, 0, {
                    'attachment_id': attachment.id,
                    'sequence': seq,
                    'include': True,
                }))
            res['attachment_line_ids'] = attachment_lines

        return res

    def action_print_report(self):
        """Genera el reporte de liquidación de gastos con los adjuntos seleccionados."""
        self.ensure_one()

        # Assukargo no incluye adjuntos
        if self.report_type == 'assukargo':
            ordered_attachment_ids = []
        else:
            # Obtener IDs de adjuntos en orden
            ordered_attachment_ids = self.attachment_line_ids.filtered(
                lambda l: l.include
            ).sorted('sequence').mapped('attachment_id').ids

        return self.env.ref(
            'adroc_facturacion_global.action_report_liquidacion_gastos'
        ).report_action(self.invoice_ids, data={
            'wizard_id': self.id,
            'report_type': self.report_type,
            'ordered_attachment_ids': ordered_attachment_ids,
        })

    def action_select_all(self):
        """Selecciona todos los adjuntos."""
        self.ensure_one()
        self.attachment_line_ids.write({'include': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'liquidacion.gastos.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_deselect_all(self):
        """Deselecciona todos los adjuntos."""
        self.ensure_one()
        self.attachment_line_ids.write({'include': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'liquidacion.gastos.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
