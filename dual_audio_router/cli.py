"""Optional command-line interface for Dual Audio Router."""

from __future__ import annotations

import sys

import pyaudiowpatch as pyaudio

from dual_audio_router.core import (
    AudioRouter,
    RoutingError,
    collect_routing_errors,
    collect_sample_rate_warnings,
    device_role,
    format_device_option,
    is_wasapi_device,
    refresh_devices,
)


def print_setup_instructions() -> None:
    print("\n" + "=" * 72)
    print("BEFORE YOU START — required Windows setup (prevents echo)")
    print("=" * 72)
    print(
        "1. Set DEFAULT playback to Laptop Speakers (not Bluetooth).\n"
        "2. Mute laptop speakers to 0%.\n"
        "3. Connect two BT headphones — do NOT set either as default.\n"
    )


def _print_devices(snapshot) -> None:
    devices = snapshot.all_devices
    print(f"\nAudio devices ({len(devices)} total):")
    for info in devices:
        print(
            f"  [{info['index']}] {device_role(info):<8} "
            f"{info['defaultSampleRate']:.0f} Hz  {info['name']}"
        )


def _pick_index(p, snapshot, prompt: str) -> dict:
    choices = snapshot.output_choices
    print("\nOutputs (WASAPI / rate-sorted):")
    for info in choices:
        label = format_device_option(info, wasapi=is_wasapi_device(p, info))
        print(f"  {label}")
    while True:
        raw = input(prompt).strip()
        try:
            index = int(raw)
        except ValueError:
            print("  Enter a device index from the list.")
            continue
        for info in choices:
            if info["index"] == index:
                return info
        print(f"  No output device with index {index}.")


def main() -> None:
    print_setup_instructions()
    p = pyaudio.PyAudio()
    router = AudioRouter(on_log=print)

    try:
        snapshot = refresh_devices(p)
        _print_devices(snapshot)
        for warning in snapshot.loopback_status.warnings:
            print(f"WARNING: {warning}")

        out_a = _pick_index(p, snapshot, "First headphone index: ")
        out_b = _pick_index(p, snapshot, "Second headphone index: ")

        errors = collect_routing_errors(p, snapshot.loopback_status.loopback, out_a, out_b)
        if errors:
            raise RoutingError(errors)

        for warning in collect_sample_rate_warnings(
            snapshot.loopback_status.loopback, out_a, out_b
        ):
            print(f"WARNING: {warning}")

        router.start(out_a, out_b)
        try:
            router.wait_until_stopped()
        except KeyboardInterrupt:
            print("\nCtrl+C received.")
        finally:
            router.stop()
    except RoutingError as exc:
        print("\nCannot start:")
        for msg in exc.messages:
            print(f"  - {msg}")
        sys.exit(1)
    finally:
        p.terminate()


if __name__ == "__main__":
    main()
