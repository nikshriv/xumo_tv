"""Constants for the homekit_controller component."""

from aiohomekit.exceptions import (
    AccessoryDisconnectedError,
    AccessoryNotFoundError,
    EncryptionError,
)
from aiohomekit.model.characteristics import CharacteristicsTypes
from aiohomekit.model.services import ServicesTypes

DOMAIN = "xumo_tv"

KNOWN_DEVICES = f"{DOMAIN}-devices"
CONTROLLER = f"{DOMAIN}-controller"
ENTITY_MAP = f"{DOMAIN}-entity-map"
TRIGGERS = f"{DOMAIN}-triggers"

HOMEKIT_DIR = ".homekit"
PAIRING_FILE = "pairing.json"

IDENTIFIER_SERIAL_NUMBER = "homekit_controller:serial-number"
IDENTIFIER_ACCESSORY_ID = "homekit_controller:accessory-id"
IDENTIFIER_LEGACY_SERIAL_NUMBER = "serial-number"
IDENTIFIER_LEGACY_ACCESSORY_ID = "accessory-id"

# Mapping from Homekit type to component.
HOMEKIT_ACCESSORY_DISPATCH = {
    ServicesTypes.TELEVISION: "media_player",
}

CHARACTERISTIC_PLATFORMS = {
    CharacteristicsTypes.REMOTE_KEY: "remote",
}

STARTUP_EXCEPTIONS = (
    TimeoutError,
    AccessoryNotFoundError,
    EncryptionError,
    AccessoryDisconnectedError,
)

# 10 seconds was chosen because it is soon enough
# for most state changes to happen but not too
# long that the BLE connection is dropped. It
# also happens to be the same value used by
# the update coordinator.
DEBOUNCE_COOLDOWN = 10  # seconds

SUBSCRIBE_COOLDOWN = 0.25  # seconds
