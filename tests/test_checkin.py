import json
import unittest
from unittest.mock import patch

import checkin


READY = '<button id="checkin"><span>每日签到</span></button>'
DONE = '<button class="btn studio-btn studio-checkin" disabled><svg></svg>今日已签到</button>'
USER = checkin.BASE_URL + "/user"


class CheckinTests(unittest.TestCase):
    def test_success_requires_confirmed_page_and_extracts_reward(self):
        responses = [("", ""), ('{"ret":1}', ""), (READY, USER),
                     (json.dumps({"ret": 1, "msg": "您获得了 6991MB 流量."}), ""), (DONE, USER)]
        with patch("checkin.request", side_effect=responses) as request:
            result = checkin.run("fake@example.com", "test-only", object())
        self.assertEqual(result["status"], "checked_in")
        self.assertEqual(result["reward_mb"], "6991")
        self.assertEqual(request.call_args_list[3].args[1:], ("/user/checkin", b""))

    def test_already_done_does_not_post(self):
        with patch("checkin.request", side_effect=[("", ""), ('{"ret":1}', ""), (DONE, USER)]) as request:
            result = checkin.run("fake@example.com", "test-only", object())
        self.assertEqual(result["status"], "already_checked_in")
        self.assertEqual(request.call_count, 3)

    def test_zero_string_does_not_count_as_login_success(self):
        with patch("checkin.request", side_effect=[("", ""), ('{"ret":"0"}', "")]):
            with self.assertRaisesRegex(checkin.CheckinError, "登录失败"):
                checkin.run("fake@example.com", "test-only", object())

    def test_success_json_without_changed_page_is_failure(self):
        with patch("checkin.request", side_effect=[("", ""), ('{"ret":1}', ""), (READY, USER),
                                                  ('{"ret":1}', ""), (READY, USER)]):
            with self.assertRaisesRegex(checkin.CheckinError, "无法确认成功"):
                checkin.run("fake@example.com", "test-only", object())

    def test_non_json_response_is_failure(self):
        with self.assertRaises(checkin.CheckinError):
            checkin.json_object("<html>challenge</html>")

    def test_missing_secrets_fails_before_network(self):
        with patch("checkin.request") as request:
            with self.assertRaises(checkin.CheckinError):
                checkin.run("", "")
        request.assert_not_called()

    def test_captcha_stops_before_submitting_password(self):
        with patch("checkin.request", return_value=("var geetest = 1;", "")) as request:
            with self.assertRaisesRegex(checkin.CheckinError, "验证码"):
                checkin.run("fake@example.com", "test-only", object())
        self.assertEqual(request.call_count, 1)

    def test_concurrent_checkin_is_recognized_by_page(self):
        with patch("checkin.request", side_effect=[("", ""), ('{"ret":1}', ""), (READY, USER),
                                                  ('{"ret":0}', ""), (DONE, USER)]):
            result = checkin.run("fake@example.com", "test-only", object())
        self.assertEqual(result["status"], "already_checked_in")


if __name__ == "__main__":
    unittest.main()
