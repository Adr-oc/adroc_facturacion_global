# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import UserError


class FacturasEntregadasReport(models.AbstractModel):
    _name = 'report.adroc_facturacion_global.report_facturas_entregadas'
    _description = 'Parser para Reporte de Facturas Entregadas'

    @api.model
    def _get_report_values(self, docids, data=None):
        invoices = self.env['account.move'].browse(docids)

        # Filtrar solo facturas de cliente
        customer_invoices = invoices.filtered(
            lambda inv: inv.move_type in ('out_invoice', 'out_refund')
        )

        if not customer_invoices:
            raise UserError(_('Debe seleccionar facturas de cliente.'))

        # Agrupar por partner
        partners_data = self._get_invoices_by_partner(customer_invoices)

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': customer_invoices,
            'partners_data': partners_data,
            'company': self.env.company,
        }

    def _get_invoices_by_partner(self, invoices):
        """Agrupa las facturas por partner y luego por embarque."""
        partners_data = []

        # Agrupar por partner
        partner_ids = invoices.mapped('partner_id')

        for partner in partner_ids.sorted(key=lambda p: p.name or ''):
            partner_invoices = invoices.filtered(lambda inv: inv.partner_id == partner)

            partners_data.append({
                'partner': partner,
                'groups': self._get_invoices_grouped(partner_invoices),
                'totals': self._get_totals(partner_invoices),
            })

        return partners_data

    def _get_invoices_grouped(self, invoices):
        """Retorna las facturas agrupadas por embarque."""
        grouped = {}

        for invoice in invoices.sorted(key=lambda r: (
            r.mrdc_shipment_id.name or '',
            r.date_sent or fields.Date.today(),
            r.name
        )):
            shipment = invoice.mrdc_shipment_id
            shipment_key = shipment.id if shipment else 0

            if shipment_key not in grouped:
                grouped[shipment_key] = {
                    'shipment': shipment,
                    'shipment_name': shipment.name if shipment else _('Sin Embarque'),
                    'invoices': self.env['account.move'],
                }
            grouped[shipment_key]['invoices'] |= invoice

        return list(grouped.values())

    def _get_totals(self, invoices):
        """Calcula los totales del reporte."""
        total = sum(invoices.mapped('amount_total'))
        total_cuenta_ajena = sum(
            invoices.filtered('mrdc_external_account_id').mapped('amount_total')
        )
        total_honorarios = 0.0

        return {
            'total': total,
            'cuenta_ajena': total_cuenta_ajena,
            'honorarios': total_honorarios,
        }
