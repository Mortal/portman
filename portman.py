#!/usr/bin/env python3
import contextlib
import os
import string
import subprocess
import sys
import termios
import threading
import traceback
import tty
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypedDict,
)

import alsaaudio
import jack

import pyscarlett


class PortRef(NamedTuple):
    client_name: str
    subclient_name: str
    port_name: str


class Port(TypedDict):
    connections: Dict[PortRef, None]


class Client(TypedDict):
    ports: Dict[PortRef, Port]


class ConnectionTrackProtocol(Protocol):
    def get(self) -> bool:
        ...

    def set(self, v: bool) -> None:
        ...

    def print(self, c: str) -> None:
        ...


class SimpleEqMixin:
    def __eq__(self, o: Any) -> bool:
        return o.__class__ is self.__class__ and self.__dict__ == o.__dict__


class AmixerTrackBase(SimpleEqMixin):
    def __init__(self, card_index: int, control_name: str) -> None:
        self.card_index = card_index
        self.control_name = control_name

    def _get_lines(self) -> Dict[str, str]:
        lines = subprocess.check_output(
            ("amixer", "-c1", "sget", "%s,0" % self.control_name),
            universal_newlines=True,
        ).splitlines()
        assert lines[0].startswith("Simple mixer control")
        return {k: v for line in lines[1:] for k, v in [line.strip().split(": ", 1)]}

    def _set(self, s: str) -> None:
        subprocess.check_call(
            ("amixer", "-c1", "sset", "%s,0" % self.control_name, s),
            stdout=subprocess.DEVNULL,
        )


class AmixerEnumTrack(AmixerTrackBase):
    def __init__(
        self, card_index: int, control_name: str, off_setting: str, on_setting: str
    ) -> None:
        super().__init__(card_index, control_name)
        self.off_setting = off_setting
        self.on_setting = on_setting

    def get(self) -> bool:
        return self._get_lines()["Item0"] == "'%s'" % self.on_setting

    def set(self, v: bool) -> None:
        self._set(self.on_setting if v else self.off_setting)

    def __repr__(self) -> str:
        return f"<AmixerEnumTrack control_name={self.control_name} off={self.off_setting} on={self.on_setting}>"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")


class AmixerVolumeTrack(AmixerTrackBase):
    def __init__(self, card_index: int, control_name: str, on_setting: int) -> None:
        super().__init__(card_index, control_name)
        self.off_setting = 0
        self.on_setting = on_setting

    def get(self) -> bool:
        return int(self._get_lines()["Mono"].split()[1]) == self.on_setting

    def set(self, v: bool) -> None:
        self._set(str(self.on_setting if v else self.off_setting))

    def __repr__(self) -> str:
        return f"<AmixerVolumeTrack control_name={self.control_name} off={self.off_setting} on={self.on_setting}>"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")


class KeyedEqMixin:
    key: Any

    def __eq__(self, o: Any) -> bool:
        return o.__class__ is self.__class__ and self.key == o.key


_mixers: Dict[Tuple[int, str], alsaaudio.Mixer] = {}


def _get_mixer(card_index: int, control_name: str) -> alsaaudio.Mixer:
    try:
        return _mixers[card_index, control_name]
    except KeyError:
        _mixers[card_index, control_name] = m = alsaaudio.Mixer(
            cardindex=card_index, control=control_name
        )
        return m


class PyalsaaudioEnumTrack(KeyedEqMixin):
    def __init__(
        self, card_index: int, control_name: str, off_setting: str, on_setting: str
    ) -> None:
        self.key = (card_index, control_name, off_setting, on_setting)
        self.card_index = card_index
        self.control_name = control_name
        self.mixer = _get_mixer(card_index, control_name)
        self.off_setting = off_setting
        self.on_setting = on_setting

    def get(self) -> bool:
        return self.mixer.getenum()[0] == self.on_setting

    def set(self, v: bool) -> None:
        c, vs = self.mixer.getenum()
        self.mixer.setenum(vs.index(self.on_setting if v else self.off_setting))

    def __repr__(self) -> str:
        args = ", ".join(
            "%s=%r" % (k, getattr(self, k))
            for k in "card_index control_name off_setting on_setting".split()
        )
        return f"{self.__class__.__name__}({args})"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")


class PyalsaaudioVolumeTrack(KeyedEqMixin):
    def __init__(self, card_index: int, control_name: str, on_setting: int) -> None:
        self.key = (card_index, control_name, on_setting)
        self.card_index = card_index
        self.control_name = control_name
        self.mixer = _get_mixer(card_index, control_name)
        self.off_setting = 0
        self.on_setting = on_setting

    def get(self) -> bool:
        v = self.mixer.getvolume()[0]
        return v == self.on_setting

    def set(self, v: bool) -> None:
        self.mixer.setvolume(self.on_setting if v else self.off_setting)

    def __repr__(self) -> str:
        args = ", ".join(
            "%s=%r" % (k, getattr(self, k))
            for k in "card_index control_name on_setting".split()
        )
        return f"{self.__class__.__name__}({args})"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")


class Scarlett:
    def __init__(self) -> None:
        self.channels = pyscarlett.get_channels()
        self.card_index = self.channels["card_index"]
        self.pcms = self.channels["pcms"]
        self.inputs = self.channels["inputs"]
        self.outputs = self.channels["outputs"]
        self.mixes = self.channels["mixes"]

    def set_analogue_outputs(self, *args: Optional[str]) -> ConnectionTrackProtocol:
        assert len(args) == self.outputs
        switches = [
            self.switch_analogue_output(i, s)
            for i, s in enumerate(args)
            if s is not None
        ]
        return MultiConnectionTrack(*switches)

    def set_pcm_outputs(self, *args: Optional[str]) -> ConnectionTrackProtocol:
        assert len(args) == self.pcms
        switches = [
            self.switch_pcm_output(i, s) for i, s in enumerate(args) if s is not None
        ]
        return MultiConnectionTrack(*switches)

    def set_mixer_inputs(self, *args: Optional[str]) -> ConnectionTrackProtocol:
        assert len(args) == self.inputs
        switches = [
            self.switch_mixer_input(i, s)
            for i, s in enumerate(args, 1)
            if s is not None
        ]
        return MultiConnectionTrack(*switches)

    def set_mix(
        self, inputs: List[Optional[str]], *args: List[Optional[int]]
    ) -> ConnectionTrackProtocol:
        assert len(inputs) == self.inputs
        assert len(args) == self.inputs
        assert all(len(a) == self.mixes for a in args)
        switches = [
            self.switch_mix(c, i, v)
            for i, a in enumerate(args, 1)
            for c, v in zip(string.ascii_uppercase, a)
            if v is not None
        ]
        return MultiConnectionTrack(self.set_mixer_inputs(*inputs), *switches)

    def switch_analogue_output(
        self, output_index: int, on_state: str
    ) -> ConnectionTrackProtocol:
        assert 0 <= output_index < self.outputs
        return PyalsaaudioEnumTrack(
            self.card_index,
            "Analogue Output %02d" % (1 + output_index),
            "Off",
            on_state,
        )

    def switch_pcm_output(
        self, output_index: int, on_state: str
    ) -> ConnectionTrackProtocol:
        assert 0 <= output_index < self.pcms
        return PyalsaaudioEnumTrack(
            self.card_index, "PCM %02d" % (1 + output_index), "Off", on_state
        )

    def switch_mixer_input(self, inp: int, on_state: str) -> ConnectionTrackProtocol:
        assert 1 <= inp <= self.inputs
        return PyalsaaudioEnumTrack(
            self.card_index, "Mixer Input %02d" % inp, "Off", on_state
        )

    def switch_mix(
        self, mix: str, inp: int, volume: int = 100
    ) -> ConnectionTrackProtocol:
        assert 1 <= inp <= self.inputs
        assert ord("A") <= ord(mix) < ord("A") + self.mixes
        return PyalsaaudioVolumeTrack(
            self.card_index, f"Mix {mix} Input {inp:02d}", volume
        )

    def switch_mix_stereo(
        self, mixmix: str, inpinp: int, volume: int = 100
    ) -> ConnectionTrackProtocol:
        assert len(mixmix) == 2
        m, n = mixmix[0], mixmix[1]
        i, j = divmod(inpinp, 10)
        return MultiConnectionTrack(self.switch_mix(m, i), self.switch_mix(n, j))


class Swap(KeyedEqMixin):
    def __init__(self, *tracks: ConnectionTrackProtocol) -> None:
        self.key = tuple(tracks)
        assert len(tracks) % 2 == 0
        self.a = tracks[::2]
        self.b = tracks[1::2]

    def get(self) -> bool:
        a_s = [t.get() for t in self.a]
        b_s = [t.get() for t in self.b]
        return a_s != b_s

    def set(self, _v: bool) -> None:
        a_s = [t.get() for t in self.a]
        b_s = [t.get() for t in self.b]
        print("\r\x1b[K%s %s %s %s" % (self.a, a_s, self.b, b_s))
        for a, t in zip(a_s, self.b):
            t.set(a)
        for b, t in zip(b_s, self.a):
            t.set(b)

    def print(self, c: str) -> None:
        print(c, "Swap", end="\r\n")


class Push(KeyedEqMixin):
    def __init__(self, *tracks: ConnectionTrackProtocol) -> None:
        self.key = tuple(tracks)
        assert len(tracks) % 2 == 0
        self.froms = tracks[::2]
        self.tos = tracks[1::2]

    def get(self) -> bool:
        a_s = [t.get() for t in self.froms]
        b_s = [t.get() for t in self.tos]
        return a_s != b_s

    def set(self, _v: bool) -> None:
        vals = [u.get() for u in self.froms], [u.get() for u in self.tos]
        print("\r\x1b[K%s %s" % vals)
        for u, v in zip(vals[0], self.tos):
            v.set(u)
            # print("\r\x1b[K%r %s %s" % (v, u, v.get()))
        vals = [u.get() for u in self.froms], [u.get() for u in self.tos]
        print("\r\x1b[K%s %s" % vals)

    def print(self, c: str) -> None:
        print(c, "Push", end="\r\n")


class ConnectionTrack(SimpleEqMixin):
    def __init__(self, pm: "PortMan", a: PortRef, b: PortRef) -> None:
        self.pm = pm
        self.a = a
        self.b = b

    def get(self) -> bool:
        a_client = self.pm.clients[self.a.client_name]
        a_port = a_client["ports"][self.a]
        return self.b in a_port["connections"]

    def set(self, v: bool) -> None:
        a_name = f"{self.a.subclient_name}:{self.a.port_name}"
        b_name = f"{self.b.subclient_name}:{self.b.port_name}"
        if v and not self.get():
            self.pm._conn.connect(a_name, b_name)
        elif not v and self.get():
            self.pm._conn.disconnect(a_name, b_name)

    def print(self, c: str) -> None:
        print(
            c,
            self.a.client_name,
            self.a.port_name,
            self.b.client_name,
            self.b.port_name,
            end="\r\n",
        )


class MultiConnectionTrack(SimpleEqMixin):
    def __init__(self, *tracks: ConnectionTrackProtocol) -> None:
        self.tracks = tracks

    def __repr__(self) -> str:
        return "%s(%s)" % (self.__class__.__name__, ", ".join(map(repr, self.tracks)))

    def get(self) -> bool:
        return self.tracks[0].get()

    def set(self, v: bool) -> None:
        for t in self.tracks:
            t.set(v)

    def print(self, c: str) -> None:
        for t in self.tracks:
            try:
                t.print(c)
            except Exception as e:
                print(c, t, repr(e))


class PortMan:
    name = "PortMan"
    samplerate: int
    blocksize: int

    def __init__(self) -> None:
        self._real_remote_client: Dict[str, str] = {}
        self._graph_order_callback: List[Callable[[], None]] = []

    @contextlib.contextmanager
    def graph_order_callback(self, f: Callable[[], None]) -> Iterator[None]:
        self._graph_order_callback.append(f)
        try:
            yield
        finally:
            try:
                self._graph_order_callback.remove(f)
            except ValueError:
                traceback.print_exc()

    def __enter__(self) -> "PortMan":
        @jack.set_error_function
        def error(msg):
            print("Error:", msg)

        @jack.set_info_function
        def info(msg):
            print("Info:", msg)

        self._conn = jackconn = jack.Client(self.name)

        # if jackconn.status.server_started:
        #     print('JACK server was started')
        # else:
        #     print('JACK server was already running')
        # if jackconn.status.name_not_unique:
        #     print('unique client name generated:', jackconn.name)

        # print('registering callbacks')

        @jackconn.set_shutdown_callback
        def shutdown(status, reason):
            print("JACK shutdown!")
            print("status:", status)
            print("reason:", reason)

        @jackconn.set_freewheel_callback
        def freewheel(starting):
            print(["stopping", "starting"][starting], "freewheel mode")

        @jackconn.set_blocksize_callback
        def blocksize(blocksize):
            self.blocksize = blocksize

        @jackconn.set_samplerate_callback
        def samplerate(samplerate):
            self.samplerate = samplerate

        @jackconn.set_client_registration_callback
        def client_registration(client_name, register):
            if register:
                self.clients.setdefault(client_name, {"ports": {}})
            else:
                self.clients.pop(client_name, None)

        @jackconn.set_port_registration_callback
        def port_registration(port: jack.Port, register):
            port_ref = self._jack_port_name_to_ref(port.name)
            client = self.clients.setdefault(port_ref.client_name, {"ports": {}})
            if register:
                client["ports"].setdefault(port_ref, {"connections": {}})
            else:
                client["ports"].pop(port_ref, None)

        @jackconn.set_port_connect_callback
        def port_connect(a: jack.Port, b: jack.Port, connect):
            a_ref = self._jack_port_name_to_ref(a.name)
            b_ref = self._jack_port_name_to_ref(b.name)
            a_client = self.clients.setdefault(a_ref.client_name, {"ports": {}})
            b_client = self.clients.setdefault(b_ref.client_name, {"ports": {}})
            a_ports = a_client["ports"]
            b_ports = b_client["ports"]
            try:
                a_port = a_ports[a_ref]
                b_port = b_ports[b_ref]
            except KeyError:
                print(f"Port connect/disconnect between unknown ports: {a!r} {b!r}")
                return
            if connect:
                b_port["connections"][a_ref] = None
                a_port["connections"][b_ref] = None
            else:
                b_port["connections"].pop(a_ref, None)
                a_port["connections"].pop(b_ref, None)

        try:

            @jackconn.set_port_rename_callback
            def port_rename(port, old, new):
                print("renamed", port, "from", repr(old), "to", repr(new))

        except AttributeError:
            print("Could not register port rename callback (not available on JACK1).")

        self.graph_reordered: Optional[threading.Event] = threading.Event()

        def graph_reordered_thread():
            while self.graph_reordered is not None:
                self.graph_reordered.wait()
                # print("\r\x1b[Kgraph_reordered - wait for it to settle...")
                if self.graph_reordered is None:
                    return
                self.graph_reordered.clear()
                while self.graph_reordered.wait(0.05):
                    # print("\r\x1b[Kgraph_reordered - woop")
                    if self.graph_reordered is None:
                        return
                    self.graph_reordered.clear()
                # print("\r\x1b[Kgraph_reordered")
                for f in self._graph_order_callback:
                    try:
                        f()
                    except Exception:
                        traceback.print_exc()

        threading.Thread(target=graph_reordered_thread).start()

        @jackconn.set_graph_order_callback
        def graph_order():
            if self.graph_reordered is not None:
                self.graph_reordered.set()

        @jackconn.set_xrun_callback
        def xrun(delay):
            pass  # print('\r\x1b[Kxrun; delay', delay, 'microseconds', end="\r\n")

        try:

            @jackconn.set_property_change_callback
            def property_change(subject, key, changed):
                print("subject {}: ".format(subject), end="")
                if not key:
                    assert changed == jack.PROPERTY_DELETED
                    print("all properties were removed")
                    return
                print(
                    "property {!r} was {}".format(
                        key,
                        {
                            jack.PROPERTY_CREATED: "created",
                            jack.PROPERTY_CHANGED: "changed",
                            jack.PROPERTY_DELETED: "removed",
                        }[changed],
                    )
                )

        except jack.JackError as e:
            print(e)

        jackconn.__enter__()
        self.clients: Dict[str, Client] = {}
        for port in jackconn.get_ports():
            ref = self._jack_port_name_to_ref(port.name)
            # print(repr(port), repr(ref))
            portconns = self.clients.setdefault(ref.client_name, {"ports": {}})[
                "ports"
            ].setdefault(ref, {"connections": {}})["connections"]
            assert port.shortname == ref.port_name, (port.shortname, port.name)
            for connection in jackconn.get_all_connections(port):
                connref = self._jack_port_name_to_ref(connection.name)
                portconns[connref] = None
        return self

    def _jack_port_name_to_ref(self, port_name: str) -> PortRef:
        remote_client, shortname = port_name.split(":", 1)
        try:
            real_client = self._real_remote_client[remote_client]
        except KeyError:
            real_client = self._real_remote_client[
                remote_client
            ] = self._conn.get_client_name_by_uuid(
                self._conn.get_uuid_for_client_name(remote_client)
            )
        return PortRef(real_client, remote_client, shortname)

    def __exit__(self, exb, exv, ext) -> None:
        if self.graph_reordered is not None:
            g = self.graph_reordered
            self.graph_reordered = None
            g.set()
        self._conn.__exit__(exb, exv, ext)

    def print_all_clients(self) -> None:
        for client_name, client in self.clients.items():
            print(client_name)

    def print_all_ports(self) -> None:
        for client_name, client in self.clients.items():
            print(client_name)
            print("{%s}" % ", ".join(repr(p.port_name) for p in client["ports"]))

    def print_all_connections(self) -> None:
        for client_name, client in self.clients.items():
            print(client_name)
            for port_ref, port in client["ports"].items():
                print(f"- {port_ref.port_name}")
                for n in port["connections"]:
                    print(f"  -> {n.subclient_name}:{n.port_name}")

    def stereo_out_ref(
        self, client_name: str, channels: Optional[Sequence[str]] = None
    ) -> List[PortRef]:
        client = self.clients[client_name]
        ports = {p.port_name: p for p in client["ports"]}
        if channels is not None:
            ports = {n: p for n, p in ports.items() if "playback" not in n}
            if any("capture" in n for n in ports):
                ports = {n: p for n, p in ports.items() if "monitor" not in n}
            res = []
            for c in channels:
                # print(c, ports.keys())
                p, = [p for n, p in ports.items() if c in n]
                res.append(p)
            return res
        port_names = set(ports.keys())
        # Built-in Audio Analog Stereo
        if port_names == {
            "capture_FL",
            "capture_FR",
            "playback_FL",
            "monitor_FL",
            "playback_FR",
            "monitor_FR",
        }:
            return [ports["capture_FL"], ports["capture_FR"]]
        # Firefox
        if port_names == {"output_FL", "output_FR"}:
            return [ports["output_FL"], ports["output_FR"]]
        # Liesl
        if port_names == {"playback_FL", "monitor_FL", "playback_FR", "monitor_FR"}:
            return [ports["monitor_FL"], ports["monitor_FR"]]
        # Playback
        if port_names == {"playback_FL", "capture_FL", "playback_FR", "capture_FR"}:
            return [ports["capture_FL"], ports["capture_FR"]]
        # Blue Microphones Pro
        if port_names == {
            "playback_AUX0",
            "monitor_AUX0",
            "capture_AUX0",
            "capture_AUX1",
            "monitor_AUX1",
            "playback_AUX1",
        }:
            return [ports["capture_AUX0"], ports["capture_AUX1"]]
        raise Exception("Don't know how to get a stereo ref from %r" % port_names)

    def stereo_speaker_ref(
        self, client_name: str, channels: Optional[Sequence[str]] = None
    ) -> List[PortRef]:
        client = self.clients[client_name]
        ports = {p.port_name: p for p in client["ports"]}
        if channels is not None:
            ports = {n: p for n, p in ports.items() if "playback" in n}
            res = []
            for c in channels:
                p, = [p for n, p in ports.items() if c in n]
                res.append(p)
            return res
        port_names = set(ports.keys())
        # Built-in Audio Analog Stereo
        if port_names == {
            "capture_FL",
            "capture_FR",
            "playback_FL",
            "monitor_FL",
            "playback_FR",
            "monitor_FR",
        }:
            return [ports["playback_FL"], ports["playback_FR"]]
        # Liesl
        if port_names == {"playback_FL", "monitor_FL", "playback_FR", "monitor_FR"}:
            return [ports["playback_FL"], ports["playback_FR"]]
        # Playback
        if port_names == {"playback_FL", "capture_FL", "playback_FR", "capture_FR"}:
            return [ports["playback_FL"], ports["playback_FR"]]
        # Blue Yeti
        if port_names == {
            "capture_AUX0",
            "capture_AUX1",
            "monitor_AUX0",
            "monitor_AUX1",
            "playback_AUX0",
            "playback_AUX1",
        }:
            return [ports["playback_AUX0"], ports["playback_AUX1"]]
        raise Exception(
            "Don't know how to get a stereo ref from %r" % ",".join(sorted(port_names))
        )

    def stereo_outs(self) -> Dict[str, List[PortRef]]:
        res = {}
        for client_name in self.clients:
            try:
                res[client_name] = self.stereo_out_ref(client_name)
            except Exception:
                pass
        return res

    def stereo_speakers(self) -> Dict[str, List[PortRef]]:
        res = {}
        for client_name in self.clients:
            try:
                res[client_name] = self.stereo_speaker_ref(client_name)
            except Exception:
                pass
        return res

    def connection_track(self, a: PortRef, b: PortRef) -> ConnectionTrack:
        return ConnectionTrack(self, a, b)

    def multi_connection_track(
        self, a_refs: List[PortRef], b_refs: List[PortRef]
    ) -> MultiConnectionTrack:
        tracks = [
            self.connection_track(a_ref, b_ref) for a_ref, b_ref in zip(a_refs, b_refs)
        ]
        return MultiConnectionTrack(*tracks)

    @staticmethod
    def set_default_sink(client_name: str) -> None:
        items = {}
        cmdline = "pactl list sinks"
        stdout = subprocess.check_output(cmdline, shell=True, universal_newlines=True)
        for line in stdout.splitlines():
            if not line.strip():
                continue
            if not line.startswith("\t"):
                items = {}
                continue
            if line.startswith(("\t\t", "\t ")):
                continue
            assert ":" in line, line
            k, v = line.split(":", 1)
            items[k.strip()] = v.strip()
            if k.strip() == "Description" and v.strip() == client_name:
                break
        else:
            raise Exception("Client not found in output of %s" % cmdline)
        subprocess.check_call(("pactl", "set-default-sink", items["Name"]))


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
