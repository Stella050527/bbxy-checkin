"""BBXY daily check-in using Python's standard library only."""

import datetime as dt
import html
from html.parser import HTMLParser
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.bbxy01.net"
TIMEOUT = 30


class CheckinError(Exception):
    pass


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_form = False
        self.hidden = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.in_form = attrs.get("id") == "login_form"
        if tag == "input" and self.in_form and attrs.get("type") == "hidden":
            if attrs.get("name"):
                self.hidden[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).netloc != "www.bbxy01.net" or not newurl.startswith("https://"):
            raise CheckinError("网站跳转到其他域名；请检查网站地址。")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(opener, path, data=None):
    headers = {"User-Agent": "Mozilla/5.0 BBXY-Daily-Checkin/1.0", "Referer": BASE_URL + "/user"}
    if data is not None:
        headers.update({"Origin": BASE_URL, "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers)
    # A lost POST response can mean the check-in succeeded. Repeating is safe:
    # the server limits check-in to once per day, and the final page is verified.
    for attempt in range(3):
        try:
            with opener.open(req, timeout=TIMEOUT) as response:
                return response.read().decode("utf-8"), response.geturl()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise CheckinError(f"网站请求失败，HTTP {exc.code}。") from None
            if attempt == 2:
                raise CheckinError(f"网站暂时不可用，HTTP {exc.code}，已重试。") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise CheckinError("网络连接失败或超时，已重试。") from None
        time.sleep(2 ** (attempt + 1))


def json_object(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise CheckinError("网站未返回预期 JSON；可能需要验证或网站接口已变化。") from None
    if not isinstance(value, dict):
        raise CheckinError("网站返回的 JSON 格式不正确。")
    return value


def successful(value):
    return value is True or (isinstance(value, (int, float)) and value > 0) or value == "1"


def button_state(text):
    match = re.search(r'<button\b(?=[^>]*(?:\bid=[\"\']checkin[\"\']|\bclass=[\"\'][^\"\']*\bstudio-checkin\b))[^>]*>(.*?)</button>', text, re.S | re.I)
    if not match:
        return None
    label = html.unescape(re.sub(r"<[^>]*>", "", match.group(1))).strip()
    return "already_checked_in" if "已签到" in label else "ready"


def run(email, password, opener=None):
    if not email or not password:
        raise CheckinError("缺少 BBXY_EMAIL 或 BBXY_PASSWORD，请配置 GitHub Actions Secrets。")
    if opener is None:
        opener = urllib.request.build_opener(
            SameOriginRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    login_page, _ = request(opener, "/v2/login")
    if re.search(r"\bgeetest\s*=\s*1\b", login_page):
        raise CheckinError("网站已开启验证码，需要人工处理。")
    form = LoginForm()
    form.feed(login_page)
    fields = dict(form.hidden)
    fields.update({"email": email, "passwd": password, "code_2fa": "", "2fa-code": "", "remember_me": "1"})
    login_result, _ = request(opener, "/v2/login", urllib.parse.urlencode(fields).encode())
    if not successful(json_object(login_result).get("ret")):
        # Never print server login responses, which may contain credentials.
        raise CheckinError("登录失败，请检查 Secrets、账号状态、二步验证或验证码。")
    page, url = request(opener, "/user")
    if urllib.parse.urlsplit(url).path.rstrip("/") != "/user" or button_state(page) is None:
        raise CheckinError("登录后未找到签到按钮，无法确认登录状态或页面已变化。")
    if button_state(page) == "already_checked_in":
        return {"status": "already_checked_in", "message": "今日已签到", "reward_mb": None}
    body, _ = request(opener, "/user/checkin", b"")
    result = json_object(body)
    verified_page, verified_url = request(opener, "/user")
    if (urllib.parse.urlsplit(verified_url).path.rstrip("/") != "/user"
            or button_state(verified_page) != "already_checked_in"):
        raise CheckinError("签到后页面未显示今日已签到，无法确认成功。")
    if not successful(result.get("ret")):
        # Another execution may have checked in between our GET and POST.
        return {"status": "already_checked_in", "message": "页面已确认今日签到完成", "reward_mb": None}
    reward = re.search(r"获得了?\s*([\d.]+)\s*MB", str(result.get("msg", "")), re.I)
    return {"status": "checked_in", "message": "签到成功", "reward_mb": reward.group(1) if reward else None}


def main():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
    try:
        result = run(os.environ.get("BBXY_EMAIL", ""), os.environ.get("BBXY_PASSWORD", ""))
        exit_code = 0
    except CheckinError as exc:
        result = {"status": "failed", "message": str(exc), "reward_mb": None}
        exit_code = 1
    except Exception:
        result = {"status": "failed", "message": "发生未预期错误，请检查网站接口与运行环境。", "reward_mb": None}
        exit_code = 1
    result["time_beijing"] = now
    Path("result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a", encoding="utf-8") as stream:
            stream.write(f"## 百变小樱每日签到\n\n- 北京时间：{now}\n- 结果：{result['message']}\n")
            if result["reward_mb"]:
                stream.write(f"- 奖励流量：{result['reward_mb']} MB\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
