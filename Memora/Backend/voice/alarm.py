import winsound


class Alarm:
    """
    Plays a simple beep sound. Used to signal transitions,
    e.g. "moving to the next person".
    """

    def beep(self, frequency=1000, duration_ms=300):
        winsound.MessageBeep(frequency, duration_ms)