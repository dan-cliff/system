# -*- coding: utf-8 -*-
"""Helpers for testing Node roles. Other apps' tests import these:

    from odoo.addons.iot_interfaces.tests.common import pair
"""
import time

from ..lib import iot_auth


class Signer:
    """Signs requests the way a paired Node does."""

    def __init__(self, node_key, secret, mac='b8:27:eb:00:00:01'):
        self.node_key = node_key
        self.secret = secret
        self.mac = mac
        self.last = 0

    def headers(self, method, path, body=b'', timestamp=None, secret=None):
        if timestamp is None:
            self.last = timestamp = max(int(time.time() * 1000), self.last + 1)
        return {
            iot_auth.HEADER_NODE: self.node_key,
            iot_auth.HEADER_TIMESTAMP: str(timestamp),
            iot_auth.HEADER_MAC: self.mac,
            iot_auth.HEADER_SIGNATURE: iot_auth.sign(
                secret or self.secret, method, path, timestamp, self.mac, self.node_key, body),
        }


class FakeRequest:
    """Enough of a werkzeug request for _iot_authenticate."""

    def __init__(self, method, path, headers, body=b''):
        self.method = method
        self.path, _sep, query = path.partition('?')
        self.query_string = query.encode()
        self.headers = headers
        self.body = body

    def get_data(self, cache=True):
        return self.body


def pair(node, mac='b8:27:eb:00:00:01', macs=None):
    """Pair a Node as its program would: returns a Signer holding its key."""
    code = node.env['iot.node.pair.wizard'].browse(node.action_pair()['res_id']).code
    paired, secret = node._iot_pair(code, node.role, mac, macs or [mac], 'raspberrypi')
    return Signer(paired.node_key, secret, mac)
