# -*- coding: utf-8 -*-

from odoo import api, fields, models


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

    # Campos computados para buscar la línea de cuenta ajena y el gasto relacionado
    related_external_line_id = fields.Many2one(
        'mrdc.external_account.line',
        string='Línea Cuenta Ajena Relacionada',
        compute='_compute_related_external_line',
        store=False,
        help='Línea de cuenta ajena donde esta factura aparece como asiento contable',
    )
    related_expense_id = fields.Many2one(
        'account.move',
        string='Gasto Relacionado',
        compute='_compute_related_external_line',
        store=False,
        help='Gasto de la línea de cuenta ajena relacionada',
    )
    related_expense_series = fields.Char(
        string='Serie Factura CA',
        compute='_compute_related_external_line',
        store=False,
        help='Serie de la factura del gasto relacionado',
    )
    related_expense_number = fields.Char(
        string='No. Factura CA',
        compute='_compute_related_external_line',
        store=False,
        help='Número de la factura del gasto relacionado',
    )

    @api.depends('name')
    def _compute_related_external_line(self):
        ExternalLine = self.env['mrdc.external_account.line']
        for move in self:
            # Buscar si esta factura aparece como move_id en alguna línea de cuenta ajena
            line = ExternalLine.search([('move_id', '=', move.id)], limit=1)
            move.related_external_line_id = line
            if line:
                move.related_expense_id = line.expense_id
                move.related_expense_series = line.invoice_series or ''
                move.related_expense_number = line.invoice_number or ''
            else:
                move.related_expense_id = False
                move.related_expense_series = ''
                move.related_expense_number = ''
