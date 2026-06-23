import unittest

from app.service_leader_auth import ServiceLeaderAccessManager


class ServiceLeaderAccessManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ServiceLeaderAccessManager(
            pairing_ttl_seconds=30,
            session_max_age_seconds=120,
            session_idle_timeout_seconds=60,
        )

    def test_pairing_token_is_single_use(self):
        token = self.manager.create_pairing(now=100)
        exchanged = self.manager.exchange_pairing(token, now=110)

        self.assertIsNotNone(exchanged)
        self.assertIsNone(self.manager.exchange_pairing(token, now=111))

    def test_pairing_token_expires(self):
        token = self.manager.create_pairing(now=100)

        self.assertIsNone(self.manager.exchange_pairing(token, now=131))

    def test_session_has_separate_csrf_token_and_can_be_revoked(self):
        token = self.manager.create_pairing(now=100)
        session_token, session = self.manager.exchange_pairing(token, now=101)

        self.assertNotEqual(session_token, session.csrf_token)
        self.assertTrue(self.manager.csrf_is_valid(session, session.csrf_token))
        self.assertIsNotNone(self.manager.verify_session(session_token, now=110))
        self.manager.revoke_session(session_token)
        self.assertIsNone(self.manager.verify_session(session_token, now=111))

    def test_session_idle_timeout_is_server_enforced(self):
        token = self.manager.create_pairing(now=100)
        session_token, _session = self.manager.exchange_pairing(token, now=101)

        self.assertIsNone(self.manager.verify_session(session_token, now=162))

    def test_status_checks_can_avoid_extending_idle_timeout(self):
        token = self.manager.create_pairing(now=100)
        session_token, _session = self.manager.exchange_pairing(token, now=101)

        self.assertIsNotNone(self.manager.verify_session(session_token, now=140, touch=False))
        self.assertIsNone(self.manager.verify_session(session_token, now=162, touch=False))

    def test_new_pairing_replaces_an_unused_pairing(self):
        first = self.manager.create_pairing(now=100)
        second = self.manager.create_pairing(now=101)

        self.assertIsNone(self.manager.exchange_pairing(first, now=102))
        self.assertIsNotNone(self.manager.exchange_pairing(second, now=102))

    def test_default_idle_timeout_is_two_hours(self):
        manager = ServiceLeaderAccessManager()
        self.assertEqual(manager.session_idle_timeout_seconds, 2 * 60 * 60)

    def test_session_can_be_explicitly_extended(self):
        token = self.manager.create_pairing(now=100)
        session_token, session = self.manager.exchange_pairing(token, now=101)
        original = session.last_seen_at

        extended = self.manager.extend_session(session_token, now=150)

        self.assertIsNotNone(extended)
        self.assertGreater(extended.last_seen_at, original)

    def test_access_state_reports_and_cancels_pending_pairing(self):
        self.manager.create_pairing(now=100)

        state = self.manager.access_state(now=110)

        self.assertTrue(state["pairing_active"])
        self.assertEqual(state["pairing_remaining_seconds"], 20)
        self.manager.cancel_pairings()
        self.assertFalse(self.manager.access_state(now=111)["pairing_active"])

    def test_access_state_counts_active_sessions(self):
        token = self.manager.create_pairing(now=100)
        self.manager.exchange_pairing(token, now=101)

        self.assertEqual(self.manager.access_state(now=102)["active_sessions"], 1)


if __name__ == "__main__":
    unittest.main()
