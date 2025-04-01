"""Support for HomeKit TV Remote Keys not supported by media_player."""

from __future__ import annotations

import logging
from wakeonlan import send_magic_packet

from aiohomekit.model.characteristics import (
    CharacteristicsTypes,
    RemoteKeyValues,
    ActivationStateValues,
)
from aiohomekit.model.services import Service, ServicesTypes
from aiohomekit.utils import clamp_enum_to_char

from homeassistant.components.remote import (
    RemoteEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KNOWN_DEVICES
from .connection import HKDevice
from .entity import CharacteristicEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Homekit TV Remote."""
    hkid: str = config_entry.data["AccessoryPairingID"]
    conn: HKDevice = hass.data[KNOWN_DEVICES][hkid]
    tv_mac_address = config_entry.data["TV_MAC_ADDRESS"]
    send_magic_packet(tv_mac_address)
    service=conn.get_service(ServicesTypes.TELEVISION)
    info = {"aid": service.accessory.aid, "iid": service.iid}
    entity = HomeKitTVRemote(conn, info, service.__getitem__(CharacteristicsTypes.REMOTE_KEY))
    entity.mac_address = tv_mac_address
    async_add_entities([entity])

class HomeKitTVRemote(CharacteristicEntity, RemoteEntity):
    """Representation of a HomeKit Television Remote Keys not supported in media_player entity."""

    _attr_entity_registry_visible_default = False

    def _init_(self, conn, info, char):
        self.mac_address = ""

    def get_characteristic_types(self) -> list[str]:
        """Define the homekit characteristics the entity cares about."""
        return [CharacteristicsTypes.REMOTE_KEY, CharacteristicsTypes.ACTIVE]
        
    async def async_turn_on(self):
        """Turn on TV"""
        send_magic_packet(self.mac_address)

        await self.async_put_characteristics(
            {CharacteristicsTypes.ACTIVE: ActivationStateValues.ACTIVE}
        )

    async def async_turn_off(self) -> None:
        """Turn off the TV."""
        await self.async_put_characteristics(
            {CharacteristicsTypes.ACTIVE: ActivationStateValues.INACTIVE}
        )

    async def async_send_command(self, command, **kwargs):
        """Send Remote Command."""
        for com in command:
            if com in RemoteKeyValues.__members__.keys():
                await self.async_put_characteristics(
                    {CharacteristicsTypes.REMOTE_KEY: RemoteKeyValues[com]}
                )