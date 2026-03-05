#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import time
import random
import json
import urllib3
import http.cookies
import pwinput
from Crypto.Util.number import bytes_to_long
import authentication_pb2 as pb2
import familygroups_pb2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

# 使用 curl_cffi 替代 requests
from curl_cffi import requests, CurlMime

from bs4 import BeautifulSoup
import matplotlib.pyplot as plt

# 禁用不安全请求的警告（与 verify=False 配合使用）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------- 常量 ----------
STORE_COOKIE_FILE = "store_cookie.txt"

# ---------- 自定义异常 ----------
class SteamGuardError(Exception):
    def __init__(self, eresult, message=""):
        self.eresult = eresult
        self.message = message
        super().__init__(f"SteamGuard error {eresult}: {message}")

class AuthFailedError(Exception):
    """认证失败（如密码错误）"""
    def __init__(self, eresult, message=""):
        self.eresult = eresult
        super().__init__(message)

# ---------- 加载保存的 store cookie ----------
def load_store_cookie():
    """从文件加载 store.steampowered.com 的原始 Set-Cookie 字符串，并解析出 steamLoginSecure 的值"""
    try:
        with open(STORE_COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookie_str = f.read().strip()
    except FileNotFoundError:
        return None
    except Exception:
        return None

    # 解析 cookie 字符串
    simple_cookie = http.cookies.SimpleCookie()
    simple_cookie.load(cookie_str)
    if 'steamLoginSecure' in simple_cookie:
        return simple_cookie['steamLoginSecure'].value
    return None

def extract_token_and_steamid_from_value(cookie_value):
    """从 steamLoginSecure 的值中解析出 steamid 和 token"""
    if cookie_value and '%7C%7C' in cookie_value:
        parts = cookie_value.split('%7C%7C')
        return parts[0], parts[1]
    return None, None

# ---------- 家庭库相关函数 ----------
def get_family_groupid(session, access_token, steamid):
    url = "https://api.steampowered.com/IFamilyGroupsService/GetFamilyGroupForUser/v1"
    req = familygroups_pb2.CFamilyGroups_GetFamilyGroupForUser_Request()
    req.steamid = int(steamid)
    req.include_family_group_response = False
    proto_bytes = req.SerializeToString()
    input_b64 = base64.b64encode(proto_bytes).decode('ascii')
    params = {
        "access_token": access_token,
        "origin": "https://store.steampowered.com",
        "input_protobuf_encoded": input_b64,
    }
    try:
        resp = session.get(url, params=params, timeout=15, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"获取家庭组 ID 失败: {e}")
        return None
    response = familygroups_pb2.CFamilyGroups_GetFamilyGroupForUser_Response()
    response.ParseFromString(resp.content)
    return str(response.family_groupid)

def get_family_members(session, access_token, family_groupid):
    url = "https://api.steampowered.com/IFamilyGroupsService/GetFamilyGroup/v1"
    req = familygroups_pb2.CFamilyGroups_GetFamilyGroup_Request()
    req.family_groupid = int(family_groupid)
    proto_bytes = req.SerializeToString()
    input_b64 = base64.b64encode(proto_bytes).decode('ascii')
    params = {
        "access_token": access_token,
        "origin": "https://store.steampowered.com",
        "input_protobuf_encoded": input_b64,
    }
    try:
        resp = session.get(url, params=params, timeout=15, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"获取家庭成员失败: {e}")
        return []
    response = familygroups_pb2.CFamilyGroups_GetFamilyGroup_Response()
    response.ParseFromString(resp.content)
    members = [str(member.steamid) for member in response.members]
    print(f"找到 {len(members)} 位家庭成员")
    return members

def get_user_nickname(session, steamid):
    url = f'https://steamcommunity.com/profiles/{steamid}'
    try:
        resp = session.get(url, timeout=15, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"请求用户 {steamid} 的个人资料失败: {e}")
        return str(steamid)
    soup = BeautifulSoup(resp.text, 'html.parser')
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        title = title_tag.string
        if ' :: ' in title:
            return title.split(' :: ')[-1].strip()
    return str(steamid)

def get_family_library(session, access_token, family_groupid):
    url = "https://api.steampowered.com/IFamilyGroupsService/GetSharedLibraryApps/v1"
    req = familygroups_pb2.CFamilyGroups_GetSharedLibraryApps_Request()
    req.family_groupid = int(family_groupid)
    req.include_own = True
    req.include_excluded = True
    req.language = "schinese"
    proto_bytes = req.SerializeToString()
    input_b64 = base64.b64encode(proto_bytes).decode('ascii')
    params = {
        "access_token": access_token,
        "origin": "https://store.steampowered.com",
        "input_protobuf_encoded": input_b64,
    }
    try:
        resp = session.get(url, params=params, timeout=15, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"获取家庭库失败: {e}")
        return None
    response = familygroups_pb2.CFamilyGroups_GetSharedLibraryApps_Response()
    response.ParseFromString(resp.content)
    print(f"家庭共享库共有 {len(response.apps)} 个游戏")
    return response

def process_family_library(session, access_token, steamid):
    """主家庭库处理流程，使用传入的 access_token 和 steamid"""
    print(f"当前用户 SteamID: {steamid}")
    print("获取家庭组 ID...")
    family_groupid_str = get_family_groupid(session, access_token, steamid)
    if not family_groupid_str:
        print("无法获取家庭组 ID，程序终止")
        return
    family_groupid = int(family_groupid_str)
    print(f"家庭组 ID: {family_groupid}")

    print("获取家庭成员列表...")
    members = get_family_members(session, access_token, family_groupid)
    if not members:
        print("无法获取家庭成员，程序终止")
        return

    print("获取每个家庭成员的昵称...")
    steamid_to_name = {}
    for mid in members:
        print(f"  正在获取 {mid} 的昵称...")
        nickname = get_user_nickname(session, mid)
        steamid_to_name[mid] = nickname
        print(f"    昵称: {nickname}")

    print("获取家庭共享库游戏列表...")
    family_response = get_family_library(session, access_token, family_groupid)
    if not family_response:
        print("家庭共享库为空或获取失败")
        return

    # 统计贡献
    contribution = {mid: 0 for mid in members}
    game_owners = {}
    for app in family_response.apps:
        if app.HasField('exclude_reason'):
            continue
        owners = []
        for owner in app.owner_steamids:
            owner_str = str(owner)
            if owner_str in contribution:
                contribution[owner_str] += 1
            owners.append(steamid_to_name.get(owner_str, owner_str))
        if owners:
            game_owners[app.appid] = owners

    sorted_contrib = sorted(contribution.items(), key=lambda x: x[1], reverse=True)

    print("\n========== 家庭库贡献值排名 ==========")
    rank = 1
    for sid, count in sorted_contrib:
        nickname = steamid_to_name.get(sid, sid)
        print(f"{rank}. {nickname} 贡献游戏数: {count}")
        rank += 1

    with open('contribution_rank.json', 'w', encoding='utf-8') as f:
        json.dump(sorted_contrib, f, ensure_ascii=False, indent=2)
    print("\n排名已保存到 contribution_rank.json")

    # 绘图
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False

    nicknames = [steamid_to_name.get(sid, sid) for sid, _ in sorted_contrib]
    counts = [c for _, c in sorted_contrib]
    total_family = len([app for app in family_response.apps if not app.HasField('exclude_reason')])
    percentages = [c / total_family * 100 if total_family > 0 else 0 for c in counts]

    plt.figure(figsize=(10, 6))
    bars = plt.bar(nicknames, counts, color='skyblue')
    plt.ylabel('贡献游戏数')
    plt.title('家庭库成员贡献值')
    for bar, count, pct in zip(bars, counts, percentages):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 f'{count} ({pct:.1f}%)', ha='center', va='bottom')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig('contribution_bar.png')
    plt.show()

    nonzero = [(n, c) for n, c in zip(nicknames, counts) if c > 0]
    if nonzero:
        labels_nz, sizes_nz = zip(*nonzero)
        plt.figure(figsize=(8, 8))
        plt.pie(sizes_nz, labels=labels_nz, autopct='%1.1f%%', startangle=90)
        plt.title('家庭库贡献占比（仅显示有贡献成员）')
        plt.axis('equal')
        plt.savefig('contribution_pie.png')
        plt.show()
    else:
        print("没有成员有贡献，无法绘制饼图。")

# ---------- 登录类 ----------
class SteamLogin:
    def __init__(self, session=None):
        self.session = session or requests.Session(impersonate="chrome")
        self.headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'origin': 'https://store.steampowered.com',
            'referer': 'https://store.steampowered.com/',
            'sec-ch-ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0'
        }
        self.session.headers.update(self.headers)
        self.store_cookie_str = None  # 用于保存从 store 域返回的原始 Set-Cookie

    def _request_with_retry(self, method, url, **kwargs):
        """发送请求，遇到限流时自动等待并重试"""
        max_retries = 3
        for attempt in range(max_retries):
            resp = method(url, **kwargs)
            if resp.status_code == 429 or resp.headers.get('X-eresult') == '84':
                wait_time = 60 * (attempt + 1)
                print(f"[-] 触发限流，等待 {wait_time} 秒后重试 ({attempt+1}/{max_retries})...")
                time.sleep(wait_time)
                continue
            return resp
        raise Exception(f"请求失败，达到最大重试次数，最后状态码: {resp.status_code}")

    def get_rsa_key(self, account_name):
        req = pb2.CAuthentication_GetPasswordRSAPublicKey_Request()
        req.account_name = account_name
        data_b64 = base64.b64encode(req.SerializeToString()).decode('ascii')
        params = {
            'origin': 'https://store.steampowered.com',
            'input_protobuf_encoded': data_b64
        }
        url = 'https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1'
        resp = self._request_with_retry(self.session.get, url, params=params, verify=False)
        resp.raise_for_status()
        rsa_resp = pb2.CAuthentication_GetPasswordRSAPublicKey_Response()
        rsa_resp.ParseFromString(resp.content)
        return rsa_resp

    def _decode_base64_flexible(self, s):
        s = s.strip()
        missing_padding = len(s) % 4
        if missing_padding:
            s += '=' * (4 - missing_padding)
        return base64.b64decode(s)

    def encrypt_password(self, password, modulus_str, exponent_str):
        """本地 RSA 加密，使用 PKCS1v15 填充"""
        modulus_str = modulus_str.strip()
        exponent_str = exponent_str.strip()
        try:
            modulus_bytes = bytes.fromhex(modulus_str)
        except ValueError:
            modulus_bytes = self._decode_base64_flexible(modulus_str)
        try:
            exponent_bytes = bytes.fromhex(exponent_str)
        except ValueError:
            exponent_bytes = self._decode_base64_flexible(exponent_str)

        n = int.from_bytes(modulus_bytes, 'big')
        e = int.from_bytes(exponent_bytes, 'big')
        public_key = rsa.RSAPublicNumbers(e, n).public_key(backend=default_backend())

        ciphertext = public_key.encrypt(
            password.encode('utf-8'),
            padding.PKCS1v15()
        )
        return base64.b64encode(ciphertext).decode('ascii')

    def check_device(self, client_id, steamid):
        url = f"https://login.steampowered.com/jwt/checkdevice/{steamid}"
        mime = CurlMime()
        mime.addpart(name="clientid", data=str(client_id).encode('utf-8'))
        mime.addpart(name="steamid", data=str(steamid).encode('utf-8'))
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Origin": "https://store.steampowered.com",
            "Pragma": "no-cache",
            "Referer": "https://store.steampowered.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": self.headers['user-agent'],
            "sec-ch-ua": self.headers['sec-ch-ua'],
            "sec-ch-ua-mobile": self.headers['sec-ch-ua-mobile'],
            "sec-ch-ua-platform": self.headers['sec-ch-ua-platform'],
        }
        resp = self._request_with_retry(self.session.post, url, multipart=mime, headers=headers, verify=False)
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("result") == 1:
                    print("[+] 设备确认成功")
                    return True
                else:
                    print("[-] 设备未记录，需要进行验证")
                    return False
            except Exception as e:
                print(f"[-] 解析设备确认响应失败: {e}")
                return False
        else:
            print(f"[-] 设备确认 HTTP 错误: {resp.status_code}")
            return False

    def begin_auth_session(self, account_name, encrypted_password, timestamp,
                           remember_login=True, platform_type=0, persistence=1,
                           website_id='Store', language=6, qos_level=2):
        req = pb2.CAuthentication_BeginAuthSessionViaCredentials_Request()
        req.account_name = account_name
        req.encrypted_password = encrypted_password
        req.encryption_timestamp = timestamp
        req.remember_login = remember_login
        req.platform_type = platform_type
        req.persistence = persistence
        req.website_id = website_id
        req.language = language
        req.qos_level = qos_level
        details = pb2.CAuthentication_DeviceDetails()
        details.device_friendly_name = self.headers['user-agent']
        details.platform_type = 2
        details.os_type = 0
        details.gaming_device_type = 0
        details.client_count = 0
        details.machine_id = b''
        details.app_type = 0
        req.device_details.CopyFrom(details)
        data_b64 = base64.b64encode(req.SerializeToString()).decode('ascii')
        url = 'https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1'
        mime = CurlMime()
        mime.addpart(name="input_protobuf_encoded", data=data_b64.encode('utf-8'), content_type="application/octet-stream")
        resp = self._request_with_retry(self.session.post, url, multipart=mime, verify=False)
        eresult_header = resp.headers.get('X-eresult')
        if eresult_header and eresult_header != '1':
            eresult = int(eresult_header)
            if eresult == 5:
                raise AuthFailedError(eresult, "用户名或密码错误")
            else:
                error_msg = f"认证失败，EResult: {eresult_header}"
                if 'X-error_message' in resp.headers:
                    error_msg += f", 信息: {resp.headers['X-error_message']}"
                raise Exception(error_msg)
        resp.raise_for_status()
        auth_resp = pb2.CAuthentication_BeginAuthSessionViaCredentials_Response()
        auth_resp.ParseFromString(resp.content)
        return auth_resp

    def update_auth_session_with_guard(self, client_id, steamid, code, code_type):
        req = pb2.CAuthentication_UpdateAuthSessionWithSteamGuardCode_Request()
        req.client_id = client_id
        req.steamid = steamid
        req.code = code
        req.code_type = code_type
        data_b64 = base64.b64encode(req.SerializeToString()).decode('ascii')
        url = 'https://api.steampowered.com/IAuthenticationService/UpdateAuthSessionWithSteamGuardCode/v1'
        mime = CurlMime()
        mime.addpart(name="input_protobuf_encoded", data=data_b64.encode('utf-8'), content_type="application/octet-stream")
        resp = self._request_with_retry(self.session.post, url, multipart=mime, verify=False)

        if resp.status_code != 200:
            raise Exception(f"HTTP error {resp.status_code}: {resp.text}")

        eresult_str = resp.headers.get('X-eresult')
        if not eresult_str:
            eresult = 1
        else:
            eresult = int(eresult_str)

        if eresult != 1:
            raise SteamGuardError(eresult)

        update_resp = pb2.CAuthentication_UpdateAuthSessionWithSteamGuardCode_Response()
        update_resp.ParseFromString(resp.content)
        return update_resp

    def poll_auth_session(self, client_id, request_id, token_to_revoke=None, max_attempts=60, interval=5):
        for attempt in range(max_attempts):
            req = pb2.CAuthentication_PollAuthSessionStatus_Request()
            req.client_id = client_id
            req.request_id = request_id
            if token_to_revoke:
                req.token_to_revoke = token_to_revoke
            data_b64 = base64.b64encode(req.SerializeToString()).decode('ascii')
            url = 'https://api.steampowered.com/IAuthenticationService/PollAuthSessionStatus/v1'
            mime = CurlMime()
            mime.addpart(name="input_protobuf_encoded", data=data_b64.encode('utf-8'), content_type="application/octet-stream")
            resp = self._request_with_retry(self.session.post, url, multipart=mime, verify=False)

            eresult_str = resp.headers.get('X-eresult')
            if not eresult_str:
                if resp.status_code != 200:
                    print(f"轮询 HTTP 错误: {resp.status_code}，重试...")
                    time.sleep(interval)
                    continue
                else:
                    eresult = 1
            else:
                eresult = int(eresult_str)

            if eresult != 1:
                print(f"[-] 轮询返回 EResult: {eresult}")
                if eresult == 2:
                    print("   暂时性错误，继续轮询...")
                    time.sleep(interval)
                    continue
                elif eresult in (9, 27):
                    print("   会话已过期，需要重新开始登录")
                    return False, None
                elif eresult == 84:
                    print("   请求过于频繁，请稍后再试")
                    return False, None
                elif eresult == 118:
                    try:
                        poll_resp = pb2.CAuthentication_PollAuthSessionStatus_Response()
                        poll_resp.ParseFromString(resp.content)
                        if poll_resp.HasField('agreement_session_url') and poll_resp.agreement_session_url:
                            url = poll_resp.agreement_session_url
                            print(f"[!] 需要同意 Steam 协议，请访问以下链接并完成操作：")
                            print(f"    {url}")
                            input("完成后请按回车键继续...")
                            continue
                        else:
                            print("   需要同意协议，但响应中无 URL")
                            return False, None
                    except Exception as e:
                        print(f"   解析协议 URL 失败: {e}")
                        return False, None
                else:
                    print("   未知错误，停止轮询")
                    return False, None

            poll_resp = pb2.CAuthentication_PollAuthSessionStatus_Response()
            poll_resp.ParseFromString(resp.content)

            if poll_resp.HasField('agreement_session_url') and poll_resp.agreement_session_url:
                url = poll_resp.agreement_session_url
                print(f"[!] 需要同意 Steam 协议，请访问以下链接并完成操作：")
                print(f"    {url}")
                input("完成后请按回车键继续...")
                continue

            if poll_resp.HasField('refresh_token') and poll_resp.refresh_token:
                return True, {
                    'refresh_token': poll_resp.refresh_token,
                    'access_token': poll_resp.access_token,
                    'account_name': poll_resp.account_name,
                    'new_guard_data': poll_resp.new_guard_data if poll_resp.HasField('new_guard_data') else None
                }

            # 不打印内部更新信息
            if poll_resp.HasField('new_client_id'):
                client_id = poll_resp.new_client_id
            # 忽略 new_challenge_url
            time.sleep(interval)
        return False, None

    def finalize_login(self, nonce, redir='https://store.steampowered.com/'):
        if 'sessionid' not in self.session.cookies:
            self.session.get('https://store.steampowered.com', timeout=5, verify=False)
        sessionid = self.session.cookies.get('sessionid', '')
        if not sessionid:
            print("[-] 无法获取 sessionid，将使用空字符串，可能失败")
        url = 'https://login.steampowered.com/jwt/finalizelogin'
        data = {
            'nonce': nonce,
            'sessionid': sessionid,
            'redir': redir
        }
        resp = self._request_with_retry(self.session.post, url, data=data, verify=False)
        if resp.status_code != 200:
            print(f"finalizelogin HTTP 错误: {resp.status_code}")
            return False, None
        json_data = resp.json()
        if not (json_data.get('transfer_info') and json_data.get('steamID')):
            print("finalizelogin 返回数据缺少必要字段")
            return False, None
        transfer_info = json_data['transfer_info']
        steam_id = json_data['steamID']
        success_count = 0
        for item in transfer_info:
            url = item['url']
            params = item['params'].copy()
            params['steamID'] = steam_id
            try:
                r = self._request_with_retry(self.session.post, url, data=params, timeout=10, verify=False)
                if r.status_code == 200 and r.json().get('result') == 1:
                    success_count += 1
                else:
                    print(f"分发到 {url} 失败: {r.status_code} - {r.text}")
                
                # 只保存 store.steampowered.com 的 Set-Cookie
                if "store.steampowered.com/login/settoken" in url:
                    for key, value in r.headers.items():
                        if key.lower() == 'set-cookie':
                            self.store_cookie_str = value
                            break
            except Exception as e:
                print(f"分发到 {url} 异常: {e}")
        return success_count > 0, json_data

    def login(self, account_name, password):
        self.session.get('https://store.steampowered.com', timeout=5, verify=False)

        rsa_key = self.get_rsa_key(account_name)
        encrypted_pw = self.encrypt_password(password, rsa_key.publickey_mod, rsa_key.publickey_exp)

        print("[*] 发起认证会话...")
        auth_resp = self.begin_auth_session(
            account_name=account_name,
            encrypted_password=encrypted_pw,
            timestamp=rsa_key.timestamp,
            remember_login=True,
            website_id='Store',
            language=6
        )

        if auth_resp.allowed_confirmations:
            need_code = True
            for conf in auth_resp.allowed_confirmations:
                if conf.confirmation_type == 6:
                    print("[!] 需要进行设备确认，自动发送请求...")
                    if self.check_device(auth_resp.client_id, auth_resp.steamid):
                        print("[*] 设备确认完成，将进入轮询...")
                        need_code = False
                    else:
                        pass
                else:
                    print(f"    - 类型 {conf.confirmation_type}: {conf.associated_message}")

            if need_code:
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        code_type = int(input("请输入验证码类型 (2=邮件, 3=验证器): ").strip())
                        code = input("请输入验证码: ").strip()
                    except ValueError:
                        print("[-] 输入无效，请重新输入")
                        continue
                    print("[*] 提交验证码...")
                    try:
                        self.update_auth_session_with_guard(
                            client_id=auth_resp.client_id,
                            steamid=auth_resp.steamid,
                            code=code,
                            code_type=code_type
                        )
                        print("[+] 验证码提交成功，登录中...")
                        break
                    except SteamGuardError as e:
                        if e.eresult in (65, 88):
                            print("[-] 验证码错误，请重新输入")
                            if attempt == max_attempts - 1:
                                print("[-] 多次尝试失败，登录终止")
                                return
                            # 继续下一次循环
                        else:
                            print(f"[-] 验证码提交失败 (错误码 {e.eresult})，登录终止")
                            return
                    except Exception as e:
                        print(f"[-] 提交验证码失败: {e}")
                        return

        interval = auth_resp.interval if auth_resp.interval > 0 else 5
        success, poll_result = self.poll_auth_session(
            client_id=auth_resp.client_id,
            request_id=auth_resp.request_id,
            max_attempts=60,
            interval=interval
        )
        if not success:
            print("[-] 轮询失败，登录未完成")
            return

        refresh_token = poll_result['refresh_token']
        access_token = poll_result['access_token']

        finalize_ok, _ = self.finalize_login(nonce=refresh_token)
        if finalize_ok:
            print("[+] 登录成功！")
            if self.store_cookie_str:
                with open(STORE_COOKIE_FILE, 'w', encoding='utf-8') as f:
                    f.write(self.store_cookie_str)
                print("[+] cookie 已保存")
            else:
                print("[-] 未捕获到 cookie，无法保存")
            process_family_library(self.session, access_token, str(auth_resp.steamid))
        else:
            print("[-] 最终分发失败，但可能已有部分域成功。")

# ---------- 主程序 ----------
def main():
    print("╔════════════════════════════════════════════╗")
    print("║                                            ║")
    print("║        Steam Family Analyzer v1.0          ║")
    print("║                                            ║")
    print("║            家庭库贡献统计工具              ║")
    print("║                                            ║")
    print("╚════════════════════════════════════════════╝")
    print()
    
    while True:
        # 尝试从文件加载保存的 store cookie
        cookie_value = load_store_cookie()
        if cookie_value:
            steamid, token = extract_token_and_steamid_from_value(cookie_value)
            if steamid and token:
                print("[+] 使用保存的 store cookie")
                session = requests.Session(impersonate="chrome")
                session.cookies.set(
                    name='steamLoginSecure',
                    value=cookie_value,
                    domain='store.steampowered.com',
                    path='/',
                    secure=True
                )
                process_family_library(session, token, steamid)
                return
            else:
                print("[-] 保存的 cookie 无效，需要重新登录")
        else:
            print("[*] 未找到保存的 cookie，需要登录")

        account = input("请输入账号: ").strip()
        password = pwinput.pwinput("请输入密码: ", mask='*').strip()
        steamer = SteamLogin()
        try:
            steamer.login(account, password)
            break  # 登录成功，退出循环
        except AuthFailedError as e:
            print("[-] 用户名或密码错误，请重试")
            continue
        except Exception as e:
            print(f"[-] 出错: {e}")
            import traceback
            traceback.print_exc()
            break

if __name__ == '__main__':
    main()
    input("\n按 Enter 键退出...")

