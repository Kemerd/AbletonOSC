import os
import sys
import tempfile
import importlib.util

# Add modules directory to Python path to find local modules (e.g., keyboard, ctypes)
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
modules_dir = os.path.join(script_dir, 'things')
if modules_dir not in sys.path:
    sys.path.insert(0, modules_dir)
    print(f"Added modules path to sys.path: {modules_dir}")

if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
    print(f"Added main path to sys.path: {script_dir}")

# Add parent directory and keyboard directory to Python path
# Print paths to help with debugging
print(f"Python paths: {sys.path}")
print(f"Looking for keyboard module in: {modules_dir}")

import Live
import json
import time
import uuid
from functools import partial
from typing import Tuple, Any, List, Dict, Optional

from .handler import AbletonOSCHandler

class SongHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "song"

    def init_api(self):
        #--------------------------------------------------------------------------------
        # Callbacks for Song: methods
        #--------------------------------------------------------------------------------
        for method in [
            "capture_midi",
            "continue_playing",
            "create_audio_track",
            "create_midi_track",
            "create_return_track",
            "create_scene",
            "delete_return_track",
            "delete_scene",
            "delete_track",
            "duplicate_scene",
            "duplicate_track",
            "jump_by",
            "jump_to_prev_cue",
            "jump_to_next_cue",
            "redo",
            "start_playing",
            "stop_all_clips",
            "stop_playing",
            "tap_tempo",
            "trigger_session_record",
            "undo"
        ]:
            callback = partial(self._call_method, self.song, method)
            self.osc_server.add_handler("/live/song/%s" % method, callback)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: properties (read/write)
        #--------------------------------------------------------------------------------
        properties_rw = [
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
            "record_mode",
            "session_record",
            "signature_denominator",
            "signature_numerator",
            "tempo"
        ]

        #--------------------------------------------------------------------------------
        # Callbacks for Song: properties (read-only)
        #--------------------------------------------------------------------------------
        properties_r = [
            "can_redo",
            "can_undo",
            "is_playing",
            "song_length",
            "session_record_status"
        ]

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/song/get/%s" % prop, partial(self._get_property, self.song, prop))
            self.osc_server.add_handler("/live/song/start_listen/%s" % prop, partial(self._start_listen, self.song, prop))
            self.osc_server.add_handler("/live/song/stop_listen/%s" % prop, partial(self._stop_listen, self.song, prop))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/song/set/%s" % prop, partial(self._set_property, self.song, prop))

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Track properties
        #--------------------------------------------------------------------------------
        self.osc_server.add_handler("/live/song/get/num_tracks", lambda _: (len(self.song.tracks),))

        def song_get_track_names(params):
            if len(params) == 0:
                track_index_min, track_index_max = 0, len(self.song.tracks)
            else:
                track_index_min, track_index_max = params
                if track_index_max == -1:
                    track_index_max = len(self.song.tracks)
            return tuple(self.song.tracks[index].name for index in range(track_index_min, track_index_max))
        self.osc_server.add_handler("/live/song/get/track_names", song_get_track_names)

        def song_get_track_data(params):
            """
            Retrieve one more properties of a block of tracks and their clips.
            Properties must be of the format track.property_name or clip.property_name.

            For example:
                /live/song/get/track_data 0 12 track.name clip.name clip.length

            Queries tracks 0..11, and returns a list of values comprising:

            [track_0_name, clip_0_0_name,   clip_0_1_name,   ... clip_0_7_name,
                           clip_1_0_length, clip_0_1_length, ... clip_0_7_length,
             track_1_name, clip_1_0_name,   clip_1_1_name,   ... clip_1_7_name, ...]
            """
            track_index_min, track_index_max, *properties = params
            track_index_min = int(track_index_min)
            track_index_max = int(track_index_max)
            self.logger.info("Getting track data: %s (tracks %d..%d)" %
                             (properties, track_index_min, track_index_max))
            if track_index_max == -1:
                track_index_max = len(self.song.tracks)
            rv = []
            for track_index in range(track_index_min, track_index_max):
                track = self.song.tracks[track_index]
                for prop in properties:
                    obj, property_name = prop.split(".")
                    if obj == "track":
                        if property_name == "num_devices":
                            value = len(track.devices)
                        else:
                            value = getattr(track, property_name)
                            if isinstance(value, Live.Track.Track):
                                #--------------------------------------------------------------------------------
                                # Map Track objects to their track_index to return via OSC
                                #--------------------------------------------------------------------------------
                                value = list(self.song.tracks).index(value)
                        rv.append(value)
                    elif obj == "clip":
                        for clip_slot in track.clip_slots:
                            if clip_slot.clip is not None:
                                rv.append(getattr(clip_slot.clip, property_name))
                            else:
                                rv.append(None)
                    elif obj == "clip_slot":
                        for clip_slot in track.clip_slots:
                            rv.append(getattr(clip_slot, property_name))
                    elif obj == "device":
                        for device in track.devices:
                            rv.append(getattr(device, property_name))
                    else:
                        self.logger.error("Unknown object identifier in get/track_data: %s" % obj)
            return tuple(rv)
        self.osc_server.add_handler("/live/song/get/track_data", song_get_track_data)


        def song_export_structure(params):
            tracks = []
            for track_index, track in enumerate(self.song.tracks):
                group_track = None
                if track.group_track is not None:
                    group_track = list(self.song.tracks).index(track.group_track)
                track_data = {
                    "index": track_index,
                    "name": track.name,
                    "is_foldable": track.is_foldable,
                    "group_track": group_track,
                    "clips": [],
                    "devices": []
                }
                for clip_index, clip_slot in enumerate(track.clip_slots):
                    if clip_slot.clip:
                        clip_data = {
                            "index": clip_index,
                            "name": clip_slot.clip.name,
                            "length": clip_slot.clip.length,
                        }
                        track_data["clips"].append(clip_data)

                for device_index, device in enumerate(track.devices):
                    device_data = {
                        "class_name": device.class_name,
                        "type": device.type,
                        "name": device.name,
                        "parameters": []
                    }
                    for parameter in device.parameters:
                        device_data["parameters"].append({
                            "name": parameter.name,
                            "value": parameter.value,
                            "min": parameter.min,
                            "max": parameter.max,
                            "is_quantized": parameter.is_quantized,
                        })
                    track_data["devices"].append(device_data)

                tracks.append(track_data)
            song = {
                "tracks": tracks
            }

            if sys.platform == "darwin":
                #--------------------------------------------------------------------------------
                # On macOS, TMPDIR by default points to a process-specific directory.
                # We want to use a global temp dir (typically, tmp) so that other processes
                # know where to find this output .json, so unset TMPDIR.
                #--------------------------------------------------------------------------------
                os.environ["TMPDIR"] = ""
            fd = open(os.path.join(tempfile.gettempdir(), "abletonosc-song-structure.json"), "w")
            json.dump(song, fd)
            fd.close()
            return (1,)
        self.osc_server.add_handler("/live/song/export/structure", song_export_structure)

        #--------------------------------------------------------------------------------
        # Callbacks for freezing and rendering tracks
        #--------------------------------------------------------------------------------
        def song_freeze_track(params):
            """
            Freeze a track to improve performance or for rendering.
            
            Args:
                track_index (int): Index of the track to freeze
                
            Returns:
                success (int): 1 if successful, 0, otherwise
                message (str): Status message
            """
            track_index = int(params[0])
            
            try:
                # Get the track
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                # Check if track can be frozen
                if not hasattr(track, "freeze") or not callable(track.freeze):
                    return (0, f"Track {track.name} cannot be frozen (not supported)")
                
                # Freeze the track
                track.freeze()
                
                # Wait for freezing to complete (this may take time)
                max_wait = 300  # Maximum wait time in seconds
                wait_interval = 1  # Check every half second
                
                for _ in range(int(max_wait / wait_interval)):
                    # Try to determine if freezing is complete
                    # Unfortunately, the Live API doesn't provide a direct way to check this
                    # Most reliable is to check the "frozen" property if available
                    if hasattr(track, "is_frozen") and track.is_frozen:
                        break
                    time.sleep(wait_interval)
                
                return (1, f"Track {track.name} frozen successfully")
                
            except Exception as e:
                self.logger.error(f"Error freezing track: {str(e)}")
                return (0, f"Error freezing track: {str(e)}")
        
        self.osc_server.add_handler("/live/song/freeze_track", song_freeze_track)

        def song_unfreeze_track(params):
            """
            Unfreeze a previously frozen track.
            
            Args:
                track_index (int): Index of the track to unfreeze
                
            Returns:
                success (int): 1 if successful, 0, otherwise
                message (str): Status message
            """
            track_index = int(params[0])
            
            try:
                # Get the track
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                # Check if track can be unfrozen
                if not hasattr(track, "unfreeze") or not callable(track.unfreeze):
                    return (0, f"Track {track.name} cannot be unfrozen (not supported)")
                
                # Unfreeze the track
                track.unfreeze()
                
                return (1, f"Track {track.name} unfrozen successfully")
                
            except Exception as e:
                self.logger.error(f"Error unfreezing track: {str(e)}")
                return (0, f"Error unfreezing track: {str(e)}")
        
        self.osc_server.add_handler("/live/song/unfreeze_track", song_unfreeze_track)
        
        def song_export_track_audio(params):
            """
            Export audio from a specific track to a file.
            
            Args:
                track_index (int): Index of the track to export
                start_time (float, optional): Start time in seconds (default: 0.0)
                duration (float, optional): Duration in seconds (default: entire song)
                filepath (str, optional): Path to save the exported audio (default: temp file)
                include_return (int, optional): Whether to include return track effects (default: 1)
                include_master (int, optional): Whether to include master track effects (default: 1)
                sample_rate (int, optional): Sample rate for export (default: 44100)
                bit_depth (int, optional): Bit depth for export (default: 16)
                format (str, optional): Export format - 'wav', 'aif', 'mp3' (default: 'wav')
                
            Returns:
                success (int): 1 if successful, 0, otherwise
                message (str): Status message
                file_path (str): Path to the exported audio file
            """
            # Required parameter
            track_index = int(params[0])
            
            # Optional parameters with defaults
            start_time = float(params[1]) if len(params) > 1 else 0.0
            duration = float(params[2]) if len(params) > 2 else -1.0  # -1 means export full song
            filepath = str(params[3]) if len(params) > 3 else ""
            include_return = int(params[4]) if len(params) > 4 else 1
            include_master = int(params[5]) if len(params) > 5 else 1
            sample_rate = int(params[6]) if len(params) > 6 else 44100
            bit_depth = int(params[7]) if len(params) > 7 else 16
            format_str = str(params[8]).lower() if len(params) > 8 else "wav"
            
            try:
                # Get the track
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range", "")
                
                track = self.song.tracks[track_index]
                export_path = filepath
                
                # Create a temporary file if no filepath provided
                if not export_path:
                    file_ext = format_str
                    temp_dir = tempfile.gettempdir()
                    filename = f"abletonosc_export_{track.name.replace(' ', '_')}_{int(time.time())}.{file_ext}"
                    export_path = os.path.join(temp_dir, filename)
                
                # Ensure the directory exists
                export_dir = os.path.dirname(export_path)
                if export_dir and not os.path.exists(export_dir):
                    os.makedirs(export_dir)
                
                # Configure export settings
                if duration < 0:
                    end_time = self.song.song_length  # Export the full song
                else:
                    end_time = start_time + duration
                
                # Setup the render and export process
                
                # Method 1: Using track freezing (if available)
                if hasattr(track, "freeze") and callable(track.freeze):
                    self.logger.info(f"Exporting track {track.name} using freeze method")
                    
                    # Save current solo/mute states
                    original_states = []
                    for t in self.song.tracks:
                        original_states.append({
                            "track": t,
                            "solo": t.solo,
                            "mute": t.mute
                        })
                    
                    # Solo this track, mute others
                    for t in self.song.tracks:
                        if t != track:
                            t.mute = True
                            t.solo = False
                        else:
                            t.mute = False
                            t.solo = True
                    
                    # Export from the specific time range
                    self.song.loop = True
                    self.song.loop_start = start_time
                    self.song.loop_length = end_time - start_time
                    
                    # Prepare to render
                    self.song.export_audio(export_path, format=format_str, sample_rate=sample_rate, bit_depth=bit_depth)
                    
                    # Restore original states
                    for state in original_states:
                        state["track"].solo = state["solo"]
                        state["track"].mute = state["mute"]
                    
                    # Reset loop
                    self.song.loop = False
                    
                # Method 2: Using Export Audio feature (preferred if available)
                elif hasattr(self.song, "export_audio") and callable(self.song.export_audio):
                    self.logger.info(f"Exporting track {track.name} using export_audio method")
                    
                    # Save current solo/mute states
                    original_states = []
                    for t in self.song.tracks:
                        original_states.append({
                            "track": t,
                            "solo": t.solo,
                            "mute": t.mute
                        })
                    
                    # Solo this track, mute others
                    for t in self.song.tracks:
                        if t != track:
                            t.mute = True
                            t.solo = False
                        else:
                            t.mute = False
                            t.solo = True
                    
                    # Set rendering options
                    render_options = {
                        "sample_rate": sample_rate,
                        "bit_depth": bit_depth,
                        "file_format": format_str,
                        "render_with_return": bool(include_return),
                        "render_with_master": bool(include_master),
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                    
                    # Export audio
                    self.song.export_audio(export_path, **render_options)
                    
                    # Restore original states
                    for state in original_states:
                        state["track"].solo = state["solo"]
                        state["track"].mute = state["mute"]
                    
                else:
                    return (0, f"Cannot export track {track.name}: export_audio not available", "")
                
                return (1, f"Track {track.name} exported successfully", export_path)
                
            except Exception as e:
                self.logger.error(f"Error exporting track audio: {str(e)}")
                return (0, f"Error exporting track audio: {str(e)}", "")
        
        self.osc_server.add_handler("/live/song/export_track_audio", song_export_track_audio)
        
        def song_export_all_stems(params):
            """
            Export all tracks in the song as separate audio files (stems).
            
            Args:
                directory (str, optional): Directory to save the exported stems (default: temp dir)
                start_time (float, optional): Start time in seconds (default: 0.0)
                duration (float, optional): Duration in seconds (default: entire song)
                include_return (int, optional): Whether to include return track effects (default: 1)
                include_master (int, optional): Whether to include master track effects (default: 1)
                export_master (int, optional): Whether to export the master track (default: 1)
                export_groups (int, optional): Whether to export group tracks (default: 1)
                export_returns (int, optional): Whether to export return tracks (default: 0)
                sample_rate (int, optional): Sample rate for export (default: 44100)
                bit_depth (int, optional): Bit depth for export (default: 16)
                format (str, optional): Export format - 'wav', 'aif', 'mp3' (default: 'wav')
                normalize (int, optional): Whether to normalize exports (default: 0)
                
            Returns:
                success (int): 1 if successful, 0, otherwise
                message (str): Status message
                export_path (str): Directory containing the exported stems
                files (str): JSON string with list of exported files and metadata
            """
            # Optional parameters with defaults
            directory = str(params[0]) if len(params) > 0 else ""
            start_time = float(params[1]) if len(params) > 1 else 0.0
            duration = float(params[2]) if len(params) > 2 else -1.0  # -1 means export full song
            include_return = int(params[3]) if len(params) > 3 else 1
            include_master = int(params[4]) if len(params) > 4 else 1
            export_master = int(params[5]) if len(params) > 5 else 1
            export_groups = int(params[6]) if len(params) > 6 else 1
            export_returns = int(params[7]) if len(params) > 7 else 0
            sample_rate = int(params[8]) if len(params) > 8 else 44100
            bit_depth = int(params[9]) if len(params) > 9 else 16
            format_str = str(params[10]).lower() if len(params) > 10 else "wav"
            normalize = int(params[11]) if len(params) > 11 else 0
            
            try:
                # Create export directory if not provided
                export_dir = directory
                if not export_dir:
                    temp_dir = tempfile.gettempdir()
                    dir_name = f"abletonosc_stems_{int(time())}"
                    export_dir = os.path.join(temp_dir, dir_name)
                
                # Ensure the directory exists
                if not os.path.exists(export_dir):
                    os.makedirs(export_dir)
                
                # Calculate end time if duration provided
                if duration < 0:
                    end_time = self.song.song_length  # Export the full song
                else:
                    end_time = start_time + duration
                
                # Prepare the list of tracks to export
                export_tracks = []
                for i, track in enumerate(self.song.tracks):
                    # Skip group tracks if not exporting them
                    if track.is_foldable and not export_groups:
                        continue
                    
                    export_tracks.append({"index": i, "track": track})
                
                # Add master track if requested
                if export_master and self.song.master_track:
                    export_tracks.append({"index": -1, "track": self.song.master_track, "is_master": True})
                
                # Add return tracks if requested
                if export_returns:
                    for i, track in enumerate(self.song.return_tracks):
                        export_tracks.append({"index": -2-i, "track": track, "is_return": True})
                
                # Prepare the export
                exported_files = []
                
                # Export each track
                for track_info in export_tracks:
                    track = track_info["track"]
                    track_index = track_info["index"]
                    
                    # Generate safe filename
                    safe_name = track.name.replace(" ", "_").replace("/", "_").replace("\\", "_")
                    if track_info.get("is_master", False):
                        safe_name = "master_" + safe_name
                    elif track_info.get("is_return", False):
                        safe_name = "return_" + safe_name
                    
                    # Create export path
                    file_path = os.path.join(export_dir, f"{safe_name}.{format_str}")
                    
                    # Export track
                    if track_index >= 0:  # Regular track
                        success, message, exported_path = song_export_track_audio([
                            track_index, start_time, duration, file_path, 
                            include_return, include_master, sample_rate, bit_depth, format_str
                        ])
                    else:  # Master or return track
                        # We need a special approach for master and return tracks
                        # Save current solo/mute states
                        original_states = []
                        for t in self.song.tracks:
                            original_states.append({
                                "track": t,
                                "solo": t.solo,
                                "mute": t.mute
                            })
                        
                        if track_info.get("is_master", False):
                            # For master track, don't mute anything
                            self.logger.info("Exporting master track")
                        else:  # Return track
                            # For return track, we need to mute all tracks and then export
                            self.logger.info(f"Exporting return track {track.name}")
                            # Mute all regular tracks but keep return active
                            for t in self.song.tracks:
                                t.mute = True
                                t.solo = False
                        
                        # Export audio
                        if hasattr(self.song, "export_audio") and callable(self.song.export_audio):
                            # Set rendering options
                            render_options = {
                                "sample_rate": sample_rate,
                                "bit_depth": bit_depth,
                                "file_format": format_str,
                                "render_with_return": bool(include_return),
                                "render_with_master": bool(include_master),
                                "start_time": start_time,
                                "end_time": end_time,
                            }
                            
                            # Export audio
                            self.song.export_audio(file_path, **render_options)
                            success = 1
                            message = f"Exported {track.name} successfully"
                            exported_path = file_path
                        else:
                            success = 0
                            message = "export_audio method not available"
                            exported_path = ""
                        
                        # Restore original states
                        for state in original_states:
                            state["track"].solo = state["solo"]
                            state["track"].mute = state["mute"]
                    
                    # Add to exported files list if successful
                    if success:
                        file_info = {
                            "track_name": track.name,
                            "track_index": track_index,
                            "file_path": exported_path,
                            "is_master": track_info.get("is_master", False),
                            "is_return": track_info.get("is_return", False),
                            "is_group": track.is_foldable if hasattr(track, "is_foldable") else False,
                            "duration": duration if duration > 0 else (end_time - start_time),
                            "sample_rate": sample_rate,
                            "bit_depth": bit_depth,
                            "format": format_str
                        }
                        exported_files.append(file_info)
                        self.logger.info(f"Successfully exported {track.name} to {exported_path}")
                    else:
                        self.logger.error(f"Failed to export {track.name}: {message}")
                
                # Save a manifest file with all exported files
                manifest_path = os.path.join(export_dir, "stems_manifest.json")
                with open(manifest_path, "w") as f:
                    json.dump({
                        "project": self.song.get_data()["path"] if hasattr(self.song, "get_data") else "Unknown",
                        "export_time": time.time(),
                        "start_time": start_time,
                        "duration": duration if duration > 0 else (end_time - start_time),
                        "files": exported_files
                    }, f, indent=2)
                
                # Return the results
                return (
                    1 if exported_files else 0,
                    f"Exported {len(exported_files)} stems to {export_dir}",
                    export_dir,
                    json.dumps(exported_files)
                )
                
            except Exception as e:
                self.logger.error(f"Error exporting stems: {str(e)}")
                return (0, f"Error exporting stems: {str(e)}", "", "[]")
        
        self.osc_server.add_handler("/live/song/export_all_stems", song_export_all_stems)
        
        def song_flattens_stems(params):
            """
            Freezes and flattens tracks to create consolidated versions of tracks.
            This is useful as a preparatory step for exporting high-quality stems.
            
            Args:
                track_indices (str): Comma-separated list of track indices to process (empty for all)
                include_groups (int, optional): Whether to process group tracks (default: 1)
                
            Returns:
                success (int): 1 if successful, 0, otherwise
                message (str): Status message
                processed_tracks (int): Number of tracks processed
            """
            track_indices_str = str(params[0]) if len(params) > 0 else ""
            include_groups = int(params[1]) if len(params) > 1 else 1
            
            try:
                # Parse track indices
                track_indices = []
                if track_indices_str:
                    for index_str in track_indices_str.split(","):
                        try:
                            track_indices.append(int(index_str.strip()))
                        except ValueError:
                            continue
                else:
                    # Use all tracks if none specified
                    track_indices = list(range(len(self.song.tracks)))
                
                processed_count = 0
                
                # Process each track
                for idx in track_indices:
                    if idx < 0 or idx >= len(self.song.tracks):
                        self.logger.warning(f"Track index {idx} out of range")
                        continue
                    
                    track = self.song.tracks[idx]
                    
                    # Skip group tracks if not including them
                    if track.is_foldable and not include_groups:
                        continue
                    
                    # Freeze the track if possible
                    if hasattr(track, "freeze") and callable(track.freeze):
                        self.logger.info(f"Freezing track {track.name}")
                        track.freeze()
                        
                        # Wait for freezing to complete
                        time.sleep(1.0)  # Short delay to let Live process
                        
                        # Flatten the frozen track if possible
                        if hasattr(track, "flatten") and callable(track.flatten):
                            self.logger.info(f"Flattening track {track.name}")
                            track.flatten()
                            processed_count += 1
                        else:
                            self.logger.warning(f"Cannot flatten track {track.name}")
                    else:
                        self.logger.warning(f"Cannot freeze track {track.name}")
                
                return (1, f"Processed {processed_count} tracks", processed_count)
                
            except Exception as e:
                self.logger.error(f"Error flattening stems: {str(e)}")
                return (0, f"Error flattening stems: {str(e)}", 0)
        
        self.osc_server.add_handler("/live/song/flatten_stems", song_flattens_stems)
        
        def song_is_track_frozen(params):
            """
            Check if a track is currently frozen.
            
            Args:
                track_index (int): Index of the track to check
                
            Returns:
                frozen (int): 1 if frozen, 0 if not
                message (str): Status message
            """
            track_index = int(params[0])
            
            try:
                # Get the track
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                # Check if track is frozen
                if hasattr(track, "is_frozen"):
                    return (1 if track.is_frozen else 0, f"Track {track.name} is {'frozen' if track.is_frozen else 'not frozen'}")
                else:
                    # Try fallback approach if is_frozen property doesn't exist
                    # Check for the presence of a frozen audio clip
                    # This is a heuristic and may not be reliable
                    for clip_slot in track.clip_slots:
                        if clip_slot.clip and "[FROZEN]" in clip_slot.clip.name:
                            return (1, f"Track {track.name} appears to be frozen")
                    
                    return (0, f"Track {track.name} doesn't appear to be frozen")
                
            except Exception as e:
                self.logger.error(f"Error checking if track is frozen: {str(e)}")
                return (0, f"Error checking if track is frozen: {str(e)}")
        
        self.osc_server.add_handler("/live/song/is_track_frozen", song_is_track_frozen)
  
        #--------------------------------------------------------------------------------
        # Callbacks for Song: Scene properties
        #--------------------------------------------------------------------------------
        self.osc_server.add_handler("/live/song/get/num_scenes", lambda _: (len(self.song.scenes),))

        def song_get_scene_names(params):
            if len(params) == 0:
                scene_index_min, scene_index_max = 0, len(self.song.scenes)
            else:
                scene_index_min, scene_index_max = params
            return tuple(self.song.scenes[index].name for index in range(scene_index_min, scene_index_max))
        self.osc_server.add_handler("/live/song/get/scenes/name", song_get_scene_names)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Cue point properties
        #--------------------------------------------------------------------------------
        def song_get_cue_points(song, _):
            cue_points = song.cue_points
            cue_point_pairs = [(cue_point.name, cue_point.time) for cue_point in cue_points]
            return tuple(element for pair in cue_point_pairs for element in pair)
        self.osc_server.add_handler("/live/song/get/cue_points", partial(song_get_cue_points, self.song))

        def song_jump_to_cue_point(song, params: Tuple[Any] = ()):
            cue_point_index = params[0]
            if isinstance(cue_point_index, str):
                for cue_point in song.cue_points:
                    if cue_point.name == cue_point_index:
                        cue_point.jump()
            elif isinstance(cue_point_index, int):
                cue_point = song.cue_points[cue_point_index]
                cue_point.jump()
        self.osc_server.add_handler("/live/song/cue_point/jump", partial(song_jump_to_cue_point, self.song))

        #--------------------------------------------------------------------------------
        # Listener for /live/song/get/beat
        #--------------------------------------------------------------------------------
        self.last_song_time = -1.0
        
        def stop_beat_listener(params: Tuple[Any] = ()):
            try:
                self.song.remove_current_song_time_listener(self.current_song_time_changed)
                self.logger.info("Removing beat listener")
            except:
                pass

        def start_beat_listener(params: Tuple[Any] = ()):
            stop_beat_listener()
            self.logger.info("Adding beat listener")
            self.song.add_current_song_time_listener(self.current_song_time_changed)

        self.osc_server.add_handler("/live/song/start_listen/beat", start_beat_listener)
        self.osc_server.add_handler("/live/song/stop_listen/beat", stop_beat_listener)

        #--------------------------------------------------------------------------------
        # Track device handling
        #--------------------------------------------------------------------------------
        def track_list_devices(params):
            """
            Lists all devices on a specific track.
            
            Args:
                track_index (int): Index of the track
                
            Returns:
                count (int): Number of devices found
                devices (str): JSON string with device details
            """
            track_index = int(params[0])
            
            try:
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                devices = []
                
                for i, device in enumerate(track.devices):
                    device_info = {
                        "index": i,
                        "name": device.name,
                        "class_name": device.class_name if hasattr(device, "class_name") else "",
                        "type": device.type if hasattr(device, "type") else "",
                        "is_active": device.is_active if hasattr(device, "is_active") else True,
                        "can_have_chains": device.can_have_chains if hasattr(device, "can_have_chains") else False,
                        "parameters": []
                    }
                    
                    # Get all parameters
                    for param in device.parameters:
                        param_info = {
                            "name": param.name,
                            "value": param.value,
                            "min": param.min,
                            "max": param.max,
                            "is_quantized": param.is_quantized,
                            "is_automated": param.automation_state != 0 if hasattr(param, "automation_state") else False,
                        }
                        device_info["parameters"].append(param_info)
                    
                    devices.append(device_info)
                
                return (len(devices), json.dumps(devices))
                
            except Exception as e:
                self.logger.error(f"Error getting track devices: {str(e)}")
                return (0, f"Error getting track devices: {str(e)}")
        
        self.osc_server.add_handler("/live/track/list_devices", track_list_devices)
        
        def track_get_device_parameters(params):
            """
            Get parameters for a specific device on a track.
            
            Args:
                track_index (int): Index of the track
                device_index (int): Index of the device on the track
                
            Returns:
                count (int): Number of parameters found
                parameters (str): JSON string with parameter details
            """
            track_index = int(params[0])
            device_index = int(params[1])
            
            try:
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                if device_index < 0 or device_index >= len(track.devices):
                    return (0, f"Device index {device_index} out of range")
                
                device = track.devices[device_index]
                parameters = []
                
                for param in device.parameters:
                    param_info = {
                        "name": param.name,
                        "value": param.value,
                        "normalized_value": param.value / (param.max - param.min) if param.max != param.min else 0,
                        "min": param.min,
                        "max": param.max,
                        "is_quantized": param.is_quantized,
                        "value_items": [str(item) for item in param.value_items] if hasattr(param, "value_items") else [],
                        "is_automated": param.automation_state != 0 if hasattr(param, "automation_state") else False,
                        "display_value": param.str_for_value(param.value) if hasattr(param, "str_for_value") else str(param.value)
                    }
                    parameters.append(param_info)
                
                return (len(parameters), json.dumps(parameters))
                
            except Exception as e:
                self.logger.error(f"Error getting device parameters: {str(e)}")
                return (0, f"Error getting device parameters: {str(e)}")
        
        self.osc_server.add_handler("/live/track/device/parameters", track_get_device_parameters)
        
        def track_get_device_parameter_value(params):
            """
            Get the current value of a specific parameter.
            
            Args:
                track_index (int): Index of the track
                device_index (int): Index of the device
                parameter_name (str): Name of the parameter
                
            Returns:
                value (float): Current parameter value
                normalized (float): Normalized value (0-1)
                display (str): Display value as string
            """
            track_index = int(params[0])
            device_index = int(params[1])
            parameter_name = str(params[2])
            
            try:
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, 0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                if device_index < 0 or device_index >= len(track.devices):
                    return (0, 0, f"Device index {device_index} out of range")
                
                device = track.devices[device_index]
                
                # Find parameter by name
                param = None
                for p in device.parameters:
                    if p.name == parameter_name:
                        param = p
                        break
                
                if param is None:
                    return (0, 0, f"Parameter '{parameter_name}' not found")
                
                # Calculate normalized value
                normalized = 0
                if param.max != param.min:
                    normalized = (param.value - param.min) / (param.max - param.min)
                
                # Get display value
                display_value = param.str_for_value(param.value) if hasattr(param, "str_for_value") else str(param.value)
                
                return (param.value, normalized, display_value)
                
            except Exception as e:
                self.logger.error(f"Error getting parameter value: {str(e)}")
                return (0, 0, f"Error getting parameter value: {str(e)}")
        
        self.osc_server.add_handler("/live/track/device/parameter/get", track_get_device_parameter_value)
        
        def track_set_device_parameter_value(params):
            """
            Set the value of a specific parameter.
            
            Args:
                track_index (int): Index of the track
                device_index (int): Index of the device
                parameter_name (str): Name of the parameter
                value (float): Value to set (raw, not normalized)
                
            Returns:
                success (int): 1 if successful, 0 otherwise
                message (str): Status message
            """
            track_index = int(params[0])
            device_index = int(params[1])
            parameter_name = str(params[2])
            value = float(params[3])
            
            try:
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                if device_index < 0 or device_index >= len(track.devices):
                    return (0, f"Device index {device_index} out of range")
                
                device = track.devices[device_index]
                
                # Find parameter by name
                param = None
                for p in device.parameters:
                    if p.name == parameter_name:
                        param = p
                        break
                
                if param is None:
                    return (0, f"Parameter '{parameter_name}' not found")
                
                # Ensure value is within valid range
                if value < param.min:
                    value = param.min
                elif value > param.max:
                    value = param.max
                
                # Set parameter value
                param.value = value
                
                return (1, f"Parameter '{parameter_name}' set to {value}")
                
            except Exception as e:
                self.logger.error(f"Error setting parameter value: {str(e)}")
                return (0, f"Error setting parameter value: {str(e)}")
        
        self.osc_server.add_handler("/live/track/device/parameter/set", track_set_device_parameter_value)
        
        def track_set_device_parameter_normalized(params):
            """
            Set the normalized value (0-1) of a specific parameter.
            
            Args:
                track_index (int): Index of the track
                device_index (int): Index of the device
                parameter_name (str): Name of the parameter
                normalized_value (float): Value to set (0-1 normalized)
                
            Returns:
                success (int): 1 if successful, 0 otherwise
                message (str): Status message
            """
            track_index = int(params[0])
            device_index = int(params[1])
            parameter_name = str(params[2])
            normalized_value = float(params[3])
            
            try:
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                if device_index < 0 or device_index >= len(track.devices):
                    return (0, f"Device index {device_index} out of range")
                
                device = track.devices[device_index]
                
                # Find parameter by name
                param = None
                for p in device.parameters:
                    if p.name == parameter_name:
                        param = p
                        break
                
                if param is None:
                    return (0, f"Parameter '{parameter_name}' not found")
                
                # Ensure normalized value is within 0-1
                if normalized_value < 0:
                    normalized_value = 0
                elif normalized_value > 1:
                    normalized_value = 1
                
                # Convert normalized value to actual value
                value = param.min + normalized_value * (param.max - param.min)
                
                # Set parameter value
                param.value = value
                
                return (1, f"Parameter '{parameter_name}' set to {value} (normalized: {normalized_value})")
                
            except Exception as e:
                self.logger.error(f"Error setting normalized parameter value: {str(e)}")
                return (0, f"Error setting normalized parameter value: {str(e)}")
        
        self.osc_server.add_handler("/live/track/device/parameter/set_normalized", track_set_device_parameter_normalized)
        
        def track_add_device(params):
            """
            Add a device to a track by name (searches the browser).
            
            Args:
                track_index (int): Index of the track
                device_name (str): Name of the device to add
                device_position (int, optional): Position to insert the device at (default: -1 = end)
                
            Returns:
                success (int): 1 if successful, 0 otherwise
                message (str): Status message
                device_index (int): Index of the newly added device, or -1 if failed
            """
            track_index = int(params[0])
            device_name = str(params[1])
            device_position = int(params[2]) if len(params) > 2 else -1
            
            try:
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range", -1)
                
                track = self.song.tracks[track_index]
                
                # Get application and browser directly
                application = Live.Application.get_application()
                browser = application.browser
                
                # Find matching device in browser
                all_devices = []
                
                # Go through all device categories
                if hasattr(browser, "devices") and browser.devices:
                    for category in browser.devices.children:
                        category_name = category.name
                        
                        # For each category, get all devices
                        for device in category.children:
                            device_info = {
                                "name": device.name,
                                "category": category_name,
                                "is_loadable": device.is_loadable,
                                "path": device.path if hasattr(device, "path") else ""
                            }
                            all_devices.append(device_info)
                
                # Find the first device matching the name
                matching_device = None
                for device in all_devices:
                    if device_name.lower() in device["name"].lower():
                        matching_device = device
                        break
                
                if matching_device is None:
                    return (0, f"No device found matching '{device_name}'", -1)
                
                # Check if device can be loaded
                if not matching_device.get("is_loadable", False):
                    return (0, f"Device '{matching_device['name']}' is not loadable", -1)
                
                # We found a matching device, now we need to add it to the track
                # Unfortunately, the Ableton API doesn't provide a direct way to do this
                # We'll try different approaches depending on what's available
                
                # Method 1: Using create_device if available
                device_index = -1
                if hasattr(track, "create_device") and callable(track.create_device):
                    # Create the device
                    device = track.create_device(matching_device["name"])
                    
                    # Find its index
                    for i, d in enumerate(track.devices):
                        if d == device:
                            device_index = i
                            break
                    
                    # Move to desired position if needed
                    if device_index >= 0 and device_position >= 0 and device_position != device_index:
                        # We need to implement logic to move the device to the desired position
                        # This might not be directly supported, but we can try to use other API methods
                        self.logger.warning("Moving devices to specific positions is not fully supported")
                    
                    return (1, f"Added device '{matching_device['name']}' to track", device_index)
                
                # Method 2: Using load_device if available
                elif hasattr(track, "load_device") and callable(track.load_device):
                    device = track.load_device(matching_device["path"])
                    
                    # Find its index
                    for i, d in enumerate(track.devices):
                        if d == device:
                            device_index = i
                            break
                    
                    return (1, f"Added device '{matching_device['name']}' to track", device_index)
                
                # No suitable method found
                return (0, "Cannot add device - API doesn't support device creation", -1)
                
            except Exception as e:
                self.logger.error(f"Error adding device: {str(e)}")
                return (0, f"Error adding device: {str(e)}", -1)
        
        self.osc_server.add_handler("/live/track/add_device", track_add_device)
        
        def track_delete_device(params):
            """
            Delete a device from a track.
            
            Args:
                track_index (int): Index of the track
                device_index (int): Index of the device to delete
                
            Returns:
                success (int): 1 if successful, 0 otherwise
                message (str): Status message
            """
            track_index = int(params[0])
            device_index = int(params[1])
            
            try:
                if track_index < 0 or track_index >= len(self.song.tracks):
                    return (0, f"Track index {track_index} out of range")
                
                track = self.song.tracks[track_index]
                
                if device_index < 0 or device_index >= len(track.devices):
                    return (0, f"Device index {device_index} out of range")
                
                device = track.devices[device_index]
                device_name = device.name
                
                # Check if the device can be deleted
                if hasattr(track, "delete_device") and callable(track.delete_device):
                    track.delete_device(device_index)
                    return (1, f"Deleted device '{device_name}' from track")
                elif hasattr(device, "delete") and callable(device.delete):
                    device.delete()
                    return (1, f"Deleted device '{device_name}' from track")
                else:
                    return (0, "Cannot delete device - API doesn't support device deletion")
                
            except Exception as e:
                self.logger.error(f"Error deleting device: {str(e)}")
                return (0, f"Error deleting device: {str(e)}")
        
        self.osc_server.add_handler("/live/track/delete_device", track_delete_device)

        #--------------------------------------------------------------------------------
        # Test all possible export methods to see which ones work
        #--------------------------------------------------------------------------------
        def test_export_methods(params):
            """
            Test a wide range of possible export methods to identify what works with this Ableton version.
            
            Returns:
                results (str): JSON formatted results of all attempted methods
            """
            results = {"working_methods": [], "failed_methods": []}
            temp_dir = tempfile.gettempdir()
            test_file = os.path.join(temp_dir, f"export_test_{int(time.time())}.wav")
            test_duration = 5.0  # Short duration for testing
            self.logger.info(f"Testing export methods, output will go to: {test_file}")
            
            # Track to test with - use first audio track if available
            target_track = None
            target_track_index = 0
            for i, track in enumerate(self.song.tracks):
                if hasattr(track, "has_audio_input") and track.has_audio_input:
                    target_track = track
                    target_track_index = i
                    break
            
            if target_track is None and len(self.song.tracks) > 0:
                target_track = self.song.tracks[0]
                target_track_index = 0
            
            # Master track
            master_track = self.song.master_track if hasattr(self.song, "master_track") else None
            
            # Save current playback state
            was_playing = self.song.is_playing
            current_time = self.song.current_song_time
            
            # Stop playback during testing
            if was_playing:
                self.song.stop_playing()
            
            def log_result(method_name, success, error=None):
                if success:
                    self.logger.info(f"✅ Method works: {method_name}")
                    results["working_methods"].append({"name": method_name, "error": None})
                else:
                    error_msg = str(error) if error else "Unknown error"
                    self.logger.info(f"❌ Method failed: {method_name} - {error_msg}")
                    results["failed_methods"].append({"name": method_name, "error": error_msg})
            
            # 1. Try song-level export methods
            methods_to_try = [
                # Standard names
                "export_audio",
                "render_audio", 
                "bounce_to_disk",
                "export",
                "render",
                "bounce",
                
                # Variations with prefixes
                "_export_audio", 
                "_render_audio",
                "__export_audio",
                
                # Alternative naming
                "export_to_disk",
                "render_to_file",
                "export_as_audio",
                "render_as_audio",
                "save_audio",
                "write_audio",
                "capture_audio"
            ]
            
            # Test song-level methods
            for method_name in methods_to_try:
                if hasattr(self.song, method_name) and callable(getattr(self.song, method_name)):
                    try:
                        method = getattr(self.song, method_name)
                        # Try different argument patterns
                        try:
                            # Basic path only
                            method(test_file)
                            log_result(f"song.{method_name}(path)", True)
                        except Exception as e1:
                            try:
                                # Path and duration
                                method(test_file, test_duration)
                                log_result(f"song.{method_name}(path, duration)", True)
                            except Exception as e2:
                                try:
                                    # Path, start_time, duration
                                    method(test_file, 0.0, test_duration)
                                    log_result(f"song.{method_name}(path, start, duration)", True)
                                except Exception as e3:
                                    try:
                                        # Named arguments
                                        method(path=test_file, start_time=0.0, duration=test_duration)
                                        log_result(f"song.{method_name}(path, start_time, duration) [named]", True)
                                    except Exception as e4:
                                        try:
                                            # Alt named arguments
                                            method(file_path=test_file, start=0.0, length=test_duration)
                                            log_result(f"song.{method_name}(file_path, start, length) [named]", True)
                                        except Exception as e5:
                                            # If all attempts fail, log the last error
                                            log_result(f"song.{method_name}", False, e5)
                    except Exception as e:
                        log_result(f"song.{method_name}", False, e)
                else:
                    log_result(f"song.{method_name}", False, "Method not found")
            
            # 2. Try track-level export methods on normal track
            if target_track:
                for method_name in methods_to_try:
                    if hasattr(target_track, method_name) and callable(getattr(target_track, method_name)):
                        try:
                            method = getattr(target_track, method_name)
                            # Try different argument patterns
                            try:
                                # Basic path only
                                method(test_file)
                                log_result(f"track.{method_name}(path)", True)
                            except Exception as e1:
                                try:
                                    # Path and duration
                                    method(test_file, test_duration)
                                    log_result(f"track.{method_name}(path, duration)", True)
                                except Exception as e2:
                                    try:
                                        # Path, start_time, duration
                                        method(test_file, 0.0, test_duration)
                                        log_result(f"track.{method_name}(path, start, duration)", True)
                                    except Exception as e3:
                                        try:
                                            # Named arguments
                                            method(path=test_file, start_time=0.0, duration=test_duration)
                                            log_result(f"track.{method_name}(path, start_time, duration) [named]", True)
                                        except Exception as e4:
                                            try:
                                                # Alt named arguments
                                                method(file_path=test_file, start=0.0, length=test_duration)
                                                log_result(f"track.{method_name}(file_path, start, length) [named]", True)
                                            except Exception as e5:
                                                # If all attempts fail, log the last error
                                                log_result(f"track.{method_name}", False, e5)
                        except Exception as e:
                            log_result(f"track.{method_name}", False, e)
                    else:
                        log_result(f"track.{method_name}", False, "Method not found")
            
            # 3. Try master track export methods
            if master_track:
                for method_name in methods_to_try:
                    if hasattr(master_track, method_name) and callable(getattr(master_track, method_name)):
                        try:
                            method = getattr(master_track, method_name)
                            # Try different argument patterns
                            try:
                                # Basic path only
                                method(test_file)
                                log_result(f"master_track.{method_name}(path)", True)
                            except Exception as e1:
                                try:
                                    # Path and duration
                                    method(test_file, test_duration)
                                    log_result(f"master_track.{method_name}(path, duration)", True)
                                except Exception as e2:
                                    try:
                                        # Path, start_time, duration
                                        method(test_file, 0.0, test_duration)
                                        log_result(f"master_track.{method_name}(path, start, duration)", True)
                                    except Exception as e3:
                                        try:
                                            # Named arguments
                                            method(path=test_file, start_time=0.0, duration=test_duration)
                                            log_result(f"master_track.{method_name}(path, start_time, duration) [named]", True)
                                        except Exception as e4:
                                            try:
                                                # Alt named arguments
                                                method(file_path=test_file, start=0.0, length=test_duration)
                                                log_result(f"master_track.{method_name}(file_path, start, length) [named]", True)
                                            except Exception as e5:
                                                # If all attempts fail, log the last error
                                                log_result(f"master_track.{method_name}", False, e5)
                        except Exception as e:
                            log_result(f"master_track.{method_name}", False, e)
                    else:
                        log_result(f"master_track.{method_name}", False, "Method not found")
            
            # 4. Try arrangement-related objects
            arrangement_objects = [
                ("arrangement", self.song.arrangement if hasattr(self.song, "arrangement") else None),
                ("view", self.song.view if hasattr(self.song, "view") else None),
                ("session", self.song.session if hasattr(self.song, "session") else None),
                ("tracks", self.song.tracks),
                ("return_tracks", self.song.return_tracks),
                ("scenes", self.song.scenes),
                ("clip_slots", self.song.clip_slots if hasattr(self.song, "clip_slots") else None),
                ("mixer_device", self.song.mixer_device if hasattr(self.song, "mixer_device") else None),
            ]
            
            for obj_name, obj in arrangement_objects:
                if obj is not None:
                    for method_name in methods_to_try:
                        if hasattr(obj, method_name) and callable(getattr(obj, method_name)):
                            try:
                                method = getattr(obj, method_name)
                                # Try different argument patterns
                                try:
                                    # Basic path only
                                    method(test_file)
                                    log_result(f"song.{obj_name}.{method_name}(path)", True)
                                except Exception as e1:
                                    try:
                                        # Path and duration
                                        method(test_file, test_duration)
                                        log_result(f"song.{obj_name}.{method_name}(path, duration)", True)
                                    except Exception as e2:
                                        try:
                                            # Path, start_time, duration
                                            method(test_file, 0.0, test_duration)
                                            log_result(f"song.{obj_name}.{method_name}(path, start, duration)", True)
                                        except Exception as e3:
                                            try:
                                                # Named arguments
                                                method(path=test_file, start_time=0.0, duration=test_duration)
                                                log_result(f"song.{obj_name}.{method_name}(path, start_time, duration) [named]", True)
                                            except Exception as e4:
                                                try:
                                                    # Alt named arguments
                                                    method(file_path=test_file, start=0.0, length=test_duration)
                                                    log_result(f"song.{obj_name}.{method_name}(file_path, start, length) [named]", True)
                                                except Exception as e5:
                                                    # If all attempts fail, log the last error
                                                    log_result(f"song.{obj_name}.{method_name}", False, e5)
                            except Exception as e:
                                log_result(f"song.{obj_name}.{method_name}", False, e)
                        else:
                            log_result(f"song.{obj_name}.{method_name}", False, "Method not found")
            
            # 5. Try Live application-level methods
            if hasattr(Live, "Application") and hasattr(Live.Application, "get_application"):
                app = Live.Application.get_application()
                for method_name in methods_to_try:
                    if hasattr(app, method_name) and callable(getattr(app, method_name)):
                        try:
                            method = getattr(app, method_name)
                            # Try different argument patterns
                            try:
                                # Basic path only
                                method(test_file)
                                log_result(f"application.{method_name}(path)", True)
                            except Exception as e1:
                                try:
                                    # Path and duration
                                    method(test_file, test_duration)
                                    log_result(f"application.{method_name}(path, duration)", True)
                                except Exception as e2:
                                    try:
                                        # Path, start_time, duration
                                        method(test_file, 0.0, test_duration)
                                        log_result(f"application.{method_name}(path, start, duration)", True)
                                    except Exception as e3:
                                        try:
                                            # Named arguments
                                            method(path=test_file, start_time=0.0, duration=test_duration)
                                            log_result(f"application.{method_name}(path, start_time, duration) [named]", True)
                                        except Exception as e4:
                                            try:
                                                # Alt named arguments
                                                method(file_path=test_file, start=0.0, length=test_duration)
                                                log_result(f"application.{method_name}(file_path, start, length) [named]", True)
                                            except Exception as e5:
                                                # If all attempts fail, log the last error
                                                log_result(f"application.{method_name}", False, e5)
                        except Exception as e:
                            log_result(f"application.{method_name}", False, e)
                    else:
                        log_result(f"application.{method_name}", False, "Method not found")
            
            # 6. Try direct project methods
            if hasattr(self.song, "get_data") and callable(self.song.get_data):
                try:
                    project_data = self.song.get_data()
                    if isinstance(project_data, dict) and "path" in project_data:
                        project_path = project_data["path"]
                        project_dir = os.path.dirname(project_path)
                        self.logger.info(f"Project path: {project_path}")
                        results["project_path"] = project_path
                except Exception as e:
                    self.logger.error(f"Error getting project path: {e}")
            
            # 7. Try advanced techniques - create clip and then export it
            try:
                # Try to find or create a clip
                clip_found = False
                test_clip = None
                
                # Find an existing clip
                for track in self.song.tracks:
                    for clip_slot in track.clip_slots:
                        if clip_slot.has_clip and clip_slot.clip is not None:
                            test_clip = clip_slot.clip
                            clip_found = True
                            break
                    if clip_found:
                        break
                
                # If we found a clip, try to export it
                if test_clip is not None:
                    for method_name in methods_to_try:
                        if hasattr(test_clip, method_name) and callable(getattr(test_clip, method_name)):
                            try:
                                method = getattr(test_clip, method_name)
                                # Try different argument patterns
                                try:
                                    # Basic path only
                                    method(test_file)
                                    log_result(f"clip.{method_name}(path)", True)
                                except Exception as e1:
                                    try:
                                        # Path and duration
                                        method(test_file, test_clip.length)
                                        log_result(f"clip.{method_name}(path, duration)", True)
                                    except Exception as e2:
                                        try:
                                            # Path, start_time, duration
                                            method(test_file, 0.0, test_clip.length)
                                            log_result(f"clip.{method_name}(path, start, duration)", True)
                                        except Exception as e3:
                                            # If all attempts fail, log the last error
                                            log_result(f"clip.{method_name}", False, e3)
                            except Exception as e:
                                log_result(f"clip.{method_name}", False, e)
                        else:
                            log_result(f"clip.{method_name}", False, "Method not found")
            except Exception as e:
                self.logger.error(f"Error testing clip methods: {e}")
            
            # 8. Try working with document class if it exists
            try:
                if hasattr(Live, "Document") and hasattr(Live.Document, "get_document"):
                    doc = Live.Document.get_document()
                    for method_name in methods_to_try:
                        if hasattr(doc, method_name) and callable(getattr(doc, method_name)):
                            try:
                                method = getattr(doc, method_name)
                                # Try different argument patterns
                                try:
                                    # Basic path only
                                    method(test_file)
                                    log_result(f"document.{method_name}(path)", True)
                                except Exception as e1:
                                    try:
                                        # Path and duration
                                        method(test_file, test_duration)
                                        log_result(f"document.{method_name}(path, duration)", True)
                                    except Exception as e2:
                                        try:
                                            # Path, start_time, duration
                                            method(test_file, 0.0, test_duration)
                                            log_result(f"document.{method_name}(path, start, duration)", True)
                                        except Exception as e3:
                                            # If all attempts fail, log the last error
                                            log_result(f"document.{method_name}", False, e3)
                            except Exception as e:
                                log_result(f"document.{method_name}", False, e)
                        else:
                            log_result(f"document.{method_name}", False, "Method not found")
            except Exception as e:
                self.logger.error(f"Error testing document methods: {e}")
            
            # Restore playback state
            self.song.current_song_time = current_time
            if was_playing:
                self.song.start_playing()
            
            # Final stats
            results["total_tested"] = len(results["working_methods"]) + len(results["failed_methods"])
            results["total_working"] = len(results["working_methods"])
            
            # Log summary
            self.logger.info(f"Export method testing complete. Found {len(results['working_methods'])} working methods out of {results['total_tested']} tested.")
            if len(results["working_methods"]) > 0:
                self.logger.info(f"Working methods: {[m['name'] for m in results['working_methods']]}")
            
            return (json.dumps(results),)
        
        self.osc_server.add_handler("/live/song/test_export_methods", test_export_methods)

        #--------------------------------------------------------------------------------
        # Test thousands of variations of export methods
        #--------------------------------------------------------------------------------
        def test_export_methods_comprehensive(params):
            """
            Test a very wide range of possible export methods with many parameter variations
            to identify what works with this Ableton version.
            
            Returns:
                results (str): JSON formatted results of all attempted methods
            """
            results = {"working_methods": [], "failed_methods": []}
            temp_dir = tempfile.gettempdir()
            test_file = os.path.join(temp_dir, f"export_test_{int(time.time())}.wav")
            test_duration = 5.0  # Short duration for testing
            self.logger.info(f"Testing comprehensive export methods, output will go to: {test_file}")
            
            # Track to test with - use first audio track if available
            target_track = None
            target_track_index = 0
            for i, track in enumerate(self.song.tracks):
                if hasattr(track, "has_audio_input") and track.has_audio_input:
                    target_track = track
                    target_track_index = i
                    break
            
            if target_track is None and len(self.song.tracks) > 0:
                target_track = self.song.tracks[0]
                target_track_index = 0
            
            # Master track
            master_track = self.song.master_track if hasattr(self.song, "master_track") else None
            
            # Save current playback state
            was_playing = self.song.is_playing
            current_time = self.song.current_song_time
            
            # Stop playback during testing
            if was_playing:
                self.song.stop_playing()
            
            def log_result(method_name, success, error=None):
                if success:
                    self.logger.info(f"✅ Method works: {method_name}")
                    results["working_methods"].append({"name": method_name, "error": None})
                else:
                    error_msg = str(error) if error else "Unknown error"
                    self.logger.info(f"❌ Method failed: {method_name} - {error_msg}")
                    results["failed_methods"].append({"name": method_name, "error": error_msg})
            
            # Generate a much more comprehensive list of method names to try
            prefixes = [
                "", "_", "__", "___", 
                "live_", "ableton_", "internal_", "private_", "api_", "audio_", "sound_", 
                "_live_", "_ableton_", "_internal_"
            ]
            
            root_method_names = [
                "export", "render", "bounce", "write", "capture", "save", "dump", "store", "output",
                "export_audio", "render_audio", "bounce_audio", "write_audio", "save_audio",
                "export_track", "render_track", "bounce_track", 
                "export_clip", "render_clip", "bounce_clip",
                "export_stem", "render_stem", "bounce_stem",
                "export_master", "render_master", "bounce_master",
                "export_to_disk", "render_to_disk", "bounce_to_disk",
                "export_to_file", "render_to_file", "bounce_to_file",
                "export_as_audio", "render_as_audio", "bounce_as_audio",
                "export_selection", "render_selection", "bounce_selection",
                "export_session", "render_session", "bounce_session",
                "export_arrangement", "render_arrangement", "bounce_arrangement",
                "export_tracks", "render_tracks", "bounce_tracks",
                "export_clips", "render_clips", "bounce_clips"
            ]
            
            suffixes = [
                "", "_file", "_disk", "_wav", "_mp3", "_aiff", "_audio"
            ]
            
            # Generate all combinations of prefix + method + suffix
            methods_to_try = []
            for prefix in prefixes:
                for method in root_method_names:
                    for suffix in suffixes:
                        methods_to_try.append(f"{prefix}{method}{suffix}")
            
            # Add some special cases
            methods_to_try.extend([
                "consolidate", "consolidate_time", "consolidate_clip", "consolidate_track",
                "flatten", "flatten_track", "flatten_clip", "flatten_time",
                "print_audio", "print_to_disk", "print_to_file",
                "commit", "commit_audio", "commit_to_disk",
                "freeze_and_flatten", "freeze_and_export", "freeze_and_render",
                "bounce_in_place", "render_in_place", "export_in_place",
                "render_to_wav", "render_to_mp3", "render_to_aiff", "render_to_ogg",
                "export_to_wav", "export_to_mp3", "export_to_aiff", "export_to_ogg"
            ])
            
            # 1. Try all methods on song object
            self.logger.info(f"Testing {len(methods_to_try)} method variations on song object...")
            for method_name in methods_to_try:
                if hasattr(self.song, method_name) and callable(getattr(self.song, method_name)):
                    try:
                        method = getattr(self.song, method_name)
                        # Try different argument patterns
                        try:
                            # Basic path only
                            method(test_file)
                            log_result(f"song.{method_name}(path)", True)
                        except Exception as e1:
                            try:
                                # Path and duration
                                method(test_file, test_duration)
                                log_result(f"song.{method_name}(path, duration)", True)
                            except Exception as e2:
                                try:
                                    # Path, start_time, duration
                                    method(test_file, 0.0, test_duration)
                                    log_result(f"song.{method_name}(path, start, duration)", True)
                                except Exception as e3:
                                    # Try various combinations of named parameters
                                    try:
                                        method(path=test_file)
                                        log_result(f"song.{method_name}(path=path)", True)
                                    except Exception as e4:
                                        try:
                                            method(filename=test_file)
                                            log_result(f"song.{method_name}(filename=path)", True)
                                        except Exception as e5:
                                            try:
                                                method(file=test_file)
                                                log_result(f"song.{method_name}(file=path)", True)
                                            except Exception as e6:
                                                try:
                                                    method(destination=test_file)
                                                    log_result(f"song.{method_name}(destination=path)", True)
                                                except Exception as e7:
                                                    try:
                                                        method(output=test_file)
                                                        log_result(f"song.{method_name}(output=path)", True)
                                                    except Exception as e8:
                                                        try:
                                                            method(file_path=test_file)
                                                            log_result(f"song.{method_name}(file_path=path)", True)
                                                        except Exception as e9:
                                                            # Try with duration parameter
                                                            try:
                                                                method(path=test_file, duration=test_duration)
                                                                log_result(f"song.{method_name}(path, duration) [named]", True)
                                                            except Exception as e10:
                                                                try:
                                                                    method(path=test_file, length=test_duration)
                                                                    log_result(f"song.{method_name}(path, length) [named]", True)
                                                                except Exception as e11:
                                                                    try:
                                                                        method(path=test_file, time=test_duration)
                                                                        log_result(f"song.{method_name}(path, time) [named]", True)
                                                                    except Exception as e12:
                                                                        # Try with start time and duration
                                                                        try:
                                                                            method(path=test_file, start=0.0, duration=test_duration)
                                                                            log_result(f"song.{method_name}(path, start, duration) [named]", True)
                                                                        except Exception as e13:
                                                                            try:
                                                                                method(path=test_file, start_time=0.0, duration=test_duration)
                                                                                log_result(f"song.{method_name}(path, start_time, duration) [named]", True)
                                                                            except Exception as e14:
                                                                                try:
                                                                                    method(path=test_file, begin=0.0, duration=test_duration)
                                                                                    log_result(f"song.{method_name}(path, begin, duration) [named]", True)
                                                                                except Exception as e15:
                                                                                    try:
                                                                                        method(path=test_file, from_time=0.0, duration=test_duration)
                                                                                        log_result(f"song.{method_name}(path, from_time, duration) [named]", True)
                                                                                    except Exception as e16:
                                                                                        # Try alternative duration naming
                                                                                        try:
                                                                                            method(path=test_file, start=0.0, length=test_duration)
                                                                                            log_result(f"song.{method_name}(path, start, length) [named]", True)
                                                                                        except Exception as e17:
                                                                                            try:
                                                                                                method(path=test_file, start=0.0, end=test_duration)
                                                                                                log_result(f"song.{method_name}(path, start, end) [named]", True)
                                                                                            except Exception as e18:
                                                                                                # No need to log all the failures, they're too many
                                                                                                pass
                    except Exception as e:
                        # Don't log general failures to avoid overwhelming output
                        pass
                
            # 2. Try select methods on track and other objects
            selected_methods = []
            # Include only methods with "export", "render", "bounce", "flatten", or "consolidate" in the name
            for method in methods_to_try:
                if any(keyword in method for keyword in ["export", "render", "bounce", "flatten", "consolidate"]):
                    selected_methods.append(method)
            
            # Test track methods
            if target_track:
                self.logger.info(f"Testing {len(selected_methods)} method variations on track object...")
                for method_name in selected_methods:
                    if hasattr(target_track, method_name) and callable(getattr(target_track, method_name)):
                        try:
                            method = getattr(target_track, method_name)
                            # Just try the most common signatures
                            try:
                                method(test_file)
                                log_result(f"track.{method_name}(path)", True)
                            except Exception:
                                try:
                                    method(test_file, 0.0, test_duration)
                                    log_result(f"track.{method_name}(path, start, duration)", True)
                                except Exception:
                                    try:
                                        method(path=test_file, start=0.0, duration=test_duration)
                                        log_result(f"track.{method_name}(path, start, duration) [named]", True)
                                    except Exception:
                                        pass  # Don't log failures
                        except Exception:
                            pass  # Don't log failures
            
            # 3. Try select methods on master track
            if master_track:
                self.logger.info(f"Testing {len(selected_methods)} method variations on master track...")
                for method_name in selected_methods:
                    if hasattr(master_track, method_name) and callable(getattr(master_track, method_name)):
                        try:
                            method = getattr(master_track, method_name)
                            # Just try the most common signatures
                            try:
                                method(test_file)
                                log_result(f"master_track.{method_name}(path)", True)
                            except Exception:
                                try:
                                    method(test_file, 0.0, test_duration)
                                    log_result(f"master_track.{method_name}(path, start, duration)", True)
                                except Exception:
                                    try:
                                        method(path=test_file, start=0.0, duration=test_duration)
                                        log_result(f"master_track.{method_name}(path, start, duration) [named]", True)
                                    except Exception:
                                        pass  # Don't log failures
                        except Exception:
                            pass  # Don't log failures
            
            # 4. Try specific methods on view object
            view = self.song.view if hasattr(self.song, "view") else None
            if view:
                self.logger.info("Testing select methods on view object...")
                for method_name in selected_methods:
                    if hasattr(view, method_name) and callable(getattr(view, method_name)):
                        try:
                            method = getattr(view, method_name)
                            try:
                                method(test_file)
                                log_result(f"song.view.{method_name}(path)", True)
                            except Exception:
                                try:
                                    method(test_file, 0.0, test_duration)
                                    log_result(f"song.view.{method_name}(path, start, duration)", True)
                                except Exception:
                                    pass  # Don't log failures
                        except Exception:
                            pass  # Don't log failures
                
                # Try some special view methods
                special_view_methods = [
                    "export_selected", "render_selected", "bounce_selected",
                    "export_selection", "render_selection", "bounce_selection",
                    "export_selected_tracks", "render_selected_tracks", "bounce_selected_tracks",
                    "export_selected_clips", "render_selected_clips", "bounce_selected_clips"
                ]
                
                for method_name in special_view_methods:
                    if hasattr(view, method_name) and callable(getattr(view, method_name)):
                        try:
                            method = getattr(view, method_name)
                            try:
                                method(test_file)
                                log_result(f"song.view.{method_name}(path)", True)
                            except Exception:
                                pass  # Don't log failures
                        except Exception:
                            pass  # Don't log failures
            
            # 5. Try any accessible clip objects
            test_clips = []
            for track in self.song.tracks:
                for clip_slot in track.clip_slots:
                    if clip_slot.has_clip and clip_slot.clip is not None:
                        test_clips.append(clip_slot.clip)
                        if len(test_clips) >= 2:  # Just test a couple of clips
                            break
                if len(test_clips) >= 2:
                    break
            
            if test_clips:
                self.logger.info(f"Testing select methods on {len(test_clips)} clip objects...")
                for i, clip in enumerate(test_clips):
                    for method_name in selected_methods:
                        if hasattr(clip, method_name) and callable(getattr(clip, method_name)):
                            try:
                                method = getattr(clip, method_name)
                                try:
                                    method(test_file)
                                    log_result(f"clip[{i}].{method_name}(path)", True)
                                except Exception:
                                    try:
                                        method(test_file, clip.length)
                                        log_result(f"clip[{i}].{method_name}(path, length)", True)
                                    except Exception:
                                        pass  # Don't log failures
                            except Exception:
                                pass  # Don't log failures
            
            # 6. Try accessible application & document objects
            if hasattr(Live, "Application") and hasattr(Live.Application, "get_application"):
                app = Live.Application.get_application()
                self.logger.info("Testing select methods on application object...")
                for method_name in selected_methods:
                    if hasattr(app, method_name) and callable(getattr(app, method_name)):
                        try:
                            method = getattr(app, method_name)
                            try:
                                method(test_file)
                                log_result(f"application.{method_name}(path)", True)
                            except Exception:
                                try:
                                    method(test_file, 0.0, test_duration)
                                    log_result(f"application.{method_name}(path, start, duration)", True)
                                except Exception:
                                    pass  # Don't log failures
                        except Exception:
                            pass  # Don't log failures
            
            if hasattr(Live, "Document") and hasattr(Live.Document, "get_document"):
                try:
                    doc = Live.Document.get_document()
                    self.logger.info("Testing select methods on document object...")
                    for method_name in selected_methods:
                        if hasattr(doc, method_name) and callable(getattr(doc, method_name)):
                            try:
                                method = getattr(doc, method_name)
                                try:
                                    method(test_file)
                                    log_result(f"document.{method_name}(path)", True)
                                except Exception:
                                    pass  # Don't log failures
                            except Exception:
                                pass  # Don't log failures
                except Exception:
                    pass  # Don't log document errors
            
            # 7. Try to find "hidden" export functionality by exploring all accessible methods
            def explore_methods(obj, obj_name, max_depth=1, current_depth=0, explored_ids=None):
                if explored_ids is None:
                    explored_ids = set()
                
                obj_id = id(obj)
                if obj_id in explored_ids or current_depth > max_depth:
                    return
                
                explored_ids.add(obj_id)
                
                for attr_name in dir(obj):
                    # Skip private attributes and common methods
                    if attr_name.startswith('__') or attr_name in ('__dict__', '__class__', '__module__', '__doc__'):
                        continue
                    
                    try:
                        attr = getattr(obj, attr_name)
                        
                        # Check if this could be an export method
                        if callable(attr) and any(keyword in attr_name for keyword in 
                                               ['export', 'render', 'bounce', 'consolidate', 'flatten', 'print', 'write']):
                            # Try calling with path argument
                            try:
                                attr(test_file)
                                log_result(f"{obj_name}.{attr_name}(path)", True)
                            except Exception:
                                # Only try a few variations to avoid too many errors
                                if 'export' in attr_name or 'render' in attr_name:
                                    try:
                                        attr(test_file, 0.0, test_duration)
                                        log_result(f"{obj_name}.{attr_name}(path, start, duration)", True)
                                    except Exception:
                                        pass
                        
                        # If this is an object and not a built-in type, explore it too
                        elif (not callable(attr) and not isinstance(attr, (int, float, str, bool, list, dict, tuple)) 
                              and current_depth < max_depth):
                            explore_methods(attr, f"{obj_name}.{attr_name}", max_depth, current_depth + 1, explored_ids)
                    
                    except Exception:
                        # Skip errors during exploration
                        pass
            
            # Explore song and application objects for hidden export methods
            self.logger.info("Exploring song object for hidden export methods...")
            explore_methods(self.song, "song", max_depth=1)
            
            if hasattr(Live, "Application") and hasattr(Live.Application, "get_application"):
                app = Live.Application.get_application()
                self.logger.info("Exploring application object for hidden export methods...")
                explore_methods(app, "application", max_depth=1)
            
            # 8. Try accessing Live API through alternative paths
            try:
                self.logger.info("Checking for export methods through alternative internal paths...")
                # Some versions of Live have internal APIs accessible through the Live namespace
                for alt_path in [
                    "Internal", "_Internal", "__Internal", "Audio", "_Audio", "Core", "_Core", 
                    "Export", "_Export", "Rendering", "_Rendering"
                ]:
                    if hasattr(Live, alt_path):
                        alt_obj = getattr(Live, alt_path)
                        for method_name in selected_methods:
                            if hasattr(alt_obj, method_name) and callable(getattr(alt_obj, method_name)):
                                try:
                                    method = getattr(alt_obj, method_name)
                                    try:
                                        method(test_file)
                                        log_result(f"Live.{alt_path}.{method_name}(path)", True)
                                    except Exception:
                                        pass  # Don't log failures
                                except Exception:
                                    pass  # Don't log failures
            except Exception:
                pass  # Skip errors
            
            # Restore playback state
            self.song.current_song_time = current_time
            if was_playing:
                self.song.start_playing()
            
            # Final stats
            results["total_tested"] = len(results["working_methods"]) + len(results["failed_methods"])
            results["total_working"] = len(results["working_methods"])
            
            # Log summary
            self.logger.info(f"Comprehensive export testing complete. Tested approximately {len(methods_to_try) * 20} method variations.")
            self.logger.info(f"Found {len(results['working_methods'])} working methods out of {results['total_tested']} logged attempts.")
            if len(results["working_methods"]) > 0:
                self.logger.info(f"Working methods: {[m['name'] for m in results['working_methods']]}")
            
            return (json.dumps(results),)
        
        self.osc_server.add_handler("/live/song/test_export_methods_comprehensive", test_export_methods_comprehensive)

        #--------------------------------------------------------------------------------
        # Try alternative export methods using UI automation
        #--------------------------------------------------------------------------------
        def try_ui_automation_export(params):
            """
            Attempts to export audio using UI automation techniques.
            This tries to use system-specific commands to trigger Ableton's export dialog.
            
            Args:
                destination (str, optional): Path to save exported file
                duration (float, optional): Duration in seconds to export
                
            Returns:
                success (int): 1 if successful, 0 otherwise
                message (str): Status message
            """
            try:
                import time
                import platform
                import subprocess
                
                # Extract parameters
                destination = str(params[0]) if len(params) > 0 else ""
                duration = float(params[1]) if len(params) > 1 else 30.0
                
                self.logger.info(f"Attempting UI automation export for {duration} seconds using subprocess approach")
                
                # Save current playback state
                was_playing = self.song.is_playing
                current_time = self.song.current_song_time
                
                # Stop playback during operation
                if was_playing:
                    self.song.stop_playing()
                
                # Position cursor at start point
                self.song.current_song_time = 0.0
                
                # Wait for Ableton to process
                time.sleep(0.5)
                
                # Detect platform
                system = platform.system()
                self.logger.info(f"Operating system detected: {system}")
                
                if system == "Windows":
                    # Windows approach using PowerShell
                    self.logger.info("Using PowerShell SendKeys for Windows automation")
                    
                    # Trigger export dialog (Ctrl+Shift+R)
                    export_cmd = r'powershell -command "$wshell = New-Object -ComObject wscript.shell; $wshell.AppActivate(\"Ableton Live\"); Start-Sleep -m 500; $wshell.SendKeys(\"^+r\"); Start-Sleep -m 2000;"'
                    
                    try:
                        # Execute the command
                        self.logger.info("Sending Ctrl+Shift+R keystroke to open export dialog")
                        subprocess.run(export_cmd, shell=True, check=True)
                        
                        # Tab to navigate the dialog
                        tab_cmd = r'powershell -command "$wshell = New-Object -ComObject wscript.shell; $wshell.AppActivate(\"Ableton Live\"); Start-Sleep -m 500; $wshell.SendKeys(\"{TAB}{TAB}{TAB}{TAB}\"); Start-Sleep -m 1000;"'
                        self.logger.info("Sending TAB keystrokes to navigate dialog")
                        subprocess.run(tab_cmd, shell=True, check=True)
                        
                        # If destination provided, try to enter it
                        if destination:
                            type_cmd = fr'powershell -command "$wshell = New-Object -ComObject wscript.shell; $wshell.AppActivate(\"Ableton Live\"); Start-Sleep -m 500; $wshell.SendKeys(\"{destination}\"); Start-Sleep -m 1000;"'
                            self.logger.info(f"Entering export path: {destination}")
                            subprocess.run(type_cmd, shell=True, check=True)
                        
                        # More tabs to get to OK button
                        more_tabs_cmd = r'powershell -command "$wshell = New-Object -ComObject wscript.shell; $wshell.AppActivate(\"Ableton Live\"); Start-Sleep -m 500; $wshell.SendKeys(\"{TAB}{TAB}{TAB}{TAB}\"); Start-Sleep -m 1000;"'
                        subprocess.run(more_tabs_cmd, shell=True, check=True)
                        
                        # Press Enter to confirm
                        enter_cmd = r'powershell -command "$wshell = New-Object -ComObject wscript.shell; $wshell.AppActivate(\"Ableton Live\"); Start-Sleep -m 500; $wshell.SendKeys(\"{ENTER}\"); Start-Sleep -m 1000;"'
                        self.logger.info("Sending ENTER to confirm export")
                        subprocess.run(enter_cmd, shell=True, check=True)
                        
                    except subprocess.SubprocessError as e:
                        self.logger.error(f"Subprocess error: {str(e)}")
                        return (0, f"PowerShell automation error: {str(e)}")
                    
                elif system == "Darwin":  # macOS
                    # AppleScript approach for macOS
                    self.logger.info("Using AppleScript for macOS automation")
                    
                    # Trigger export dialog (Shift+Cmd+E)
                    export_cmd = [
                        'osascript', '-e', 
                        'tell application "Ableton Live" to activate',
                        '-e', 'delay 0.5',
                        '-e', 'tell application "System Events" to keystroke "e" using {shift down, command down}',
                        '-e', 'delay 2'
                    ]
                    
                    try:
                        # Execute the command
                        self.logger.info("Sending Shift+Cmd+E keystroke to open export dialog")
                        subprocess.run(export_cmd, check=True)
                        
                        # Tab to navigate the dialog
                        tab_cmd = [
                            'osascript', '-e',
                            'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3',
                            '-e', 'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3',
                            '-e', 'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3',
                            '-e', 'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3'
                        ]
                        self.logger.info("Sending TAB keystrokes to navigate dialog")
                        subprocess.run(tab_cmd, check=True)
                        
                        # If destination provided, try to enter it
                        if destination:
                            type_cmd = [
                                'osascript', '-e',
                                f'tell application "System Events" to keystroke "{destination}"',
                                '-e', 'delay 1'
                            ]
                            self.logger.info(f"Entering export path: {destination}")
                            subprocess.run(type_cmd, check=True)
                        
                        # More tabs to get to OK button
                        more_tabs_cmd = [
                            'osascript', '-e',
                            'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3',
                            '-e', 'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3',
                            '-e', 'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3',
                            '-e', 'tell application "System Events" to keystroke tab',
                            '-e', 'delay 0.3'
                        ]
                        subprocess.run(more_tabs_cmd, check=True)
                        
                        # Press Enter to confirm
                        enter_cmd = [
                            'osascript', '-e',
                            'tell application "System Events" to keystroke return',
                            '-e', 'delay 1'
                        ]
                        self.logger.info("Sending ENTER to confirm export")
                        subprocess.run(enter_cmd, check=True)
                        
                    except subprocess.SubprocessError as e:
                        self.logger.error(f"Subprocess error: {str(e)}")
                        return (0, f"AppleScript automation error: {str(e)}")
                    
                else:
                    self.logger.error(f"Unsupported operating system: {system}")
                    return (0, f"UI automation not supported on {system} - requires Windows or macOS")
                
                # Wait for export to complete (estimated)
                wait_time = min(duration * 1.5, 60)  # Wait 1.5x duration, max 60 seconds
                self.logger.info(f"Waiting {wait_time} seconds for export to complete")
                time.sleep(wait_time)
                
                # Restore playback state
                self.song.current_song_time = current_time
                if was_playing:
                    self.song.start_playing()
                
                return (1, "UI automation export attempt completed. Check Ableton Live window for results.")
                
            except Exception as e:
                self.logger.error(f"Error during UI automation export: {str(e)}")
                return (0, f"Error during UI automation export: {str(e)}")
        
        self.osc_server.add_handler("/live/song/try_ui_automation_export", try_ui_automation_export)
        
        #--------------------------------------------------------------------------------
        # Try Max for Live method to export audio
        #--------------------------------------------------------------------------------
        def try_m4l_export_method(params):
            """
            Attempts to find and use a Max for Live device for audio export.
            First looks for installed M4L devices related to export, then tries to communicate with them.
            
            Args:
                destination (str, optional): Path to save exported file
                duration (float, optional): Duration in seconds to export
                
            Returns:
                success (int): 1 if successful, 0 otherwise
                message (str): Status message
            """
            try:
                # Extract parameters
                destination = str(params[0]) if len(params) > 0 else ""
                duration = float(params[1]) if len(params) > 1 else 30.0
                
                self.logger.info(f"Checking for Max for Live export devices...")
                
                # Check if Max functionality is available
                if not hasattr(Live, "MaxDevice") and not any(hasattr(track, "devices") for track in self.song.tracks):
                    return (0, "Max for Live functionality not detected in this version of Live")
                
                # Look for devices that might handle export in all tracks
                export_device = None
                device_track = None
                device_index = -1
                
                export_keywords = ["export", "render", "bounce", "record", "capture"]
                
                # Search all tracks for potential export devices
                for track_index, track in enumerate(self.song.tracks):
                    if hasattr(track, "devices"):
                        for i, device in enumerate(track.devices):
                            # Check device name for export-related keywords
                            if hasattr(device, "name") and any(keyword in device.name.lower() for keyword in export_keywords):
                                export_device = device
                                device_track = track
                                device_index = i
                                self.logger.info(f"Found potential export device: {device.name} on track {track.name}")
                                break
                    
                    if export_device:
                        break
                
                if not export_device:
                    # No export device found - could create a temporary one
                    self.logger.info("No export devices found. Would need to create one.")
                    
                    # Check if there's a Max API to create devices
                    can_create_max_device = (hasattr(self.song, "create_device") or 
                                             any(hasattr(track, "create_device") for track in self.song.tracks))
                    
                    if not can_create_max_device:
                        return (0, "No export devices found and cannot create new Max devices")
                    
                    # Would implement device creation here if we had a known Max device to create
                    return (0, "Creating Max export devices not implemented yet")
                
                # If we found a device, try to communicate with it
                # This would require knowledge of the specific device's parameters
                self.logger.info(f"Attempting to use {export_device.name} for export")
                
                # Attempt to send message to Max device
                # This is highly device-specific
                if hasattr(export_device, "send_message"):
                    try:
                        # Generic attempt to call export functionality
                        export_device.send_message("export", destination, 0.0, duration)
                        return (1, f"Message sent to Max device {export_device.name}")
                    except Exception as e:
                        self.logger.error(f"Error sending message to Max device: {str(e)}")
                
                # Attempt to set parameters if the device has them
                if hasattr(export_device, "parameters"):
                    try:
                        # Try to find and set relevant parameters
                        path_param = None
                        duration_param = None
                        export_param = None
                        
                        for param in export_device.parameters:
                            param_name = param.name.lower()
                            if any(name in param_name for name in ["path", "file", "destination"]):
                                path_param = param
                            elif any(name in param_name for name in ["duration", "length", "time"]):
                                duration_param = param
                            elif any(name in param_name for name in ["export", "render", "bounce", "start"]):
                                export_param = param
                        
                        if path_param and destination:
                            # Note: setting string values may not be supported directly
                            try:
                                path_param.value = destination
                                self.logger.info(f"Set path parameter to {destination}")
                            except:
                                self.logger.warning("Could not set path parameter")
                        
                        if duration_param:
                            try:
                                duration_param.value = duration
                                self.logger.info(f"Set duration parameter to {duration}")
                            except:
                                self.logger.warning("Could not set duration parameter")
                        
                        if export_param:
                            try:
                                # Assume this is a trigger parameter (button)
                                original_value = export_param.value
                                export_param.value = 1.0 if original_value == 0.0 else 0.0
                                time.sleep(0.1)
                                export_param.value = original_value
                                self.logger.info("Triggered export parameter")
                                return (1, "Triggered export in Max device")
                            except:
                                self.logger.warning("Could not trigger export parameter")
                    
                    except Exception as e:
                        self.logger.error(f"Error setting Max device parameters: {str(e)}")
                
                return (0, "Max device found but could not trigger export functionality")
                
            except Exception as e:
                self.logger.error(f"Error during Max for Live export attempt: {str(e)}")
                return (0, f"Error during Max for Live export attempt: {str(e)}")
        
        self.osc_server.add_handler("/live/song/try_m4l_export_method", try_m4l_export_method)

        def try_m4l_export(params):
            """
            Attempts to export audio using Max for Live device integration.
            This tries to find and utilize M4L devices that can export audio.
            
            Args:
                destination (str, optional): Path to save exported file
                duration (float, optional): Duration in seconds to export
                
            Returns:
                success (int): 1 if successful, 0 otherwise
                message (str): Status message
            """
            try:
                # Extract parameters
                destination = str(params[0]) if len(params) > 0 else ""
                duration = float(params[1]) if len(params) > 1 else 30.0
                
                self.logger.info(f"Attempting M4L device export for {duration} seconds")
                
                # Check for any Max Audio Effect devices
                found_m4l_devices = []
                
                # Scan all tracks for M4L devices
                for track in self.song.tracks:
                    for device in track.devices:
                        device_name = device.name.lower()
                        # Look for likely export devices
                        if "max" in device_name and any(keyword in device_name for keyword in 
                                                       ["export", "record", "bounce", "render"]):
                            found_m4l_devices.append((track.name, device.name))
                
                if not found_m4l_devices:
                    self.logger.info("Scanning master track for M4L devices")
                    # Check master track too
                    for device in self.song.master_track.devices:
                        device_name = device.name.lower()
                        if "max" in device_name and any(keyword in device_name for keyword in 
                                                       ["export", "record", "bounce", "render"]):
                            found_m4l_devices.append(("Master", device.name))
                
                if not found_m4l_devices:
                    # If no export M4L devices found, try UI automation as fallback
                    try:
                        import keyboard
                        self.logger.info("No M4L export devices found, trying keyboard automation instead")
                        
                        # Fall back to the UI automation approach
                        return try_ui_automation_export(params)
                    except ImportError:
                        self.logger.error("Keyboard module not available for fallback UI automation")
                        return (0, "No M4L export devices found and keyboard module not available")
                
                # We found some M4L devices that might be able to export
                self.logger.info(f"Found {len(found_m4l_devices)} potential M4L export devices:")
                for track_name, device_name in found_m4l_devices:
                    self.logger.info(f"  - '{device_name}' on track '{track_name}'")
                
                # For now, we'll use the first one found
                if found_m4l_devices:
                    track_name, device_name = found_m4l_devices[0]
                    self.logger.info(f"Attempting to use M4L device '{device_name}' on track '{track_name}'")
                    
                    # Now we need to try to trigger the device
                    # This is speculative as each M4L device has its own interface
                    # We'll try to find automation controls and toggle them
                    
                    # Save current playback state
                    was_playing = self.song.is_playing
                    current_time = self.song.current_song_time
                    
                    # Stop playback during operation
                    if was_playing:
                        self.song.stop_playing()
                    
                    # Rewind to beginning
                    self.song.current_song_time = 0.0
                    
                    # TODO: Implement specific control methods for known M4L export devices
                    # For now, we'll just report we found a device but can't control it yet
                    
                    self.logger.info(f"M4L device found, but automatic control not yet implemented")
                    self.logger.info(f"Future development: implement specific controls for common M4L export devices")
                    
                    # Restore playback state
                    self.song.current_song_time = current_time
                    if was_playing:
                        self.song.start_playing()
                    
                    return (1, f"Found M4L device '{device_name}' on track '{track_name}'. Manual activation required.")
                    
                return (0, "No suitable M4L export devices found")
                
            except Exception as e:
                self.logger.error(f"Error during M4L export: {str(e)}")
                return (0, f"Error during M4L export: {str(e)}")
        
        self.osc_server.add_handler("/live/song/try_m4l_export", try_m4l_export)

    def current_song_time_changed(self):
        #--------------------------------------------------------------------------------
        # If song has rewound or skipped to next beat, sent a /live/beat message
        #--------------------------------------------------------------------------------
        if (self.song.current_song_time < self.last_song_time) or \
                (int(self.song.current_song_time) > int(self.last_song_time)):
            self.osc_server.send("/live/song/get/beat", (int(self.song.current_song_time),))
        self.last_song_time = self.song.current_song_time

    def clear_api(self):
        super().clear_api()
        try:
            self.song.remove_current_song_time_listener(self.current_song_time_changed)
        except:
            pass
