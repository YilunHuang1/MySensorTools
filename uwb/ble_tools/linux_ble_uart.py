#!/usr/bin/env python3
import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import signal
from gi.repository import GLib
from libubitrap import process_packets, startSerial, closeSerial, sendCmd
from CmdBuilder import CmdEnum, CmdBuilder
from SerialHandler import SerialHandler

SERVICE_NAME = 'org.bluez'
ADAPTER_PATH = '/org/bluez/hci0'
ADVERT_PATH = '/org/bluez/example/advertisement0'
SERVICE_UUID = '2E938FD0-6A61-11ED-A1EB-0242AC120002'
TX_UUID = '2E939AF2-6A61-11ED-A1EB-0242AC120002'
RX_UUID = '2E93998A-6A61-11ED-A1EB-0242AC120002'

mainloop = None
x_char_global = None  # <- Global reference to TX characteristic

class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'
    def __init__(self, bus, index, ad_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = ad_type
        self.service_uuids = [SERVICE_UUID]
        self.local_name = "vita_0_01"
        self.include_tx_power = True
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        props = {
            "Type": self.ad_type,
            "ServiceUUIDs": self.service_uuids,
            "LocalName": self.local_name,
            "IncludeTxPower": self.include_tx_power
        }
        return props.get(prop, None)

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return {
            "Type": self.ad_type,
            "ServiceUUIDs": self.service_uuids,
            "LocalName": self.local_name,
            "IncludeTxPower": self.include_tx_power
        }

    @dbus.service.method("org.bluez.LEAdvertisement1", in_signature="", out_signature="")
    def Release(self):
        print("Advertisement released")

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_services(self):
        return self.services

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method("org.freedesktop.DBus.ObjectManager",
                         in_signature="", out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = {
                "org.bluez.GattService1": {
                    "UUID": service.uuid,
                    "Primary": True,
                    "Characteristics": dbus.Array(
                        [c.get_path() for c in service.characteristics],
                        signature='o'
                    )
                }
            }
            for char in service.characteristics:
                response[char.get_path()] = {
                    "org.bluez.GattCharacteristic1": {
                        "UUID": char.uuid,
                        "Service": service.get_path(),
                        "Flags": dbus.Array(char.flags, signature='s')
                    }
                }
        return response


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, service, flags):
        self.path = service.path + f'/char{index}'
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.value = []
        self.notifying = False
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if prop == "UUID": return self.uuid
        if prop == "Service": return self.service.get_path()
        if prop == "Flags": return dbus.Array(self.flags, signature='s')
        if prop == "Value": return dbus.Array(self.value, signature='y')
        return None

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return {
            "UUID": self.uuid,
            "Service": self.service.get_path(),
            "Flags": dbus.Array(self.flags, signature='s'),
            "Value": dbus.Array(self.value, signature='y')
        }

    @dbus.service.method("org.bluez.GattCharacteristic1", in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, options):
        self.value = value
        rcv_data = bytes(value)
        print("📥 Received from Central:")
        print(' '.join(f'{b:02X}' for b in bytes(value)))

        if rcv_data[0] == 0x0A:
            if tx_char_global and tx_char_global.notifying:
                configureDataCmd = CmdBuilder.build(CmdEnum.UWB_CONFIGURE_DATA)
                print("📥 Notfy UWB_CONFIGURE_DATA to Central:")
                print(' '.join(f'{b:02X}' for b in configureDataCmd))
                tx_char_global.Notify(configureDataCmd)
            else:
                print("⚠️ TX not subscribed or not ready")
        if rcv_data[0] == 0x0B:
            appleFiraCmd, session_id = CmdBuilder.build(CmdEnum.SET_APPLE_FIRA, bytes(value))
            serialHandler.session_id = session_id
            serialHandler.sendCmd(appleFiraCmd)
            
    @dbus.service.method("org.bluez.GattCharacteristic1", in_signature="", out_signature="")
    def StartNotify(self):
        self.notifying = True
        print("✅ Central subscribed to TX notifications")

    @dbus.service.method("org.bluez.GattCharacteristic1", in_signature="", out_signature="")
    def StopNotify(self):
        self.notifying = False
        print("🛑 Central unsubscribed from TX notifications")

    def Notify(self, text):
        if not self.notifying:
            print("❌ Notify skipped, central not subscribed")
            return
        self.value = list(text)
        self.PropertiesChanged("org.bluez.GattCharacteristic1",
                               {"Value": dbus.Array(self.value, signature='y')}, [])

    @dbus.service.signal("org.freedesktop.DBus.Properties", signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

class Service(dbus.service.Object):
    def __init__(self, bus, index, uuid):
        self.path = f"/org/bluez/example/service{index}"
        self.bus = bus
        self.uuid = uuid
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if prop == "UUID": return self.uuid
        if prop == "Primary": return True
        if prop == "Characteristics": return [c.get_path() for c in self.characteristics]

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return {
            "UUID": self.uuid,
            "Primary": True,
            "Characteristics": [c.get_path() for c in self.characteristics]
        }
    
    @dbus.service.method('org.freedesktop.DBus.Introspectable', in_signature='', out_signature='s')
    def Introspect(self):
        return '<node><interface name="org.freedesktop.DBus.Introspectable"/></node>'

def register_app(bus):
    global tx_char_global
    service = Service(bus, 0, SERVICE_UUID)
    tx_char = Characteristic(bus, 0, TX_UUID, service, ["notify"])
    tx_char_global = tx_char
    serialHandler.tx_char_global = tx_char

    rx_char = Characteristic(bus, 1, RX_UUID, service, ["write", "write-without-response"])
    service.characteristics.append(tx_char)
    service.characteristics.append(rx_char)

    # adapter = dbus.Interface(bus.get_object(SERVICE_NAME, ADAPTER_PATH),
    #                          'org.bluez.Adapter1')
    adapter = dbus.Interface(bus.get_object(SERVICE_NAME, ADAPTER_PATH), "org.freedesktop.DBus.Properties")
    adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))

    app = Application(bus)
    app.add_service(service)

    # 注册 GATT 应用
    gatt_manager = dbus.Interface(bus.get_object(SERVICE_NAME, ADAPTER_PATH),
                                  "org.bluez.GattManager1")
    print("GATT Service path:", service.get_path())
    try:
        gatt_manager.RegisterApplication(app.get_path(), {},
                                        reply_handler=lambda: print("✅ GATT service registered"),
                                        error_handler=lambda e: print("❌ Failed to register GATT:", e))
    except Exception as e:
        print("[GATT] register failure", e)



    # 注册广播
    ad_manager = dbus.Interface(bus.get_object(SERVICE_NAME, ADAPTER_PATH),
                                "org.bluez.LEAdvertisingManager1")
    advert = Advertisement(bus, 0, "peripheral")
    ad_manager.RegisterAdvertisement(advert.get_path(), {},
                                     reply_handler=lambda: print("📡 Advertising started"),
                                     error_handler=lambda e: print("❌ Advertising error:", e))

def shutdown_handler(signum, frame):
    print(f"Received signal {signum}, exiting...")
    mainloop.quit()
    serialHandler.stop()

def main():
    global serialHandler
    global mainloop

    serialHandler = SerialHandler()
    serialHandler.start()

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    register_app(bus)
    
    ret = GLib.timeout_add(10, lambda:serialHandler.process_packets())
    print(f"glib add timeout {ret}")

    mainloop = GLib.MainLoop()
    # 注册信号处理器
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print("Main loop running. Press Ctrl+C to exit.")
    mainloop.run()

if __name__ == "__main__":
    main()
