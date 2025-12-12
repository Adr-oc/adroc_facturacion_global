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
        # Si viene de wizard, usar los datos del wizard
        report_type = 'normal'
        ordered_attachment_ids = []
        if data and data.get('wizard_id'):
            wizard = self.env['liquidacion.gastos.wizard'].browse(data['wizard_id'])
            customer_invoices = wizard.invoice_ids
            report_type = data.get('report_type', 'normal')
            # Usar IDs ordenados si están disponibles
            ordered_attachment_ids = data.get('ordered_attachment_ids')
            if ordered_attachment_ids is not None:
                # Usar lista ordenada (puede ser vacía para Assukargo)
                selected_attachments = self.env['ir.attachment'].browse(ordered_attachment_ids)
            else:
                selected_attachments = wizard.attachment_ids
        else:
            invoices = self.env['account.move'].browse(docids)
            customer_invoices = invoices.filtered(
                lambda inv: inv.move_type in ('out_invoice', 'out_refund')
            )
            selected_attachments = self.env['ir.attachment']

        if not customer_invoices:
            raise UserError(_('Debe seleccionar facturas de cliente.'))

        # Obtener todos los embarques (pueden ser múltiples)
        shipments = customer_invoices.mapped('mrdc_shipment_id')
        shipments = shipments.filtered(lambda s: s)

        # Agrupar facturas por empresa
        companies_data = self._get_invoices_by_company(customer_invoices)

        # Obtener adjuntos seleccionados o todos si no viene de wizard
        if selected_attachments:
            attachments = self._process_selected_attachments(selected_attachments)
        else:
            attachments = self._get_attachments(shipments, customer_invoices)

        # Calcular totales generales
        grand_totals = self._get_grand_totals(customer_invoices)

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': customer_invoices,
            'shipments': shipments,
            'shipment': shipments[0] if shipments else False,
            'companies_data': companies_data,
            'attachments': attachments,
            'grand_totals': grand_totals,
            'today': fields.Date.today(),
            'report_type': report_type,
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

    def _get_attachments(self, shipments, invoices):
        """Obtiene adjuntos de los embarques y de las facturas."""
        Attachment = self.env['ir.attachment']

        # Adjuntos de los embarques
        shipment_attachments = Attachment.search([
            ('res_model', '=', 'mrdc.shipment'),
            ('res_id', 'in', shipments.ids),
        ]) if shipments else Attachment

        # Adjuntos de las facturas
        invoice_attachments = Attachment.search([
            ('res_model', '=', 'account.move'),
            ('res_id', 'in', invoices.ids),
        ])

        all_attachments = shipment_attachments | invoice_attachments

        return self._process_selected_attachments(all_attachments)

    def _process_selected_attachments(self, all_attachments):
        """Procesa y separa los adjuntos por tipo, preservando el orden original."""
        # Preservar el orden original usando listas
        ordered_ids = all_attachments.ids

        # Separar por tipo manteniendo el orden
        image_ids = [att.id for att in all_attachments if att.mimetype and att.mimetype.startswith('image/')]
        pdf_ids = [att.id for att in all_attachments if att.mimetype == 'application/pdf']
        other_ids = [att.id for att in all_attachments if att.id not in image_ids and att.id not in pdf_ids]

        # Crear recordsets preservando el orden
        Attachment = self.env['ir.attachment']
        image_attachments = Attachment.browse(image_ids)
        pdf_attachments = Attachment.browse(pdf_ids)
        other_attachments = Attachment.browse(other_ids)

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
