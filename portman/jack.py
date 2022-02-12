import threading
import traceback
from typing import Dict, Optional

import jack

from .base import PortMan, Client


class PortManJack(PortMan):
    def register(self) -> None:
        super().register()

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
