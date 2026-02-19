#!/usr/bin/env python3
"""
Generate test fixtures for Sprint 3 T1 tool acceptance tests.

Fixtures generated:
- burst_80hz_4hz_sine.csv: 400 rows @ 80Hz with 4Hz sine wave on ang
- burst_5000_rows.csv: 5000 valid rows for truncation test
- burst_long_rows.csv: 50 rows with 800 char padding
"""

import csv
import math
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def generate_burst_80hz_4hz_sine():
    """Generate 400 samples @ 80Hz with pure 4Hz sine wave on ang."""
    output_path = FIXTURES_DIR / "burst_80hz_4hz_sine.csv"
    
    sample_rate = 80  # Hz
    duration = 5.0    # seconds
    freq = 4.0        # Hz sine wave
    amplitude = 1.0   # degrees
    
    n_samples = int(sample_rate * duration)
    dt = 1.0 / sample_rate
    
    header = "host_ts,mode,estop,ang,raw,gyro,set,out,pid,mot,wspd,wpos,kp,ki,kd,kv,kx,encL,encR,volRaw"
    
    with open(output_path, "w", newline="") as f:
        f.write(header + "\n")
        
        base_ts = 1739922600.0
        for i in range(n_samples):
            t = i * dt
            ts = base_ts + t
            ang = amplitude * math.sin(2 * math.pi * freq * t)
            raw = ang + 0.1  # slight offset
            gyro = amplitude * 2 * math.pi * freq * math.cos(2 * math.pi * freq * t)  # derivative
            out = ang * 20  # proportional response
            
            row = f"{ts:.6f},BALANCING,0,{ang:.4f},{raw:.4f},{gyro:.4f},0,{out:.1f},18.0,0,0,0,18,0.1,0.6,0,0,0,0,720"
            f.write(row + "\n")
    
    print(f"Generated {output_path} with {n_samples} samples")
    return output_path


def generate_burst_5000_rows():
    """Generate 5000 valid rows for truncation test."""
    output_path = FIXTURES_DIR / "burst_5000_rows.csv"
    
    header = "host_ts,mode,estop,ang,raw,gyro,set,out,pid,mot,wspd,wpos,kp,ki,kd,kv,kx,encL,encR,volRaw"
    
    with open(output_path, "w", newline="") as f:
        f.write(header + "\n")
        
        base_ts = 1739922600.0
        for i in range(5000):
            ts = base_ts + i * 0.0125  # ~80Hz
            ang = 1.0 + 0.5 * math.sin(i * 0.1)
            raw = ang + 0.1
            gyro = 0.5 * math.cos(i * 0.1)
            out = ang * 15
            
            row = f"{ts:.6f},BALANCING,0,{ang:.4f},{raw:.4f},{gyro:.4f},0,{out:.1f},18.0,0,0,0,18,0.1,0.6,0,0,0,0,720"
            f.write(row + "\n")
    
    print(f"Generated {output_path} with 5000 rows")
    return output_path


def generate_burst_long_rows():
    """Generate 50 rows with 800 char padding each."""
    output_path = FIXTURES_DIR / "burst_long_rows.csv"
    
    header = "host_ts,mode,estop,ang,raw,gyro,set,out,pid,mot,wspd,wpos,kp,ki,kd,kv,kx,encL,encR,volRaw,extra_padding"
    
    with open(output_path, "w", newline="") as f:
        f.write(header + "\n")
        
        base_ts = 1739922600.0
        for i in range(50):
            ts = base_ts + i * 0.0125
            ang = 1.5
            raw = 1.6
            gyro = 0.1
            out = 30
            
            # Add padding to make row ~800 chars
            padding = "X" * 600
            row = f"{ts:.6f},BALANCING,0,{ang:.4f},{raw:.4f},{gyro:.4f},0,{out:.1f},18.0,0,0,0,18,0.1,0.6,0,0,0,0,720,{padding}"
            f.write(row + "\n")
    
    print(f"Generated {output_path} with 50 long rows")
    return output_path


if __name__ == "__main__":
    generate_burst_80hz_4hz_sine()
    generate_burst_5000_rows()
    generate_burst_long_rows()
    print("All fixtures generated successfully!")
