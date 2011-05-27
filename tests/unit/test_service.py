# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import json
import os
import unittest

from tests.unit import BaseTest
from webtest import TestApp
from melange.common import config
from melange.ipam.models import IpBlock, IpAddress


class TestController(BaseTest):

    def test_setup(self):
        conf, melange_app = config.load_paste_app('melange',
                {"config_file":
                 os.path.abspath("../../etc/melange.conf.test")}, None)
        self.app = TestApp(melange_app)

    def assertErrorResponse(self, response, expected_status,
                            expected_error):
        self.assertEqual(response.status, expected_status)
        self.assertTrue(expected_error in response.body)


class TestIpBlockController(TestController):

    def test_create(self):
        response = self.app.post("/ipam/ip_blocks",
                                 {'network_id': "300", 'cidr': "10.1.1.0/2"})

        self.assertEqual(response.status, "200 OK")
        saved_block = IpBlock.find_by_network_id("300")
        self.assertEqual(saved_block.cidr, "10.1.1.0/2")
        self.assertEqual(response.json, saved_block.data())

    def test_cannot_create_duplicate_public_cidr(self):
        self.app.post("/ipam/ip_blocks",
                      {"network_id": "12200", 'cidr': "192.1.1.1/2",
                       'type': 'public'})

        response = self.app.post("/ipam/ip_blocks",
                      {"network_id": "22200", 'cidr': "192.1.1.1/2",
                       'type': 'public'}, status="*")

        self.assertEqual(response.status, "400 Bad Request")
        self.assertTrue("[{'cidr': 'cidr for public ip is not unique'}]"
                        in response.body)

    def test_create_with_bad_cidr(self):
        response = self.app.post("/ipam/ip_blocks",
                                 {'network_id': "300", 'cidr': "10..."},
                                 status="*")

        self.assertEqual(response.status, "400 Bad Request")
        self.assertTrue("[{'cidr': 'cidr is invalid'}]" in response.body)

    def test_show(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/2"})
        response = self.app.get("/ipam/ip_blocks/%s" % block.id)

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(response.json, block.data())

    def test_delete(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/2"})
        response = self.app.delete("/ipam/ip_blocks/%s" % block.id)

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(IpBlock.find(block.id), None)

    def test_index(self):
        blocks = _create_blocks("10.1.1.0/32", '10.2.1.0/32', '10.3.1.0/32')
        response = self.app.get("/ipam/ip_blocks")

        self.assertEqual(response.status, "200 OK")
        response_blocks = response.json['ip_blocks']
        self.assertEqual(len(response_blocks), 3)
        self.assertEqual(response_blocks, _data_of(*blocks))

    def test_index_with_pagination(self):
        blocks = _create_blocks("10.1.1.0/32", '10.2.1.0/32',
                                '10.3.1.0/32', '10.4.1.0/32')
        response = self.app.get("/ipam/ip_blocks?limit=2&marker=%s"
                                % blocks[1].id)

        response_blocks = response.json['ip_blocks']
        self.assertEqual(response.status, "200 OK")
        self.assertEqual(len(response_blocks), 2)
        self.assertEqual(response_blocks, _data_of(blocks[2], blocks[3]))


class TestIpAddressController(TestController):

    def test_create(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        response = self.app.post("/ipam/ip_blocks/%s/ip_addresses" % block.id)

        self.assertEqual(response.status, "200 OK")
        allocated_address = IpAddress.find_all_by_ip_block(block.id).first()
        self.assertEqual(allocated_address.address, "10.1.1.0")
        self.assertEqual(response.json, allocated_address.data())

    def test_create_with_given_address(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        response = self.app.post("/ipam/ip_blocks/%s/ip_addresses"
                                 % block.id,
                                 {"address": '10.1.1.2'})

        self.assertEqual(response.status, "200 OK")
        self.assertNotEqual(IpAddress.find_by_block_and_address(block.id,
                                                             "10.1.1.2"), None)

    def test_create_when_no_more_addresses(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/32"})
        block.allocate_ip()

        response = self.app.post("/ipam/ip_blocks/%s/ip_addresses" % block.id,
                                 status="*")
        self.assertEqual(response.status, "422 Unprocessable Entity")
        self.assertTrue("IpBlock is full" in response.body)

    def test_create_fails_when_addresses_are_duplicated(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/29"})
        block.allocate_ip(address='10.1.1.2')

        response = self.app.post("/ipam/ip_blocks/%s/ip_addresses" % block.id,
                                 {'address': '10.1.1.2'},
                                 status="*")
        self.assertEqual(response.status, "422 Unprocessable Entity")
        self.assertTrue("Address is already allocated" in response.body)

    def test_create_fails_when_address_doesnt_belong_to_block(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/32"})

        response = self.app.post("/ipam/ip_blocks/%s/ip_addresses" % block.id,
                                 {'address': '10.1.1.2'},
                                 status="*")
        self.assertEqual(response.status, "422 Unprocessable Entity")
        self.assertTrue("Address does not belong to IpBlock" in response.body)

    def test_create_with_port(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})

        self.app.post("/ipam/ip_blocks/%s/ip_addresses" % block.id,
                                 {"port_id": "1111"})

        allocated_address = IpAddress.find_all_by_ip_block(block.id).first()
        self.assertEqual(allocated_address.port_id, "1111")

    def test_show(self):
        block_1 = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        block_2 = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        ip = block_1.allocate_ip(port_id="3333")
        block_2.allocate_ip(port_id="9999")

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses/%s" %
                                (block_1.id, ip.address))

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(response.json, ip.data())

    def test_show_fails_for_nonexistent_address(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses/%s" %
                                (block.id, '10.1.1.0'), status="*")

        self.assertEqual(response.status, "404 Not Found")
        self.assertTrue("IpAddress Not Found" in response.body)

    def test_show_fails_for_nonexistent_block(self):
        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses/%s" %
                                (1111111111, '10.1.1.0'), status="*")

        self.assertEqual(response.status, "404 Not Found")
        self.assertTrue("IpBlock Not Found" in response.body)

    def test_delete_ip(self):
        block_1 = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        block_2 = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        ip = block_1.allocate_ip()
        block_2.allocate_ip()

        response = self.app.delete("/ipam/ip_blocks/%s/ip_addresses/%s" %
                                (block_1.id, ip.address))

        self.assertEqual(response.status, "200 OK")
        self.assertNotEqual(IpAddress.find(ip.id), None)
        self.assertTrue(IpAddress.find(ip.id).marked_for_deallocation)

    def test_index(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        address_1 = block.allocate_ip()
        address_2 = block.allocate_ip()

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses" % block.id)

        ip_addresses = response.json["ip_addresses"]
        self.assertEqual(response.status, "200 OK")
        self.assertEqual(len(ip_addresses), 2)
        self.assertEqual(ip_addresses[0]['address'], address_1.address)
        self.assertEqual(ip_addresses[1]['address'], address_2.address)

    def test_index_with_pagination(self):
        block = IpBlock.create({'network_id': "301", 'cidr': "10.1.1.0/28"})
        ips = [block.allocate_ip() for i in range(5)]

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses?"
                                "limit=2&marker=%s" % (block.id, ips[1].id))

        ip_addresses = response.json["ip_addresses"]
        self.assertEqual(len(ip_addresses), 2)
        self.assertEqual(ip_addresses[0]['address'], ips[2].address)
        self.assertEqual(ip_addresses[1]['address'], ips[3].address)

    def test_restore_deallocated_ip(self):
        block = IpBlock.create({'network_id': '312', 'cidr': "10.1.1.2/29"})
        ips = [block.allocate_ip() for i in range(5)]
        block.deallocate_ip(ips[0].address)

        response = self.app.put("/ipam/ip_blocks/%s/ip_addresses/"
                                "%s/restore" % (block.id, ips[0].address))

        ip_addresses = [ip.address for ip in
                        IpAddress.find_all_by_ip_block(block.id)]
        self.assertEqual(response.status, "200 OK")
        self.assertEqual(ip_addresses, [ip.address for ip in ips])


class TestIpNatController(TestController):

    def test_create_inside_local_nat(self):
        global_block, = _create_blocks("169.1.1.1/32")
        local_block1, = _create_blocks("10.1.1.1/32")
        local_block2, = _create_blocks("10.0.0.1/32")

        url = "/ipam/ip_blocks/%s/ip_addresses/169.1.1.1/inside_locals"
        json_data = [
            {'ip_block_id': local_block1.id, 'ip_address': "10.1.1.1"},
            {'ip_block_id': local_block2.id, 'ip_address': "10.0.0.1"},
        ]
        request_data = {'ip_addresses': json.dumps(json_data)}
        response = self.app.post(url % global_block.id, request_data)

        self.assertEqual(response.status, "200 OK")
        ips = global_block.find_allocated_ip("169.1.1.1").inside_locals()
        inside_locals = [ip.address for ip in ips]

        self.assertEqual(len(inside_locals), 2)
        self.assertTrue("10.1.1.1" in inside_locals)
        self.assertTrue("10.0.0.1" in inside_locals)
        local_ip = IpAddress.find_by_block_and_address(local_block1.id,
                                                       "10.1.1.1")
        self.assertEqual(local_ip.inside_globals()[0].address, "169.1.1.1")

    def test_create_inside_global_nat(self):
        global_block, local_block = _create_blocks('192.1.1.1/32',
                                                        '10.1.1.1/32')
        global_ip = global_block.allocate_ip()
        local_ip = local_block.allocate_ip()

        response = self.app.post("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                 "inside_globals"
                              % (local_block.id, local_ip.address),
                              {"ip_addresses": json.dumps(
                                [{"ip_block_id": global_block.id,
                                  "ip_address": global_ip.address}])})

        self.assertEqual(response.status, "200 OK")

        self.assertEqual(len(local_ip.inside_globals()), 1)
        self.assertEqual(global_ip.id, local_ip.inside_globals()[0].id)
        self.assertEqual(local_ip.id, global_ip.inside_locals()[0].id)

    def test_delete_inside_globals(self):
        global_block, local_block = _create_blocks('192.1.1.1/32',
                                                        '10.1.1.1/32')
        global_ip = global_block.allocate_ip()
        local_ip = local_block.allocate_ip()
        local_ip.add_inside_globals([global_ip])

        response = self.app.delete("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                 "inside_globals"
                              % (local_block.id, local_ip.address))

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(local_ip.inside_globals(), [])

    def test_delete_inside_global_for_specific_address(self):
        global_block, local_block = _create_blocks('192.1.1.1/28',
                                                    '10.1.1.1/28')
        global_ips, = _allocate_ips((global_block, 3))
        local_ip = local_block.allocate_ip()
        local_ip.add_inside_globals(global_ips)

        response = self.app.delete("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                 "inside_globals/%s"
                                   % (local_block.id, local_ip.address,
                                      global_ips[1].address))

        globals_left = [ip.address for ip in local_ip.inside_globals()]
        self.assertEqual(globals_left, [global_ips[0].address,
                                        global_ips[2].address])

    def test_delete_inside_local_for_specific_address(self):
        global_block, local_block = _create_blocks('192.1.1.1/28',
                                                    '10.1.1.1/28')
        local_ips, = _allocate_ips((local_block, 3))
        global_ip = global_block.allocate_ip()
        global_ip.add_inside_locals(local_ips)

        response = self.app.delete("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                 "inside_locals/%s"
                                   % (global_block.id, global_ip.address,
                                      local_ips[1].address))

        locals_left = [ip.address for ip in global_ip.inside_locals()]
        self.assertEqual(locals_left, [local_ips[0].address,
                                        local_ips[2].address])

    def test_delete_inside_locals(self):
        global_block, local_block = _create_blocks('192.1.1.1/32',
                                                        '10.1.1.1/32')
        global_ip = global_block.allocate_ip()
        local_ip = local_block.allocate_ip()
        global_ip.add_inside_locals([local_ip])

        response = self.app.delete("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                 "inside_locals"
                              % (global_block.id, global_ip.address))

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(global_ip.inside_locals(), [])

    def test_show_inside_globals(self):
        local_block, global_block_1, global_block_2 =\
                                    _create_blocks("10.1.1.1/30",
                                                        "192.1.1.1/30",
                                                        "169.1.1.1/30")
        [local_ip], [global_ip_1], [global_ip_2] =\
                                    _allocate_ips((local_block, 1),
                                                       (global_block_1, 1),
                                                       (global_block_2, 1))
        local_ip.add_inside_globals([global_ip_1, global_ip_2])

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                "inside_globals"
                                 % (local_block.id, local_ip.address))

        self.assertEqual(response.json,
                         {'ip_addresses': _data_of(global_ip_1,
                                                   global_ip_2)})

    def test_show_inside_globals_with_pagination(self):
        local_block, global_block = _create_blocks("10.1.1.1/8",
                                                   "192.1.1.1/8")
        [local_ip], global_ips = _allocate_ips((local_block, 1),
                                               (global_block, 5))
        local_ip.add_inside_globals(global_ips)

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                "inside_globals?limit=2&marker=%s"
                                % (local_block.id, local_ip.address,
                                   global_ips[1].id))

        self.assertEqual(response.json,
                        {'ip_addresses': _data_of(global_ips[2],
                                                  global_ips[3])})

    def test_show_inside_locals_with_pagination(self):
        global_block, local_block = _create_blocks("192.1.1.1/8",
                                                        "10.1.1.1/8")
        [global_ip], local_ips = _allocate_ips((global_block, 1),
                                                    (local_block, 5))
        global_ip.add_inside_locals(local_ips)

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                "inside_locals?limit=2&marker=%s"
                                % (global_block.id,
                                   global_ip.address,
                                   local_ips[1].id))

        self.assertEqual(response.json,
                         {'ip_addresses': _data_of(local_ips[2],
                                                   local_ips[3])})

    def test_show_inside_locals(self):
        global_block, local_block = _create_blocks("192.1.1.1/8",
                                                   "10.1.1.1/8")
        [global_ip], local_ips = _allocate_ips((global_block, 1),
                                               (local_block, 5))
        global_ip.add_inside_locals(local_ips)

        response = self.app.get("/ipam/ip_blocks/%s/ip_addresses/%s/"
                                "inside_locals"
                                % (global_block.id, global_ip.address))

        self.assertEqual(response.json,
                         {'ip_addresses': _data_of(*local_ips)})

    def test_show_nats_for_nonexistent_block(self):
        for action in ["inside_locals", "inside_globals"]:
            non_existant_block_id = 12122
            url = "/ipam/ip_blocks/%s/ip_addresses/%s/%s"
            response = self.app.get(url % (non_existant_block_id,
                                           "10.1.1.2", action),
                                    status='*')

            self.assertErrorResponse(response, "404 Not Found",
                                     "IpBlock Not Found")

    def test_show_nats_for_nonexistent_address(self):
        for action in ["inside_locals", "inside_globals"]:
            ip_block, = _create_blocks("191.1.1.1/10")
            url = "/ipam/ip_blocks/%s/ip_addresses/%s/%s"
            response = self.app.get(url % (ip_block.id, '10.1.1.2', action),
                                    status='*')

            self.assertErrorResponse(response, "404 Not Found",
                                     "IpAddress Not Found")

    def test_delete_nats_for_nonexistent_block(self):
        for action in ["inside_locals", "inside_globals"]:
            non_existant_block_id = 12122
            url = "/ipam/ip_blocks/%s/ip_addresses/%s/%s"
            response = self.app.delete(url % (non_existant_block_id,
                                              '10.1.1.2', action), status='*')

            self.assertErrorResponse(response, "404 Not Found",
                                     "IpBlock Not Found")

    def test_delete_nats_for_nonexistent_address(self):
        for action in ["inside_locals", "inside_globals"]:
            ip_block, = _create_blocks("191.1.1.1/10")
            url = "/ipam/ip_blocks/%s/ip_addresses/%s/%s"
            response = self.app.delete(url % (ip_block.id, '10.1.1.2', action),
                                    status='*')

            self.assertErrorResponse(response, "404 Not Found",
                                     "IpAddress Not Found")


def _allocate_ips(*args):
    return [[ip_block.allocate_ip() for i in range(num_of_ips)]
            for ip_block, num_of_ips in args]


def _create_blocks(*args):
    return [IpBlock.create({"cidr": cidr}) for cidr in args]


def _data_of(*args):
    return [model.data() for model in args]