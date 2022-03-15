from typing import Dict

from portman.jack import PortManJack as PortMan
from portman.base import (
    ConnectionTrackProtocol,
    MultiConnectionTrack,
)
from portman.scarlett import Scarlett
from portman.tui import tuiwrapper, TuiConf


@tuiwrapper
def main(pm: PortMan) -> TuiConf:
    speakers = pm.stereo_speakers()
    # outs = pm.stereo_outs()
    print(speakers.keys())
    # print(outs.keys())
    # pm.print_all_ports()
    # pm.print_all_connections()

    brand_name = "Scarlett"
    device_name = f"{brand_name} 4i4"
    client_name = f"{device_name} USB Pro"
    assert client_name in pm.clients, client_name
    blue = "Blue Microphones Pro"
    # assert blue in pm.clients, blue

    pm.set_default_sink(client_name)
    scarlett = Scarlett()
    MultiConnectionTrack(
        # PCM outputs:
        scarlett.set_pcm_outputs(
            "Mix C",
            "Mix D",
            "Analogue 3",
            "Analogue 4",
            None,
            None,
        ),
        # Analogue outputs:
        scarlett.set_analogue_outputs(
            # Analogue output 0+1 = speaker
            # Analogue output 2+3 = headphones
            "Mix A",
            "Mix B",
            "Mix C",
            "Mix D",
        ),
        scarlett.set_mix(
            # Mixer Inputs:
            [
                # PCM1+2 = Playback from host
                "PCM 1",
                "PCM 2",
                # Analogue 3+4 = Piano input
                "Analogue 3",
                "Analogue 4",
                # Analogue 1+2 = Orchestra monitor
                None,  # "Analogue 1",
                None,  # "Analogue 2",
                # PCM3+4 = Mic input
                "PCM 3",
                "PCM 4",
            ],
            [100, 0, 100, 0, 0, 0],
            [0, 100, 0, 100, 0, 0],
            [100, 0, 100, 0, 0, 0],
            [0, 100, 0, 100, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [80, 0, 80, 0, 0, 0],
            [0, 80, 0, 80, 0, 0],
        ),
    ).set(True)

    headphones_monitor = pm.stereo_out_ref(client_name, "01")
    if blue in pm.clients:
        mic_headphones = pm.stereo_speaker_ref(blue)
        pm.multi_connection_track(headphones_monitor, mic_headphones).set(True)

    def conf() -> Dict[str, ConnectionTrackProtocol]:
        if client_name not in pm.clients:
            print("\r\x1b[KMissing %s" % client_name)
            return {}
        tracks: Dict[str, ConnectionTrackProtocol] = {}
        if blue in pm.clients:
            micout = pm.stereo_out_ref(blue)
            micin = pm.stereo_speaker_ref(client_name, "23")
            tracks["Z"] = pm.multi_connection_track(micout, micin)
        tracks["X"] = scarlett.switch_mix_stereo("CD", 34)
        tracks["C"] = scarlett.switch_mix_stereo("CD", 12)
        onboard = "Built-in Audio Analog Stereo"
        laptop_speaker = pm.stereo_speaker_ref(onboard)
        # laptop_mic = pm.stereo_out_ref(onboard)
        tracks["S"] = pm.multi_connection_track(headphones_monitor, laptop_speaker)
        if "Liesl" in pm.clients:
            tracks["D"] = pm.multi_connection_track(headphones_monitor, pm.stereo_speaker_ref("Liesl"))
        return tracks

    return conf


if __name__ == "__main__":
    main()
