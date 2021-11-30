from portman import (
    PortMan,
    Scarlett,
    TuiConf,
    tuiwrapper,
)


@tuiwrapper
def main(pm: PortMan) -> TuiConf:
    the_scarlett = Scarlett()
    mixer = the_scarlett.switch_mix("A", 1)
    v = mixer.get()
    print(v)
    mixer.set(not v)
    assert mixer.get() != v

    raise SystemExit


if __name__ == "__main__":
    main()
