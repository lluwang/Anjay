# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 AVSystem <avsystem@avsystem.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import time

from framework.lwm2m_test import *

class RetransmissionTest:
    class TestMixin:
        # Note that these values differ from default ones in Anjay. This is done to
        # speed up the test execution a bit by limiting the number of retransmissions
        # as well as wait intervals between them.
        MAX_ICMP_FAILURES=7
        ACK_RANDOM_FACTOR=1.0
        ACK_TIMEOUT=2.0
        MAX_RETRANSMIT=2
        CONFIRMABLE_NOTIFICATIONS=False

        def setUp(self, *args, **kwargs):
            extra_cmdline_args=[
                '--max-icmp-failures', str(self.MAX_ICMP_FAILURES),
                '--ack-random-factor', str(self.ACK_RANDOM_FACTOR),
                '--ack-timeout', str(self.ACK_TIMEOUT),
                '--max-retransmit', str(self.MAX_RETRANSMIT),
                '--dtls-hs-retry-wait-min', str(self.ACK_TIMEOUT * self.ACK_RANDOM_FACTOR),
                '--dtls-hs-retry-wait-max', str(self.ACK_TIMEOUT * 2**self.MAX_RETRANSMIT * self.ACK_RANDOM_FACTOR),
            ]
            if self.CONFIRMABLE_NOTIFICATIONS:
                extra_cmdline_args += ['--confirmable-notifications']
            if 'extra_cmdline_args' in kwargs:
                kwargs['extra_cmdline_args'] = extra_cmdline_args + kwargs['extra_cmdline_args']
                super().setUp(*args, **kwargs)
            else:
                super().setUp(*args, **kwargs, extra_cmdline_args=extra_cmdline_args)


class ReconnectRetryTest(test_suite.PcapEnabledTest,
                         RetransmissionTest.TestMixin,
                         test_suite.Lwm2mDtlsSingleServerTest):
    MAX_ICMP_FAILURES=3

    def setup_demo_with_servers(self, **kwargs):
        for server in kwargs['servers']:
            self._server_close_stack.enter_context(server.fake_close())
        super().setup_demo_with_servers(**kwargs)

    def setUp(self):
        self._server_close_stack = contextlib.ExitStack()
        super().setUp(auto_register=False)

    def tearDown(self):
        self._server_close_stack.close()  # in case runTest() failed
        super().tearDown()

    def runTest(self):
        # wait until ultimate failure
        self.wait_until_icmp_unreachable_count(self.MAX_ICMP_FAILURES, timeout_s=16)

        # check that there are no more attempts
        time.sleep(16)
        self.assertEqual(self.MAX_ICMP_FAILURES, self.count_icmp_unreachable_packets())

        # attempt reconnection
        self.communicate('reconnect')
        # let demo make 2 more unsuccessful connections
        self.wait_until_icmp_unreachable_count(self.MAX_ICMP_FAILURES+2, timeout_s=8)
        self._server_close_stack.close()  # unclose the server socket
        self.assertDemoRegisters(self.serv, timeout_s=16)
        self.assertEqual(self.MAX_ICMP_FAILURES+2, self.count_icmp_unreachable_packets())


# Tests below check that Anjay does not go crazy when faced with network connection problems while attempting to send
# Notify messages. Some previous versions could easily get into an infinite loop of repeating the Notify message without
# any backoff, and so on - so we test that the behaviour is sane.


class NotificationTimeoutReconnectTest(RetransmissionTest.TestMixin,
                                       test_suite.Lwm2mDtlsSingleServerTest,
                                       test_suite.Lwm2mDmOperations):
    CONFIRMABLE_NOTIFICATIONS=True

    def runTest(self):
        self.create_instance(self.serv, oid=OID.Test, iid=1)
        self.observe(self.serv, oid=OID.Test, iid=1, rid=RID.Test.Timestamp)

        first_pkt = self.serv.recv(timeout_s=2)
        first_attempt = time.time()
        self.assertIsInstance(first_pkt, Lwm2mNotify)

        for attempt in range(self.MAX_RETRANSMIT):
            self.assertIsInstance(self.serv.recv(timeout_s=30), Lwm2mNotify)
        last_attempt = time.time()

        transmit_span_lower_bound = self.ACK_TIMEOUT * ((2 ** self.MAX_RETRANSMIT) - 1)
        transmit_span_upper_bound = transmit_span_lower_bound * self.ACK_RANDOM_FACTOR

        self.assertGreater(last_attempt - first_attempt, transmit_span_lower_bound - 1)
        self.assertLess(last_attempt - first_attempt, transmit_span_upper_bound + 1)

        self.assertDtlsReconnect(timeout_s=self.ACK_RANDOM_FACTOR * self.ACK_TIMEOUT * (2 ** self.MAX_RETRANSMIT) + 1)

        pkt = self.serv.recv(timeout_s=1)
        self.assertIsInstance(pkt, Lwm2mNotify)
        self.assertEqual(pkt.content, first_pkt.content)
        self.serv.send(Lwm2mReset.matching(pkt)())


class NotificationIcmpReconnectTest(test_suite.PcapEnabledTest,
                                    RetransmissionTest.TestMixin,
                                    test_suite.Lwm2mSingleServerTest,
                                    test_suite.Lwm2mDmOperations):
    CONFIRMABLE_NOTIFICATIONS=True

    def runTest(self):
        self.create_instance(self.serv, oid=OID.Test, iid=1)
        self.observe(self.serv, oid=OID.Test, iid=1, rid=RID.Test.Timestamp)

        with self.serv.fake_close():
            first_attempt = time.time()
            self.wait_until_icmp_unreachable_count(5, timeout_s=15)
            last_attempt = time.time()
            self.assertAlmostEqual(last_attempt - first_attempt, 8, delta=1)

        self.assertDemoRegisters(self.serv, timeout_s=10)

        pkt = self.serv.recv(timeout_s=1)
        self.assertIsInstance(pkt, Lwm2mNotify)
        self.serv.send(Lwm2mReset.matching(pkt)())
        self.assertEqual(5, self.count_icmp_unreachable_packets())


class NotificationDtlsIcmpReconnectTest(test_suite.PcapEnabledTest,
                                        RetransmissionTest.TestMixin,
                                        test_suite.Lwm2mDtlsSingleServerTest,
                                        test_suite.Lwm2mDmOperations):
    CONFIRMABLE_NOTIFICATIONS=True

    def runTest(self):
        self.create_instance(self.serv, oid=OID.Test, iid=1)
        self.observe(self.serv, oid=OID.Test, iid=1, rid=RID.Test.Timestamp)

        with self.serv.fake_close():
            first_attempt = time.time()
            self.wait_until_icmp_unreachable_count(5, timeout_s=10)
            last_attempt = time.time()
            self.assertAlmostEqual(last_attempt - first_attempt, 5, delta=1)

        self.assertDtlsReconnect(timeout_s=10)
        self.assertDemoRegisters(self.serv)

        pkt = self.serv.recv(timeout_s=1)
        self.assertIsInstance(pkt, Lwm2mNotify)
        self.serv.send(Lwm2mReset.matching(pkt)())
        self.assertEqual(5, self.count_icmp_unreachable_packets())
