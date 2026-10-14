"""MIDI input via python-rtmidi. A thread (or callback) relays MIDI into the
engine event queue. Also exposes a list of detected ports so the UI can pick
one without a restart.
"""
from __future__ import annotations

try:
    import rtmidi
    _HAS_RTMIDI = True
except Exception:
    _HAS_RTMIDI = False


class MidiInput:
    def __init__(self, engine):
        self.engine = engine
        self._port: rtmidi.MidiIn | None = None
        self.port_name: str | None = None
        self.ports: list[str] = []
        self.error: str | None = None
        if _HAS_RTMIDI:
            try:
                self._probe()
            except Exception as exc:
                self.error = str(exc)
        else:
            self.error = "python-rtmidi not installed"

    def _probe(self):
        m = rtmidi.MidiIn()
        self.ports = [m.get_port_name(i) for i in range(m.get_port_count())]
        m.close_port()

    def available(self) -> bool:
        return _HAS_RTMIDI and self.error is None

    def open(self, index: int | None = None) -> bool:
        if not self.available():
            return False
        index = 0 if index is None else index
        if index >= len(self.ports):
            return False
        self.close()
        try:
            self._port = rtmidi.MidiIn()
            self._port.set_callback(self._callback)
            self._port.open_port(index)
            self.port_name = self.ports[index]
            return True
        except Exception as exc:
            self.error = str(exc)
            self._port = None
            return False

    def close(self):
        if self._port is not None:
            try:
                self._port.close_port()
            except Exception:
                pass
            self._port = None
            self.port_name = None

    def _callback(self, event, data=None):
        msgs, _ts = event
        for raw in msgs:
            if not raw:
                continue
            status = raw[0]
            kind = status & 0xF0
            if kind == 0x90 and status >> 4 != 0xF:
                note, vel = raw[1], raw[2] if len(raw) > 2 else 0
                if vel > 0:
                    self.engine.push("note_on", note, vel / 127.0)
                else:
                    self.engine.push("note_off", note)
            elif kind == 0x80:
                note = raw[1]
                self.engine.push("note_off", note)
            elif kind == 0xB0:
                cc, val = raw[1], raw[2]
                if cc == 64:
                    self.engine.push("sustain", val >= 64)
                elif cc == 123 or cc == 120:
                    self.engine.push("panic")