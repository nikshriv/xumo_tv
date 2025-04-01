"""Support for HomeKit Controller Televisions."""

from __future__ import annotations

import logging
import enum
from wakeonlan import send_magic_packet

from aiohomekit.model.characteristics import (
    CharacteristicsTypes,
    CurrentMediaStateValues,
    RemoteKeyValues,
    TargetMediaStateValues,
    ActivationStateValues,
)
from aiohomekit.model.services import Service, ServicesTypes
from aiohomekit.utils import clamp_enum_to_char

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KNOWN_DEVICES
from .connection import HKDevice
from .entity import HomeKitEntity

_LOGGER = logging.getLogger(__name__)


HK_TO_HA_STATE = {
    CurrentMediaStateValues.PLAYING: MediaPlayerState.PLAYING,
    CurrentMediaStateValues.PAUSED: MediaPlayerState.PAUSED,
    CurrentMediaStateValues.STOPPED: MediaPlayerState.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Homekit television."""
    hkid: str = config_entry.data["AccessoryPairingID"]
    tv_mac_address = config_entry.data["TV_MAC_ADDRESS"]
    send_magic_packet(tv_mac_address)
    conn: HKDevice = hass.data[KNOWN_DEVICES][hkid]
    speaker_service = conn.get_service(ServicesTypes.SPEAKER)

    @callback
    def async_add_tv_service(service: Service) -> bool:
        if service.type != ServicesTypes.TELEVISION:
            return False
        speaker = None
        entities_to_add = []
        if speaker_service:
            speaker_info = {"aid":speaker_service.accessory.aid, "iid":speaker_service.iid}
            speaker = HomeKitTVSpeaker(conn,speaker_info)
            entities_to_add.append(speaker)
            conn.add_entity((speaker_service.accessory.aid,None,speaker_service.iid))
        info = {"aid": service.accessory.aid, "iid": service.iid}
        tv = HomeKitTelevision(conn, info)
        tv.speaker = speaker
        tv.mac_address = tv_mac_address
        entities_to_add.append(tv)
        conn.async_migrate_unique_id(
            tv.old_unique_id, tv.unique_id, Platform.MEDIA_PLAYER
        )
        async_add_entities(entities_to_add)
        return True

    conn.add_listener(async_add_tv_service)


class ToggleButton(enum.IntEnum):
    """Value to send if button is pressed."""

    TOGGLE_0 = 0
    TOGGLE_1 = 1


class HomeKitTelevision(HomeKitEntity, MediaPlayerEntity):
    """Representation of a HomeKit Controller Television."""

    _attr_device_class = MediaPlayerDeviceClass.TV

    def _init_(self, conn, info):
        self.speaker = None
        self.mac_address = ""

    def get_characteristic_types(self) -> list[str]:
        """Define the homekit characteristics the entity cares about."""
        return [
            CharacteristicsTypes.ACTIVE,
            CharacteristicsTypes.CURRENT_MEDIA_STATE,
            CharacteristicsTypes.TARGET_MEDIA_STATE,
            CharacteristicsTypes.REMOTE_KEY,
            CharacteristicsTypes.ACTIVE_IDENTIFIER,
            # Characterics that are on the linked INPUT_SOURCE services
            CharacteristicsTypes.CONFIGURED_NAME,
            CharacteristicsTypes.IDENTIFIER,
        ]

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        features = MediaPlayerEntityFeature(0)

        if self.service.has(CharacteristicsTypes.ACTIVE_IDENTIFIER):
            features |= MediaPlayerEntityFeature.SELECT_SOURCE

        if self.service.has(CharacteristicsTypes.ACTIVE):
            features |= (
                MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
            )

        if self.service.has(CharacteristicsTypes.TARGET_MEDIA_STATE):
            if TargetMediaStateValues.PAUSE in self.supported_media_states:
                features |= MediaPlayerEntityFeature.PAUSE

            if TargetMediaStateValues.PLAY in self.supported_media_states:
                features |= MediaPlayerEntityFeature.PLAY

            if TargetMediaStateValues.STOP in self.supported_media_states:
                features |= MediaPlayerEntityFeature.STOP
        
        if self.speaker:
            if self.speaker.service.has(CharacteristicsTypes.VOLUME):
                features |= MediaPlayerEntityFeature.VOLUME_SET

            if self.speaker.service.has(CharacteristicsTypes.VOLUME_SELECTOR):
                features |= MediaPlayerEntityFeature.VOLUME_STEP

            if self.speaker.service.has(CharacteristicsTypes.MUTE):
                features |= MediaPlayerEntityFeature.VOLUME_MUTE

        if self.service.has(CharacteristicsTypes.REMOTE_KEY):
            if RemoteKeyValues.PLAY_PAUSE in self.supported_remote_keys:
                features |= (
                    MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.PLAY
                )

            if RemoteKeyValues.PREVIOUS_TRACK in self.supported_remote_keys:
                features |= MediaPlayerEntityFeature.PREVIOUS_TRACK

            if RemoteKeyValues.NEXT_TRACK in self.supported_remote_keys:
                features |= MediaPlayerEntityFeature.NEXT_TRACK

        return features

    @property
    def supported_media_states(self) -> set[TargetMediaStateValues]:
        """Mediate state flags that are supported."""
        if not self.service.has(CharacteristicsTypes.TARGET_MEDIA_STATE):
            return set()

        return clamp_enum_to_char(
            TargetMediaStateValues,
            self.service[CharacteristicsTypes.TARGET_MEDIA_STATE],
        )

    @property
    def supported_remote_keys(self) -> set[int]:
        """Remote key buttons that are supported."""
        if not self.service.has(CharacteristicsTypes.REMOTE_KEY):
            return set()

        return clamp_enum_to_char(
            RemoteKeyValues, self.service[CharacteristicsTypes.REMOTE_KEY]
        )

    @property
    def source_list(self) -> list[str]:
        """List of all input sources for this television."""
        sources = []

        this_accessory = self._accessory.entity_map.aid(self._aid)
        this_tv = this_accessory.services.iid(self._iid)

        input_sources = this_accessory.services.filter(
            service_type=ServicesTypes.INPUT_SOURCE,
            parent_service=this_tv,
        )

        for input_source in input_sources:
            char = input_source[CharacteristicsTypes.CONFIGURED_NAME]
            sources.append(char.value)
        return sources

    @property
    def source(self) -> str | None:
        """Name of the current input source."""
        active_identifier = self.service.value(CharacteristicsTypes.ACTIVE_IDENTIFIER)
        if not active_identifier:
            return None

        this_accessory = self._accessory.entity_map.aid(self._aid)
        this_tv = this_accessory.services.iid(self._iid)

        input_source = this_accessory.services.first(
            service_type=ServicesTypes.INPUT_SOURCE,
            characteristics={CharacteristicsTypes.IDENTIFIER: active_identifier},
            parent_service=this_tv,
        )
        assert input_source
        char = input_source[CharacteristicsTypes.CONFIGURED_NAME]
        return char.value

    @property
    def state(self) -> MediaPlayerState:
        """State of the tv."""
        active = self.service.value(CharacteristicsTypes.ACTIVE)
        if not active:
            return MediaPlayerState.OFF

        homekit_state = self.service.value(CharacteristicsTypes.CURRENT_MEDIA_STATE)
        if homekit_state is not None:
            return HK_TO_HA_STATE.get(homekit_state, MediaPlayerState.ON)

        return MediaPlayerState.ON

    @property
    def is_volume_muted(self) -> bool | None:
        """Is the TV currently muted."""
        return self.speaker.service.value(CharacteristicsTypes.MUTE) > 0

    @property
    def volume_level(self) -> float | None:
        """Volume level of the TV Speaker."""
        return self.speaker.service.value(CharacteristicsTypes.VOLUME) / 100

    async def async_turn_on(self) -> None:
        """Turn on the TV."""
        send_magic_packet(self.mac_address)
            
        await self.async_put_characteristics(
            {CharacteristicsTypes.ACTIVE: ActivationStateValues.ACTIVE}
        )

    async def async_turn_off(self) -> None:
        """Turn off the TV."""
        await self.async_put_characteristics(
            {CharacteristicsTypes.ACTIVE: ActivationStateValues.INACTIVE}
        )

    async def async_media_play(self) -> None:
        """Send play command."""
        if self.state == MediaPlayerState.PLAYING:
            _LOGGER.debug("Cannot play while already playing")
            return

        if TargetMediaStateValues.PLAY in self.supported_media_states:
            await self.async_put_characteristics(
                {CharacteristicsTypes.TARGET_MEDIA_STATE: TargetMediaStateValues.PLAY}
            )
            return
        elif RemoteKeyValues.PLAY_PAUSE in self.supported_remote_keys:
            await self.async_put_characteristics(
                {CharacteristicsTypes.REMOTE_KEY: RemoteKeyValues.PLAY_PAUSE}
            )
            return

    async def async_media_pause(self) -> None:
        """Send pause command."""
        if self.state == MediaPlayerState.PAUSED:
            _LOGGER.debug("Cannot pause while already paused")
            return

        if TargetMediaStateValues.PAUSE in self.supported_media_states:
            await self.async_put_characteristics(
                {CharacteristicsTypes.TARGET_MEDIA_STATE: TargetMediaStateValues.PAUSE}
            )
            return
        elif RemoteKeyValues.PLAY_PAUSE in self.supported_remote_keys:
            await self.async_put_characteristics(
                {CharacteristicsTypes.REMOTE_KEY: RemoteKeyValues.PLAY_PAUSE}
            )
            return

    async def async_media_stop(self) -> None:
        """Send stop command."""
        if self.state == MediaPlayerState.IDLE:
            _LOGGER.debug("Cannot stop when already idle")
            return

        if TargetMediaStateValues.STOP in self.supported_media_states:
            await self.async_put_characteristics(
                {CharacteristicsTypes.TARGET_MEDIA_STATE: TargetMediaStateValues.STOP}
            )

    async def async_select_source(self, source: str) -> None:
        """Switch to a different media source."""
        this_accessory = self._accessory.entity_map.aid(self._aid)
        this_tv = this_accessory.services.iid(self._iid)

        input_source = this_accessory.services.first(
            service_type=ServicesTypes.INPUT_SOURCE,
            characteristics={CharacteristicsTypes.CONFIGURED_NAME: source},
            parent_service=this_tv,
        )

        if not input_source:
            raise ValueError(f"Could not find source {source}")

        identifier = input_source[CharacteristicsTypes.IDENTIFIER]

        await self.async_put_characteristics(
            {CharacteristicsTypes.ACTIVE_IDENTIFIER: identifier.value}
        )

    async def async_mute_volume(self, mute):
        """Toggle mute."""
        await self.speaker.async_put_characteristics(
            {CharacteristicsTypes.MUTE: ToggleButton.TOGGLE_1}
        )

    async def async_volume_up(self):
        """Volume up 1 step."""
        await self.speaker.async_put_characteristics(
            {CharacteristicsTypes.VOLUME_SELECTOR: ToggleButton.TOGGLE_0}
        )

    async def async_volume_down(self):
        """Volume down 1 step."""
        await self.speaker.async_put_characteristics(
            {CharacteristicsTypes.VOLUME_SELECTOR: ToggleButton.TOGGLE_1}
        )

    async def async_set_volume_level(self, volume):
        """Set TV Speaker volume level."""
        await self.speaker.async_put_characteristics(
            {CharacteristicsTypes.VOLUME: int(volume * 100)}
        )

class HomeKitTVSpeaker(HomeKitEntity):
    """Representation of TV Speaker HomeKit Service."""
    
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_entity_registry_visible_default = False
    _attr_entity_registry_enabled_default = False

    def get_characteristic_types(self) -> list[str]:
        """Define the homekit characteristics the entity cares about."""
        return [
            # Volume control characteristics
            CharacteristicsTypes.VOLUME_SELECTOR,
            CharacteristicsTypes.VOLUME,
            CharacteristicsTypes.MUTE,
        ]