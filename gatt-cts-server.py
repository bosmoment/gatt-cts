#!/usr/bin/env python3

# Python application to add a Bluetooth Current Time Service to a Linux Bluez
# server. Connection to Bluez is using DBus. Adapted from the HRS and Battery
# GATT server example.


import argparse
from contextlib import suppress
import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import logging

try:
    from gi.repository import GLib
except ImportError:
    import glib as GLib

import datetime
import time

BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'

GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'


class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'


class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'


class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'


class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'


class Application(dbus.service.Object):
    """
    org.bluez.GattApplication1 interface implementation
    """
    def __init__(self, bus, **kwargs):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.add_service(CurrentTimeService(bus, 0, **kwargs))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()

        return response


class Service(dbus.service.Object):
    """
    org.bluez.GattService1 interface implementation
    """
    PATH_BASE = '/org/bluez/example/service'

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
                GATT_SERVICE_IFACE: {
                        'UUID': self.uuid,
                        'Primary': self.primary,
                        'Characteristics': dbus.Array(
                                self.get_characteristic_paths(),
                                signature='o')
                }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()

        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    """
    org.bluez.GattCharacteristic1 interface implementation
    """
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        self.logger = logging.getLogger(type(self).__name__)
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
                GATT_CHRC_IFACE: {
                        'Service': self.service.get_path(),
                        'UUID': self.uuid,
                        'Flags': self.flags,
                        'Descriptors': dbus.Array(
                                self.get_descriptor_paths(),
                                signature='o')
                }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()

        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE,
                         in_signature='a{sv}',
                         out_signature='ay')
    def ReadValue(self, options):
        self.logger.error('Default ReadValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        self.logger.error('Default WriteValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        self.logger.error('Default StartNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.logger.error('Default StopNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.signal(DBUS_PROP_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class Descriptor(dbus.service.Object):
    """
    org.bluez.GattDescriptor1 interface implementation
    """
    def __init__(self, bus, index, uuid, flags, characteristic):
        self.path = characteristic.path + '/desc' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.chrc = characteristic
        self.logger = logging.getLogger(type(self).__name__)
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
                GATT_DESC_IFACE: {
                        'Characteristic': self.chrc.get_path(),
                        'UUID': self.uuid,
                        'Flags': self.flags,
                }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_DESC_IFACE:
            raise InvalidArgsException()

        return self.get_properties()[GATT_DESC_IFACE]

    @dbus.service.method(GATT_DESC_IFACE,
                         in_signature='a{sv}',
                         out_signature='ay')
    def ReadValue(self, options):
        self.logger.error('Default ReadValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_DESC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        self.logger.error('Default WriteValue called, returning error')
        raise NotSupportedException()


class CurrentTimeService(Service):
    """
    BT SIG CTS v1.1.0
    """
    CURRENT_TIME_UUID = '1805'

    def __init__(self, bus, index, **kwargs):
        Service.__init__(self, bus, index, self.CURRENT_TIME_UUID, True)
        self.add_characteristic(CurrentTimeCharacteristic(bus, 0, self, **kwargs))
        self.add_characteristic(LocalTimeInformationCharacteristic(bus, 1, self, **kwargs))


class CurrentTimeCharacteristic(Characteristic):
    CURRENT_TIME_UUID = '2a2B'

    def __init__(self, bus, index, service, **kwargs):
        Characteristic.__init__(
                self, bus, index,
                self.CURRENT_TIME_UUID,
                ['read', 'notify'],
                service)
        self.notifying = False

        with suppress(KeyError):
            notify_period = kwargs["notify_period"]
            if notify_period is not None:
                GLib.timeout_add(notify_period * 1000, self.notify_time)

    def current_time_bytes(self):
        time.tzset()  # Reset the time conversion rules, so that the local time provided by now() is always correct

        dt = datetime.datetime.now()
        year = dt.year.to_bytes(2, 'little')
        value = list([dbus.Byte(b) for b in year])
        value.append(dbus.Byte(dt.month))
        value.append(dbus.Byte(dt.day))
        value.append(dbus.Byte(dt.hour))
        value.append(dbus.Byte(dt.minute))
        value.append(dbus.Byte(dt.second))
        value.append(dbus.Byte(dt.isoweekday()))
        value.append(dbus.Byte(int((dt.microsecond * 1e-6) * 256)))
        value.append(dbus.Byte(1))

        self.logger.debug(f"CT: {dt.isoformat(timespec='microseconds')}")

        return value

    def notify_current_time(self):
        if not self.notifying:
            return
        self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {'Value': self.current_time_bytes()}, [])

    def notify_time(self):
        if not self.notifying:
            return True
        self.logger.info('Notifying current local time')
        self.notify_current_time()
        return True

    def ReadValue(self, options):
        value = self.current_time_bytes()
        self.logger.info(f"Supplying time to {options['device']}")
        return value

    def StartNotify(self):
        if self.notifying:
            self.logger.warning('Already notifying, nothing to do')
            return
        self.notifying = True

    def StopNotify(self):
        if not self.notifying:
            self.logger.warning('Not notifying, nothing to do')
            return
        self.notifying = False


class LocalTimeInformationCharacteristic(Characteristic):
    LOCAL_TIME_INFORMATION_UUID = '2a0f'

    def __init__(self, bus, index, service, **kwargs):
        Characteristic.__init__(
                self, bus, index,
                self.LOCAL_TIME_INFORMATION_UUID,
                ['read'],
                service)

    def local_time_information_bytes(self):
        time.tzset()  # Reset the time conversion rules, so that timezone and altzone are always correct

        time_zone_offset = datetime.timedelta(seconds=-time.timezone)
        dst_offset = datetime.timedelta(seconds=-time.altzone) - time_zone_offset
        time_zone_offset_15min = int(time_zone_offset / datetime.timedelta(minutes=15))
        dst_offset_15_min = int(dst_offset / datetime.timedelta(minutes=15))

        self.logger.debug(f"LTI: TZ offset = {time_zone_offset} ({time_zone_offset_15min:+d}); "
                          f"DST offset = {dst_offset} ({dst_offset_15_min:+d})")
        return [dbus.Byte(time_zone_offset_15min.to_bytes(1, 'little', signed=True)[0]),
                dbus.Byte(dst_offset_15_min)]

    def ReadValue(self, options):
        value = self.local_time_information_bytes()
        self.logger.info(f"Supplying local time information to {options['device']}")
        return value


class Server(object):
    def __init__(self, notify_period=None):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        bus = dbus.SystemBus()

        adapter = self.find_adapter(bus)
        if not adapter:
            logging.error('GattManager1 interface not found')
            return

        service_manager = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                GATT_MANAGER_IFACE)

        app = Application(bus, notify_period=notify_period)

        self.mainloop = GLib.MainLoop()

        logging.info('Registering GATT application...')

        service_manager.RegisterApplication(
                app.get_path(), {},
                reply_handler=self.register_app_cb,
                error_handler=self.register_app_error_cb)

    def run(self):
        self.mainloop.run()

    @staticmethod
    def register_app_cb():
        logging.info('GATT application registered')

    def register_app_error_cb(self, error):
        logging.error('Failed to register application: ' + str(error))
        self.mainloop.quit()

    @staticmethod
    def find_adapter(bus):
        remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                                   DBUS_OM_IFACE)
        objects = remote_om.GetManagedObjects()

        for o, props in objects.items():
            if GATT_MANAGER_IFACE in props.keys():
                return o

        return None


def parse_args():
    parser = argparse.ArgumentParser(description="Run Bluez CTS server",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--notify-period", type=int, default=None,
                        help="Notify clients of the time periodically (N.B. This is non-conformant). Unit: seconds")
    parser.add_argument("-l", "--log-level", choices=["ERROR", "WARNING", "INFO", "DEBUG"],
                        type=lambda s: s.upper(),
                        help="Set console log level (all messages with this level and higher are printed)",
                        default="INFO")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    logging.basicConfig(format='%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s', level=args.log_level)
    Server(args.notify_period).run()
