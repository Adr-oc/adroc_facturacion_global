# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LiquidacionGastosWizard(models.TransientModel):
    _name = 'liquidacion.gastos.wizard'
    _description = 'Wizard para seleccionar adjuntos de Liquidación de Gastos'

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

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'liquidacion_gastos_wizard_attachment_rel',
        'wizard_id',
        'attachment_id',
        string='Adjuntos a incluir',
    )

    available_attachment_ids = fields.Many2many(
        'ir.attachment',
        'liquidacion_gastos_wizard_available_attachment_rel',
        'wizard_id',
        'attachment_id',
        string='Adjuntos disponibles',
        compute='_compute_available_attachments',
    )

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

        # Pre-seleccionar todos los adjuntos disponibles
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
        if all_attachments:
            res['attachment_ids'] = [(6, 0, all_attachments.ids)]

        return res

    def action_print_report(self):
        """Genera el reporte de liquidación de gastos con los adjuntos seleccionados."""
        self.ensure_one()

        return self.env.ref(
            'adroc_facturacion_global.action_report_liquidacion_gastos'
        ).report_action(self.invoice_ids, data={'wizard_id': self.id})

    def action_select_all(self):
        """Selecciona todos los adjuntos disponibles."""
        self.ensure_one()
        self.attachment_ids = self.available_attachment_ids
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
        self.attachment_ids = [(5, 0, 0)]
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'liquidacion.gastos.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
