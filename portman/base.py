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


class KeyedEqMixin:
    key: Any

    def __eq__(self, o: Any) -> bool:
        return o.__class__ is self.__class__ and self.key == o.key


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
        self.register()
        return self
        
    def register(self) -> None:
        pass

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
                try:
                    p, = [p for n, p in ports.items() if c in n]
                except ValueError:
                    raise Exception("Couldn't find port that contains %r among %r" % (c, ports.keys()))
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
