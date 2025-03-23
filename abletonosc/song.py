import os
import sys
import tempfile
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
                    dir_name = f"abletonosc_stems_{int(time.time())}"
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
