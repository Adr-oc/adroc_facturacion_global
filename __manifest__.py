# -*- coding: utf-8 -*-
{
    'name': 'Adroc Facturación Global',
    'version': '19.0.1.0.2',
    'category': 'Accounting',
    'summary': 'Reportes y funcionalidades globales de facturación',
    'description': """
        Módulo de facturación global con reportes personalizados.

        Funcionalidades:
        - Reporte de Detalle de Facturas Entregadas
        - Reporte de Liquidación de Gastos de Importación
        - Agrupación por embarque y empresa
    """,
    'author': 'Adroc',
    'website': '',
    'depends': [
        'account',
        'mrdc_shipment_base',
    ],
    'data': [
        'report/facturas_entregadas_report.xml',
        'report/facturas_entregadas_template.xml',
        'report/liquidacion_gastos_report.xml',
        'report/liquidacion_gastos_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
