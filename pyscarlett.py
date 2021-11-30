import argparse
import string
from typing import Any, Iterable, Optional, TypedDict

import alsaaudio


parser = argparse.ArgumentParser()


def howmany(ss: Iterable[str], tpl: str, elms: Iterable[Any]) -> int:
    s = set(ss)
    for i, x in enumerate(elms):
        e = tpl % (x,)
        if e not in s:
            if i == 0:
                raise Exception("%r not found" % (e,))
            return i
    raise Exception("howmany: Upper limit not hit")


def main() -> None:
    parser.parse_args()

    get_and_dump()


def get_scarlett_card_index() -> Optional[int]:
    for card_index in alsaaudio.card_indexes():
        a, b = alsaaudio.card_name(card_index)
        if "Scarlett" in a:
            return card_index
    return None


class ScarlettChannels(TypedDict):
    card_index: int
    pcms: int
    inputs: int
    outputs: int
    mixes: int


FIXED = [
    "Line 01 Mute",
    "Line 02 Mute",
    "Line 03 Mute",
    "Line 04 Mute",
    "Line In 1-2 Phantom Power",
    "Phantom Power Persistence",
    "Sync Status",
    "Line 01 (Monitor L)",
    "Line 02 (Monitor R)",
    "Line 03 (Headphones L)",
    "Line 04 (Headphones R)",
    "Line In 1 Air",
    "Line In 1 Level",
    "Line In 1 Pad",
    "Line In 2 Air",
    "Line In 2 Level",
    "Line In 2 Pad",
]
C_PCM = "PCM %02d"
C_INPUT = "Mixer Input %02d"
C_OUTPUT = "Analogue Output %02d"
C_MIX = "Mix %s Input %02d"


def get_and_dump() -> int:
    channels = get_channels()
    dump_channels(channels)
    return channels["card_index"]


def get_channels() -> ScarlettChannels:
    card_index = get_scarlett_card_index()
    if card_index is None:
        raise SystemExit("Didn't find any audio card with 'Scarlett' in the name")
    mixer_names = alsaaudio.mixers(card_index)
    if not mixer_names:
        a, b = alsaaudio.card_name(card_index)
        raise SystemExit(
            "No mixers available for %s. Are you running a kernel with the right driver support?"
            % a
        )
    pcms = howmany(mixer_names, C_PCM, range(1, 100))
    inputs = howmany(mixer_names, C_INPUT, range(1, 100))
    outputs = howmany(mixer_names, C_OUTPUT, range(1, 100))
    mixes = howmany(mixer_names, C_MIX % ("%s", 1), string.ascii_uppercase)
    missing = set(FIXED) - set(mixer_names)
    if missing:
        raise Exception("Missing: %r" % (missing,))
    expected = (
        {C_PCM % i for i in range(1, pcms + 1)}
        | {C_INPUT % i for i in range(1, inputs + 1)}
        | {C_OUTPUT % i for i in range(1, outputs + 1)}
        | {
            C_MIX % (s, i)
            for s in string.ascii_uppercase[:mixes]
            for i in range(1, inputs + 1)
        }
        | set(FIXED)
    )
    unexpected = set(mixer_names) - expected
    if unexpected:
        raise Exception("Unexpected: %r" % sorted(unexpected))
    return {
        "card_index": card_index,
        "pcms": pcms,
        "inputs": inputs,
        "outputs": outputs,
        "mixes": mixes,
    }


def dump_channels(channels: ScarlettChannels) -> None:
    card_index = channels["card_index"]
    pcms = channels["pcms"]
    inputs = channels["inputs"]
    outputs = channels["outputs"]
    mixes = channels["mixes"]
    a, b = alsaaudio.card_name(card_index)
    print("Found hw:%s: %r %r" % (card_index, a, b))
    print(" ".join(string.ascii_uppercase[:mixes]))
    for i in range(1, inputs + 1):
        line = []
        for s in string.ascii_uppercase[:mixes]:
            mixer = alsaaudio.Mixer(C_MIX % (s, i), 0, card_index)
            a, b = mixer.getrange()
            v, = mixer.getvolume()
            rel = int(10 * ((v - a) / (b - a + 1)))
            line.append(str(rel))
        line.append(alsaaudio.Mixer(C_INPUT % (i,), 0, card_index).getenum()[0])
        print(" ".join(line))
    for i in range(1, pcms + 1):
        n = C_PCM % i
        print(n, "<-", alsaaudio.Mixer(n, 0, card_index).getenum()[0])
    for i in range(1, outputs + 1):
        n = C_OUTPUT % i
        print(n, "<-", alsaaudio.Mixer(n, 0, card_index).getenum()[0])

    for mixername in FIXED:
        m = alsaaudio.Mixer(mixername, 0, card_index)
        e = m.getenum()
        if e:
            print(m.mixer(), e)
            continue
        sc = m.switchcap()
        if any("Playback" in s for s in sc):
            r = m.getmute()
            print(m.mixer(), sc, r)
            continue
        elif sc:
            r = m.getrec()
            print(m.mixer(), sc, r)
            continue
        print(m.mixer(), m.getrange(), m.getvolume())
    return card_index


if __name__ == "__main__":
    main()
