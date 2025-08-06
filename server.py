#!/usr/bin/env python3

# Standard library and system-related imports
import subprocess  # Used to run system commands (like Wi-Fi scanning)
import dbus        # Python D-Bus bindings for interacting with BlueZ
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import time
from gi.repository import GLib  # For main event loop integration
import re       # Used for parsing Wi-Fi scan results
import json     # Optional: used for future JSON formatting of data

# ── Constants for D-Bus BlueZ Interfaces ──────────────────────────────────────

BLUEZ_SERVICE_NAME             = 'org.bluez'
ADAPTER_IFACE                  = 'org.bluez.Adapter1'
GATT_MANAGER_IFACE             = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE   = 'org.bluez.LEAdvertisingManager1'
GATT_SERVICE_IFACE             = 'org.bluez.GattService1'
GATT_CHRC_IFACE                = 'org.bluez.GattCharacteristic1'
ADVERTISING_IFACE              = 'org.bluez.LEAdvertisement1'

# ── GATT Application Definition ──────────────────────────────────────────────
# This is the main container for the GATT server.
# It acts as an ObjectManager that provides a list of services and characteristics.
# BlueZ interacts with this application object to discover what's exposed via GATT.

class Application(dbus.service.Object):
    PATH_BASE = '/org/bluez/example'  # Base D-Bus object path for our GATT server

    def __init__(self, bus):
        self.bus = bus
        self.path = self.PATH_BASE
        self.services = []  # Will hold the list of GATT services

        # Register this object with D-Bus under the base path
        dbus.service.Object.__init__(self, bus, self.path)

        # Add our custom service to the application
        self.add_service(MyService(bus, 0))  # Index 0 for the first service

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, svc):
        # Add a GATT service to the list of managed services
        self.services.append(svc)

    # D-Bus method that BlueZ calls to get all objects this application manages
    # Returns a dictionary mapping D-Bus paths to their properties
    @dbus.service.method('org.freedesktop.DBus.ObjectManager',
                         out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        mapped = {}
        for service in self.services:
            # Add service properties
            mapped[service.get_path()] = service.get_properties()
            # Add each characteristic's properties
            for ch in service.characteristics:
                mapped[ch.get_path()] = ch.get_properties()
        return mapped

# ── Service and Characteristic ───────────────────────────────────────────────

class MyService(dbus.service.Object):
    """
    Defines a custom GATT service.
    Each GATT service groups a set of related characteristics.
    """
    def __init__(self, bus, index):
        self.bus = bus
        self.index = index

        # Create the D-Bus object path for this service
        # Example: /org/bluez/example/service0
        self.path = f'{Application.PATH_BASE}/service{index}'

        # Define a unique 128-bit UUID for this custom service
        self.uuid = '12345678-1234-5678-1234-56789abcdef1'

        # Set this service as a primary service
        self.primary = True

        # List of characteristics this service provides
        self.characteristics = []

        # Register this object on the D-Bus
        dbus.service.Object.__init__(self, bus, self.path)

        # Add a read/write characteristic to this service
        self.add_characteristic(MyCharacteristic(
            bus, 0,
            uuid='12345678-1234-5678-1234-56789abcdef0',
            flags=['read', 'write-without-response'],
            service=self
        ))

        # Add a "notify" characteristic that can send updates to connected clients
        self.notify_char = NotifyCharacteristic(
            bus, 1,
            uuid='12345678-1234-5678-1234-56789abcdef2',
            service=self
        )
        self.add_characteristic(self.notify_char)

    def get_path(self):
        """
        Returns the D-Bus object path of this service.
        """
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        """
        Required by BlueZ to describe this service's metadata.
        Returns a dictionary describing the service:
        - UUID
        - Whether it's primary
        - The list of characteristics under this service
        """
        return {
            GATT_SERVICE_IFACE: {
                'UUID':    self.uuid,
                'Primary': dbus.Boolean(self.primary),
                'Characteristics': dbus.Array(
                    [ch.get_path() for ch in self.characteristics],
                    signature='o'  # "o" = D-Bus object path
                )
            }
        }

    def add_characteristic(self, ch):
        """
        Adds a characteristic to the service.
        """
        self.characteristics.append(ch)


class NotifyCharacteristic(dbus.service.Object):
    """
    A custom characteristic that supports 'notify'.
    This means the server can push data to subscribed clients asynchronously.
    """

    def __init__(self, bus, index, uuid, service):
        self.bus = bus
        self.index = index
        self.uuid = uuid
        self.flags = ['notify']  # Only supports notification, not read/write
        self.service = service

        self.notifying = False   # Tracks whether a client has subscribed
        self.value = []          # Most recent value sent

        # Object path for this characteristic
        self.path = f"{service.path}/char_notify{index}"

        # Register this object on the D-Bus
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        """
        Returns the D-Bus object path of the characteristic.
        """
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        """
        Describes this characteristic to BlueZ.
        Includes:
        - UUID
        - Flags (notify only)
        - The current value (as an array of bytes)
        """
        return {
            GATT_CHRC_IFACE: {
                'UUID':    self.uuid,
                'Service': self.service.get_path(),
                'Flags':   dbus.Array(self.flags, signature='s'),
                'Value':   dbus.Array(self.value, signature='y')  # 'y' = byte
            }
        }

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StartNotify(self):
        """
        Called by the client to subscribe to notifications.
        """
        self.notifying = True
        print("🔔 StartNotify called", flush=True)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StopNotify(self):
        """
        Called by the client to unsubscribe from notifications.
        """
        self.notifying = False
        print("🔕 StopNotify called", flush=True)

    def send_notification(self, message: str):
        """
        Server-side function to notify the client with new data.
        Converts string to list of dbus.Bytes and sends via PropertiesChanged signal.
        """
        if not self.notifying:
            print("⚠️ Cannot notify, client hasn't subscribed", flush=True)
            return

        # Convert message to bytes and update characteristic value
        self.value = [dbus.Byte(b) for b in message.encode()]

        # Emit the PropertiesChanged signal to notify client
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': self.value},
            []
        )

    @dbus.service.signal(dbus_interface='org.freedesktop.DBus.Properties',
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        """
        D-Bus signal used to notify clients about property changes.
        Required for 'notify' to work.
        """
        pass



class MyCharacteristic(dbus.service.Object):
    """
    A GATT characteristic that allows a BLE client to:
    - Write data (JSON commands or simple strings)
    - Read back last written value
    - Trigger server-side logic (like Wi-Fi scanning and connection)
    """

    def __init__(self, bus, index, uuid, flags, service):
        self.bus = bus
        self.index = index
        self.uuid = uuid
        self.flags = flags  # Example: ['read', 'write-without-response']
        self.service = service

        # Default value (single byte set to 0)
        self.value = [dbus.Byte(0x00)]

        # D-Bus object path for this characteristic
        self.path = f"{service.path}/char{index}"

        # Register with the D-Bus system
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        """
        Returns characteristic metadata to BlueZ:
        - UUID
        - Associated service path
        - Supported flags (read/write/etc.)
        """
        return {
            GATT_CHRC_IFACE: {
                'UUID':    self.uuid,
                'Service': self.service.get_path(),
                'Flags':   dbus.Array(self.flags, signature='s'),
            }
        }

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        """
        Called when a BLE client writes data to this characteristic.
        Parses incoming text and acts based on command.

        Expected formats:
        - "SCAN_WIFI" (triggers a Wi-Fi scan)
        - JSON string with {"ssid": ..., "password": ...}
        """

        try:
            text = bytes(value).decode('utf-8')  # Convert byte array to string
            print(f"📥 WriteValue: {text}", flush=True)

            if text == 'SCAN_WIFI':
                # Run a scan using iwlist
                try:
                    networks = scan_networks()

                    if not networks:
                        print('not networks', flush=True)
                        raise Exception('Failed to scan networks')

                    print(networks, flush=True)

                    # Convert list of networks to JSON string
                    json_str = json.dumps(networks)

                    # Send results to the client via notify characteristic
                    self.service.notify_char.send_notification(json_str)

                except Exception as e:
                    print(f'Some error happend: {e}', e, flush=True)
                return

            # Try to parse incoming data as JSON
            data = json.loads(text)
            print(f"✅ Parsed JSON: {data}", flush=True)

            ssid = data.get('ssid')
            password = data.get('password')
            print(f"📡 SSID: {ssid}, 🔑 Password: {password}", flush=True)

            if not ssid or not password:
                print("❌ Missing SSID or password", flush=True)
                return

            # Run a Wi-Fi scan and optionally notify
            command = "sudo iwlist scan | grep 'ESSID'"
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                output = result.stdout.strip()
                if not output:
                    output = "No ESSIDs found"
            else:
                output = f"Error: {result.stderr.strip()}"

            print("🔹 Notifying via Bluetooth...", flush=True)
            self.service.notify_char.send_notification(output)

            # Connect to Wi-Fi using NetworkManager CLI
            command = f"sudo nmcli device wifi connect '{ssid}' password '{password}'"
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                print("✅ Wi-Fi credentials accepted", flush=True)
                self.service.notify_char.send_notification("✅ Connected to Wi-Fi")
            else:
                print("❌ Failed to connect to Wi-Fi", flush=True)
                self.service.notify_char.send_notification("❌ Failed to connect")
                print("✅ Wi-Fi config updated. Reconnect on next boot or reconfigure now.", flush=True)

        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}", flush=True)
        except Exception as e:
            print(e, flush=True)
            print(f"📥 WriteValue (raw): {list(value)}", flush=True)

        # Store last written value
        self.value = value

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        """
        Called when a BLE client reads the value of this characteristic.
        """
        print("📤 ReadValue called", flush=True)
        return self.value

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        """
        Called by BlueZ to get a specific property of this characteristic.
        """
        return self.get_properties()[interface][prop]

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        """
        Called by BlueZ to get all properties of this characteristic.
        """
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException('Invalid interface')
        return self.get_properties()[interface]


# ── Advertisement ─────────────────────────────────────────────────────────────

class Advertisement(dbus.service.Object):
    """
    Represents a Bluetooth LE advertising packet exposed via D-Bus.
    BLE advertising is how your device broadcasts its presence and
    allows clients to discover the GATT services it offers.

    This class defines what gets advertised and registers itself
    with BlueZ's LEAdvertisingManager1 interface.
    """

    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index):
        self.bus = bus
        self.index = index

        # D-Bus object path for this advertisement instance
        self.path = f"{self.PATH_BASE}{index}"

        # List of 128-bit service UUIDs to advertise.
        # This should match the UUID of your GATT service(s).
        self.service_uuids = ['12345678-1234-5678-1234-56789abcdef1']

        # The local device name that shows up in scanning apps
        self.local_name = 'RaspiBLE'

        # List of "Includes" tells the advertiser to include
        # certain standard data fields automatically.
        # 'tx-power' includes the transmit power level in the advertisement.
        self.includes = ['tx-power']

        # Register this object on the D-Bus at the path self.path
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        """
        Returns the D-Bus object path for this advertisement.
        """
        return dbus.ObjectPath(self.path)

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        """
        Returns all properties of this advertisement.
        This method is called by BlueZ to know what to advertise.
        """
        if interface != ADVERTISING_IFACE:
            raise dbus.exceptions.DBusException('Invalid interface')

        return {
            'Type':          'peripheral',  # We act as a BLE peripheral device
            'ServiceUUIDs':  dbus.Array(self.service_uuids, signature='s'),  # Services advertised
            'LocalName':     self.local_name,  # Friendly device name
            'Includes':      dbus.Array(self.includes, signature='s'),  # Extra fields to include
        }

    @dbus.service.method(ADVERTISING_IFACE, in_signature='', out_signature='')
    def Release(self):
        """
        Called when BlueZ or the system wants to stop advertising and
        release this advertisement object.
        Useful for cleanup or logging.
        """
        print("❌ Advertisement released", flush=True)


# ── Helpers & Main ───────────────────────────────────────────────────────────

def find_adapter(bus):
    """
    Finds the system's Bluetooth adapter by querying BlueZ's D-Bus ObjectManager.

    Steps:
    - Get the root D-Bus object from BlueZ service.
    - Use ObjectManager interface to list all managed objects.
    - Search for an object path that implements the Adapter interface (org.bluez.Adapter1).
    - Return the adapter's D-Bus object path (e.g., '/org/bluez/hci0').

    Why:
    - The adapter path is needed to register GATT services and advertisements.
    - Multiple adapters may exist; this function returns the first one found.
    """
    obj = bus.get_object(BLUEZ_SERVICE_NAME, '/')
    manager = dbus.Interface(obj, 'org.freedesktop.DBus.ObjectManager')
    objs = manager.GetManagedObjects()
    for path, ifs in objs.items():
        if ADAPTER_IFACE in ifs:
            return path
    return None

def register_app_cb():
    """
    Callback invoked by BlueZ upon successful registration of the GATT application.
    """
    print("✅ GATT application registered", flush=True)

def register_app_error_cb(error):
    """
    Callback invoked if GATT application registration fails.
    """
    print("❌ Failed to register application:", error, flush=True)

def register_ad_cb():
    """
    Callback invoked when the advertisement is successfully registered with BlueZ.
    """
    print("📣 Advertisement registered", flush=True)

def register_ad_error_cb(error):
    """
    Callback invoked if advertisement registration fails.
    """
    print("❌ Failed to register advertisement:", error, flush=True)

# ── Wi-Fi Scanner ─────────────────────────────────────────────────────────────
# This function scans available Wi-Fi networks using the `iwlist` command
# and parses the output to extract ESSIDs (names) and MAC addresses.

def scan_networks():
    try:
        # Run the Wi-Fi scan command using subprocess
        result = subprocess.run(
            ['sudo', 'iwlist', 'wlan0', 'scan'],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout

        # Regex to extract MAC addresses and ESSIDs
        cell_re = re.compile(r'Cell \d+ - Address: ([\da-fA-F:]{17})')
        essid_re = re.compile(r'ESSID:"(.*?)"')

        addresses = cell_re.findall(output)
        essids = essid_re.findall(output)

        seen_essids = set()
        unique_networks = []

        # Avoid listing duplicate ESSIDs
        for addr, essid in zip(addresses, essids):
            if essid not in seen_essids and essid != "":
                seen_essids.add(essid)
                unique_networks.append({
                    "address": addr,
                    "essid": essid
                })

        return unique_networks

    except subprocess.CalledProcessError as e:
        print("Failed to scan Wi-Fi:", e, flush=True)
        return []

def main():
    # Use the GLib main loop for handling asynchronous D-Bus events.
    # This integration is necessary for BlueZ's asynchronous APIs.
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Connect to the system bus (used for system services like BlueZ)
    bus = dbus.SystemBus()

    # Find the Bluetooth adapter's D-Bus object path (e.g., '/org/bluez/hci0')
    adapter = find_adapter(bus)
    if not adapter:
        print("❌ No Bluetooth adapter found", flush=True)
        return  # Exit if no Bluetooth hardware is available

    # Create instances of your GATT application and advertisement
    app = Application(bus)
    adv = Advertisement(bus, 0)

    # Get the GATT Manager interface to register your GATT application
    svc_m = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        GATT_MANAGER_IFACE
    )

    # Get the LE Advertising Manager interface to register your advertisement
    adv_m = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        LE_ADVERTISING_MANAGER_IFACE
    )

    # Sleep a bit to let BlueZ settle and be ready for registration calls
    time.sleep(1)

    print("ℹ️  Registering GATT application …", flush=True)
    # Register your GATT Application with BlueZ asynchronously
    svc_m.RegisterApplication(
        app.get_path(),
        {},  # Options dictionary, usually empty
        reply_handler=register_app_cb,
        error_handler=register_app_error_cb
    )

    print("ℹ️  Registering Advertisement …", flush=True)
    # Register your Advertisement object with BlueZ asynchronously
    adv_m.RegisterAdvertisement(
        adv.get_path(),
        {},  # Options dictionary, usually empty
        reply_handler=register_ad_cb,
        error_handler=register_ad_error_cb
    )

    # Run the GLib main event loop forever
    # This loop handles incoming D-Bus calls and BLE events
    GLib.MainLoop().run()

if __name__ == '__main__':
    main()
