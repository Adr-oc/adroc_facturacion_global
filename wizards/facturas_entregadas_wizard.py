# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FacturasEntregadasWizard(models.TransientModel):
    _name = 'facturas.entregadas.wizard'
    _description = 'Wizard para Reporte de Facturas Entregadas'

    invoice_ids = fields.Many2many(
        'account.move',
        'facturas_entregadas_wizard_invoice_rel',
        'wizard_id',
        'invoice_id',
        string='Facturas',
    )

    line_ids = fields.One2many(
        'facturas.entregadas.wizard.line',
        'wizard_id',
        string='Clientes',
    )

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

        # Generar líneas agrupadas por cliente
        if 'line_ids' in fields_list:
            res['line_ids'] = self._prepare_lines(customer_invoices)

        return res

    def _prepare_lines(self, invoices):
        """Prepara las líneas del wizard agrupadas por cliente."""
        # Filtrar facturas que tengan cliente asignado
        invoices_with_partner = invoices.filtered(lambda inv: inv.partner_id)

        # Agrupar facturas por partner
        partner_invoices = {}
        for invoice in invoices_with_partner:
            partner = invoice.partner_id
            if partner and partner.id:
                if partner.id not in partner_invoices:
                    partner_invoices[partner.id] = {
                        'partner': partner,
                        'invoices': self.env['account.move'],
                    }
                partner_invoices[partner.id]['invoices'] |= invoice

        # Crear comandos para líneas
        lines_commands = []
        for partner_id, data in partner_invoices.items():
            partner = data['partner']
            if not partner or not partner.id:
                continue
            partner_invs = data['invoices']
            # Construir la dirección por defecto del partner
            default_address = self._get_partner_address(partner)

            lines_commands.append((0, 0, {
                'partner_id': partner.id,
                'invoice_ids': [(6, 0, partner_invs.ids)],
                'address': default_address,
                'invoice_count': len(partner_invs),
                'total_amount': sum(partner_invs.mapped('amount_total')),
            }))

        return lines_commands

    def _get_partner_address(self, partner):
        """Construye la dirección formateada del partner."""
        parts = []
        if partner.street:
            parts.append(partner.street)
        if partner.street2:
            parts.append(partner.street2)
        if partner.city:
            parts.append(partner.city)
        if partner.state_id:
            parts.append(partner.state_id.name)
        if partner.zip:
            parts.append(partner.zip)
        if partner.country_id:
            parts.append(partner.country_id.name)

        return ', '.join(parts) if parts else ''

    def action_print_report(self):
        """Genera el reporte de facturas entregadas con las direcciones personalizadas."""
        self.ensure_one()

        # Preparar datos de direcciones personalizadas
        custom_addresses = {}
        for line in self.line_ids:
            custom_addresses[line.partner_id.id] = line.address

        return self.env.ref(
            'adroc_facturacion_global.action_report_facturas_entregadas'
        ).report_action(
            self.invoice_ids,
            data={
                'wizard_id': self.id,
                'custom_addresses': custom_addresses,
            }
        )


class FacturasEntregadasWizardLine(models.TransientModel):
    _name = 'facturas.entregadas.wizard.line'
    _description = 'Línea de Wizard Facturas Entregadas'

    wizard_id = fields.Many2one(
        'facturas.entregadas.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
    )

    invoice_ids = fields.Many2many(
        'account.move',
        'facturas_entregadas_wizard_line_invoice_rel',
        'line_id',
        'invoice_id',
        string='Facturas',
    )

    address = fields.Text(
        string='Dirección de Entrega',
        help='Dirección donde se entregarán las facturas. Por defecto se usa la dirección del cliente.',
    )

    invoice_count = fields.Integer(
        string='# Facturas',
        readonly=True,
    )

    total_amount = fields.Float(
        string='Total',
        readonly=True,
    )
