#!/usr/bin/env bash
# Cable, step 1-1: give the Mac's USB-Ethernet port (cable to the Go2) an address on the dog's network,
# then ping the dog.   bash robot/cable_check.sh
# The Go2's onboard computer is 192.168.123.161; this Mac takes 192.168.123.222/24.
# Setting a network address needs an administrator, so macOS asks for the Mac password once.
# Only the wired adapter is changed; Wi-Fi (internet) stays as it is.
# Messages are in English, or in Chinese with GO2_LANG=zh (the panel sets it in 中文 mode).
set -u
ROBOT=192.168.123.161
ME=192.168.123.222
say() { if [ "${GO2_LANG:-en}" = zh ]; then echo "$2"; else echo "$1"; fi; }

# ---- which wired port has the cable? --------------------------------------------------------
# network services with a device; skip Wi-Fi, Bluetooth, Thunderbolt, iPhone and Jetson (Tegra) links,
# and wired ports that are already on another network (a dock or office Ethernet with internet)
SVC=""; DEV=""
while IFS='|' read -r name dev; do
  [ "$(ifconfig "$dev" 2>/dev/null | awk '/status:/{print $2}')" = "active" ] || continue
  addr=$(ipconfig getifaddr "$dev" 2>/dev/null)
  case "$addr" in
    ""|169.254.*|192.168.123.*) SVC="$name"; DEV="$dev"; break ;;
    *) say "skipping $dev ($name): it is on another network ($addr)" "跳过 $dev($name):它连着别的网络($addr)" ;;
  esac
done < <(networksetup -listnetworkserviceorder | awk '
  /^\([0-9]+\) /{sub(/^\([0-9]+\) /,""); name=$0}
  /Device: en/{d=$0; sub(/.*Device: /,"",d); sub(/\).*/,"",d)
               if (name !~ /Wi-Fi|Bluetooth|Thunderbolt|iPhone|Tegra/) print name"|"d}')
if [ -z "$DEV" ]; then
  say "No wired port with a cable found on the Mac. Plug the USB-C to Ethernet adapter into the Mac and the cable into the dog, turn the dog on, then try again." \
      "Mac 上没找到插着网线的有线网口:把 USB-C 转网口插到 Mac,网线接狗,狗开机后再试。"
  exit 1
fi
echo "wired port with a cable: $DEV ($SVC)"

# ---- give it 192.168.123.222 (once) ---------------------------------------------------------
if ifconfig "$DEV" | grep -q "inet $ME "; then
  echo "$DEV already has $ME"
else
  say "setting $DEV to $ME (macOS asks for your Mac password)..." "把 $DEV 设成 $ME(macOS 会要 Mac 开机密码)……"
  osascript - "$SVC" "$ME" <<'OSA' || { say "Not changed (password dialog cancelled?)." "没有改(密码窗口被取消了?)。"; exit 1; }
on run argv
	do shell script "/usr/sbin/networksetup -setmanual " & quoted form of (item 1 of argv) & " " & (item 2 of argv) & " 255.255.255.0" with administrator privileges
end run
OSA
  for i in $(seq 1 10); do ifconfig "$DEV" | grep -q "inet $ME " && break; sleep 1; done
fi
ifconfig "$DEV" | awk '/inet /{print "  " $1, $2}'

# ---- ping the dog ---------------------------------------------------------------------------
echo "pinging the robot..."
if ping -c 3 -W 1000 "$ROBOT"; then
  echo "ROBOT REACHABLE on $DEV"
else
  say "No reply: check the cable, that the dog is on (wait 1 minute after power on), and turn off any VPN." \
      "ping 不通:检查网线、狗是否开机(开机后等 1 分钟),并关掉 VPN。"
  exit 3
fi
