#!/usr/bin/env python3
import contextlib
import os
import sys
import termios
import tty
from typing import (
    Callable,
    Dict,
    Iterator,
)


@contextlib.contextmanager
def get_rawchars() -> Iterator[Iterator[str]]:
    def gen():
        while True:
            c = sys.stdin.read(1)
            if ord(c) == 3:
                break
            yield c

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    # new = termios.tcgetattr(fd)
    # new[3] = new[3] & ~termios.ECHO          # lflags
    try:
        tty.setraw(fd)
        yield gen()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


TuiKeys = Dict[str, ConnectionTrackProtocol]
TuiConf = Callable[[], TuiKeys]


def tuiwrapper(fn: Callable[[PortMan], TuiConf]) -> Callable[[], None]:
    def wrapper() -> None:
        with contextlib.ExitStack() as stack:
            try:
                pm = stack.enter_context(PortMan())
            except jack.JackOpenError:
                if not os.environ.get("PORTMAN_INNER"):
                    print("Trying to re-exec with pw-jack...")
                    os.execvpe(
                        "pw-jack",
                        ["pw-jack", sys.executable, *sys.argv],
                        {**os.environ, "PORTMAN_INNER": "1"},
                    )
                raise
        with PortMan() as pm:
            conf = fn(pm)

            keys: TuiKeys = {}

            def get_the_status() -> str:
                return "".join(
                    c.upper() if v.get() else c.lower() for c, v in keys.items()
                )

            def update_the_status() -> None:
                nonlocal keys
                keys2 = conf()
                if keys2 == keys:
                    print("\r\x1b[K" + get_the_status(), end="", flush=True)
                    return
                keys = keys2
                print("", end="\r\n")
                print("", end="\r\n")
                for c, v in keys.items():
                    v.print(c)
                print("", end="\r\n")
                print("\r\x1b[K" + get_the_status(), end="", flush=True)

            print("")
            update_the_status()

            with pm.graph_order_callback(update_the_status):
                with get_rawchars() as rawchars:
                    for c in rawchars:
                        # print("\r\x1b[K%s" % c)
                        if c.upper() in keys:
                            track = keys[c.upper()]
                            track.set(not track.get())
                        update_the_status()

        print("")

    return wrapper
