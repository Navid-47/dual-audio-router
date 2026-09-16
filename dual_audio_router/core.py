"""
Audio routing engine — WASAPI loopback capture fan-out to two outputs.

Used by both the desktop GUI and the optional CLI.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import pyaudiowpatch as pyaudio

CHUNK_SIZE = 4096
PRIME_BUFFER_COUNT = 3
AUDIO_FORMAT = pyaudio.paInt16

LogCallback = Callable[[str], None]


class RoutingError(Exception):
    """Validation or stream-open failure with user-facing messages."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("\n".join(messages))


@dataclass
class LoopbackStatus:
    loopback: dict[str, Any]
    default_output: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass
class DeviceSnapshot:
    all_devices: list[dict[str, Any]]
    loopback_status: LoopbackStatus
    output_choices: list[dict[str, Any]]


def device_base_name(name: str) -> str:
    return name.replace(" [Loopback]", "").strip()


def names_same_device(name_a: str, name_b: str) -> bool:
    a = device_base_name(name_a).casefold()
    b = device_base_name(name_b).casefold()
    return a == b or a in b or b in a


def device_role(info: dict[str, Any]) -> str:
    if info.get("isLoopbackDevice"):
        return "loopback"
    if info["maxInputChannels"] > 0 and info["maxOutputChannels"] > 0:
        return "duplex"
    if info["maxInputChannels"] > 0:
        return "input"
    if info["maxOutputChannels"] > 0:
        return "output"
    return "unknown"


def is_wasapi_device(p: pyaudio.PyAudio, info: dict[str, Any]) -> bool:
    try:
        wasapi_index = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    except OSError:
        return False
    return info["hostApi"] == wasapi_index


def format_device_option(info: dict[str, Any], *, wasapi: bool) -> str:
    api = "WASAPI" if wasapi else "other"
    rate = int(info["defaultSampleRate"])
    return f"[{info['index']}] {info['name']} ({rate} Hz, {api})"


def enumerate_devices(p: pyaudio.PyAudio) -> list[dict[str, Any]]:
    return [p.get_device_info_by_index(i) for i in range(p.get_device_count())]


def get_default_wasapi_output(p: pyaudio.PyAudio) -> dict[str, Any]:
    return p.get_default_wasapi_device(d_out=True)


def get_loopback_status(p: pyaudio.PyAudio) -> LoopbackStatus:
    default_out = get_default_wasapi_output(p)
    loopback = p.get_default_wasapi_loopback()
    warnings: list[str] = []

    captured = device_base_name(loopback["name"])
    default_name = device_base_name(default_out["name"])

    if names_same_device(default_name, captured):
        bt_like = any(
            token in default_name.casefold()
            for token in ("headphone", "headset", "earphone", "buds", "airpods")
        )
        if bt_like:
            warnings.append(
                "Windows default output is a Bluetooth device. Set default to "
                "Laptop Speakers (muted) to avoid echo."
            )
    else:
        warnings.append(
            "Default output name does not match loopback source — confirm Sound settings."
        )

    return LoopbackStatus(loopback=loopback, default_output=default_out, warnings=warnings)


def list_output_choices(p: pyaudio.PyAudio, devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    loopback_rate = int(get_loopback_status(p).loopback["defaultSampleRate"])
    outputs = [d for d in devices if d["maxOutputChannels"] > 0 and not d.get("isLoopbackDevice")]

    def sort_key(info: dict[str, Any]) -> tuple[int, int, str]:
        wasapi = is_wasapi_device(p, info)
        rate_match = int(info["defaultSampleRate"]) == loopback_rate
        return (0 if wasapi else 1, 0 if rate_match else 1, info["name"].casefold())

    return sorted(outputs, key=sort_key)


def refresh_devices(p: pyaudio.PyAudio) -> DeviceSnapshot:
    all_devices = enumerate_devices(p)
    loopback_status = get_loopback_status(p)
    output_choices = list_output_choices(p, all_devices)
    return DeviceSnapshot(
        all_devices=all_devices,
        loopback_status=loopback_status,
        output_choices=output_choices,
    )


def collect_routing_errors(
    p: pyaudio.PyAudio,
    loopback: dict[str, Any],
    out_a: dict[str, Any],
    out_b: dict[str, Any],
) -> list[str]:
    default_out = get_default_wasapi_output(p)
    captured_from = device_base_name(loopback["name"])
    errors: list[str] = []

    if names_same_device(device_base_name(out_a["name"]), device_base_name(out_b["name"])):
        errors.append(
            "Both outputs appear to be the same physical device. "
            "Pick two different Bluetooth headphones."
        )

    for out, label in ((out_a, "A"), (out_b, "B")):
        out_name = device_base_name(out["name"])

        if names_same_device(out_name, captured_from):
            errors.append(
                f"Output {label} is the loopback capture device — causes feedback/echo."
            )

        if names_same_device(out_name, device_base_name(default_out["name"])):
            errors.append(
                f"Output {label} is the Windows default device — causes double playback/echo."
            )

        try:
            out_loopback = p.get_wasapi_loopback_analogue_by_dict(out)
            if out_loopback["index"] == loopback["index"]:
                errors.append(f"Output {label} is re-captured by loopback (feedback loop).")
        except ValueError:
            pass

    return errors


def collect_sample_rate_warnings(
    loopback: dict[str, Any], out_a: dict[str, Any], out_b: dict[str, Any]
) -> list[str]:
    src_rate = int(loopback["defaultSampleRate"])
    warnings: list[str] = []
    for out, label in ((out_a, "A"), (out_b, "B")):
        out_rate = int(out["defaultSampleRate"])
        if out_rate != src_rate:
            warnings.append(
                f"Output {label} reports {out_rate} Hz but loopback is {src_rate} Hz."
            )
    return warnings


def _stream_params_from_loopback(loopback: dict[str, Any]) -> dict[str, Any]:
    channels = loopback["maxInputChannels"]
    rate = int(loopback["defaultSampleRate"])
    if channels < 1:
        raise RoutingError(["Loopback device reports 0 input channels."])
    return {"format": AUDIO_FORMAT, "channels": channels, "rate": rate}


def _silence_chunk(channels: int) -> bytes:
    return b"\x00" * (CHUNK_SIZE * channels * 2)


def _prime_output_buffers(stream_a: Any, stream_b: Any, channels: int) -> None:
    silence = _silence_chunk(channels)
    for _ in range(PRIME_BUFFER_COUNT):
        stream_a.write(silence)
        stream_b.write(silence)


def _write_chunk(stream: Any, chunk: bytes) -> None:
    stream.write(chunk, CHUNK_SIZE)


def _open_with_debug(open_fn: Callable[[], Any], device: dict[str, Any], label: str) -> Any:
    try:
        return open_fn()
    except Exception as exc:
        lines = [
            f"Failed to open {label} on device {device['index']}: {exc}",
            "Device info:",
        ]
        for key, value in sorted(device.items()):
            lines.append(f"  {key}: {value}")
        raise RoutingError(lines) from exc


class AudioRouter:
    """Background audio router — start() runs on a worker thread; stop() tears down."""

    def __init__(
        self,
        on_log: LogCallback | None = None,
        on_stopped: Callable[[], None] | None = None,
    ) -> None:
        self._on_log = on_log or (lambda _msg: None)
        self._on_stopped = on_stopped or (lambda: None)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._p: pyaudio.PyAudio | None = None
        self._input_stream: Any | None = None
        self._stream_a: Any | None = None
        self._stream_b: Any | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def log(self, message: str) -> None:
        self._on_log(message)

    def start(self, out_a: dict[str, Any], out_b: dict[str, Any]) -> None:
        if self._running:
            raise RoutingError(["Routing is already running."])

        self._stop_event.clear()
        self._p = pyaudio.PyAudio()
        snapshot = refresh_devices(self._p)
        loopback = snapshot.loopback_status.loopback

        errors = collect_routing_errors(self._p, loopback, out_a, out_b)
        if errors:
            self._cleanup_pyaudio()
            raise RoutingError(errors)

        for warning in collect_sample_rate_warnings(loopback, out_a, out_b):
            self.log(f"Warning: {warning}")

        params = _stream_params_from_loopback(loopback)
        self.log(
            f"Opening streams: {params['channels']} ch, {params['rate']} Hz, "
            f"buffer={CHUNK_SIZE}"
        )

        self._input_stream = _open_with_debug(
            lambda: self._p.open(
                format=params["format"],
                channels=params["channels"],
                rate=params["rate"],
                frames_per_buffer=CHUNK_SIZE,
                input=True,
                input_device_index=loopback["index"],
            ),
            loopback,
            "loopback input",
        )
        self._stream_a = _open_with_debug(
            lambda: self._p.open(
                format=params["format"],
                channels=params["channels"],
                rate=params["rate"],
                frames_per_buffer=CHUNK_SIZE,
                output=True,
                output_device_index=out_a["index"],
            ),
            out_a,
            "output A",
        )
        self._stream_b = _open_with_debug(
            lambda: self._p.open(
                format=params["format"],
                channels=params["channels"],
                rate=params["rate"],
                frames_per_buffer=CHUNK_SIZE,
                output=True,
                output_device_index=out_b["index"],
            ),
            out_b,
            "output B",
        )
        _prime_output_buffers(self._stream_a, self._stream_b, params["channels"])

        self._running = True
        self._thread = threading.Thread(
            target=self._route_loop,
            args=(out_a, out_b),
            name="dual-audio-route",
            daemon=True,
        )
        self._thread.start()
        self.log("Routing started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._close_streams()
        self._cleanup_pyaudio()
        self._running = False
        self.log("Routing stopped.")

    def _route_loop(self, out_a: dict[str, Any], out_b: dict[str, Any]) -> None:
        a_alive = True
        b_alive = True
        error_lock = threading.Lock()

        def mark_dead(label: str, out: dict[str, Any], exc: Exception) -> None:
            nonlocal a_alive, b_alive
            with error_lock:
                if label == "A":
                    a_alive = False
                else:
                    b_alive = False
                self.log(
                    f"Output {label} [{out['index']}] failed — other continues. ({exc})"
                )

        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="audio-out") as pool:
                while not self._stop_event.is_set():
                    audio_chunk = self._input_stream.read(
                        CHUNK_SIZE, exception_on_overflow=False
                    )
                    pending: list[tuple[str, dict[str, Any], Any]] = []
                    if a_alive:
                        pending.append(
                            ("A", out_a, pool.submit(_write_chunk, self._stream_a, audio_chunk))
                        )
                    if b_alive:
                        pending.append(
                            ("B", out_b, pool.submit(_write_chunk, self._stream_b, audio_chunk))
                        )
                    for label, out, future in pending:
                        try:
                            future.result()
                        except Exception as exc:
                            mark_dead(label, out, exc)
                    if not a_alive and not b_alive:
                        self.log("Both outputs failed. Stopping.")
                        break
        except Exception as exc:
            if not self._stop_event.is_set():
                self.log(f"Routing error: {exc}")
        finally:
            self._running = False
            self._on_stopped()

    def wait_until_stopped(self) -> None:
        if self._thread is not None:
            self._thread.join()

    def _close_streams(self) -> None:
        for stream in (self._input_stream, self._stream_a, self._stream_b):
            if stream is not None:
                try:
                    if stream.is_active():
                        stream.stop_stream()
                    stream.close()
                except Exception as exc:
                    self.log(f"Warning closing stream: {exc}")
        self._input_stream = None
        self._stream_a = None
        self._stream_b = None

    def _cleanup_pyaudio(self) -> None:
        if self._p is not None:
            try:
                self._p.terminate()
            except Exception as exc:
                self.log(f"Warning terminating PyAudio: {exc}")
            self._p = None
