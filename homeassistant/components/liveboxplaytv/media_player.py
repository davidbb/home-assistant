"""Support for interface with an Orange Livebox Play TV appliance."""
from datetime import timedelta
import logging

import requests
import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerDevice, PLATFORM_SCHEMA)
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_CHANNEL, SUPPORT_NEXT_TRACK, SUPPORT_PAUSE,
    SUPPORT_PLAY, SUPPORT_PREVIOUS_TRACK, SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_STEP)
from homeassistant.const import (
    CONF_HOST, CONF_NAME, CONF_PORT, STATE_OFF, STATE_ON, STATE_PAUSED,
    STATE_PLAYING)
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'Livebox Play TV'
DEFAULT_PORT = 8080

SUPPORT_LIVEBOXPLAYTV = SUPPORT_TURN_OFF | SUPPORT_TURN_ON | \
    SUPPORT_NEXT_TRACK | SUPPORT_PAUSE | SUPPORT_PREVIOUS_TRACK | \
    SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | SUPPORT_SELECT_SOURCE | \
    SUPPORT_PLAY

MIN_TIME_BETWEEN_SCANS = timedelta(seconds=10)
MIN_TIME_BETWEEN_FORCED_SCANS = timedelta(seconds=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Orange Livebox Play TV platform."""
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    name = config.get(CONF_NAME)

    livebox_devices = []

    try:
        device = LiveboxPlayTvDevice(host, port, name)
        livebox_devices.append(device)
    except IOError:
        _LOGGER.error("Failed to connect to Livebox Play TV at %s:%s. "
                      "Please check your configuration", host, port)
    async_add_entities(livebox_devices, True)


class LiveboxPlayTvDevice(MediaPlayerDevice):
    """Representation of an Orange Livebox Play TV."""

    def __init__(self, host, port, name):
        """Initialize the Livebox Play TV device."""
        from liveboxplaytv import LiveboxPlayTv
        self._client = LiveboxPlayTv(host, port)
        # Assume that the appliance is not muted
        self._muted = False
        self._name = name
        self._current_source = None
        self._state = None
        self._channel_list = {}
        self._current_channel = None
        self._current_program = None
        self._media_duration = None
        self._media_remaining_time = None
        self._media_image_url = None
        self._media_last_updated = None

    async def async_update(self):
        """Retrieve the latest data."""
        import pyteleloisirs
        try:
            self._state = self.refresh_state()
            # Update channel list
            self.refresh_channel_list()
            # Update current channel
            channel = self._client.channel
            if channel is not None:
                self._current_channel = channel
                program = await \
                    self._client.async_get_current_program()
                if program and self._current_program != program.get('name'):
                    self._current_program = program.get('name')
                    # Media progress info
                    self._media_duration = \
                        pyteleloisirs.get_program_duration(program)
                    rtime = pyteleloisirs.get_remaining_time(program)
                    if rtime != self._media_remaining_time:
                        self._media_remaining_time = rtime
                        self._media_last_updated = dt_util.utcnow()
                # Set media image to current program if a thumbnail is
                # available. Otherwise we'll use the channel's image.
                img_size = 800
                prg_img_url = await \
                    self._client.async_get_current_program_image(img_size)
                if prg_img_url:
                    self._media_image_url = prg_img_url
                else:
                    chan_img_url = \
                        self._client.get_current_channel_image(img_size)
                    self._media_image_url = chan_img_url
        except requests.ConnectionError:
            self._state = None

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    @property
    def source(self):
        """Return the current input source."""
        return self._current_channel

    @property
    def source_list(self):
        """List of available input sources."""
        # Sort channels by tvIndex
        return [self._channel_list[c] for c in
                sorted(self._channel_list.keys())]

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        # return self._client.media_type
        return MEDIA_TYPE_CHANNEL

    @property
    def media_image_url(self):
        """Image url of current playing media."""
        return self._media_image_url

    @property
    def media_title(self):
        """Title of current playing media."""
        if self._current_channel:
            if self._current_program:
                return '{}: {}'.format(self._current_channel,
                                       self._current_program)
            return self._current_channel

    @property
    def media_duration(self):
        """Duration of current playing media in seconds."""
        return self._media_duration

    @property
    def media_position(self):
        """Position of current playing media in seconds."""
        return self._media_remaining_time

    @property
    def media_position_updated_at(self):
        """When was the position of the current playing media valid.

        Returns value from homeassistant.util.dt.utcnow().
        """
        return self._media_last_updated

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_LIVEBOXPLAYTV

    def refresh_channel_list(self):
        """Refresh the list of available channels."""
        new_channel_list = {}
        # update channels
        for channel in self._client.get_channels():
            new_channel_list[int(channel['index'])] = channel['name']
        self._channel_list = new_channel_list

    def refresh_state(self):
        """Refresh the current media state."""
        state = self._client.media_state
        if state == 'PLAY':
            return STATE_PLAYING
        if state == 'PAUSE':
            return STATE_PAUSED

        return STATE_ON if self._client.is_on else STATE_OFF

    def turn_off(self):
        """Turn off media player."""
        self._state = STATE_OFF
        self._client.turn_off()

    def turn_on(self):
        """Turn on the media player."""
        self._state = STATE_ON
        self._client.turn_on()

    def volume_up(self):
        """Volume up the media player."""
        self._client.volume_up()

    def volume_down(self):
        """Volume down media player."""
        self._client.volume_down()

    def mute_volume(self, mute):
        """Send mute command."""
        self._muted = mute
        self._client.mute()

    def media_play_pause(self):
        """Simulate play pause media player."""
        self._client.play_pause()

    def select_source(self, source):
        """Select input source."""
        self._current_source = source
        self._client.set_channel(source)

    def media_play(self):
        """Send play command."""
        self._state = STATE_PLAYING
        self._client.play()

    def media_pause(self):
        """Send media pause command to media player."""
        self._state = STATE_PAUSED
        self._client.pause()

    def media_next_track(self):
        """Send next track command."""
        self._client.channel_up()

    def media_previous_track(self):
        """Send the previous track command."""
        self._client.channel_down()
