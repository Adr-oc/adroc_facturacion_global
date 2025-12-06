# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    password_payment_date = fields.Date(
        string='Fecha Pago Contraseña',
        help='Fecha de pago de la contraseña',
    )
    invoice_comment = fields.Text(
        string='Comentario Factura',
        help='Comentario o nota adicional de la factura',
    )
