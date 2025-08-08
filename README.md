# Raspberry Pi BLE GATT Server with Wi-Fi Management

This project implements a Bluetooth Low Energy (BLE) GATT server on Linux (e.g., Raspberry Pi) using Python and BlueZ D-Bus API. It allows BLE clients (smartphones, laptops) to scan for Wi-Fi networks and configure Wi-Fi credentials remotely via BLE.

Work with this [repo](https://github.com/ClimateNetTumoLabs/bluetooth_app) React App

---

## Features

- **Custom GATT Service** with:
  - **Read/Write Characteristic**: Accepts commands and Wi-Fi credentials from BLE clients.
  - **Notify Characteristic**: Sends asynchronous updates (Wi-Fi scan results, connection status) to subscribed clients.
- **Wi-Fi Scanning**: Scans available Wi-Fi networks using `iwlist` and returns unique ESSIDs and MAC addresses.
- **Wi-Fi Connection**: Connects to Wi-Fi using NetworkManager CLI (`nmcli`) based on received credentials.
- **BLE Advertising**: Broadcasts the custom service UUID and device name (`RaspiBLE`) for discovery by clients.
- **D-Bus Integration**: Uses BlueZ's D-Bus API for GATT and advertising management.
- **GLib Main Loop** for asynchronous event handling.

---

## Requirements

- Linux system with Bluetooth adapter (e.g., Raspberry Pi)
- BlueZ 5.43 or later (with D-Bus support)
- Python 3
- Python packages:
  - `dbus-python`
  - `pygobject` (for GLib main loop)
- Wi-Fi scanning and connection tools:
  - `iwlist` (usually part of `wireless-tools`)
  - `nmcli` (NetworkManager CLI)

---

## Setup

1. **Install dependencies**

```bash
sudo apt-get update
sudo apt-get install -y python3-dbus python3-gi wireless-tools network-manager
```

2. Enable Bluetooth and Wi-Fi

Make sure Bluetooth is enabled and your Wi-Fi adapter supports scanning and connection.

3. Run script with sudo

The script requires root privileges to scan Wi-Fi and manage connections:

```bash
sudo python3 server.py
```

## Usage

- The device advertises as `RaspiBLE` with a custom GATT service UUID.
- Connect from any BLE client (e.g., smartphone BLE apps like **nRF Connect**, or our React Native App).
- Write to the read/write characteristic:
  - Send `"SCAN_WIFI"` (string) to trigger Wi-Fi scanning.
  - Send JSON data with Wi-Fi credentials to connect, e.g.:
    ```json
    { "ssid": "MyNetwork", "password": "MyPassword" }
    ```
- Subscribe to the notify characteristic to receive asynchronous updates:
  - Wi-Fi scan results in JSON format.
  - Connection success/failure messages.

---

## BLE GATT Structure

| Component                 | UUID                                 | Properties                   | Description                      |
| ------------------------- | ------------------------------------ | ---------------------------- | -------------------------------- |
| Custom Service            | 12345678-1234-5678-1234-56789abcdef1 | Primary                      | Groups the characteristics       |
| Read/Write Characteristic | 12345678-1234-5678-1234-56789abcdef0 | Read, Write Without Response | Accepts commands and credentials |
| Notify Characteristic     | 12345678-1234-5678-1234-56789abcdef2 | Notify                       | Sends asynchronous notifications |

---

## Code Structure

- `ble_gatt_server.py`: Main script containing
  - Wi-Fi scanning function
  - GATT application, service, and characteristics definitions
  - Advertisement class for BLE advertising
  - Bluetooth adapter discovery and registration logic
  - Main loop to run the BLE server

---

## Troubleshooting

- **No Bluetooth adapter found:** Make sure your Bluetooth device is plugged in and enabled.
- **Permission errors:** Run the script as root (`sudo`) because Wi-Fi scanning requires elevated privileges.
- **BlueZ version issues:** Ensure your BlueZ stack supports GATT and D-Bus API (version 5.43+ recommended).
- **Wi-Fi connection failures:** Verify NetworkManager is managing your Wi-Fi adapter and that `nmcli` works manually.

---

## License

This project is open-source under the MIT License.

---

## Acknowledgements

- BlueZ official documentation: https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc
- D-Bus Python bindings: https://dbus.freedesktop.org/doc/dbus-python/
- BLE and GATT concepts inspired by Bluetooth SIG specs.

---
## Developer Notes 🛠️ (To Do)

- Need to refactor whole code
- Split into logical files
- Add additional functionality
- Add status management in case of success or failure
- Need to generate and change service and characteristics UUID
- Add logging part
- ...
---

## Contact

For questions or contributions, please open an issue or pull request.
