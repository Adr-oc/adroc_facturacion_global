# -*- coding: utf-8 -*-

import base64
import logging
from io import BytesIO
from odoo import api, models

_logger = logging.getLogger(__name__)

# Intentar importar PyPDF2
try:
    from PyPDF2 import PdfMerger, PdfReader
    HAS_PYPDF2 = True
except ImportError:
    try:
        from PyPDF2 import PdfFileMerger as PdfMerger, PdfFileReader as PdfReader
        HAS_PYPDF2 = True
    except ImportError:
        HAS_PYPDF2 = False
        _logger.warning("PyPDF2 no está instalado. No se podrán concatenar PDFs.")

# Intentar importar PIL para convertir imágenes a PDF
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    _logger.warning("PIL/Pillow no está instalado. No se podrán convertir imágenes a PDF.")


class IrActionsReportLiquidacion(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None, **kwargs):
        """Override para concatenar PDFs e imágenes al reporte de liquidación."""
        # Generar el PDF base
        pdf_content, content_type = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data, **kwargs)

        # Verificar si es el reporte de liquidación
        report = self._get_report(report_ref)
        if report.report_name != 'adroc_facturacion_global.report_liquidacion_gastos':
            return pdf_content, content_type

        # Verificar si viene del wizard con adjuntos
        if not data or not data.get('wizard_id'):
            return pdf_content, content_type

        if not HAS_PYPDF2:
            _logger.warning("PyPDF2 no disponible, no se pueden concatenar adjuntos")
            return pdf_content, content_type

        # Obtener el wizard
        wizard = self.env['liquidacion.gastos.wizard'].browse(data['wizard_id'])
        if not wizard.exists():
            return pdf_content, content_type

        # Usar los IDs ordenados pasados desde el wizard (vacío para Assukargo)
        ordered_attachment_ids = data.get('ordered_attachment_ids')
        if ordered_attachment_ids is None:
            # Fallback: usar attachment_ids del wizard
            ordered_attachment_ids = wizard.attachment_ids.ids

        if not ordered_attachment_ids:
            return pdf_content, content_type

        try:
            # Crear merger
            merger = PdfMerger()

            # Agregar el PDF principal del reporte
            merger.append(BytesIO(pdf_content))

            # Procesar adjuntos EN EL ORDEN EXACTO de la lista
            Attachment = self.env['ir.attachment']
            for att_id in ordered_attachment_ids:
                attachment = Attachment.browse(att_id)
                if not attachment.exists() or not attachment.datas:
                    continue

                mimetype = attachment.mimetype or ''

                if mimetype == 'application/pdf':
                    # Es un PDF
                    try:
                        pdf_data = base64.b64decode(attachment.datas)
                        merger.append(BytesIO(pdf_data))
                        _logger.info(f"PDF adjunto agregado: {attachment.name}")
                    except Exception as e:
                        _logger.warning(f"Error al agregar PDF {attachment.name}: {e}")

                elif mimetype.startswith('image/') and HAS_PIL:
                    # Es una imagen
                    try:
                        img_pdf = self._image_to_pdf(attachment)
                        if img_pdf:
                            merger.append(BytesIO(img_pdf))
                            _logger.info(f"Imagen convertida a PDF: {attachment.name}")
                    except Exception as e:
                        _logger.warning(f"Error al convertir imagen {attachment.name}: {e}")

            # Generar PDF final
            output = BytesIO()
            merger.write(output)
            merger.close()

            return output.getvalue(), content_type

        except Exception as e:
            _logger.error(f"Error al concatenar PDFs: {e}")
            return pdf_content, content_type

    def _image_to_pdf(self, attachment):
        """Convierte una imagen adjunta a PDF."""
        if not HAS_PIL:
            return None

        try:
            # Decodificar la imagen
            img_data = base64.b64decode(attachment.datas)
            img = Image.open(BytesIO(img_data))

            # Convertir a RGB si es necesario (para evitar problemas con RGBA)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Crear fondo blanco
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Redimensionar si es muy grande
            max_size = (2000, 2000)
            img.thumbnail(max_size, Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)

            # Convertir a PDF
            pdf_buffer = BytesIO()
            img.save(pdf_buffer, format='PDF', resolution=100.0)

            return pdf_buffer.getvalue()

        except Exception as e:
            _logger.warning(f"Error al convertir imagen a PDF: {e}")
            return None
