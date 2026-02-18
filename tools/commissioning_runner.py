#!/usr/bin/env python3
"""
Semi-automatic commissioning runner for tumbller_v06_nano_balance_v2.

Usage:
  python3 tools/commissioning_runner.py --port /dev/cu.usbserial-2210
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

try:
    import serial
except ImportError as exc:
    print("ERROR: pyserial is required. Install with: pip install pyserial")
    raise SystemExit(2) from exc


@dataclass
class CsvSample:
    ms: int
    mode: int
    estop: int
    setpoint: float
    angle: float
    accel: float
    gyro: float
    pid: float
    motion: float
    wspd: float
    wpos: float
    cmd_l: float
    cmd_r: float
    enc_l: int
    enc_r: int
    vol: int
    kp: float
    ki: float
    kd: float
    kv: float
    kx: float
    q_a: float
    q_b: float
    r_m: float

    @staticmethod
    def from_csv_line(line: str) -> "CsvSample":
        p = [x.strip() for x in line.split(",")]
        if len(p) < 25 or p[0] != "CSV":
            raise ValueError("not a valid CSV line")
        return CsvSample(
            ms=int(p[1]),
            mode=int(p[2]),
            estop=int(p[3]),
            setpoint=float(p[4]),
            angle=float(p[5]),
            accel=float(p[6]),
            gyro=float(p[7]),
            pid=float(p[8]),
            motion=float(p[9]),
            wspd=float(p[10]),
            wpos=float(p[11]),
            cmd_l=float(p[12]),
            cmd_r=float(p[13]),
            enc_l=int(float(p[14])),
            enc_r=int(float(p[15])),
            vol=int(float(p[16])),
            kp=float(p[17]),
            ki=float(p[18]),
            kd=float(p[19]),
            kv=float(p[20]),
            kx=float(p[21]),
            q_a=float(p[22]),
            q_b=float(p[23]),
            r_m=float(p[24]),
        )


class Runner:
    def __init__(self, port: str, baud: int, timeout: float = 0.1):
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.log_lines: List[str] = []

    def close(self) -> None:
        self.ser.close()

    def _readline(self, deadline: float) -> Optional[str]:
        while time.time() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if line:
                self.log_lines.append(line)
                return line
        return None

    def drain(self, seconds: float = 0.4) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            line = self._readline(deadline)
            if not line:
                break

    def send(self, cmd: str) -> None:
        self.ser.write((cmd + "\n").encode("utf-8"))
        self.ser.flush()

    def send_expect(self, cmd: str, contains: str, timeout: float = 2.0) -> str:
        self.send(cmd)
        deadline = time.time() + timeout
        while True:
            line = self._readline(deadline)
            if line is None:
                raise TimeoutError(f"Timed out waiting for '{contains}' after '{cmd}'")
            if contains in line:
                return line

    def read_until(self, predicate, timeout: float) -> str:
        deadline = time.time() + timeout
        while True:
            line = self._readline(deadline)
            if line is None:
                raise TimeoutError("Timed out waiting for condition")
            if predicate(line):
                return line

    def get_status(self) -> Dict[str, str]:
        self.send("GET")
        line = self.read_until(lambda s: s.startswith("STATUS "), timeout=2.0)
        tokens = line.split()
        out: Dict[str, str] = {}
        for t in tokens[1:]:
            if "=" in t:
                k, v = t.split("=", 1)
                out[k] = v
        return out

    def wait_ready(self, timeout: float = 8.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.get_status()
                return
            except Exception:
                self.drain(0.2)
                time.sleep(0.2)
        raise TimeoutError("Firmware did not become ready (no STATUS response)")


def load_cfg(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ask(msg: str, auto: bool = False, wait_s: float = 2.0) -> None:
    if auto:
        print(f"\n{msg}\nAuto mode: waiting {wait_s:.1f}s...")
        time.sleep(wait_s)
        return
    input(f"\n{msg}\nPress Enter when done...")


def apply_baseline(r: Runner, c: Dict) -> None:
    r.send("DISARM")
    # DISARM may be idempotent and produce no MODE line if already SAFE_IDLE.
    time.sleep(0.15)
    r.drain(0.3)
    r.send_expect("LOGCSV 0", "OK LOGCSV", timeout=2.0)
    r.send_expect("LOGT 0", "OK LOGT", timeout=2.0)
    r.send_expect("MOTOROFF", "OK MOTOROFF", timeout=2.0)
    hw = c.get("hardware", {})
    axis = hw.get("axis")
    if axis:
        r.send_expect(f"AXIS {axis}", "OK AXIS", timeout=2.0)
    if "swapaxis" in hw:
        r.send_expect(f"SWAPAXIS {1 if hw['swapaxis'] else 0}", "OK SWAPAXIS", timeout=2.0)
    if "imupol" in hw:
        r.send_expect(f"IMUPOL {int(hw['imupol'])}", "OK IMUPOL", timeout=2.0)
    if "motorpol" in hw:
        r.send_expect(f"MOTORPOL {int(hw['motorpol'])}", "OK MOTORPOL", timeout=2.0)
    encmode = hw.get("encmode")
    if encmode:
        r.send_expect(f"ENCMODE {encmode}", "OK ENCMODE", timeout=2.0)
    r.send_expect("CAL ZERO", "OK CAL ZERO", timeout=4.0)
    r.send_expect(f"SETPOINT {c['baseline']['setpoint']}", "OK SETPOINT", timeout=2.0)
    pid = c["baseline"]["pid"]
    r.send_expect(f"PID {pid[0]} {pid[1]} {pid[2]}", "OK PID", timeout=2.0)
    lim = c["baseline"]["limits"]
    r.send_expect(f"LIMITS {lim[0]} {lim[1]} {lim[2]}", "OK LIMITS", timeout=2.0)
    mot = c["baseline"]["motion"]
    r.send_expect(f"MOTION {mot[0]} {mot[1]}", "OK MOTION", timeout=2.0)
    r.send_expect("SAVECFG", "OK SAVECFG", timeout=2.0)


def motor_preflight(r: Runner) -> None:
    # Quick command-path sanity pulse (user observes movement).
    r.send("STATE SAFE")
    time.sleep(0.1)
    r.send_expect("MOTOR 120 120", "OK MOTOR", timeout=2.0)
    time.sleep(0.25)
    r.send_expect("MOTOROFF", "OK MOTOROFF", timeout=2.0)


def encoder_check(r: Runner, c: Dict, auto_prompts: bool = False) -> Dict[str, int]:
    pre = r.get_status()
    ask("SPIN LEFT WHEEL BY HAND FOR 2s (robot lifted)", auto_prompts, 2.0)
    left = r.get_status()
    ask("SPIN RIGHT WHEEL BY HAND FOR 2s (robot lifted)", auto_prompts, 2.0)
    right = r.get_status()

    pre_l = int(float(pre.get("encL", "0")))
    pre_r = int(float(pre.get("encR", "0")))
    left_l = int(float(left.get("encL", "0")))
    left_r = int(float(left.get("encR", "0")))
    right_l = int(float(right.get("encL", "0")))
    right_r = int(float(right.get("encR", "0")))

    dl_left = abs(left_l - pre_l)
    dr_left = abs(left_r - pre_r)
    dl_right = abs(right_l - left_l)
    dr_right = abs(right_r - left_r)

    min_edges = int(c["thresholds"]["encoder_min_edges"])
    encmode = str(c.get("hardware", {}).get("encmode", "AUTO")).upper()
    if encmode == "LEFT":
        ok_left_spin = dl_left >= min_edges
        ok_right_spin = True
    elif encmode == "RIGHT":
        ok_left_spin = dr_left >= min_edges
        ok_right_spin = True
    else:
        ok_left_spin = max(dl_left, dr_left) >= min_edges
        ok_right_spin = max(dl_right, dr_right) >= min_edges

    print("\nEncoder check:")
    print(f" left-spin delta: encL={dl_left} encR={dr_left}")
    print(f" right-spin delta: encL={dl_right} encR={dr_right}")
    print(f" mode={encmode} PASS left_spin={ok_left_spin} right_spin={ok_right_spin}")

    return {
        "dl_left": dl_left,
        "dr_left": dr_left,
        "dl_right": dl_right,
        "dr_right": dr_right,
        "ok": int(ok_left_spin and ok_right_spin),
    }


def motor_pulse_check(r: Runner, c: Dict) -> Dict[str, int]:
    t = c.get("thresholds", {})
    min_edges = int(t.get("motor_pulse_min_edges", 10))
    excitation_cfg = c.get("excitation", {})
    pulse_cmd = int(excitation_cfg.get("motor_cmd", 50))
    pulse_ms = int(excitation_cfg.get("hold_ms", 300))
    settle_ms = int(excitation_cfg.get("settle_ms", 120))

    pre = r.get_status()
    pre_l = int(float(pre.get("encL", "0")))
    pre_r = int(float(pre.get("encR", "0")))

    r.send("STATE SAFE")
    time.sleep(0.12)
    r.drain(0.15)
    r.send_expect(f"MOTOR {pulse_cmd} {pulse_cmd}", "OK MOTOR", timeout=2.0)
    time.sleep(max(0.0, pulse_ms * 0.001))
    r.send_expect("MOTOROFF", "OK MOTOROFF", timeout=2.0)
    time.sleep(max(0.0, settle_ms * 0.001))

    post = r.get_status()
    post_l = int(float(post.get("encL", "0")))
    post_r = int(float(post.get("encR", "0")))
    d_l = abs(post_l - pre_l)
    d_r = abs(post_r - pre_r)

    encmode = str(c.get("hardware", {}).get("encmode", "AUTO")).upper()
    if encmode == "LEFT":
        ok = d_l >= min_edges
    elif encmode == "RIGHT":
        ok = d_r >= min_edges
    else:
        ok = max(d_l, d_r) >= min_edges

    print("\nMotor pulse check:")
    print(f" pulse_cmd={pulse_cmd} hold_ms={pulse_ms} enc_deltaL={d_l} enc_deltaR={d_r}")
    print(f" mode={encmode} PASS motor_pulse={ok}")
    return {"d_l": d_l, "d_r": d_r, "ok": int(ok)}


def run_burst(r: Runner, c: Dict, auto_prompts: bool = False) -> List[CsvSample]:
    b = c["burst"]
    ask("Place robot in test posture (upright support), ready for burst capture", auto_prompts, 1.5)
    # Temporary commissioning aid: re-zero right before burst to reduce setup bias.
    r.send_expect("CAL ZERO", "OK CAL ZERO", timeout=4.0)
    r.send_expect(f"BURSTCSV {b['delay_ms']} {b['lines']}", "OK BURSTCSV", timeout=2.0)
    r.send("ARM")
    # If already ARMED this may not emit MODE line; continue regardless.
    time.sleep(0.15)
    r.drain(0.3)

    samples: List[CsvSample] = []
    tcfg = c["timeouts"]
    deadline = time.time() + tcfg["burst_total_s"]
    force_bal_after = float(tcfg.get("arm_to_bal_s", 2.0))
    arm_t0 = time.time()
    force_bal_sent = False
    while time.time() < deadline:
        if not force_bal_sent and (time.time() - arm_t0) > force_bal_after and len(samples) == 0:
            # If arming conditions are not met (e.g. not upright), force BAL once.
            r.send("STATE BAL")
            force_bal_sent = True
        line = r._readline(deadline)
        if line is None:
            continue
        if line.startswith("CSV,"):
            try:
                samples.append(CsvSample.from_csv_line(line))
            except Exception:
                pass
        if "BURSTCSV DONE" in line:
            break
        if "BURSTCSV CANCELED" in line or "MODE FAULT" in line:
            break

    if len(samples) == 0:
        print("No burst CSV captured. Running fallback timed capture...")
        fcfg = c.get("fallback_capture", {})
        fallback_s = float(fcfg.get("seconds", 3.0))
        r.send_expect("LOGCSV 1", "OK LOGCSV", timeout=2.0)
        r.send("STATE BAL")
        fb_deadline = time.time() + fallback_s
        while time.time() < fb_deadline:
            line = r._readline(fb_deadline)
            if line is None:
                continue
            if line.startswith("CSV,"):
                try:
                    samples.append(CsvSample.from_csv_line(line))
                except Exception:
                    pass
        r.send_expect("LOGCSV 0", "OK LOGCSV", timeout=2.0)

    r.send("DISARM")
    time.sleep(0.1)
    r.drain(0.3)
    return samples


def evaluate(samples: List[CsvSample], c: Dict) -> Dict[str, float]:
    if not samples:
        return {"ok": 0.0}
    abs_angles = [abs(s.angle) for s in samples]
    mean_abs = statistics.mean(abs_angles)
    max_abs = max(abs_angles)
    drift = abs(samples[-1].wpos - samples[0].wpos)
    estop_events = sum(1 for s in samples if s.estop != 0 or s.mode != 2)

    t = c["thresholds"]
    pass_mean = mean_abs <= t["mean_abs_angle_deg_max"]
    pass_peak = max_abs <= t["max_abs_angle_deg_max"]
    pass_drift = drift <= t["burst_drift_counts_max"]
    pass_mode = estop_events == 0

    ok = pass_mean and pass_peak and pass_drift and pass_mode
    return {
        "ok": 1.0 if ok else 0.0,
        "mean_abs_angle_deg": mean_abs,
        "max_abs_angle_deg": max_abs,
        "drift_counts": drift,
        "estop_or_mode_events": float(estop_events),
        "pass_mean": float(pass_mean),
        "pass_peak": float(pass_peak),
        "pass_drift": float(pass_drift),
        "pass_mode": float(pass_mode),
    }


def save_outputs(out_dir: Path, samples: List[CsvSample], metrics: Dict[str, float]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    csv_path = out_dir / f"run_{ts}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "ms",
                "mode",
                "estop",
                "setpoint",
                "angle",
                "accel",
                "gyro",
                "pid",
                "motion",
                "wspd",
                "wpos",
                "cmdL",
                "cmdR",
                "encL",
                "encR",
                "vol",
                "kp",
                "ki",
                "kd",
                "kv",
                "kx",
                "qA",
                "qB",
                "rM",
            ]
        )
        for s in samples:
            w.writerow(
                [
                    s.ms,
                    s.mode,
                    s.estop,
                    s.setpoint,
                    s.angle,
                    s.accel,
                    s.gyro,
                    s.pid,
                    s.motion,
                    s.wspd,
                    s.wpos,
                    s.cmd_l,
                    s.cmd_r,
                    s.enc_l,
                    s.enc_r,
                    s.vol,
                    s.kp,
                    s.ki,
                    s.kd,
                    s.kv,
                    s.kx,
                    s.q_a,
                    s.q_b,
                    s.r_m,
                ]
            )
    metrics_path = out_dir / f"metrics_{ts}.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nSaved: {csv_path}")
    print(f"Saved: {metrics_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--config",
        default="tests/commissioning_config.json",
        help="Path to config JSON",
    )
    ap.add_argument(
        "--out-dir",
        default="tests/results",
        help="Output directory for logs/reports",
    )
    ap.add_argument(
        "--auto-prompts",
        action="store_true",
        help="Do not block for prompts; wait fixed short durations instead",
    )
    args = ap.parse_args()

    cfg = load_cfg(Path(args.config))

    r = Runner(args.port, args.baud)
    try:
        print("Connected. Draining boot chatter...")
        r.drain(1.5)
        print("Waiting for firmware readiness...")
        r.wait_ready(timeout=20.0)

        print("\n[1/4] Applying baseline config...")
        apply_baseline(r, cfg)
        print("Running motor preflight pulse (visual check)...")
        motor_preflight(r)
        status = r.get_status()
        print("Status:", status)

        print("\n[2/5] Encoder integrity check...")
        enc = encoder_check(r, cfg, auto_prompts=args.auto_prompts)

        print("\n[3/5] Motor pulse validation...")
        pulse = motor_pulse_check(r, cfg)

        print("\n[4/5] Running burst capture...")
        samples = run_burst(r, cfg, auto_prompts=args.auto_prompts)
        print(f"Captured {len(samples)} CSV samples.")

        print("\n[5/5] Evaluating metrics...")
        metrics = evaluate(samples, cfg)
        metrics["enc_check_ok"] = float(enc["ok"])
        metrics["enc_dl_left"] = float(enc["dl_left"])
        metrics["enc_dr_left"] = float(enc["dr_left"])
        metrics["enc_dl_right"] = float(enc["dl_right"])
        metrics["enc_dr_right"] = float(enc["dr_right"])
        metrics["motor_pulse_ok"] = float(pulse["ok"])
        metrics["motor_pulse_dl"] = float(pulse["d_l"])
        metrics["motor_pulse_dr"] = float(pulse["d_r"])

        save_outputs(Path(args.out_dir), samples, metrics)

        print("\nCommissioning summary:")
        for k in sorted(metrics.keys()):
            print(f"  {k}: {metrics[k]}")
        if (
            metrics.get("ok", 0.0) >= 1.0
            and metrics.get("enc_check_ok", 0.0) >= 1.0
            and metrics.get("motor_pulse_ok", 0.0) >= 1.0
        ):
            print("RESULT: PASS")
            return 0
        print("RESULT: FAIL")
        return 1
    finally:
        r.close()


if __name__ == "__main__":
    raise SystemExit(main())
