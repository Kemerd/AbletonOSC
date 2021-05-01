from ableton.v2.control_surface import ControlSurface

from . import dyna

import Live
import importlib
import traceback
import functools
import logging
from typing import Tuple, Any

logger = logging.getLogger("liveosc")
file_handler = logging.FileHandler('/tmp/liveosc.log')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('(%(asctime)s) [%(levelname)s] %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

class Manager(ControlSurface):
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self.reload_imports()
        self.show_message("Loaded LiveOSC")

        self.osc_server = dyna.OSCServer()
        self.schedule_message(0, self.tick)

        self.create_session()

    def create_session(self):
        self.osc_server.add_handler("/live/test", lambda _, params: self.show_message("Received OSC OK"))

        for property in [
            "arrangement_overdub",
            "back_to_arranger",
            "clip_trigger_quantization",
            "current_song_time",
            "groove_amount",
            "loop",
            "loop_length",
            "loop_start",
            "metronome",
            "midi_recording_quantization",
            "nudge_down",
            "nudge_up",
            "punch_in",
            "punch_out",
            "record_mode"
        ]:
            def set_property(prop, address, params):
                setattr(self.song, prop, params[0])

            callback = functools.partial(set_property, property)
            self.osc_server.add_handler("/live/set/%s" % property, callback)

        for method in [
            "start_playing",
            "stop_playing",
            "stop_all_clips",
            "create_audio_track",
            "create_midi_track"
        ]:
            def call_method(_method, address, params):
                getattr(self.song, _method)()

            callback = functools.partial(call_method, method)
            self.osc_server.add_handler("/live/set/%s" % method, callback)

        self.song.add_tempo_listener(self.on_tempo_changed)

        def clip_command(func):
            def clip_command_wrapper(address, params: Tuple[Any]):
                track_index, clip_index, clip_length = params
                track = self.song.tracks[track_index]
                clip_slot = track.clip_slots[clip_index]
                return func(clip_slot, tuple(params[2:]))
            return clip_command_wrapper

        def clip_create(_, params: Tuple[Any]):
            track_index, clip_index, clip_length = params
            track = self.song.tracks[track_index]
            clip_slot = track.clip_slots[clip_index]
            clip_slot.create_clip(clip_length)
            
        def clip_slot_fire(_, params: Tuple[Any]):
            track_index, clip_index = params
            track = self.song.tracks[track_index]
            clip_slot = track.clip_slots[clip_index]
            clip_slot.fire()

        @clip_command
        def clip_set_color(clip_slot, params: Tuple[Any]):
            clip_slot.clip.color = params[0]

        def clip_get_is_midi_clip(_, params: Tuple[Any]):
            track_index, clip_index = params
            track = self.song.tracks[track_index]
            clip_slot = track.clip_slots[clip_index]
            self.osc_server.send("/live/clip/get/is_midi_clip", (track_index, clip_index, clip_slot.clip.is_midi_clip))

        def clip_add_new_note(_, params: Tuple[Any]):
            track_index, clip_index, start_time, duration, pitch, velocity, mute = params
            note = Live.Clip.MidiNoteSpecification(start_time=start_time,
                                                   duration=duration,
                                                   pitch=pitch,
                                                   velocity=velocity,
                                                   mute=mute)
            track = self.song.tracks[track_index]
            clip = track.clip_slots[clip_index].clip
            clip.add_new_notes((note,))

        self.osc_server.add_handler("/live/clip/create", clip_create)
        self.osc_server.add_handler("/live/clip/fire", clip_slot_fire)
        self.osc_server.add_handler("/live/clip/set/color", clip_set_color)
        self.osc_server.add_handler("/live/clip/get/is_midi_clip", clip_get_is_midi_clip)
        self.osc_server.add_handler("/live/clip/add_new_note", clip_add_new_note)

    def on_tempo_changed(self):
        self.show_message("Tempo: %.1f" % self.song.tempo)
        self.osc_server.send("/live/tempo", (self.song.tempo,))

    def tick(self):
        """
        Called once per 100ms "tick".
        Live's embedded Python implementation does not appear to support threading,
        and beachballs when a thread is started. Instead, this approach allows long-running
        processes such as the OSC server to perform operations.
        """
        logger.info("Tick...")
        self.osc_server.process()
        self.schedule_message(1, self.tick)

    def reload_imports(self):
        try:
            importlib.reload(dyna)
        except Exception as e:
            exc = traceback.format_exc()
            logging.warning(exc)
        logger.info("Reloaded code")

    def disconnect(self):
        self.show_message("Disconnecting...")
        self.osc_server.shutdown()
        super().disconnect()
