# Pyro Protector — Autonomous Firefighting Robot

> **Pyro** (from Greek *πῦρ* meaning *fire*) + **Protector** = an autonomous firefighting prototype.

A **prototype** IoT-enabled firefighting robot built as a Capstone project at **MMU University**. The robot roams an area, detects fire using flame sensors, alerts the user via a ThingSpeak dashboard, and extinguishes flames using a water pump system.

Built with a **Raspberry Pi 4** (Rev 1.0), later documented for an **ESP32** redesign (Rev 2.0) for lower power consumption and integrated WiFi/BT.

**Use case:** Mounted on a firefighting truck, this robot can enter hazardous areas ahead of firefighters — scouting for fire sources, suppressing small blazes, and saving critical time before crew deployment.

---

## Table of Contents

- [Features](#features)
- [System Overview](#system-overview)
- [Hardware Components](#hardware-components)
- [Pin Mapping](#pin-mapping)
- [System Connections](#system-connections)
- [Power System](#power-system)
- [Power Connection](#power-connection)
- [Robot Movement Flowchart](#robot-movement-flowchart)
- [Software & Firmware](#software--firmware)
- [IoT Dashboard](#iot-dashboard)
- [Navigation & Control Modes](#navigation--control-modes)
- [Project Versions](#project-versions)
- [Old vs New Design](#old-vs-new-design)
- [Budget](#budget)
- [Getting Started](#getting-started)
- [Future Improvements](#future-improvements)
- [Acknowledgments](#acknowledgments)

---

## Features

- **Autonomous roaming** — systematic area coverage using Boustrophedon Cellular Decomposition with ultrasonic obstacle avoidance
- **Fire detection** — IR/flame sensors detect fire in real-time
- **Automatic fire suppression** — servo-aimed water nozzle activated via relay-controlled water pump
- **Dual control modes** — *Roaming Mode* (autonomous exploration) and *Pilot Mode* (manual override)
- **IoT connectivity** — cloud-connected via ThingSpeak for real-time sensor telemetry
- **ThingSpeak dashboard** — monitor sensor data (temperature, humidity, flame, water level)
- **Environmental monitoring** — DHT11 temperature & humidity sensing, ultrasonic water tank level monitoring

---

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                        Battery                          │
│                6000mAh 12V / 18650 Cells                 │
└──────────┬──────────────────────────────────┬───────────┘
           │ 5V / 3A (RPi)                    │ 5V / 12V (Motors)
           ▼                                  ▼
┌─────────────────────┐            ┌──────────────────────┐
│   Microcontroller    │            │    L298N / BTS7960   │
│  RPi 4 / ESP32       │◄──────────►    Motor Driver      │
│                      │            └──────────┬───────────┘
│  GPIO Pins:          │                       ▼
│  • Ultrasonic (HC-   │            ┌──────────────────────┐
│    SR04)             │            │   4x DC Motors        │
│  • Servo (SG90)      │            │   (Omni / Fixed)     │
│  • Flame Sensor      │            └──────────────────────┘
│  • DHT11             │
│  • Water Pump Relay  │            ┌──────────────────────┐
│  • Camera (CSI)      │            │   Water Pump System   │
└──────────────────────┘            │  R385 Diaphragm Pump │
                                    │  + Servo Nozzle      │
                                    │  + Water Tank        │
                                    └──────────────────────┘
```

### Operating Modes

1. **Roaming Mode (Autonomous)**
   - Robot explores area using ultrasonic obstacle avoidance
   - Flame sensors continuously scan for fire
   - When fire detected, robot stops and triggers ThingSpeak alert

2. **Pilot Mode (Manual)**
   - User takes control via serial commands or ThingSpeak dashboard
   - Manual driving controls + servo aiming + pump activation

---

## Hardware Components

### Rev 1.0 (Raspberry Pi 4)

| Component | Model / Spec | Purpose |
|-----------|-------------|---------|
| **Microcontroller** | Raspberry Pi 4 Model B | Main control unit |
| **Camera** | OV5647 5MP (CSI) | Live feed & future CV |
| **Motor Driver** | L298N (dual-channel) | Controls 4 DC motors (2 per channel) |
| **Motors** | 4x DC motors (65mm fixed wheels) | Drive system |
| **Ultrasonic Sensor** | HC-SR04 (2x) | Obstacle avoidance + water level |
| **Flame Sensor** | IR flame sensor (4x) | Fire direction detection |
| **Temperature Sensor** | DHT11 | Ambient temperature & humidity |
| **Servo Motor** | SG90 Micro-servo | Camera/nozzle pan & ultrasonic scanning |
| **Water Pump** | R385 DC 12V diaphragm pump | Water propulsion |
| **Relay Module** | 1-channel relay | Pump activation switch |
| **Power** | 6000mAh 12V battery | System power |
| **Chassis** | Acrylic / 3D-printed PLA | Robot frame |
| **3D Design** | Tinkercad (2 designs, 2nd improved) | Custom brackets & enclosures |

### 3D Design

Two designs were created using **Tinkercad** online tool. The second design improved structural rigidity, component fitment, and cable routing. Covers motor brackets, servo mounts, water pump holder, and sensor housings.

### Custom Motor Driver

A discrete motor driver was built using **L298D ICs** and discrete components on a prototype board. It mimics the L298N module pinout and behavior. This was a learning exercise in power electronics — future versions will replace it with a proper PCB.

### Rev 2.0 (ESP32 — Planned)

| Change | Reason |
|--------|--------|
| ESP32 replaces RPi 4 | Lower power (~900mAh vs ~3A), built-in WiFi/BT, cheaper |
| BTS7960 motor driver | Higher current handling (43A peak) |
| 18650 Li-ion cells | Modular battery with BMS protection |
| Omni wheels | Better maneuverability, less motor strain |

### Sensors & Actuators Summary

| Pin Type | Components | Count |
|----------|-----------|-------|
| 5V | Ultrasonic, Servo, Flame sensor, Water pump relay | 4 |
| 3.3V | DHT11 | 1 |
| GPIO | Ultrasonic trigger/echo (2), DHT11 (1), Servo (1), Flame (1), Relay (1) | 7 |

---

## Pin Mapping

### Raspberry Pi 4 (Rev 1.0 — BCM numbering)

| GPIO Pin | Component | Function |
|----------|-----------|----------|
| GPIO 23 | L298N IN1 | Right motors forward |
| GPIO 24 | L298N IN2 | Right motors backward |
| GPIO 25 | L298N IN3 | Left motors forward |
| GPIO 8  | L298N IN4 | Left motors backward |
| GPIO 17 | HC-SR04 TRIG | Ultrasonic trigger |
| GPIO 4  | HC-SR04 ECHO | Ultrasonic echo |
| GPIO 10 | Servo SG90 | PWM control |
| GPIO 2  | Servo (alt) | PWM control (alternate build) |
| GPIO 2 | DHT11 | Temperature/humidity data |

### ESP32 (Rev 2.0 — Planned)

Pin mapping TBD per ESP32 dev board selection. Key differences:
- Built-in WiFi/BT eliminates USB dongle
- ADC pins enable battery level monitoring
- Deep sleep modes for power saving

---

## System Connections

![System connections diagram](assets/images/system_connections.png)

Wiring diagram showing GPIO connections between Raspberry Pi 4, L298N motor driver, HC-SR04 ultrasonic sensor, servo motors, flame sensors, DHT11, relay module, and water pump.

---

## Power System

### Rev 1.0 — Battery

| Component | Voltage | Current (typical) |
|-----------|---------|-------------------|
| Raspberry Pi 4 | 5V | ~900mA – 3A |
| 4x DC Motors | 5–12V | ~300mA each (1.2A total) |
| Servo SG90 | 5V | ~100mA |
| Water Pump | 12V | ~1A |
| **Total** | Mixed | ~3.5A peak |

- **Power source:** 6000mAh 12V battery
- **DC-DC step down:** LM2596 converter drops 12V → 5V for Raspberry Pi
- **Runtime (system):** ~1.7h at full load (6Ah / 3.5A)
- Motors powered separately — battery cannot supply motor driver peak current (needs 10A+)

### Rev 2.0 — 18650 Cells

- Separate batteries for microcontroller and motors
- 18650 Li-ion with BMS protection
- Solar charging circuit (planned)
- Short-circuit & over-discharge protection
- ESP32 ADC for battery level monitoring

---

## Power Connection

![Power connection diagram](assets/images/Power_Connection.jpeg)

---

## Software & Firmware

### Rev 1.0 (Python on Raspberry Pi)

| Module | File | Description |
|--------|------|-------------|
| Motor control | `motors.py` | Forward, backward, left, right, stop via L298N |
| Ultrasonic ranging | `ultrasonic.py` | HC-SR04 distance measurement |
| Servo scanning | `servo_scan.py` | 180° pan for obstacle detection |
| Obstacle avoidance | `obstacle.py` | Avoid + choose clearest path |
| Fire detection | `fire_detect.py` | Flame sensor readings → ThingSpeak |
| DHT11 telemetry | `dht11_thingspeak.py` | Temp/humidity → ThingSpeak |
| Water pump | `water_pump.py` | Relay-controlled extinguishing |

**Key libraries:** `RPi.GPIO`, `adafruit_dht`, `thingspeak`, `time`

### Rev 2.0 (Arduino C++ on ESP32)

- Arduino framework with ESP32 board package
- PWM motor control via BTS7960
- Same sensor suite, rewritten in C++ for lower overhead

### IoT Dashboard (ThingSpeak)

![IoT dashboard screenshot](assets/images/IoT_Dashboard.jpeg)

Sensor data sent to ThingSpeak cloud channel:
- **Field 1:** Temperature (°C)
- **Field 2:** Humidity (%)
- **Field 3:** Flame detected (binary)
- **Field 4:** Water level (cm)

Dashboard accessible from any browser for remote monitoring.

---

## Robot Movement Flowchart

![Robot movement flowchart](assets/images/flowchart.png)

---

## Navigation & Control Modes

### Roaming Algorithm

The robot uses **Boustrophedon Cellular Decomposition** ("lawnmower pattern") for systematic area coverage:

1. Area divided into cells (e.g., 1m² grid)
2. Robot traverses horizontally, sweeping back in opposite direction
3. Ultrasonic sensor on servo scans ahead; when obstacle <20cm, robot stops
4. Servo pans left (0°) and right (170°) to measure available space
5. Robot turns toward the direction with more open space
6. Coverage continues until area is fully explored

### Obstacle Avoidance Logic

```
WHILE roaming:
    distance = measure_distance()
    IF distance > 20cm:
        move_forward()
    ELSE:
        stop_motors()
        scan_left()    → distance_L
        scan_right()   → distance_R
        IF distance_L > distance_R:
            turn_left()
        ELSE:
            turn_right()
```

### Fire Detection Logic

```
WHILE roaming:
    IF flame_sensor_detected():
        stop_robot()
        alert_user_via_thingspeak()
        SWITCH TO pilot_mode()

IN pilot_mode:
    WHILE user_controls:
        drive(direction)
        aim_servo(angle)
        if pump_triggered():
            activate_water_pump()
```

---

## Project Versions

| Feature | Rev 1.0 | Rev 2.0 |
|---------|---------|---------|
| **MCU** | Raspberry Pi 4 | ESP32 |
| **Language** | Python | Arduino C++ |
| **Motor Driver** | L298N (2A) | BTS7960 (43A peak) |
| **Wheels** | Fixed 65mm | Omni wheels |
| **Power** | 6000mAh 12V battery | 18650 Li-ion cells |
| **Chassis** | Wood prototype | Acrylic / 3D-printed |
| **Cloud** | ThingSpeak | ThingSpeak |
| **Camera** | RPi Camera (CSI) | ESP32-CAM (optional) |
| **Notable** | First prototype, high power, learning experience | Lower power, cheaper, more robust |

---

## Old vs New Design

![Old vs new design comparison](assets/images/old_vs_new_design.png)

Side-by-side comparison of Rev 1.0 (Raspberry Pi, wood chassis, fixed wheels, breadboard wiring) and the improved design with better component layout, cable management, and structural changes.

---

## Budget

| Item | Unit Price (RM) | Qty | Total (RM) |
|------|:-:|:-:|:-:|
| Raspberry Pi 3B+ (used) | 120 | 1 | 120 |
| Geared Motors with 65mm Wheels | 5 | 4 | 20 |
| HDMI cable | 7 | 1 | 7 |
| 4/7mm Misting nozzle | 5 | 1 | 5 |
| 5V Relay | 8 | 1 | 8 |
| MDF wood A4 3mm (robot base) | 3 | 2 | 6 |
| Raspberry Pi camera OV5647 | 35 | 1 | 35 |
| Flame Sensor | 4 | 4 | 16 |
| Servo Motor SG90 | 7 | 1 | 7 |
| Servo Motor MG996R | 15 | 1 | 15 |
| R385 DC 12V Water Pump | 15 | 1 | 15 |
| Water Tank 500 ml | 2 | 1 | 2 |
| Ultrasonic sensor HC-SR04 | 5 | 2 | 10 |
| 12V 6000mAh LiPo Battery (used) | 30 | 1 | 30 |
| DC Voltage step down LM2596 | 10 | 1 | 10 |
| RPi camera 1m ribbon cable | 2 | 1 | 2 |
| L298 dual channel Motor driver | 10 | 1 | 10 |
| L298D Motor driver IC | 3 | 1 | 3 |
| Jumper wires & hook up wires | 7 | 2 | 14 |
| Terminal Blocks | 5 | 2 | 10 |
| DHT11 Temperature & Humidity sensor | 5 | 1 | 5 |
| Switch | 4 | 2 | 8 |
| DC Geared Motor brackets | 3 | 2 | 6 |
| Single Side PCB Copper Clad | 8 | 1 | 8 |
| Terminal Block KF2EDG 2 pins | 4 | 2 | 8 |
| 3.81mm KF2EDG PCB Screw Terminal (8 pins) | 4 | 1 | 4 |
| Capacitor 47µF | 1 | 1 | 1 |
| **Total** | | | **361** |

---

## Getting Started

### Prerequisites

- Raspberry Pi 4 (Rev 1.0) or ESP32 (Rev 2.0)
- Raspberry Pi OS (for RPi) or Arduino IDE (for ESP32)
- Python 3.7+ (for RPi version)

### Hardware Assembly

1. Mount motors onto chassis with wheels
2. Connect motor driver to motors and MCU (see [Pin Mapping](#pin-mapping))
3. Mount ultrasonic sensor on servo for pan-scan
4. Install water pump, relay, nozzle, and tank
5. Connect flame sensors at front bumper positions
6. Wire DHT11 for temperature monitoring
7. Power up and verify each subsystem

### Firmware Setup (RPi)

```bash
# 1. Install system dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip

# 2. Install Python packages
pip3 install -r firmware/requirements.txt

# 3. Set ThingSpeak credentials
#    Edit firmware/thingspeak.py → replace CHANNEL_ID and WRITE_KEY

# 4. Run
cd firmware
python3 main.py
```

### Pin Checklist Before First Run

| Pin | Connection | Verify |
|-----|-----------|--------|
| GPIO 23, 24 | L298N IN1, IN2 → right motors | Motors spin forward/back |
| GPIO 25, 8 | L298N IN3, IN4 → left motors | Motors spin forward/back |
| GPIO 17, 4 | HC-SR04 obstacle trig/echo | Readings change with distance |
| GPIO 27, 22 | HC-SR04 water trig/echo | Readings change with water level |
| GPIO 10 | Servo signal wire | Pans left/center/right |
| GPIO 5, 6, 13, 19 | Flame sensors front/left/right/back | Goes HIGH near flame |
| GPIO 21 | Relay IN → water pump | Clicks when fire detected |
| GPIO 2 | DHT11 data pin | Temp/humidity prints to console |

### Auto-start on Boot (optional)

Create a systemd service so the robot starts automatically when the Pi powers on:

```bash
sudo nano /etc/systemd/system/pyro-protector.service
```

```
[Unit]
Description=Pyro Protector Firefighting Robot
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/pyro-protector/firmware/main.py
WorkingDirectory=/home/pi/pyro-protector/firmware
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pyro-protector
sudo systemctl start pyro-protector
```

### Software Setup (ESP32)

1. Install Arduino IDE and ESP32 board package
2. Configure WiFi credentials and ThingSpeak API keys
3. Flash firmware to ESP32

---

## Future Improvements

- [ ] **Computer vision fire detection** — integrate YOLO or OpenCV with Pi Camera for visual fire confirmation
- [ ] **Dedicated mobile app** — build Flutter or MIT App Inventor app for direct robot control and camera feed
- [ ] **Custom PCB** — design a single board for motor driver and whole system, eliminating loose wires and breadboard
- [ ] **BMS (Battery Management System)** — add low-voltage cutoff to detect full discharge and shut down system, preventing Li-ion battery damage and extending lifespan
- [ ] SLAM (Simultaneous Localization and Mapping) for precise indoor navigation
- [ ] Solar panel charging for extended autonomous operation
- [ ] Custom 3D-printed enclosures for all modules
- [ ] LiPo/LiFePO4 battery upgrade for longer runtime
- [ ] Multi-robot coordination for larger area coverage
- [ ] Gas/smoke sensor (MQ-2) for early fire detection
- [ ] Thermal camera for better fire localization
- [ ] RTSP/WebRTC streaming for low-latency camera feed

---

## Acknowledgments

- Built as a Capstone project at **MMU University**
- Inspired by the need for affordable autonomous firefighting solutions for small spaces
- Special thanks to the open-source community for libraries, tutorials, and tools

---

## License

This project is open-source and available for educational and research purposes.

---

> **Note:** This is a prototype built for educational purposes. Rev 1.0 (Raspberry Pi) had limitations — high power draw, prototype wiring, no CV or mobile app. Rev 2.0 (ESP32) addresses many of these with lower power, integrated WiFi, and modular battery design.
