"""
Dual Audio Router — Hallmark Cobalt workbench desktop UI.

Design: macrostructure Workbench + theme Cobalt (modern-minimal / dev-tool).
Cool paper, hairline panels, one cobalt signal accent, graphite activity log.
"""

from __future__ import annotations

import queue
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
import pyaudiowpatch as pyaudio

from dual_audio_router import __version__
from dual_audio_router.core import (
    AudioRouter,
    DeviceSnapshot,
    RoutingError,
    format_device_option,
    is_wasapi_device,
    refresh_devices,
)
from dual_audio_router.tokens import TOKENS

SETUP_STEPS = [
    "Set Windows default output to laptop speakers (not Bluetooth).",
    "Mute speakers to 0% — listen only on the routed headphones.",
    "Connect two BT headphones; keep neither as default.",
    "Pick WASAPI devices matching the capture sample rate.",
]


class DualAudioRouterApp(ctk.CTk):
    _STACK_BREAKPOINT = 760
    _NARROW_BREAKPOINT = 640

    def __init__(self) -> None:
        super().__init__()
        self._apply_theme()

        self.title(f"Dual Audio Router")
        self.minsize(520, 560)
        self.geometry("860x680")
        self.configure(fg_color=TOKENS.paper)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._stacked_layout = False
        self._narrow_actions = False
        self._workbench_grid: ctk.CTkFrame | None = None
        self._setup_panel: ctk.CTkFrame | None = None
        self._controls_panel: ctk.CTkFrame | None = None
        self._action_bar: ctk.CTkFrame | None = None
        self._action_left: ctk.CTkFrame | None = None
        self._action_right: ctk.CTkFrame | None = None
        self._step_labels: list[ctk.CTkLabel] = []
        self._meta_value_labels: list[ctk.CTkLabel] = []

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._router = AudioRouter(
            on_log=self._enqueue_log,
            on_stopped=lambda: self.after(0, self._on_router_stopped),
        )
        self._pyaudio = pyaudio.PyAudio()
        self._snapshot: DeviceSnapshot | None = None
        self._device_by_label: dict[str, dict[str, Any]] = {}

        self._build_ui()
        self.bind("<Configure>", self._on_window_configure)
        self.after_idle(self._apply_responsive_layout)
        self._refresh_devices()
        self._poll_log_queue()

    def _apply_theme(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        ctk.set_widget_scaling(1.0)

    def _font_display(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(family=TOKENS.font_display[0], size=size, weight=weight)

    def _font_body(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(family=TOKENS.font_body[0], size=size, weight=weight)

    def _font_mono(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(family=TOKENS.font_mono[0], size=size, weight=weight)

    def _panel(self, parent: ctk.CTkBaseClass, **kwargs: Any) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=TOKENS.paper,
            border_color=TOKENS.rule,
            border_width=1,
            corner_radius=TOKENS.radius_sm,
            **kwargs,
        )

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)

        self._build_nav()
        self._build_workbench()
        self._build_action_bar()
        self._build_log_panel()

    def _build_nav(self) -> None:
        nav = ctk.CTkFrame(self, fg_color=TOKENS.paper, corner_radius=0, height=56)
        nav.grid(row=0, column=0, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        nav.grid_propagate(False)

        bottom_rule = ctk.CTkFrame(nav, fg_color=TOKENS.rule, height=1, corner_radius=0)
        bottom_rule.place(relx=0, rely=1, relwidth=1, anchor="sw")

        ctk.CTkLabel(
            nav,
            text="Dual Audio Router",
            font=self._font_display(18, "bold"),
            text_color=TOKENS.ink,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=14)

        meta = ctk.CTkFrame(nav, fg_color="transparent")
        meta.grid(row=0, column=1, sticky="e", padx=20, pady=10)

        ctk.CTkLabel(
            meta,
            text=f"v{__version__}",
            font=self._font_mono(11),
            text_color=TOKENS.ink_3,
        ).pack(side="left", padx=(0, 12))

        self._status_chip = ctk.CTkLabel(
            meta,
            text="READY",
            font=self._font_mono(11, "bold"),
            text_color=TOKENS.ink_3,
            fg_color=TOKENS.paper_2,
            corner_radius=TOKENS.radius_sm,
            width=96,
            height=28,
        )
        self._status_chip.pack(side="left")

    def _build_workbench(self) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=20, pady=(16, 8))
        body.grid_columnconfigure(0, weight=1)

        eyebrow = ctk.CTkLabel(
            body,
            text="WINDOWS AUDIO ROUTING",
            font=self._font_mono(11),
            text_color=TOKENS.accent,
        )
        eyebrow.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._headline = ctk.CTkLabel(
            body,
            text="Route system audio to two Bluetooth headphones",
            font=self._font_display(22, "bold"),
            text_color=TOKENS.ink,
            anchor="w",
            wraplength=760,
            justify="left",
        )
        self._headline.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self._workbench_grid = ctk.CTkFrame(body, fg_color="transparent")
        self._workbench_grid.grid(row=2, column=0, sticky="ew")
        self._workbench_grid.grid_columnconfigure(0, weight=2)
        self._workbench_grid.grid_columnconfigure(1, weight=3)

        self._setup_panel = self._build_setup_panel(self._workbench_grid)
        self._controls_panel = self._build_controls_panel(self._workbench_grid)

    def _build_setup_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        panel = self._panel(parent)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="SETUP",
            font=self._font_mono(11, "bold"),
            text_color=TOKENS.ink_3,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        steps = ctk.CTkFrame(panel, fg_color="transparent")
        steps.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        steps.grid_columnconfigure(0, weight=1)
        for i, step in enumerate(SETUP_STEPS, start=1):
            step_label = ctk.CTkLabel(
                steps,
                text=f"{i}. {step}",
                font=self._font_body(13),
                text_color=TOKENS.ink_2,
                anchor="w",
                justify="left",
                wraplength=300,
            )
            step_label.grid(row=i - 1, column=0, sticky="ew", pady=3)
            self._step_labels.append(step_label)

        ctk.CTkFrame(panel, fg_color=TOKENS.rule, height=1, corner_radius=0).grid(
            row=2, column=0, sticky="ew", padx=16, pady=4
        )

        ctk.CTkLabel(
            panel,
            text="CAPTURE",
            font=self._font_mono(11, "bold"),
            text_color=TOKENS.ink_3,
        ).grid(row=3, column=0, sticky="w", padx=16, pady=(12, 6))

        self._default_label = self._meta_row(panel, 4, "Default output")
        self._loopback_label = self._meta_row(panel, 5, "Loopback tap")
        self._rate_label = self._meta_row(panel, 6, "Sample rate")
        self._meta_value_labels.extend(
            [self._default_label, self._loopback_label, self._rate_label]
        )
        return panel

    def _meta_row(self, parent: ctk.CTkFrame, row: int, label: str) -> ctk.CTkLabel:
        ctk.CTkLabel(
            parent,
            text=label,
            font=self._font_mono(11),
            text_color=TOKENS.ink_3,
            width=110,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=16, pady=3)
        value = ctk.CTkLabel(
            parent,
            text="—",
            font=self._font_body(13),
            text_color=TOKENS.ink,
            anchor="w",
            wraplength=280,
            justify="left",
        )
        value.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=3)
        parent.grid_columnconfigure(1, weight=1)
        return value

    def _build_controls_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        panel = self._panel(parent)
        panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        panel.grid_columnconfigure(0, weight=0)
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="OUTPUTS",
            font=self._font_mono(11, "bold"),
            text_color=TOKENS.ink_3,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 10))

        ctk.CTkLabel(
            panel,
            text="Headphone 1",
            font=self._font_body(13),
            text_color=TOKENS.ink_2,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=8)
        self._combo_a = ctk.CTkComboBox(
            panel,
            state="readonly",
            font=self._font_body(13),
            dropdown_font=self._font_body(13),
            border_color=TOKENS.rule,
            button_color=TOKENS.paper_2,
            button_hover_color=TOKENS.rule,
            fg_color=TOKENS.paper,
            text_color=TOKENS.ink,
            corner_radius=TOKENS.radius_sm,
        )
        self._combo_a.grid(row=1, column=1, sticky="ew", padx=(8, 16), pady=8)

        ctk.CTkLabel(
            panel,
            text="Headphone 2",
            font=self._font_body(13),
            text_color=TOKENS.ink_2,
        ).grid(row=2, column=0, sticky="w", padx=16, pady=8)
        self._combo_b = ctk.CTkComboBox(
            panel,
            state="readonly",
            font=self._font_body(13),
            dropdown_font=self._font_body(13),
            border_color=TOKENS.rule,
            button_color=TOKENS.paper_2,
            button_hover_color=TOKENS.rule,
            fg_color=TOKENS.paper,
            text_color=TOKENS.ink,
            corner_radius=TOKENS.radius_sm,
        )
        self._combo_b.grid(row=2, column=1, sticky="ew", padx=(8, 16), pady=8)
        return panel

    def _build_action_bar(self) -> None:
        self._action_bar = self._panel(self)
        self._action_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        self._action_bar.grid_columnconfigure(0, weight=1)
        self._action_bar.grid_columnconfigure(1, weight=0)

        self._action_left = ctk.CTkFrame(self._action_bar, fg_color="transparent")
        self._action_left.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self._action_left.grid_columnconfigure(0, weight=1)

        self._action_right = ctk.CTkFrame(self._action_bar, fg_color="transparent")
        self._action_right.grid(row=0, column=1, sticky="e", padx=12, pady=12)
        self._action_right.grid_columnconfigure(0, weight=1)
        self._action_right.grid_columnconfigure(1, weight=1)

        self._refresh_btn = ctk.CTkButton(
            self._action_left,
            text="Refresh devices",
            command=self._refresh_devices,
            font=self._font_body(13),
            fg_color=TOKENS.paper_2,
            hover_color=TOKENS.rule,
            text_color=TOKENS.ink,
            border_color=TOKENS.rule,
            border_width=1,
            corner_radius=TOKENS.radius_sm,
            height=36,
        )
        self._refresh_btn.grid(row=0, column=0, sticky="ew")

        self._start_btn = ctk.CTkButton(
            self._action_right,
            text="Start routing",
            command=self._start_routing,
            font=self._font_body(13, "bold"),
            fg_color=TOKENS.accent,
            hover_color=TOKENS.accent_hover,
            text_color=TOKENS.accent_ink,
            corner_radius=TOKENS.radius_sm,
            height=36,
            width=140,
        )
        self._start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            self._action_right,
            text="Stop",
            command=self._stop_routing,
            state="disabled",
            font=self._font_body(13, "bold"),
            fg_color=TOKENS.danger,
            hover_color=TOKENS.danger_hover,
            text_color=TOKENS.accent_ink,
            corner_radius=TOKENS.radius_sm,
            height=36,
            width=100,
        )
        self._stop_btn.grid(row=0, column=1, sticky="ew")

    def _on_window_configure(self, event: Any) -> None:
        if event.widget is not self:
            return
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        width = max(self.winfo_width(), 1)
        content_width = max(width - 40, 280)

        self._headline.configure(wraplength=content_width)

        setup_wrap = max(int(content_width * 0.45), 220) if width >= self._STACK_BREAKPOINT else content_width - 32
        meta_wrap = max(setup_wrap - 130, 160)
        for label in self._step_labels:
            label.configure(wraplength=setup_wrap)
        for label in self._meta_value_labels:
            label.configure(wraplength=meta_wrap)

        stacked = width < self._STACK_BREAKPOINT
        if stacked != self._stacked_layout and self._workbench_grid and self._setup_panel and self._controls_panel:
            self._stacked_layout = stacked
            if stacked:
                self._workbench_grid.grid_columnconfigure(0, weight=1)
                self._workbench_grid.grid_columnconfigure(1, weight=0)
                self._setup_panel.grid(
                    row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8)
                )
                self._controls_panel.grid(
                    row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0
                )
            else:
                self._workbench_grid.grid_columnconfigure(0, weight=2)
                self._workbench_grid.grid_columnconfigure(1, weight=3)
                self._setup_panel.grid(
                    row=0, column=0, columnspan=1, sticky="nsew", padx=(0, 8), pady=0
                )
                self._controls_panel.grid(
                    row=0, column=1, columnspan=1, sticky="nsew", padx=(8, 0), pady=0
                )

        narrow = width < self._NARROW_BREAKPOINT
        if narrow != self._narrow_actions and self._action_bar and self._action_left and self._action_right:
            self._narrow_actions = narrow
            if narrow:
                self._action_bar.grid_columnconfigure(0, weight=1)
                self._action_bar.grid_columnconfigure(1, weight=0)
                self._action_left.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 0))
                self._action_right.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 12))
                self._start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
                self._stop_btn.grid(row=0, column=1, sticky="ew", padx=0)
            else:
                self._action_bar.grid_columnconfigure(0, weight=1)
                self._action_bar.grid_columnconfigure(1, weight=0)
                self._action_left.grid(row=0, column=0, columnspan=1, sticky="ew", padx=12, pady=12)
                self._action_right.grid(row=0, column=1, columnspan=1, sticky="e", padx=12, pady=12)
                self._start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
                self._stop_btn.grid(row=0, column=1, sticky="ew", padx=0)

    def _build_log_panel(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=3, column=0, sticky="nsew", padx=20, pady=(8, 20))
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            wrap,
            text="ACTIVITY LOG",
            font=self._font_mono(11, "bold"),
            text_color=TOKENS.ink_3,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        log_shell = ctk.CTkFrame(
            wrap,
            fg_color=TOKENS.graphite,
            border_color=TOKENS.rule_2,
            border_width=1,
            corner_radius=TOKENS.radius_md,
        )
        log_shell.grid(row=1, column=0, sticky="nsew")
        log_shell.grid_columnconfigure(0, weight=1)
        log_shell.grid_rowconfigure(0, weight=1)

        self._log_box = ctk.CTkTextbox(
            log_shell,
            font=self._font_mono(12),
            fg_color=TOKENS.graphite,
            text_color=TOKENS.graphite_ink,
            border_width=0,
            corner_radius=TOKENS.radius_md,
            wrap="word",
            activate_scrollbars=True,
        )
        self._log_box.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self._log_box.configure(state="disabled")

    def _set_status(self, label: str, running: bool = False) -> None:
        if running:
            self._status_chip.configure(
                text="ROUTING",
                text_color=TOKENS.accent_ink,
                fg_color=TOKENS.accent,
            )
        else:
            self._status_chip.configure(
                text=label.upper(),
                text_color=TOKENS.ink_3 if label == "Ready" else TOKENS.ink_2,
                fg_color=TOKENS.paper_2,
            )

    def _append_log(self, message: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _enqueue_log(self, message: str) -> None:
        self._log_queue.put(message)

    def _poll_log_queue(self) -> None:
        while True:
            try:
                self._append_log(self._log_queue.get_nowait())
            except queue.Empty:
                break
        self.after(100, self._poll_log_queue)

    def _set_routing_ui(self, running: bool) -> None:
        combo_state = "disabled" if running else "readonly"
        self._combo_a.configure(state=combo_state)
        self._combo_b.configure(state=combo_state)
        self._refresh_btn.configure(state="disabled" if running else "normal")
        self._start_btn.configure(state="disabled" if running else "normal")
        self._stop_btn.configure(state="normal" if running else "disabled")
        self._set_status("Routing" if running else "Ready", running=running)

    def _refresh_devices(self) -> None:
        if self._router.is_running:
            return

        try:
            self._snapshot = refresh_devices(self._pyaudio)
        except OSError as exc:
            messagebox.showerror("WASAPI unavailable", str(exc), parent=self)
            return
        except LookupError as exc:
            messagebox.showerror("Loopback not found", str(exc), parent=self)
            return

        status = self._snapshot.loopback_status
        lb = status.loopback
        default = status.default_output

        self._default_label.configure(
            text=f"[{default['index']}] {default['name']}"
        )
        self._loopback_label.configure(text=f"[{lb['index']}] {lb['name']}")
        self._rate_label.configure(text=f"{int(lb['defaultSampleRate'])} Hz")

        labels: list[str] = []
        self._device_by_label.clear()
        for info in self._snapshot.output_choices:
            label = format_device_option(info, wasapi=is_wasapi_device(self._pyaudio, info))
            labels.append(label)
            self._device_by_label[label] = info

        self._combo_a.configure(values=labels)
        self._combo_b.configure(values=labels)
        if labels:
            self._combo_a.set(labels[0])
        if len(labels) >= 2:
            self._combo_b.set(labels[1])

        for warning in status.warnings:
            self._enqueue_log(f"warn · {warning}")
        self._enqueue_log(f"info · found {len(labels)} output device(s)")

    def _selected_device(self, combo: ctk.CTkComboBox) -> dict[str, Any] | None:
        return self._device_by_label.get(combo.get())

    def _start_routing(self) -> None:
        out_a = self._selected_device(self._combo_a)
        out_b = self._selected_device(self._combo_b)

        if out_a is None or out_b is None:
            messagebox.showwarning("Select devices", "Choose two output devices.", parent=self)
            return
        if out_a["index"] == out_b["index"]:
            messagebox.showwarning(
                "Select devices", "Choose two different devices.", parent=self
            )
            return

        self._set_routing_ui(True)
        try:
            self._router.start(out_a, out_b)
        except RoutingError as exc:
            self._set_routing_ui(False)
            messagebox.showerror("Cannot start", "\n".join(exc.messages), parent=self)
        except Exception as exc:
            self._set_routing_ui(False)
            messagebox.showerror("Error", str(exc), parent=self)

    def _stop_routing(self) -> None:
        self._router.stop()
        self._set_routing_ui(False)

    def _on_router_stopped(self) -> None:
        if not self._router.is_running:
            self._set_routing_ui(False)
            self._set_status("Stopped")

    def _on_close(self) -> None:
        if self._router.is_running:
            self._router.stop()
        try:
            self._pyaudio.terminate()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    app = DualAudioRouterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
