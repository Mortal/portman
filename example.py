from typing import Dict

from portman import ConnectionTrackProtocol, PortMan, TuiConf, tuiwrapper


@tuiwrapper
def main(pm: PortMan) -> TuiConf:
    # Choose a speaker to route everything to.
    # A special-purpose script would probably hard-code the client name, e.g.
    # speaker = pm.stereo_speaker_ref("Blue Microphones Pro")
    # speaker = pm.stereo_speaker_ref("Scarlett 4i4 USB Pro")
    speaker = None
    for client_name in sorted(pm.clients):
        try:
            speaker = pm.stereo_speaker_ref(client_name)
            print(client_name)
            print(speaker)
        except Exception:
            pass
        else:
            # Tell pulseaudio to make this the default sink:
            # pm.set_default_sink(client_name)
            break
    assert speaker is not None
    the_speaker = speaker

    def conf() -> Dict[str, ConnectionTrackProtocol]:
        # This function runs every time the JACK graph changes,
        # so the key-bindings do not have to be fixed
        # for the duration of the script execution.

        # Find up to len(keys) clients with output ports
        # and wire them to the given keyboard keys.
        keys = "ZXCVB"
        sources = []
        for client_name in sorted(pm.clients):
            try:
                sources.append(pm.stereo_out_ref(client_name))
            except Exception:
                pass
            if len(sources) == len(keys):
                break
        return {
            k: pm.multi_connection_track(source, the_speaker)
            for k, source in zip(keys, sources)
        }

    return conf


if __name__ == "__main__":
    main()
