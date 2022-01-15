# -*- coding: utf-8 -*-
import json
import logging
import werkzeug.utils
import threading
from subprocess import call
from Queue import Queue

from openerp import http
from openerp.http import request

_logger = logging.getLogger(__name__)


class PosOrder(http.Controller):

    waiter_event_data = {}
    waiter_queue_data = { }

    cashier_event_data = threading.Event()
    cashier_event_sync = threading.Event()
    cashier_event_print_bill = threading.Event()
    cashier_queue_data = Queue()
    cashier_order_data = { 'status': False, 'orders': None }
    cashier_print_bill_data = { 'order_uid': False, 'waiter_id': None, 'status': False }
    
    waiter_sync_event = {}

    @http.route('/hw_proxy/hello', type='http', auth='none', cors='*')
    def hello(self):
        return "ping"

    @http.route('/hw_proxy/update_waiter_order', type='json', auth='none', cors='*')
    def update_waiter_order(self, order=False, options=False):
        for session_uid, waiter_client in PosOrder.waiter_event_data.items():
            PosOrder.waiter_queue_data[session_uid].put({
                'session_uid': 'cashier',
                'order': order,
                'options': options,
                'event': 'update_waiter_order'
            })
            waiter_client.set()
        return "READY"

    @http.route('/pos_order/waiter/get_serialized_order', type='json', auth='none', cors='*')
    def get_waiter_serialized_order(self, session_uid):
        if not PosOrder.waiter_event_data or session_uid not in PosOrder.waiter_event_data:
            return { 'stop_long_polling': True }
        if not PosOrder.waiter_queue_data[session_uid].empty():
            return PosOrder.waiter_queue_data[session_uid].get()
        if PosOrder.waiter_event_data[session_uid].wait(28):
            PosOrder.waiter_event_data[session_uid].clear()
            if not PosOrder.waiter_queue_data[session_uid].empty():
                return PosOrder.waiter_queue_data[session_uid].get()
        
        return {'order': False, 'event': 'update_waiter_order'}

    @http.route('/hw_proxy/update_cashier_order', type='json', auth='none', cors='*')
    def update_cashier_order(self, session_uid, order=False, options=False):
        PosOrder.cashier_queue_data.put({
            'order': order,
            'options': options,
            'event': 'update_cashier_order'
        })
        PosOrder.cashier_event_data.set()

        for key, waiter_client in PosOrder.waiter_event_data.items():
            if key != session_uid:
                PosOrder.waiter_queue_data[key].put({
                    'session_uid': session_uid,
                    'order': order,
                    'options': options,
                    'event': 'update_waiter_order'
                })
                waiter_client.set()
                
        return True

    @http.route('/pos_order/cashier/get_serialized_order', type='json', auth='none', cors='*')
    def get_cashier_serialized_order(self):
        if not PosOrder.cashier_queue_data.empty():
            return PosOrder.cashier_queue_data.get()
        if PosOrder.cashier_event_data.wait(28):
            PosOrder.cashier_event_data.clear()
            if not PosOrder.cashier_queue_data.empty():
                return PosOrder.cashier_queue_data.get()
        return {'order': False, 'event': 'update_cashier_order'}

    # this function will be call when waiter screen is loaded to sync orders data from cashier machine to local
    @http.route('/pos_order/waiter/init', type='json', auth='none', cors='*')
    def get_waiter_serialized_order_first(self, session_uid):
        if not PosOrder.waiter_event_data or session_uid not in PosOrder.waiter_event_data:
            PosOrder.waiter_event_data[session_uid] = threading.Event()
        
        if not PosOrder.waiter_queue_data or session_uid not in PosOrder.waiter_queue_data:
            PosOrder.waiter_queue_data[session_uid] = Queue()

        # add sync event in and trigger cashier response
        if PosOrder.waiter_sync_event and session_uid in PosOrder.waiter_sync_event:
            del PosOrder.waiter_sync_event[session_uid]
        PosOrder.waiter_sync_event[session_uid] = threading.Event()
        PosOrder.cashier_event_sync.set()

        if PosOrder.waiter_sync_event[session_uid].wait(28):
            PosOrder.waiter_sync_event[session_uid].clear()
            del PosOrder.waiter_sync_event[session_uid]

        result = PosOrder.cashier_order_data

        return result
        
    @http.route('/pos_order/waiter/print_bill', type='json', auth='none', cors='*')
    def waiter_print_bill(self, order_uid, session_uid):
        PosOrder.cashier_print_bill_data['order_uid'] = order_uid
        PosOrder.cashier_print_bill_data['waiter_id'] = session_uid
        PosOrder.cashier_print_bill_data['status'] = True
        PosOrder.cashier_event_print_bill.set()
    
    # Cahsier machine will call this endpoint and wait until got a sync signal
    @http.route('/pos_order/cashier/print_bill_request', type='json', auth='none', cors='*')
    def cashier_print_bill_request(self):
        if PosOrder.cashier_event_print_bill.wait(28):
            PosOrder.cashier_event_print_bill.clear()
            return PosOrder.cashier_print_bill_data
        return { 'order_uid': False, 'waiter_id': None, 'status': False }

    # Cahsier machine will call this endpoint and wait until got a sync signal
    @http.route('/pos_order/cashier/sync_order_request', type='json', auth='none', cors='*')
    def cashier_sync_order_request(self):
        if PosOrder.cashier_event_sync.wait(28):
            PosOrder.cashier_event_sync.clear()
            return { 'has_request': True, 'event': 'waiter_sync_orders'}
        return {'has_request': False, 'event': 'waiter_sync_orders'}

    # Cashier will send latest orders data to this endpoint and trigger to response waiter sync request 
    @http.route('/pos_order/cashier/sync_order_response', type='json', auth='none', cors='*')
    def cashier_sync_order_response(self, orders):
        PosOrder.cashier_order_data = { 'status': True, 'orders': orders }
        for _, e in PosOrder.waiter_sync_event.items():
            e.set()
        return {'status': True, 'event': 'waiter_sync_orders'}