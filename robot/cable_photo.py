"""Take one picture with the front camera of a REAL Unitree Go2 over the Ethernet cable. READ-ONLY.

    .venv/bin/python robot/cable_photo.py en7 front.jpg

The first argument is the Mac's network card that is on 192.168.123.x.
It asks the robot's "videohub" service for one JPEG (VideoClient.GetImageSample,
API id 1001) and writes the bytes to the file. Same idea as the SDK example
example/go2/front_camera/capture_image.py.
"""
import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.video.video_client import VideoClient

DOMAIN_ID = 0  # the real robot always uses DDS domain 0


def main():
    if len(sys.argv) < 3:
        print("usage: .venv/bin/python robot/cable_photo.py <network_card> <out.jpg>")
        sys.exit(1)
    iface, out_path = sys.argv[1], sys.argv[2]

    try:
        ChannelFactoryInitialize(DOMAIN_ID, iface)
    except Exception:
        # Cyclone DDS prints "<iface>: does not match an available interface."
        print(f"cannot use network interface '{iface}'. List the cards with: ifconfig")
        sys.exit(2)

    client = VideoClient()
    client.SetTimeout(3.0)  # seconds to wait for the robot's answer
    client.Init()

    print(f"asking the front camera for one image on {iface} ...")
    code, data = client.GetImageSample()
    if code != 0:
        # the very first call can fail while the two sides are still finding each other: try once more
        time.sleep(1.0)
        code, data = client.GetImageSample()
    if code != 0:
        # 3102 = not sent: no robot service found (wrong interface/IP, cable, robot off)
        # 3104 = sent, but no answer within the timeout
        print(f"failed, return code {code}")
        sys.exit(2)

    jpg = bytes(data)
    with open(out_path, "wb") as f:
        f.write(jpg)
    is_jpeg = jpg[:2] == b"\xff\xd8"
    print(f"saved {out_path} ({len(jpg)} bytes, JPEG header ok: {is_jpeg})")


if __name__ == "__main__":
    main()
