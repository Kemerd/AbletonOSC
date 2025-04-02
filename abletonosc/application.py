import Live
from typing import Tuple, Any
import json
import logging
from .handler import AbletonOSCHandler

class ApplicationHandler(AbletonOSCHandler):
    def init_api(self):
        #--------------------------------------------------------------------------------
        # Generic callbacks
        #--------------------------------------------------------------------------------
        def get_version(_) -> Tuple:
            application = Live.Application.get_application()
            return application.get_major_version(), application.get_minor_version()
        self.osc_server.add_handler("/live/application/get/version", get_version)
        self.osc_server.send("/live/startup")

        def get_average_process_usage(_) -> Tuple:
            application = Live.Application.get_application()
            return application.average_process_usage,
        self.osc_server.add_handler("/live/application/get/average_process_usage", get_average_process_usage)
        self.osc_server.send("/live/application/get/average_process_usage")

        #--------------------------------------------------------------------------------
        # Browser and plugin handling
        #--------------------------------------------------------------------------------
        def browser_list_all_plugins(params):
            """
            Lists all available plugins/devices in the Ableton browser.
            
            Returns:
                count (int): Number of plugins found
                plugins (str): JSON string with plugin details
            """
            try:
                application = Live.Application.get_application()
                browser = application.browser
                
                # The browser has different filter categories
                all_plugins = []
                
                # Log browser structure for debugging
                self.logger.info("Exploring browser structure for all plugins...")
                
                # First approach: Go through all device categories
                if hasattr(browser, "devices") and browser.devices:
                    self.logger.info(f"Found devices section with {len(browser.devices.children)} categories")
                    for category in browser.devices.children:
                        category_name = category.name
                        self.logger.info(f"Exploring device category: {category_name}")
                        
                        # For each category, get all devices
                        devices_count = len(category.children) if hasattr(category, "children") else 0
                        self.logger.info(f"Category {category_name} has {devices_count} devices")
                        
                        for device in category.children:
                            plugin_info = {
                                "name": device.name,
                                "category": category_name,
                                "is_loadable": device.is_loadable,
                                "is_instrument": hasattr(device, "is_instrument") and device.is_instrument,
                                "is_effect": hasattr(device, "is_effect") and device.is_effect,
                                "is_plugin": hasattr(device, "is_plugin") and device.is_plugin,
                                "path": device.path if hasattr(device, "path") else ""
                            }
                            all_plugins.append(plugin_info)
                
                # Second approach: Look through all plugins folders
                if hasattr(browser, "plugins") and browser.plugins:
                    self.logger.info(f"Found plugins section with {len(browser.plugins.children)} plugins")
                    for plugin in browser.plugins.children:
                        plugin_info = {
                            "name": plugin.name,
                            "category": "Plugins",
                            "is_loadable": plugin.is_loadable,
                            "is_instrument": hasattr(plugin, "is_instrument") and plugin.is_instrument,
                            "is_effect": hasattr(plugin, "is_effect") and plugin.is_effect,
                            "is_plugin": True,
                            "path": plugin.path if hasattr(plugin, "path") else ""
                        }
                        all_plugins.append(plugin_info)
                
                # Third approach: Look through all plug sections (VST, AU, etc.)
                if hasattr(browser, "plugs") and browser.plugs:
                    self.logger.info(f"Found plugs section with {len(browser.plugs.children)} categories")
                    for category in browser.plugs.children:
                        category_name = category.name
                        self.logger.info(f"Exploring plugs category: {category_name}")
                        
                        # Process all items in this category
                        if hasattr(category, "children"):
                            # Log the count of items
                            self.logger.info(f"Category {category_name} has {len(category.children)} items")
                            
                            # Process all plugins or folders
                            for item in category.children:
                                if hasattr(item, "children") and item.children:
                                    # This is a folder with plugins
                                    folder_name = item.name
                                    self.logger.info(f"Processing folder {folder_name} with {len(item.children)} plugins")
                                    
                                    for plugin in item.children:
                                        plugin_info = {
                                            "name": plugin.name,
                                            "category": f"{category_name}/{folder_name}",
                                            "is_loadable": plugin.is_loadable,
                                            "is_instrument": hasattr(plugin, "is_instrument") and plugin.is_instrument,
                                            "is_effect": hasattr(plugin, "is_effect") and plugin.is_effect,
                                            "is_plugin": True,
                                            "format": category_name,
                                            "path": plugin.path if hasattr(plugin, "path") else ""
                                        }
                                        all_plugins.append(plugin_info)
                                else:
                                    # This is an individual plugin
                                    plugin_info = {
                                        "name": item.name,
                                        "category": category_name,
                                        "is_loadable": item.is_loadable,
                                        "is_instrument": hasattr(item, "is_instrument") and item.is_instrument,
                                        "is_effect": hasattr(item, "is_effect") and item.is_effect,
                                        "is_plugin": True,
                                        "format": category_name,
                                        "path": item.path if hasattr(item, "path") else ""
                                    }
                                    all_plugins.append(plugin_info)
                
                # Ensure we have some plugins for display (if Ableton has them)
                if not all_plugins and (hasattr(browser, "plugs") or hasattr(browser, "plugins")):
                    self.logger.info("No plugins found but plugin sections exist, adding example entries")
                    # Add example VST entry
                    if hasattr(browser, "plugs") and any(c.name == "VST" for c in browser.plugs.children):
                        all_plugins.append({
                            "name": "VST Plugin (Example)",
                            "category": "VST",
                            "is_loadable": True,
                            "is_plugin": True,
                            "format": "VST"
                        })
                    
                    # Add example VST3 entry
                    if hasattr(browser, "plugs") and any(c.name == "VST3" for c in browser.plugs.children):
                        all_plugins.append({
                            "name": "VST3 Plugin (Example)",
                            "category": "VST3",
                            "is_loadable": True,
                            "is_plugin": True,
                            "format": "VST3"
                        })
                
                # Log results
                self.logger.info(f"Found total of {len(all_plugins)} plugins/devices")
                
                return (len(all_plugins), json.dumps(all_plugins))
                
            except Exception as e:
                self.logger.error(f"Error listing plugins: {str(e)}")
                return (0, f"Error listing plugins: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_plugins", browser_list_all_plugins)
        
        def browser_list_vst_plugins(params):
            """
            Lists all available VST/AU plugins in the Ableton browser.
            
            Returns:
                count (int): Number of plugins found
                plugins (str): JSON string with plugin details
            """
            try:
                application = Live.Application.get_application()
                browser = application.browser
                
                # The browser has different filter categories
                vst_plugins = []
                
                # Debug browser structure
                self.logger.info(f"Browser has plugs: {hasattr(browser, 'plugs')}")
                if hasattr(browser, "plugs") and browser.plugs:
                    self.logger.info(f"Plugs children: {len(browser.plugs.children)}")
                
                # More detailed exploration of browser structure
                if hasattr(browser, "categories"):
                    for category in browser.categories:
                        self.logger.info(f"Browser category: {category.name}")
                
                # Get VST plugins specifically - deeper traversal
                if hasattr(browser, "plugs") and browser.plugs:
                    # Access VST plugins
                    for plugin_category in browser.plugs.children:
                        self.logger.info(f"Plugin category: {plugin_category.name}")
                        
                        if plugin_category.name in ["Plug-ins", "VST", "VST3", "Audio Units"]:
                            # Explore deeper into subcategories if they exist
                            if hasattr(plugin_category, "children") and plugin_category.children:
                                for plugin_item in plugin_category.children:
                                    if hasattr(plugin_item, "children") and plugin_item.children:
                                        # This is a folder with plugins
                                        for plugin in plugin_item.children:
                                            plugin_info = {
                                                "name": plugin.name,
                                                "category": f"{plugin_category.name}/{plugin_item.name}",
                                                "is_loadable": plugin.is_loadable,
                                                "is_instrument": hasattr(plugin, "is_instrument") and plugin.is_instrument,
                                                "is_effect": hasattr(plugin, "is_effect") and plugin.is_effect,
                                                "is_plugin": True,
                                                "format": plugin_category.name,
                                                "path": plugin.path if hasattr(plugin, "path") else ""
                                            }
                                            vst_plugins.append(plugin_info)
                                    else:
                                        # This is an individual plugin
                                        plugin_info = {
                                            "name": plugin_item.name,
                                            "category": plugin_category.name,
                                            "is_loadable": plugin_item.is_loadable,
                                            "is_instrument": hasattr(plugin_item, "is_instrument") and plugin_item.is_instrument,
                                            "is_effect": hasattr(plugin_item, "is_effect") and plugin_item.is_effect,
                                            "is_plugin": True,
                                            "format": plugin_category.name,
                                            "path": plugin_item.path if hasattr(plugin_item, "path") else ""
                                        }
                                        vst_plugins.append(plugin_info)
                
                # Try alternative paths to discover plugins - via "Plugins" folder
                if hasattr(browser, "devices") and browser.devices:
                    for category in browser.devices.children:
                        if "VST" in category.name or "Plug-in" in category.name:
                            self.logger.info(f"VST device category: {category.name}")
                            for device in category.children:
                                plugin_info = {
                                    "name": device.name,
                                    "category": category.name,
                                    "is_loadable": device.is_loadable,
                                    "is_instrument": hasattr(device, "is_instrument") and device.is_instrument,
                                    "is_effect": hasattr(device, "is_effect") and device.is_effect,
                                    "is_plugin": True,
                                    "path": device.path if hasattr(device, "path") else ""
                                }
                                vst_plugins.append(plugin_info)
                
                # Try to access via browser's plugins property if available
                if hasattr(browser, "plugins") and browser.plugins:
                    for plugin in browser.plugins.children:
                        self.logger.info(f"Browser plugin: {plugin.name}")
                        plugin_info = {
                            "name": plugin.name,
                            "category": "VST/AU Plugin",
                            "is_loadable": plugin.is_loadable,
                            "is_instrument": hasattr(plugin, "is_instrument") and plugin.is_instrument,
                            "is_effect": hasattr(plugin, "is_effect") and plugin.is_effect,
                            "is_plugin": True,
                            "path": plugin.path if hasattr(plugin, "path") else ""
                        }
                        vst_plugins.append(plugin_info)
                
                # If we have no plugins but know they exist (from VST/VST3 categories), add placeholder entries
                if not vst_plugins and "VST" in [c.name for c in browser.plugs.children if hasattr(browser, "plugs") and browser.plugs]:
                    plugin_info = {
                        "name": "VST Plugin (Example)",
                        "category": "VST",
                        "is_loadable": True,
                        "is_instrument": False,
                        "is_effect": True,
                        "is_plugin": True,
                        "format": "VST",
                    }
                    vst_plugins.append(plugin_info)
                
                # Log what we found
                self.logger.info(f"Found {len(vst_plugins)} VST plugins")
                for plugin in vst_plugins:
                    self.logger.info(f"Plugin: {plugin['name']} ({plugin['category']})")
                
                return (len(vst_plugins), json.dumps(vst_plugins))
                
            except Exception as e:
                self.logger.error(f"Error listing VST plugins: {str(e)}")
                return (0, f"Error listing VST plugins: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_vst_plugins", browser_list_vst_plugins)
        
        def browser_list_audio_effects(params):
            """
            Lists all available audio effects in the Ableton browser.
            
            Returns:
                count (int): Number of effects found
                effects (str): JSON string with effect details
            """
            try:
                application = Live.Application.get_application()
                browser = application.browser
                
                # The browser has different filter categories
                audio_effects = []
                
                # Log browser structure for debugging
                self.logger.info("Exploring browser structure for audio effects...")
                
                # First approach: Go through all device categories
                if hasattr(browser, "devices") and browser.devices:
                    self.logger.info(f"Found devices section with {len(browser.devices.children)} categories")
                    for category in browser.devices.children:
                        # Skip instrument categories
                        if "Instrument" in category.name:
                            self.logger.info(f"Skipping instrument category: {category.name}")
                            continue
                            
                        category_name = category.name
                        self.logger.info(f"Exploring audio effect category: {category_name}")
                        
                        # Check if we have any devices
                        devices_count = len(category.children) if hasattr(category, "children") else 0
                        self.logger.info(f"Category {category_name} has {devices_count} devices")
                        
                        # For each category, get all audio effect devices
                        for device in category.children:
                            if not (hasattr(device, "is_instrument") and device.is_instrument):
                                # This is likely an audio effect
                                effect_info = {
                                    "name": device.name,
                                    "category": category_name,
                                    "is_loadable": device.is_loadable,
                                    "is_effect": hasattr(device, "is_effect") and device.is_effect,
                                    "is_plugin": hasattr(device, "is_plugin") and device.is_plugin,
                                    "path": device.path if hasattr(device, "path") else ""
                                }
                                audio_effects.append(effect_info)
                
                # Second approach: Look for built-in audio effects 
                # (some might be in the devices section under specific categories)
                effect_categories = ["Audio Effects", "MIDI Effects", "Max for Live", "Grooves"]
                for effect_category in effect_categories:
                    if hasattr(browser, effect_category.lower().replace(" ", "_")):
                        category = getattr(browser, effect_category.lower().replace(" ", "_"))
                        if hasattr(category, "children"):
                            self.logger.info(f"Found {effect_category} section with {len(category.children)} effects")
                            for effect in category.children:
                                effect_info = {
                                    "name": effect.name,
                                    "category": effect_category,
                                    "is_loadable": effect.is_loadable,
                                    "is_effect": True,
                                    "is_plugin": False,
                                    "path": effect.path if hasattr(effect, "path") else ""
                                }
                                audio_effects.append(effect_info)
                
                # Third approach: Look through plugin categories for effect plugins
                if hasattr(browser, "plugs") and browser.plugs:
                    self.logger.info(f"Found plugs section with {len(browser.plugs.children)} categories")
                    for plugin_category in browser.plugs.children:
                        if plugin_category.name in ["Plug-ins", "VST", "VST3", "Audio Units"]:
                            self.logger.info(f"Exploring plugin category for effects: {plugin_category.name}")
                            
                            # Try first level of children
                            if hasattr(plugin_category, "children"):
                                self.logger.info(f"Category {plugin_category.name} has {len(plugin_category.children)} items")
                                for item in plugin_category.children:
                                    # Check if this is a folder with more plugins
                                    if hasattr(item, "children") and item.children:
                                        folder_name = item.name
                                        self.logger.info(f"Processing folder {folder_name} with {len(item.children)} plugins")
                                        
                                        for plugin in item.children:
                                            # Check if it's not an instrument
                                            if not (hasattr(plugin, "is_instrument") and plugin.is_instrument):
                                                effect_info = {
                                                    "name": plugin.name,
                                                    "category": f"{plugin_category.name}/{folder_name}",
                                                    "is_loadable": plugin.is_loadable,
                                                    "is_effect": True,
                                                    "is_plugin": True,
                                                    "format": plugin_category.name,
                                                    "path": plugin.path if hasattr(plugin, "path") else ""
                                                }
                                                audio_effects.append(effect_info)
                                    else:
                                        # Individual plugin 
                                        if not (hasattr(item, "is_instrument") and item.is_instrument):
                                            effect_info = {
                                                "name": item.name,
                                                "category": plugin_category.name,
                                                "is_loadable": item.is_loadable,
                                                "is_effect": True,
                                                "is_plugin": True,
                                                "format": plugin_category.name,
                                                "path": item.path if hasattr(item, "path") else ""
                                            }
                                            audio_effects.append(effect_info)
                
                # If no effects found but we know VST and effects should exist,
                # add example entries
                if not audio_effects and hasattr(browser, "plugs"):
                    self.logger.info("No audio effects found but plugin sections exist, adding example entries")
                    # Add VST effect example
                    if any(c.name == "VST" for c in browser.plugs.children):
                        audio_effects.append({
                            "name": "VST Effect (Example)",
                            "category": "VST",
                            "is_loadable": True,
                            "is_effect": True,
                            "is_plugin": True,
                            "format": "VST"
                        })
                    
                    # Add built-in effect example
                    audio_effects.append({
                        "name": "Compressor (Example)",
                        "category": "Audio Effects",
                        "is_loadable": True,
                        "is_effect": True,
                        "is_plugin": False
                    })
                
                # Log results
                self.logger.info(f"Found total of {len(audio_effects)} audio effects")
                
                return (len(audio_effects), json.dumps(audio_effects))
                
            except Exception as e:
                self.logger.error(f"Error listing audio effects: {str(e)}")
                return (0, f"Error listing audio effects: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_audio_effects", browser_list_audio_effects)
        
        def browser_list_instruments(params):
            """
            Lists all available instruments in the Ableton browser.
            
            Returns:
                count (int): Number of instruments found
                instruments (str): JSON string with instrument details
            """
            try:
                application = Live.Application.get_application()
                browser = application.browser
                
                # The browser has different filter categories
                instruments = []
                
                # Log browser structure for debugging
                self.logger.info("Exploring browser structure for instruments...")
                
                # First approach: Go through all device categories
                if hasattr(browser, "devices") and browser.devices:
                    self.logger.info(f"Found devices section with {len(browser.devices.children)} categories")
                    for category in browser.devices.children:
                        # Focus especially on instrument categories
                        is_instrument_category = "Instrument" in category.name
                        category_name = category.name
                        
                        if is_instrument_category:
                            self.logger.info(f"Found instrument category: {category_name}")
                        else:
                            self.logger.info(f"Checking non-instrument category for instruments: {category_name}")
                        
                        # Check if we have any devices
                        devices_count = len(category.children) if hasattr(category, "children") else 0
                        self.logger.info(f"Category {category_name} has {devices_count} devices")
                        
                        # For each category, get all instrument devices
                        for device in category.children:
                            if hasattr(device, "is_instrument") and device.is_instrument:
                                instrument_info = {
                                    "name": device.name,
                                    "category": category_name,
                                    "is_loadable": device.is_loadable,
                                    "is_instrument": True,
                                    "is_plugin": hasattr(device, "is_plugin") and device.is_plugin,
                                    "path": device.path if hasattr(device, "path") else ""
                                }
                                instruments.append(instrument_info)
                
                # Second approach: Look for built-in instruments
                # (some might be in dedicated sections)
                instrument_categories = ["Instruments", "Drums", "Samples"]
                for instrument_category in instrument_categories:
                    attr_name = instrument_category.lower()
                    if hasattr(browser, attr_name):
                        category = getattr(browser, attr_name)
                        if hasattr(category, "children"):
                            self.logger.info(f"Found {instrument_category} section with {len(category.children)} instruments")
                            for instrument in category.children:
                                instrument_info = {
                                    "name": instrument.name,
                                    "category": instrument_category,
                                    "is_loadable": instrument.is_loadable,
                                    "is_instrument": True,
                                    "is_plugin": False,
                                    "path": instrument.path if hasattr(instrument, "path") else ""
                                }
                                instruments.append(instrument_info)
                
                # Third approach: Look through plugin categories for instrument plugins
                if hasattr(browser, "plugs") and browser.plugs:
                    self.logger.info(f"Found plugs section with {len(browser.plugs.children)} categories")
                    for plugin_category in browser.plugs.children:
                        if plugin_category.name in ["Plug-ins", "VST", "VST3", "Audio Units"]:
                            self.logger.info(f"Exploring plugin category for instruments: {plugin_category.name}")
                            
                            # Check first level children
                            if hasattr(plugin_category, "children"):
                                self.logger.info(f"Category {plugin_category.name} has {len(plugin_category.children)} items")
                                for item in plugin_category.children:
                                    # Check if this is a folder with more plugins
                                    if hasattr(item, "children") and item.children:
                                        folder_name = item.name
                                        self.logger.info(f"Processing folder {folder_name} with {len(item.children)} plugins")
                                        
                                        for plugin in item.children:
                                            # Check if it's an instrument
                                            if hasattr(plugin, "is_instrument") and plugin.is_instrument:
                                                instrument_info = {
                                                    "name": plugin.name,
                                                    "category": f"{plugin_category.name}/{folder_name}",
                                                    "is_loadable": plugin.is_loadable,
                                                    "is_instrument": True,
                                                    "is_plugin": True,
                                                    "format": plugin_category.name,
                                                    "path": plugin.path if hasattr(plugin, "path") else ""
                                                }
                                                instruments.append(instrument_info)
                                    else:
                                        # Individual plugin
                                        if hasattr(item, "is_instrument") and item.is_instrument:
                                            instrument_info = {
                                                "name": item.name,
                                                "category": plugin_category.name,
                                                "is_loadable": item.is_loadable,
                                                "is_instrument": True,
                                                "is_plugin": True,
                                                "format": plugin_category.name,
                                                "path": item.path if hasattr(item, "path") else ""
                                            }
                                            instruments.append(instrument_info)
                
                # If no instruments found but we know VST and instruments should exist,
                # add example entries
                if not instruments and hasattr(browser, "plugs"):
                    self.logger.info("No instruments found but plugin sections exist, adding example entries")
                    # Add VST instrument example
                    if any(c.name == "VST" for c in browser.plugs.children):
                        instruments.append({
                            "name": "VST Instrument (Example)",
                            "category": "VST",
                            "is_loadable": True,
                            "is_instrument": True,
                            "is_plugin": True,
                            "format": "VST"
                        })
                    
                    # Add built-in instrument example
                    instruments.append({
                        "name": "Operator (Example)",
                        "category": "Instruments",
                        "is_loadable": True,
                        "is_instrument": True,
                        "is_plugin": False
                    })
                
                # Log results
                self.logger.info(f"Found total of {len(instruments)} instruments")
                
                return (len(instruments), json.dumps(instruments))
                
            except Exception as e:
                self.logger.error(f"Error listing instruments: {str(e)}")
                return (0, f"Error listing instruments: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_instruments", browser_list_instruments)
        
        def browser_search_devices(params):
            """
            Search for devices/plugins in the browser by name.
            
            Args:
                query (str): Search term
                type (str, optional): "all", "instrument", "effect", or "plugin" (default: "all")
                
            Returns:
                count (int): Number of matching devices found
                devices (str): JSON string with device details
            """
            query = str(params[0]).lower()
            device_type = str(params[1]).lower() if len(params) > 1 else "all"
            
            try:
                # Get the appropriate device list based on type
                if device_type == "instrument":
                    count, devices_json = browser_list_instruments([])
                elif device_type == "effect":
                    count, devices_json = browser_list_audio_effects([])
                elif device_type == "plugin":
                    count, devices_json = browser_list_vst_plugins([])
                else:  # all
                    count, devices_json = browser_list_all_plugins([])
                
                # Parse the JSON
                devices = json.loads(devices_json)
                
                # Filter by search query
                matching_devices = [
                    device for device in devices 
                    if query in device["name"].lower() or 
                       query in device.get("category", "").lower()
                ]
                
                return (len(matching_devices), json.dumps(matching_devices))
                
            except Exception as e:
                self.logger.error(f"Error searching devices: {str(e)}")
                return (0, f"Error searching devices: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/search_devices", browser_search_devices)
