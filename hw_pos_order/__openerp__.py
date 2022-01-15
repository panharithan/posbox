# -*- coding: utf-8 -*-
{
    'name': 'POS Order Driver',
    'version': '1.0',
    'category': 'Hardware Drivers',
    'sequence': 6,
    'website': 'https://www.odoo.com/page/point-of-sale',
    'summary': 'Hardware Driver for ESC/POS Printers and Cashdrawers',
    'description': """
POS Order Sync Driver
=======================
""",
    'author': 'Sswitchh Consultant',
    'depends': ['hw_proxy'],
    'external_dependencies': {
        'python' : ['usb.core','serial','qrcode'],
    },
    'test': [
    ],
    'installable': True,
    'auto_install': False,
}
