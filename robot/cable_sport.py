"""Send ONE high-level sport command to a REAL Unitree Go2 over the Ethernet cable.

THIS MAKES THE ROBOT MOVE. Clear 2 m around it and keep the remote in hand
(remote emergency stop: hold L2 then press B = damping).

The first argument is the Mac's network card on 192.168.123.x (en7 here):
    .venv/bin/python robot/cable_sport.py en7 standup        # lying -> standing, joints locked   (API 1004)
    .venv/bin/python robot/cable_sport.py en7 balance        # standing -> balance stand, ready to walk (1002)
    .venv/bin/python robot/cable_sport.py en7 move 0.2 0 0 2 # walk: vx vy vyaw seconds            (1008)
    .venv/bin/python robot/cable_sport.py en7 stop           # stop walking, stay standing        (1003)
    .venv/bin/python robot/cable_sport.py en7 standdown      # standing -> lying on the floor     (1005)
    .venv/bin/python robot/cable_sport.py en7 damp           # all motors go soft (damping)       (1001)
    .venv/bin/python robot/cable_sport.py en7 recovery       # get up again after a fall          (1006)
Add --dry-run to only print what would be sent (no network, no robot needed).
Add --yes to skip the 'Press Enter' question (the control panel asks in a dialog instead).

Suggested first session:  standup -> balance -> move (small) -> stop -> standdown -> damp
Damp while STANDING makes the robot sink to the floor, so lie it down first.

move limits (clamped here): |vx| <= 0.3 m/s forward, |vy| <= 0.2 m/s left,
|vyaw| <= 0.5 rad/s turn left, seconds <= 3. StopMove is always sent at the end.
"""
import signal
import sys
import time


STOP_REQUESTED = False


def _terminated(signum, frame):
    # 'kill', 'timeout' or the panel's STOP send SIGTERM. Remember it, and the first time turn it into Ctrl+C
    # so the move loop still sends StopMove. The flag matters because the SDK swallows Ctrl+C while it waits
    # for a reply, so an interrupted command must also check the flag before it sends anything.
    global STOP_REQUESTED
    first = not STOP_REQUESTED
    STOP_REQUESTED = True
    if first:
        raise KeyboardInterrupt


signal.signal(signal.SIGTERM, _terminated)

DOMAIN_ID = 0  # the real robot always uses DDS domain 0

LIMITS = {"vx": 0.3, "vy": 0.2, "vyaw": 0.5, "seconds": 3.0}
MOVE_PERIOD = 0.05  # re-send the Move command every 0.05 s (20 times per second)

# action -> (SportClient method name, API id, what it does, asks for Enter first?)
ACTIONS = {
    "standup":   ("StandUp",       1004, "stand up and lock the joints", True),
    "balance":   ("BalanceStand",  1002, "switch to balance stand (needed before walking)", True),
    "recovery":  ("RecoveryStand", 1006, "recover to standing (e.g. after a fall)", True),
    "stop":      ("StopMove",      1003, "stop moving, keep the current stance", False),
    "standdown": ("StandDown",     1005, "lie down on the floor", False),
    "damp":      ("Damp",          1001, "damping: all motors go soft (robot sinks if standing)", False),
    "move":      ("Move",          1008, "walk with a velocity, then StopMove", True),
}

# Return codes from unitree_sdk2py/rpc/internal.py and go2/sport/sport_api.py
CODE_MEANING = {
    0: "OK",
    3001: "unknown error",
    # 3102: the SDK waits up to SetTimeout() seconds for the robot's service to
    # appear on the network; if nobody is listening it gives up with 3102.
    3102: "NOT SENT: no robot service found (wrong interface or IP, cable, robot off)",
    3103: "API not registered in the client",
    3104: "sent, but no answer in time",
    3105: "answer did not match the request",
    3203: "the robot does not implement this API",
    3204: "the robot rejected the parameters",
    4201: "sport service overtime",
    4202: "sport service not initialised",
}


def usage():
    print(__doc__)
    sys.exit(1)


def clamp(name, value):
    lim = LIMITS[name]
    clamped = max(-lim, min(lim, value))
    if clamped != value:
        print(f"  note: {name} = {value} clamped to {clamped}")
    return clamped


def explain(code):
    return f"{code} ({CODE_MEANING.get(code, 'robot-side error code')})"


def parse_args(argv):
    dry_run = "--dry-run" in argv
    yes = "--yes" in argv
    args = [a for a in argv if a not in ("--dry-run", "--yes")]
    if len(args) < 2 or args[1] not in ACTIONS:
        usage()
    iface, action = args[0], args[1]
    move = None
    if action == "move":
        if len(args) != 6:
            print("move needs 4 numbers: vx vy vyaw seconds   e.g.  move 0.2 0 0 2")
            sys.exit(1)
        vx, vy, vyaw, secs = (float(x) for x in args[2:6])
        vx, vy, vyaw = clamp("vx", vx), clamp("vy", vy), clamp("vyaw", vyaw)
        if not 0.0 <= secs <= LIMITS["seconds"]:
            print(f"  note: seconds = {secs} clamped to 0..{LIMITS['seconds']}")
            secs = min(max(secs, 0.0), LIMITS["seconds"])
        move = (vx, vy, vyaw, secs)
    elif len(args) != 2:
        print(f"'{action}' takes no extra numbers")
        sys.exit(1)
    return iface, action, move, dry_run, yes


def check_mode():
    """Read-only: ask the motion switcher which controller is active.
    SportClient only works while a sport mode (for example 'normal') is active.
    An empty name means sport mode was released for low-level control."""
    from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
    msc = MotionSwitcherClient()
    msc.SetTimeout(3.0)
    msc.Init()
    code, result = msc.CheckMode()
    if code != 0:
        print(f"  motion switcher CheckMode: {explain(code)} (continuing)")
        return True
    name = result.get("name", "") if isinstance(result, dict) else ""
    print(f"  motion switcher mode: {result}")
    if not name:
        print("  sport mode is RELEASED (low-level mode), so sport commands will not work.")
        print("  Ask the instructor, or reboot the robot to get sport mode back.")
        return False
    return True


def main():
    iface, action, move, dry_run, yes = parse_args(sys.argv[1:])
    method, api_id, what, confirm = ACTIONS[action]

    print(f"interface {iface}, domain {DOMAIN_ID}")
    print(f"about to send: {method} (API {api_id}) = {what}")
    if move:
        vx, vy, vyaw, secs = move
        print(f"  Move(vx={vx}, vy={vy}, vyaw={vyaw}) every {MOVE_PERIOD} s for {secs} s, then StopMove")
    if dry_run:
        print("dry run: nothing sent")
        return

    # Import here so that --dry-run works even without the SDK.
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.go2.sport.sport_client import SportClient

    try:
        ChannelFactoryInitialize(DOMAIN_ID, iface)
    except Exception:
        # Cyclone DDS prints "<iface>: does not match an available interface."
        print(f"cannot use network interface '{iface}'. List the cards with: ifconfig")
        sys.exit(2)
    # stop and damp must go out at once: no mode check first (it can wait up to 3 s)
    if action not in ("stop", "damp") and not check_mode():
        sys.exit(3)

    client = SportClient()
    client.SetTimeout(5.0)  # seconds to wait for the robot's answer
    client.Init()

    if confirm and not yes:
        input("Press Enter to send (Ctrl+C to cancel) ... ")

    if STOP_REQUESTED and action not in ("stop", "damp", "standdown"):
        print(f"STOP was pressed before {method} went out: nothing sent")
        if action != "move":
            return

    if action != "move":
        code = getattr(client, method)()
        if code != 0 and action in ("stop", "damp", "standdown"):
            # safe to repeat: send it once more if the first try got no answer
            code = getattr(client, method)()
        print(f"{method} returned {explain(code)}")
        return

    # move: keep sending the velocity, then always stop.
    vx, vy, vyaw, secs = move
    first_code, n_sent = None, 0
    t_end = None
    try:
        while not STOP_REQUESTED and (t_end is None or time.time() < t_end):
            code = client.Move(vx, vy, vyaw)  # no reply from the robot: 0 only means "sent"
            if first_code is None:
                first_code = code
                t_end = time.time() + secs  # the clock starts when the first Move has gone out
            if code != 0:
                break  # could not send, so do not keep trying
            n_sent += 1
            time.sleep(MOVE_PERIOD)
    except KeyboardInterrupt:
        print("Ctrl+C: stopping")
    finally:
        code = client.StopMove()
        if code != 0:
            code = client.StopMove()
        first = explain(first_code) if first_code is not None else "none sent"
        print(f"Move sent {n_sent} times, first return {first}")
        print(f"StopMove returned {explain(code)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("stopped by STOP or the time limit")
