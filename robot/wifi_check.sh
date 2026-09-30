#!/usr/bin/env bash
# Wi-Fi, step 1-1: is the Mac on the dog's network, and does the dog answer?
#   bash robot/wifi_check.sh                 the dog's own hotspot (the dog is 192.168.12.1)
#   bash robot/wifi_check.sh 192.168.1.23    the dog and the Mac on the same router
# Nothing is changed on the Mac: joining the dog's Wi-Fi is done in the Wi-Fi menu (top right of the screen).
# Messages are in English, or in Chinese with GO2_LANG=zh (the panel sets it in 中文 mode).
set -u
cd "$(dirname "$0")/.."
TARGET="${1:-ap}"
say() { if [ "${GO2_LANG:-en}" = zh ]; then echo "$2"; else echo "$1"; fi; }
WIFI=$(networksetup -listallhardwareports | awk '/Hardware Port: Wi-Fi/{getline; print $2}')
IP=$(ipconfig getifaddr "$WIFI" 2>/dev/null)
echo "Mac Wi-Fi ($WIFI) address: ${IP:-none}"

if [ "$TARGET" = ap ]; then
  DOG=192.168.12.1
  case "$IP" in
    192.168.12.*) say "The Mac is on the dog's own Wi-Fi." "Mac 已经连在狗自己的 Wi-Fi 上。" ;;
    *) say "The Mac is NOT on the dog's Wi-Fi yet. Click the Wi-Fi icon at the top right of the screen and join the dog's network (its name usually starts with Go2; ask the instructor for the password), then click 1-1 again." \
           "Mac 还没连上狗的 Wi-Fi:点屏幕右上角的 Wi-Fi 图标,选狗的网络(名字一般以 Go2 开头,密码问老师),再点一次 1-1。"
       exit 1 ;;
  esac
else
  DOG="$TARGET"
fi

echo "checking the dog at $DOG ..."
ping -c 2 -W 1000 "$DOG" >/dev/null 2>&1 && echo "  ping: answers" || echo "  ping: no answer (some dogs do not answer ping)"
if nc -z -G 2 "$DOG" 9991 2>/dev/null || nc -z -G 2 "$DOG" 8081 2>/dev/null; then
  echo "DOG REACHABLE over Wi-Fi at $DOG"
else
  say "The dog's Wi-Fi control port does not answer at $DOG: is the dog on (wait 1 minute after power on)?" \
      "狗的 Wi-Fi 控制端口没有回应($DOG):狗开机了吗?开机后要等 1 分钟。"
  exit 3
fi
say "Close the Unitree phone app: the dog accepts only one Wi-Fi client at a time." \
    "先关掉手机上的 Unitree App:狗一次只接受一个 Wi-Fi 连接。"

if [ -n "${GO2_AES_KEY:-}" ] || grep -qE '^[0-9a-fA-F]{32}$' robot/.go2_aes_key 2>/dev/null; then
  say "AES key: found (needed only on firmware 1.1.15 or newer)" "AES 密钥:有(只有固件 1.1.15 或更新才需要)"
elif [ -e robot/.go2_aes_key ]; then
  say "AES key: robot/.go2_aes_key does not look like a key (32 letters and digits). Delete it with  rm robot/.go2_aes_key  and fetch it again (see the README)." \
      "AES 密钥:robot/.go2_aes_key 看起来不是密钥(应该是 32 个字母和数字)。用 rm robot/.go2_aes_key 删掉,再重新获取(见 README)。"
else
  say "AES key: none (fine on firmware 1.1.14 or older; newer firmware needs it, see the README)" \
      "AES 密钥:没有(固件 1.1.14 或更老不需要;更新的固件需要,见 README)"
fi

if curl -s -m 3 -o /dev/null https://www.apple.com; then
  say "Internet: yes, through $(route -n get default 2>/dev/null | awk '/interface:/{print $2}')" \
      "外网:有,走 $(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
else
  say "Internet: no. The dog does not need it. To keep internet as well, connect a phone with a USB cable and turn on its hotspot." \
      "外网:没有。控制狗不需要网;想同时上网,就用数据线连手机并打开热点。"
fi
