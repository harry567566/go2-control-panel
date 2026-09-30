"""Shared parts of the Wi-Fi scripts (wifi_state.py, wifi_photo.py, wifi_record.py, wifi_sport.py).

Over Wi-Fi the Go2 is reached the way the phone app reaches it: WebRTC, through the library
unitree_webrtc_connect (legion1581). It works on Go2 AIR, PRO and EDU. Environment: .venv (made by setup.sh).

The first argument of every Wi-Fi script says where the dog is:
    ap              the Mac is on the dog's own Wi-Fi hotspot (the dog is always 192.168.12.1 there)
    192.168.x.y     the dog and the Mac are on the same router; the dog's address on that router

Firmware 1.1.15 and newer also needs the dog's own AES key (32 hex characters). Put it in
robot/.go2_aes_key or in the environment variable GO2_AES_KEY. Fetch it once, with internet, using the
Unitree account the dog is bound to:  .venv/bin/unitree-fetch-aes-key --email ... --device-type Go2

Only ONE Wi-Fi client can be connected at a time: close the Unitree phone app first, and run one script
at a time.

Messages come in English; with GO2_LANG=zh (the panel sets it in 中文 mode) they come in Chinese.
"""
import asyncio
import os
import re
import signal
import sys

DOG_AP_IP = "192.168.12.1"  # the dog's address on its own hotspot
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".go2_aes_key")

STOP = {"requested": False}  # set by SIGTERM (panel STOP / time limit) or Ctrl+C


def aes_key():
    """The dog's AES key (32 hex characters) from GO2_AES_KEY or robot/.go2_aes_key, or None."""
    key = os.environ.get("GO2_AES_KEY", "").strip()
    if not key and os.path.exists(KEY_FILE):
        key = open(KEY_FILE).read().strip()
    if key and not re.fullmatch(r"[0-9a-fA-F]{32}", key):
        say("robot/.go2_aes_key does not look like a key (it should be 32 letters and digits), so it is ignored. "
            "Delete it with  rm robot/.go2_aes_key  and fetch the key again.",
            "robot/.go2_aes_key 看起来不是密钥(应该是 32 个字母和数字),先不用它。用 rm robot/.go2_aes_key 删掉,重新获取。")
        return None
    return key or None


def watch_for_stop(event):
    """SIGTERM or Ctrl+C: remember it and wake anything waiting on `event` (inside the running loop)."""
    loop = asyncio.get_running_loop()

    def stop():
        STOP["requested"] = True
        event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop)


async def connect(target, timeout=25.0):
    """Open the WebRTC connection to the dog. Exits with a clear message if that fails."""
    from unitree_webrtc_connect import unitree_auth as auth
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod

    key = aes_key()
    if target == "ap":
        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP, aes_128_key=key)
        where = f"{DOG_AP_IP} (the dog's own Wi-Fi)"
    else:
        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=target, aes_128_key=key)
        where = f"{target} on the shared router"
    print(f"connecting over Wi-Fi to {where}" + (" with the AES key" if key else "") + " ...", flush=True)
    try:
        await asyncio.wait_for(conn.connect(), timeout)
    except auth.RobotBusyError:
        fail(4, "The dog already has a Wi-Fi client: close the Unitree phone app (or any other program) and try again.",
             "狗已经被别的程序连着:先关掉手机上的 Unitree App,再试。")
    except auth.AesKeyRequiredError:
        fail(5, "This firmware (1.1.15 or newer) needs the dog's AES key in robot/.go2_aes_key. See the README.",
             "这个固件需要狗的 AES 密钥(放在 robot/.go2_aes_key),见 README。")
    except auth.AesKeyRejectedError:
        fail(5, "The dog rejected the AES key in robot/.go2_aes_key: it belongs to another dog, or it is mistyped.",
             "狗不认这个 AES 密钥:可能是别的狗的,或者抄错了。")
    except (auth.LocalSignalingPortError, OSError, ValueError):
        fail(2, f"Cannot reach the dog at {where}. Is the Mac's Wi-Fi on the dog's network, and is the dog on?",
             "连不上狗:Mac 的 Wi-Fi 连的是狗的网络吗?狗开机了吗?")
    except (asyncio.TimeoutError, auth.NoSdpAnswerError, auth.DataChannelTimeoutError):
        fail(2, f"The dog did not finish the Wi-Fi handshake within {timeout:.0f} s. Move closer, check that the phone "
                "app is closed, then try again.", "Wi-Fi 握手没完成:靠近一点,确认手机 App 已关,再试一次。")
    except Exception as err:  # anything else the library raises
        fail(2, f"Wi-Fi connection failed: {err}", f"Wi-Fi 连接失败:{err}")
    print("connected", flush=True)
    return conn


async def disconnect(conn):
    """Always hang up: the dog accepts only one Wi-Fi client, so a dangling connection blocks the next one."""
    try:
        await asyncio.wait_for(conn.disconnect(), 5)
    except Exception:
        pass


def say(en, zh):
    print(zh if os.environ.get("GO2_LANG") == "zh" else en, flush=True)


def fail(code, en, zh):
    say(en, zh)
    sys.exit(code)
