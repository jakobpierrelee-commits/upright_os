# ESP32 Wiring Map (From Current Nano Build)

This maps the current `balance_mvp_v2_core` signal layout to an ESP32 DevKit-style board.

## Drop-In Pins Block (ESP32)
```cpp
namespace Pins {
  const uint8_t LED = 2;        // Onboard LED (common on many ESP32 dev boards)

  const uint8_t ENC_LEFT = 32;  // Encoder A / left tick
  const uint8_t ENC_RIGHT = 33; // Encoder B / right tick

  const uint8_t PWMA = 25;      // Motor A PWM
  const uint8_t PWMB = 26;      // Motor B PWM
  const uint8_t AIN1 = 27;      // Motor A direction
  const uint8_t STBY = 13;      // Driver standby/enable
  const uint8_t BIN1 = 14;      // Motor B direction

  const uint8_t VOL = 34;       // Battery sense ADC (input-only pin)
}

// I2C pins on ESP32 (replace Wire.begin() with:)
// Wire.begin(21, 22); // SDA=21, SCL=22
```

## Nano -> ESP32 Signal Mapping

| Signal | Nano Pin | ESP32 Pin |
|---|---:|---:|
| `ENC_LEFT` | `D2` | `GPIO32` |
| `ENC_RIGHT` | `D4` | `GPIO33` |
| `PWMA` | `D5` | `GPIO25` |
| `PWMB` | `D6` | `GPIO26` |
| `AIN1` | `D7` | `GPIO27` |
| `STBY` | `D8` | `GPIO13` |
| `BIN1` | `D12` | `GPIO14` |
| `VOL` | `A2` | `GPIO34` |
| `SDA` (IMU) | `A4` | `GPIO21` |
| `SCL` (IMU) | `A5` | `GPIO22` |
| `GND` | `GND` | `GND` |

## Mermaid Wiring Diagram
```mermaid
flowchart LR
  subgraph N["Legacy Nano Signals"]
    N_D2["D2 (ENC_LEFT)"]
    N_D4["D4 (ENC_RIGHT)"]
    N_D5["D5 (PWMA)"]
    N_D6["D6 (PWMB)"]
    N_D7["D7 (AIN1)"]
    N_D8["D8 (STBY)"]
    N_D12["D12 (BIN1)"]
    N_A2["A2 (VOL ADC)"]
    N_A4["A4 (SDA)"]
    N_A5["A5 (SCL)"]
    N_GND["GND"]
  end

  subgraph E["ESP32 Target Pins"]
    E_32["GPIO32 (ENC_LEFT)"]
    E_33["GPIO33 (ENC_RIGHT)"]
    E_25["GPIO25 (PWMA)"]
    E_26["GPIO26 (PWMB)"]
    E_27["GPIO27 (AIN1)"]
    E_13["GPIO13 (STBY)"]
    E_14["GPIO14 (BIN1)"]
    E_34["GPIO34 (VOL ADC)"]
    E_21["GPIO21 (SDA)"]
    E_22["GPIO22 (SCL)"]
    E_GND["GND"]
  end

  subgraph P["Peripherals"]
    DRV["Motor Driver\n(TB6612 style)\nAIN1/BIN1/PWMA/PWMB/STBY"]
    IMU["IMU (MPU6050)\nI2C"]
    ENC["Wheel Encoders"]
    VBAT["Battery Divider -> ADC"]
  end

  N_D2 --> E_32 --> ENC
  N_D4 --> E_33 --> ENC
  N_D5 --> E_25 --> DRV
  N_D6 --> E_26 --> DRV
  N_D7 --> E_27 --> DRV
  N_D8 --> E_13 --> DRV
  N_D12 --> E_14 --> DRV
  N_A2 --> E_34 --> VBAT
  N_A4 --> E_21 --> IMU
  N_A5 --> E_22 --> IMU
  N_GND --> E_GND
  E_GND --> DRV
  E_GND --> IMU
  E_GND --> ENC
  E_GND --> VBAT
```

## Solder Notes
- Keep a single shared ground between ESP32, motor driver, IMU, encoder board, and battery divider.
- `GPIO34` is input-only (good for `VOL` ADC; do not use as output).
- ESP32 is 3.3V logic: confirm motor driver and encoder outputs are 3.3V-safe.
- If IMU board is 5V-powered, verify I2C pullups are not forcing 5V on SDA/SCL.
