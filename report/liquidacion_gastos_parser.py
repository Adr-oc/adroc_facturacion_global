# -*- coding: utf-8 -*-

import base64
from datetime import date
from io import BytesIO
from odoo import api, models, fields, _
from odoo.exceptions import UserError

# Fecha mínima para ordenamiento
MIN_DATE = date(1900, 1, 1)

# Intentar importar PyPDF2 para concatenar PDFs
try:
    from PyPDF2 import PdfMerger
    HAS_PYPDF2 = True
except ImportError:
    try:
        from PyPDF2 import PdfFileMerger as PdfMerger
        HAS_PYPDF2 = True
    except ImportError:
        HAS_PYPDF2 = False


class LiquidacionGastosReport(models.AbstractModel):
    _name = 'report.adroc_facturacion_global.report_liquidacion_gastos'
    _description = 'Parser para Reporte de Liquidación de Gastos de Importación'

    @api.model
    def _get_report_values(self, docids, data=None):
        invoices = self.env['account.move'].browse(docids)

        # Filtrar solo facturas de cliente
        customer_invoices = invoices.filtered(
            lambda inv: inv.move_type in ('out_invoice', 'out_refund')
        )

        if not customer_invoices:
            raise UserError(_('Debe seleccionar facturas de cliente.'))

        # Validar que todas las facturas sean del mismo embarque
        shipments = customer_invoices.mapped('mrdc_shipment_id')
        shipments = shipments.filtered(lambda s: s)  # Filtrar los que no son False

        if len(shipments) > 1:
            raise UserError(_(
                'Todas las facturas deben pertenecer al mismo embarque.\n'
                'Embarques seleccionados: %s'
            ) % ', '.join(shipments.mapped('name')))

        if not shipments:
            raise UserError(_('Las facturas seleccionadas no tienen embarque asociado.'))

        shipment = shipments[0]

        # Agrupar facturas por empresa
        companies_data = self._get_invoices_by_company(customer_invoices)

        # Obtener adjuntos
        attachments = self._get_attachments(shipment, customer_invoices)

        # Calcular totales generales
        grand_totals = self._get_grand_totals(customer_invoices)

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': customer_invoices,
            'shipment': shipment,
            'companies_data': companies_data,
            'attachments': attachments,
            'grand_totals': grand_totals,
            'today': fields.Date.today(),
        }

    def _get_invoices_by_company(self, invoices):
        """Agrupa las facturas por empresa (company_id)."""
        companies_data = []
        company_ids = invoices.mapped('company_id')

        for company in company_ids.sorted(key=lambda c: c.name or ''):
            company_invoices = invoices.filtered(lambda inv: inv.company_id == company)

            # Calcular totales por moneda
            totals_gtq = sum(company_invoices.filtered(
                lambda inv: inv.currency_id.name == 'GTQ'
            ).mapped('amount_total'))

            totals_usd = sum(company_invoices.filtered(
                lambda inv: inv.currency_id.name == 'USD'
            ).mapped('amount_total'))

            companies_data.append({
                'company': company,
                'invoices': company_invoices.sorted(key=lambda r: (
                    r.date_sent or MIN_DATE,
                    r.invoice_date or MIN_DATE,
                    r.name or ''
                )),
                'total_gtq': totals_gtq,
                'total_usd': totals_usd,
                'bank_gtq': company.cuenta if hasattr(company, 'cuenta') else False,
                'bank_usd': company.cuenta_dolar if hasattr(company, 'cuenta_dolar') else False,
            })

        return companies_data

    def _get_attachments(self, shipment, invoices):
        """Obtiene adjuntos del embarque y de las facturas."""
        Attachment = self.env['ir.attachment']

        # Adjuntos del embarque
        shipment_attachments = Attachment.search([
            ('res_model', '=', 'mrdc.shipment'),
            ('res_id', '=', shipment.id),
        ])

        # Adjuntos de las facturas
        invoice_attachments = Attachment.search([
            ('res_model', '=', 'account.move'),
            ('res_id', 'in', invoices.ids),
        ])

        all_attachments = shipment_attachments | invoice_attachments

        # Separar por tipo
        image_attachments = all_attachments.filtered(
            lambda a: a.mimetype and a.mimetype.startswith('image/')
        )
        pdf_attachments = all_attachments.filtered(
            lambda a: a.mimetype == 'application/pdf'
        )
        other_attachments = all_attachments - image_attachments - pdf_attachments

        return {
            'images': image_attachments,
            'pdfs': pdf_attachments,
            'others': other_attachments,
            'all': all_attachments,
            'has_pypdf2': HAS_PYPDF2,
        }

    def _get_grand_totals(self, invoices):
        """Calcula los totales generales por moneda."""
        totals_gtq = sum(invoices.filtered(
            lambda inv: inv.currency_id.name == 'GTQ'
        ).mapped('amount_total'))

        totals_usd = sum(invoices.filtered(
            lambda inv: inv.currency_id.name == 'USD'
        ).mapped('amount_total'))

        return {
            'total_gtq': totals_gtq,
            'total_usd': totals_usd,
        }
