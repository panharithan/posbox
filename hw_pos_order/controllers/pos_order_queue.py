# -*- coding: utf-8 -*-
import json
import logging
import werkzeug.utils
import threading
from subprocess import call
from collections import deque

from openerp import http
from openerp.http import request

_logger = logging.getLogger(__name__)
lock = threading.Lock()

class PosOrder(http.Controller):
    waiter_event_data = {}

    event_data_stack = deque()
    sending_event_data_stack = []
    
    cashier_event_data = threading.Event()
    cashier_event_sync = threading.Event()
    cashier_event_print_bill = threading.Event()

    cashier_client_data = { 'order': False, 'event': False }
    cashier_order_data = { 'status': False, 'orders': None }
    cashier_print_bill_data = { 'order_uid': False, 'waiter_id': None, 'status': False }
    
    waiter_sync_event = {}


    @http.route('/hw_proxy/hello', type='http', auth='none', cors='*')
    def hello(self):
        return "ping"

    @http.route('/hw_proxy/update_waiter_order', type='json', auth='none', cors='*')
    def update_waiter_order(self, order=False, options=False):
        PosOrder.event_data_stack.append({
            'order': order,
            'session_uid': 'cashier',
            'options': options,
            'event': 'update_waiter_order',
        })
        return "READY"

    @http.route('/pos_order/waiter/get_serialized_order', type='json', auth='none', cors='*')
    def get_waiter_serialized_order(self, session_uid):
        result = PosOrder.sending_event_data_stack
        if not PosOrder.waiter_event_data or session_uid not in PosOrder.waiter_event_data:
            return { 'stop_long_polling': True }
        if PosOrder.waiter_event_data[session_uid].wait(28):
            _logger.info("------> get_waiter_serialized_order ----=++++++ : %s", len(PosOrder.sending_event_data_stack))
            PosOrder.waiter_event_data[session_uid].clear()
            return result
        return {'order': False, 'event': 'update_waiter_order'}

    @http.route('/hw_proxy/update_cashier_order', type='json', auth='none', cors='*')
    def update_cashier_order(self, session_uid, order=False, options=False):
        _logger.info("------> update_cashier_order == session_uid: %s", session_uid)
        PosOrder.cashier_client_data['order'] = order
        PosOrder.cashier_client_data['session_uid'] = session_uid
        PosOrder.cashier_client_data['options'] = options
        PosOrder.cashier_client_data['event'] = 'update_cashier_order'
        PosOrder.cashier_event_data.set()
        
        PosOrder.event_data_stack.append({
            'order': order,
            'session_uid': session_uid,
            'options': options,
            'event': 'update_waiter_order',
        })
                
        return PosOrder.cashier_client_data

    @http.route('/pos_order/cashier/get_serialized_order', type='json', auth='none', cors='*')
    def get_cashier_serialized_order(self):
        result = PosOrder.cashier_client_data
        if PosOrder.cashier_event_data.wait(28):
            PosOrder.cashier_event_data.clear()
            return result
        return {'order': False, 'event': 'update_cashier_order'}

    # this function will be call when waiter screen is loaded to sync orders data from cashier machine to local
    @http.route('/pos_order/waiter/init', type='json', auth='none', cors='*')
    def get_waiter_serialized_order_first(self, session_uid):
        if not PosOrder.waiter_event_data or session_uid not in PosOrder.waiter_event_data:
            PosOrder.waiter_event_data[session_uid] = threading.Event()
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


def send_event_data():
    lock.acquire()
    try:
        _logger.info("------> PosOrder.event_data_stack: %s", PosOrder.event_data_stack)
        
        if not PosOrder.event_data_stack:
            return
        PosOrder.sending_event_data_stack.clear()
        while PosOrder.event_data_stack:
            PosOrder.sending_event_data_stack.append(PosOrder.event_data_stack.popleft())

        _logger.info("------> get_waiter_serialized_order: %s", 2)
        for _, waiter_client in PosOrder.waiter_event_data.items():
            waiter_client.set()
        _logger.info("------> get_waiter_serialized_order: %s", 3)

    finally:
        lock.release() # release lock, no matter what


def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec) 
        func()  
    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t

# 3 sec interval to prevent lost data events
set_interval(send_event_data, 3)