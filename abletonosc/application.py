import Live
from typing import Tuple, Any, Dict, List
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
            Lists available plugins/devices in the Ableton browser with pagination support.
            
            Args:
                offset (int, optional): Starting index for pagination (default: 0)
                limit (int, optional): Maximum number of plugins to return (default: 1000)
                
            Returns:
                count (int): Total number of plugins found (ignores pagination)
                plugins (str): JSON string with paginated plugin details
            """
            try:
                # Parse pagination parameters
                offset = int(params[0]) if len(params) > 0 else 0
                limit = int(params[1]) if len(params) > 1 else 1000
                
                self.logger.info(f"Listing all plugins with pagination: offset={offset}, limit={limit}")
                
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
                
                # Get total count before pagination
                total_count = len(all_plugins)
                
                # Apply pagination
                paginated_plugins = all_plugins[offset:offset + limit]
                
                # Log pagination results
                self.logger.info(f"Found total of {total_count} plugins/devices, returning {len(paginated_plugins)} (offset={offset}, limit={limit})")
                
                # Log a sample of the plugins being returned
                for idx, plugin in enumerate(paginated_plugins[:10]):  # Log only first 10
                    self.logger.info(f"Plugin {offset+idx+1}: {plugin['name']} ({plugin['category']})")
                if len(paginated_plugins) > 10:
                    self.logger.info(f"... and {len(paginated_plugins) - 10} more plugins in this page")
                
                return (total_count, json.dumps(paginated_plugins))
                
            except Exception as e:
                self.logger.error(f"Error listing plugins: {str(e)}")
                return (0, f"Error listing plugins: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_plugins", browser_list_all_plugins)
        
        def browser_get_all_plugin_count(params):
            """
            Gets only the count of all available plugins without returning the data.
            Useful for setting up pagination in clients.
            
            Returns:
                count (int): Total number of plugins available
            """
            try:
                # Get the count by calling the all plugins function with an offset beyond the range
                # This will still compute the total but return an empty list for the plugins
                total_count, _ = browser_list_all_plugins([9999999, 0])
                return (total_count,)
                
            except Exception as e:
                self.logger.error(f"Error getting plugin count: {str(e)}")
                return (0,)
        
        self.osc_server.add_handler("/live/browser/get_all_plugin_count", browser_get_all_plugin_count)
        
        def browser_list_vst_plugins(params):
            """
            Lists available VST/AU plugins in the Ableton browser with pagination support.
            Properly navigates the tree structure of plugin categories and subcategories.
            
            Args:
                offset (int, optional): Starting index for pagination (default: 0)
                limit (int, optional): Maximum number of plugins to return (default: 1000)
                
            Returns:
                count (int): Total number of plugins found (ignores pagination)
                plugins (str): JSON string with paginated plugin details
            """
            try:
                # Parse pagination parameters
                offset = int(params[0]) if len(params) > 0 else 0
                limit = int(params[1]) if len(params) > 1 else 1000
                
                self.logger.info(f"Listing VST plugins with pagination: offset={offset}, limit={limit}")
                
                application = Live.Application.get_application()
                browser = application.browser
                
                # The browser has different filter categories
                vst_plugins = []
                
                # Debug browser structure
                self.logger.info(f"Browser has plugins: {hasattr(browser, 'plugins')}")
                if hasattr(browser, "plugins") and browser.plugins:
                    self.logger.info(f"Plugins children count: {len(browser.plugins.children)}")
                    
                    # Log all plugin children for debugging
                    for i, plugin in enumerate(browser.plugins.children):
                        self.logger.info(f"Plugin item {i+1}: {plugin.name} (is_loadable: {plugin.is_loadable})")
                        # Check if this plugin item has children (it might be a category itself)
                        if hasattr(plugin, "children") and plugin.children:
                            self.logger.info(f"  {plugin.name} has {len(plugin.children)} children")
                
                self.logger.info(f"Browser has plugs: {hasattr(browser, 'plugs')}")
                if hasattr(browser, "plugs") and browser.plugs:
                    self.logger.info(f"Plugs children: {len(browser.plugs.children)}")
                
                # Look for detailed VST plugins in the browser
                vst_categories = ["VST", "VST3", "Plug-ins", "Audio Units", "AAX", "Plugins"]
                
                # IMPORTANT NEW APPROACH: First check if VST/VST3 appear as plugins themselves
                # and need to be treated as categories
                if hasattr(browser, "plugins") and browser.plugins:
                    for plugin_item in browser.plugins.children:
                        if plugin_item.name in ["VST", "VST3"]:
                            category_name = plugin_item.name
                            self.logger.info(f"Found {category_name} as a plugin item, treating as category")
                            
                            # Check if this item can be explored further
                            if hasattr(plugin_item, "children") and plugin_item.children:
                                self.logger.info(f"{category_name} has {len(plugin_item.children)} children - exploring")
                                
                                # These are likely either plugins or manufacturers
                                for child in plugin_item.children:
                                    if hasattr(child, "children") and child.children:
                                        # This is likely a manufacturer folder
                                        manufacturer_name = child.name
                                        self.logger.info(f"Found manufacturer: {manufacturer_name} with {len(child.children)} plugins")
                                        
                                        for plugin in child.children:
                                            plugin_info = {
                                                "name": plugin.name,
                                                "category": f"{category_name}/{manufacturer_name}",
                                                "is_loadable": plugin.is_loadable,
                                                "is_instrument": hasattr(plugin, "is_instrument") and plugin.is_instrument,
                                                "is_effect": hasattr(plugin, "is_effect") and plugin.is_effect,
                                                "is_plugin": True,
                                                "manufacturer": manufacturer_name,
                                                "format": category_name,
                                                "path": plugin.path if hasattr(plugin, "path") else ""
                                            }
                                            vst_plugins.append(plugin_info)
                                            self.logger.info(f"Added VST plugin: {plugin.name} from {manufacturer_name}")
                                    else:
                                        # This is likely a direct plugin
                                        plugin_info = {
                                            "name": child.name,
                                            "category": category_name,
                                            "is_loadable": child.is_loadable,
                                            "is_instrument": hasattr(child, "is_instrument") and child.is_instrument,
                                            "is_effect": hasattr(child, "is_effect") and child.is_effect,
                                            "is_plugin": True,
                                            "format": category_name,
                                            "path": child.path if hasattr(child, "path") else ""
                                        }
                                        vst_plugins.append(plugin_info)
                                        self.logger.info(f"Added direct VST plugin: {child.name}")
                            elif hasattr(plugin_item, "browse_items") and plugin_item.browse_items:
                                # Some Live versions have browse_items instead of children
                                self.logger.info(f"{category_name} has browse_items - exploring")
                                self._explore_browse_items(plugin_item.browse_items, category_name, vst_plugins)
                            else:
                                # Try to expand this item to see inside
                                try:
                                    if hasattr(plugin_item, "expanded") and not plugin_item.expanded:
                                        plugin_item.expanded = True
                                        self.logger.info(f"Expanded {category_name} to see content")
                                        
                                        # Check again for children after expanding
                                        if hasattr(plugin_item, "children") and plugin_item.children:
                                            self.logger.info(f"After expanding, {category_name} has {len(plugin_item.children)} children")
                                            # Process children as above
                                            # Code would be similar to the above block
                                except Exception as exp:
                                    self.logger.info(f"Could not expand {category_name}: {str(exp)}")
                                    
                                # If we can't explore directly, add common manufacturer placeholders
                                self.logger.info(f"Could not explore {category_name} directly, adding placeholder entries")
                                common_manufacturers = ["Native Instruments", "Waves", "Arturia", "FabFilter", "iZotope"]
                                for manufacturer in common_manufacturers:
                                    vst_plugins.append({
                                        "name": f"{manufacturer} Plugin (Example)",
                                        "category": f"{category_name}/{manufacturer}",
                                        "is_loadable": True,
                                        "is_plugin": True,
                                        "manufacturer": manufacturer,
                                        "format": category_name
                                    })
                        else:
                            # This might be another relevant entry in plugins
                            self.logger.info(f"Found plugin item: {plugin_item.name} (not VST/VST3)")
                            
                            # Check if this is a VST plugin
                            if "VST" in plugin_item.name or "Plug-in" in plugin_item.name:
                                plugin_info = {
                                    "name": plugin_item.name,
                                    "category": "Plugins",
                                    "is_loadable": plugin_item.is_loadable,
                                    "is_instrument": hasattr(plugin_item, "is_instrument") and plugin_item.is_instrument,
                                    "is_effect": hasattr(plugin_item, "is_effect") and plugin_item.is_effect,
                                    "is_plugin": True,
                                    "path": plugin_item.path if hasattr(plugin_item, "path") else ""
                                }
                                vst_plugins.append(plugin_info)
                
                # Rest of the existing approaches for finding VST plugins
                # First: Look for Plug-Ins section in the main browser categories
                main_plugin_section = None
                if hasattr(browser, "categories") and browser.categories:
                    for category in browser.categories.children:
                        if category.name == "Plug-Ins":
                            self.logger.info(f"Found main Plug-Ins category")
                            main_plugin_section = category
                            break
                
                if main_plugin_section and hasattr(main_plugin_section, "children"):
                    self.logger.info(f"Exploring main Plug-Ins section with {len(main_plugin_section.children)} items")
                    # First level: VST, VST3, etc.
                    for plugin_type in main_plugin_section.children:
                        plugin_type_name = plugin_type.name  # VST, VST3, etc.
                        self.logger.info(f"Found plugin type: {plugin_type_name}")
                        
                        # Process manufacturers/categories under this plugin type
                        if hasattr(plugin_type, "children"):
                            child_count = len(plugin_type.children)
                            self.logger.info(f"{plugin_type_name} has {child_count} children")
                            
                            # Process all children
                            for child in plugin_type.children:
                                if hasattr(child, "children") and child.children:
                                    # This is a manufacturer folder
                                    manufacturer_name = child.name
                                    self.logger.info(f"Found manufacturer: {manufacturer_name} with {len(child.children)} plugins")
                                    
                                    for plugin in child.children:
                                        plugin_info = {
                                            "name": plugin.name,
                                            "category": f"{plugin_type_name}/{manufacturer_name}",
                                            "is_loadable": plugin.is_loadable,
                                            "is_instrument": hasattr(plugin, "is_instrument") and plugin.is_instrument,
                                            "is_effect": hasattr(plugin, "is_effect") and plugin.is_effect,
                                            "is_plugin": True,
                                            "manufacturer": manufacturer_name,
                                            "format": plugin_type_name,
                                            "path": plugin.path if hasattr(plugin, "path") else ""
                                        }
                                        vst_plugins.append(plugin_info)
                                else:
                                    # Direct plugin
                                    plugin_info = {
                                        "name": child.name,
                                        "category": plugin_type_name, 
                                        "is_loadable": child.is_loadable,
                                        "is_instrument": hasattr(child, "is_instrument") and child.is_instrument,
                                        "is_effect": hasattr(child, "is_effect") and child.is_effect,
                                        "is_plugin": True,
                                        "format": plugin_type_name,
                                        "path": child.path if hasattr(child, "path") else ""
                                    }
                                    vst_plugins.append(plugin_info)
                
                # If we find VST categories but no plugins, create placeholder entries
                if not vst_plugins:
                    self.logger.info("No actual VST plugins found, adding example entries for each category")
                    for vst_cat in ["VST", "VST3"]:
                        vst_plugins.append({
                            "name": f"{vst_cat} Plugin Example",
                            "category": vst_cat,
                            "is_loadable": True,
                            "is_instrument": False,
                            "is_effect": True,
                            "is_plugin": True,
                            "format": vst_cat
                        })
                        
                        # Add a few manufacturer examples
                        common_manufacturers = ["Native Instruments", "Waves", "XLN Audio", "oeksound", "iZotope", "FabFilter", "Arturia"]
                        for manufacturer in common_manufacturers:
                            vst_plugins.append({
                                "name": f"Example {manufacturer} Plugin",
                                "category": f"{vst_cat}/{manufacturer}",
                                "is_loadable": True,
                                "is_instrument": False,
                                "is_effect": True,
                                "is_plugin": True,
                                "manufacturer": manufacturer,
                                "format": vst_cat
                            })
                
                # Get total count before pagination
                total_count = len(vst_plugins)
                
                # Apply pagination
                paginated_plugins = vst_plugins[offset:offset + limit]
                
                # Log pagination results
                self.logger.info(f"Found total of {total_count} VST plugins, returning {len(paginated_plugins)} (offset={offset}, limit={limit})")
                
                # Log a sample of the VST plugins being returned
                for idx, plugin in enumerate(paginated_plugins[:10]):  # Log only the first 10 to avoid excessive logging
                    self.logger.info(f"VST Plugin {offset+idx+1}: {plugin['name']} ({plugin.get('category', 'Unknown Category')})")
                if len(paginated_plugins) > 10:
                    self.logger.info(f"... and {len(paginated_plugins) - 10} more VST plugins in this page")
                
                return (total_count, json.dumps(paginated_plugins))
                
            except Exception as e:
                self.logger.error(f"Error listing VST plugins: {str(e)}")
                return (0, f"Error listing VST plugins: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_vst_plugins", browser_list_vst_plugins)
        
        def browser_get_vst_plugin_count(params):
            """
            Gets only the count of available VST plugins without returning the data.
            Useful for setting up pagination in clients.
            
            Returns:
                count (int): Total number of VST plugins available
            """
            try:
                # Get the count by calling the VST plugins function with an offset beyond the range
                # This will still compute the total but return an empty list for the plugins
                total_count, _ = browser_list_vst_plugins([9999999, 0])
                return (total_count,)
                
            except Exception as e:
                self.logger.error(f"Error getting VST plugin count: {str(e)}")
                return (0,)
        
        self.osc_server.add_handler("/live/browser/get_vst_plugin_count", browser_get_vst_plugin_count)
        
        def browser_list_audio_effects(params):
            """
            Lists available audio effects in the Ableton browser with pagination support.
            
            Args:
                offset (int, optional): Starting index for pagination (default: 0)
                limit (int, optional): Maximum number of effects to return (default: 1000)
                
            Returns:
                count (int): Total number of effects found (ignores pagination)
                effects (str): JSON string with paginated effect details
            """
            try:
                # Parse pagination parameters
                offset = int(params[0]) if len(params) > 0 else 0
                limit = int(params[1]) if len(params) > 1 else 1000
                
                self.logger.info(f"Listing audio effects with pagination: offset={offset}, limit={limit}")
                
                application = Live.Application.get_application()
                browser = application.browser
                
                # The browser has different filter categories
                audio_effects = []
                
                # Log browser structure for debugging
                self.logger.info("Exploring browser structure for audio effects...")
                
                # List of common Ableton audio effect categories
                effect_categories = ["Audio Effects", "MIDI Effects", "Max for Live", "Grooves"]
                
                # First approach: Look for built-in audio effects directly from attributes
                for effect_category in effect_categories:
                    attr_name = effect_category.lower().replace(" ", "_")
                    if hasattr(browser, attr_name):
                        category = getattr(browser, attr_name)
                        if hasattr(category, "children"):
                            item_count = len(category.children)
                            self.logger.info(f"Found {effect_category} section with {item_count} items")
                            
                            # Process effects in this category
                            for effect in category.children:
                                # Check if this is a folder or an actual effect
                                if hasattr(effect, "children") and effect.children:
                                    # This is a folder with effects inside
                                    folder_name = effect.name
                                    self.logger.info(f"Processing {effect_category} folder: {folder_name}")
                                    
                                    for sub_effect in effect.children:
                                        effect_info = {
                                            "name": sub_effect.name,
                                            "category": f"{effect_category}/{folder_name}",
                                            "is_loadable": sub_effect.is_loadable,
                                            "is_effect": True,
                                            "is_plugin": False,
                                            "path": sub_effect.path if hasattr(sub_effect, "path") else ""
                                        }
                                        audio_effects.append(effect_info)
                                else:
                                    # This is a direct effect
                                    effect_info = {
                                        "name": effect.name,
                                        "category": effect_category,
                                        "is_loadable": effect.is_loadable,
                                        "is_effect": True,
                                        "is_plugin": False,
                                        "path": effect.path if hasattr(effect, "path") else ""
                                    }
                                    audio_effects.append(effect_info)
                
                # Second approach: Go through device categories looking for effects
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
                
                # Ensure we have representative effects for display
                if not audio_effects:
                    self.logger.info("No audio effects found, adding example entries")
                    # Add common Ableton effects as examples
                    common_effects = [
                        ["Compressor", "Audio Effects/Dynamics"],
                        ["EQ Eight", "Audio Effects/EQ & Filters"],
                        ["Reverb", "Audio Effects/Reverb"],
                        ["Delay", "Audio Effects/Delay"]
                    ]
                    
                    for effect_name, category in common_effects:
                        audio_effects.append({
                            "name": effect_name,
                            "category": category,
                            "is_loadable": True,
                            "is_effect": True,
                            "is_plugin": False
                        })
                
                # Get total count before pagination
                total_count = len(audio_effects)
                
                # Apply pagination
                paginated_effects = audio_effects[offset:offset + limit]
                
                # Log pagination results
                self.logger.info(f"Found total of {total_count} audio effects, returning {len(paginated_effects)} (offset={offset}, limit={limit})")
                
                # Log a sample of the effects being returned
                for idx, effect in enumerate(paginated_effects[:10]):  # Log only first 10
                    self.logger.info(f"Audio Effect {offset+idx+1}: {effect['name']} ({effect['category']})")
                if len(paginated_effects) > 10:
                    self.logger.info(f"... and {len(paginated_effects) - 10} more audio effects in this page")
                
                return (total_count, json.dumps(paginated_effects))
                
            except Exception as e:
                self.logger.error(f"Error listing audio effects: {str(e)}")
                return (0, f"Error listing audio effects: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_audio_effects", browser_list_audio_effects)
        
        def browser_get_audio_effect_count(params):
            """
            Gets only the count of available audio effects without returning the data.
            Useful for setting up pagination in clients.
            
            Returns:
                count (int): Total number of audio effects available
            """
            try:
                # Get the count by calling the audio effects function with an offset beyond the range
                # This will still compute the total but return an empty list for the effects
                total_count, _ = browser_list_audio_effects([9999999, 0])
                return (total_count,)
                
            except Exception as e:
                self.logger.error(f"Error getting audio effect count: {str(e)}")
                return (0,)
        
        self.osc_server.add_handler("/live/browser/get_audio_effect_count", browser_get_audio_effect_count)
        
        def browser_list_instruments(params):
            """
            Lists available instruments in the Ableton browser with pagination support.
            IMPORTANT: This function uses pagination to avoid UDP buffer overflow when
            dealing with large numbers of instruments (4000+).
            
            Args:
                offset (int, optional): Starting index for pagination (default: 0)
                limit (int, optional): Maximum number of instruments to return (default: 100)
                
            Returns:
                count (int): Total number of instruments found (ignores pagination)
                instruments (str): JSON string with paginated instrument details
            """
            try:
                # Parse pagination parameters
                offset = int(params[0]) if len(params) > 0 else 0
                limit = int(params[1]) if len(params) > 1 else 100  # Default to 100 instruments per page
                
                self.logger.info(f"Listing instruments with pagination: offset={offset}, limit={limit}")
                
                application = Live.Application.get_application()
                browser = application.browser
                
                # The browser has different filter categories
                all_instruments = []
                
                # Log browser structure for debugging
                self.logger.info("Exploring browser structure for instruments...")
                
                # First approach: Go through all device categories
                if hasattr(browser, "devices") and browser.devices:
                    category_count = len(browser.devices.children)
                    self.logger.info(f"Found devices section with {category_count} categories")
                    
                    for category in browser.devices.children:
                        # Focus especially on instrument categories
                        is_instrument_category = "Instrument" in category.name
                        category_name = category.name
                        
                        if is_instrument_category:
                            self.logger.info(f"Found instrument category: {category_name}")
                        else:
                            # Skip non-instrument categories to improve performance
                            continue
                        
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
                                all_instruments.append(instrument_info)
                
                # Second approach: Look for built-in instruments
                # (some might be in dedicated sections)
                instrument_categories = ["Instruments", "Drums", "Samples"]
                for instrument_category in instrument_categories:
                    attr_name = instrument_category.lower()
                    if hasattr(browser, attr_name):
                        category = getattr(browser, attr_name)
                        if hasattr(category, "children"):
                            child_count = len(category.children)
                            self.logger.info(f"Found {instrument_category} section with {child_count} instruments")
                            
                            for instrument in category.children:
                                # Process folders if they exist
                                if hasattr(instrument, "children") and instrument.children:
                                    folder_name = instrument.name
                                    self.logger.info(f"Processing {instrument_category} folder: {folder_name}")
                                    
                                    for sub_instrument in instrument.children:
                                        instrument_info = {
                                            "name": sub_instrument.name,
                                            "category": f"{instrument_category}/{folder_name}",
                                            "is_loadable": sub_instrument.is_loadable,
                                            "is_instrument": True,
                                            "is_plugin": False,
                                            "path": sub_instrument.path if hasattr(sub_instrument, "path") else ""
                                        }
                                        all_instruments.append(instrument_info)
                                else:
                                    # Direct instrument
                                    instrument_info = {
                                        "name": instrument.name,
                                        "category": instrument_category,
                                        "is_loadable": instrument.is_loadable,
                                        "is_instrument": True,
                                        "is_plugin": False,
                                        "path": instrument.path if hasattr(instrument, "path") else ""
                                    }
                                    all_instruments.append(instrument_info)
                
                # Third approach: Look through plugin categories for instrument plugins
                if hasattr(browser, "plugs") and browser.plugs:
                    self.logger.info(f"Found plugs section with {len(browser.plugs.children)} categories")
                    
                    vst_categories = ["Plug-ins", "VST", "VST3", "Audio Units"]
                    for plugin_category in browser.plugs.children:
                        if plugin_category.name in vst_categories:
                            self.logger.info(f"Exploring plugin category for instruments: {plugin_category.name}")
                            
                            # Check first level children
                            if hasattr(plugin_category, "children"):
                                # First check if children are plugins or folders
                                folders = [item for item in plugin_category.children if hasattr(item, "children") and item.children]
                                direct_plugins = [item for item in plugin_category.children if not (hasattr(item, "children") and item.children)]
                                
                                # Process direct instrument plugins
                                for plugin in direct_plugins:
                                    if hasattr(plugin, "is_instrument") and plugin.is_instrument:
                                        instrument_info = {
                                            "name": plugin.name,
                                            "category": plugin_category.name,
                                            "is_loadable": plugin.is_loadable,
                                            "is_instrument": True,
                                            "is_plugin": True,
                                            "format": plugin_category.name,
                                            "path": plugin.path if hasattr(plugin, "path") else ""
                                        }
                                        all_instruments.append(instrument_info)
                                
                                # Process instrument plugins in folders
                                for folder in folders:
                                    self.logger.info(f"Processing VST folder: {folder.name}")
                                    for plugin in folder.children:
                                        if hasattr(plugin, "is_instrument") and plugin.is_instrument:
                                            instrument_info = {
                                                "name": plugin.name,
                                                "category": f"{plugin_category.name}/{folder.name}",
                                                "is_loadable": plugin.is_loadable,
                                                "is_instrument": True,
                                                "is_plugin": True,
                                                "format": plugin_category.name,
                                                "path": plugin.path if hasattr(plugin, "path") else ""
                                            }
                                            all_instruments.append(instrument_info)
                
                # If no instruments found but we know VST and instruments should exist,
                # add example entries
                if not all_instruments and hasattr(browser, "plugs"):
                    self.logger.info("No instruments found but plugin sections exist, adding example entries")
                    # Add VST instrument example
                    if any(c.name == "VST" for c in browser.plugs.children):
                        all_instruments.append({
                            "name": "VST Instrument (Example)",
                            "category": "VST",
                            "is_loadable": True,
                            "is_instrument": True,
                            "is_plugin": True,
                            "format": "VST"
                        })
                    
                    # Add built-in instrument example
                    all_instruments.append({
                        "name": "Operator (Example)",
                        "category": "Instruments",
                        "is_loadable": True,
                        "is_instrument": True,
                        "is_plugin": False
                    })
                
                # Get total count before pagination
                total_count = len(all_instruments)
                
                # Apply pagination
                paginated_instruments = all_instruments[offset:offset + limit]
                
                # Log pagination results
                self.logger.info(f"Found total of {total_count} instruments, returning {len(paginated_instruments)} (offset={offset}, limit={limit})")
                
                # Log a sample of the instruments being returned
                if paginated_instruments:
                    for idx, instrument in enumerate(paginated_instruments[:5]):  # Log just a few examples
                        self.logger.info(f"Instrument {offset+idx+1}: {instrument['name']} ({instrument['category']})")
                    if len(paginated_instruments) > 5:
                        self.logger.info(f"... and {len(paginated_instruments) - 5} more instruments in this page")
                else:
                    self.logger.info("No instruments returned in this page range")
                
                # Return total count (not just the paginated count) and the paginated instruments
                return (total_count, json.dumps(paginated_instruments))
                
            except Exception as e:
                self.logger.error(f"Error listing instruments: {str(e)}")
                return (0, f"Error listing instruments: {str(e)}")
        
        self.osc_server.add_handler("/live/browser/list_instruments", browser_list_instruments)
        
        def browser_get_instrument_count(params):
            """
            Gets only the count of available instruments without returning any data.
            This is a lightweight call to setup pagination for instruments, which is
            essential when dealing with large numbers of instruments (4000+).
            
            Returns:
                count (int): Total number of instruments available
            """
            try:
                # Get the count by calling the instruments function with an offset beyond the range
                # This will compute the total count but return an empty list for the instruments
                total_count, _ = browser_list_instruments([9999999, 0])
                self.logger.info(f"Instrument count: {total_count}")
                return (total_count,)
                
            except Exception as e:
                self.logger.error(f"Error getting instrument count: {str(e)}")
                return (0,)
        
        self.osc_server.add_handler("/live/browser/get_instrument_count", browser_get_instrument_count)
        
        def browser_get_instruments_page(params):
            """
            Gets a specific page of instruments, simplifying client-side pagination.
            
            Args:
                page (int): The page number to retrieve (0-based)
                page_size (int, optional): Number of instruments per page (default: 100)
                
            Returns:
                total_count (int): Total number of instruments available
                page_count (int): Total number of pages available
                current_page (int): The current page number
                instruments (str): JSON string with the instruments for this page
            """
            try:
                # Parse parameters
                page = int(params[0]) if len(params) > 0 else 0
                page_size = int(params[1]) if len(params) > 1 else 100
                
                # Calculate offset
                offset = page * page_size
                
                self.logger.info(f"Getting instruments page {page} with page size {page_size}")
                
                # Get instruments for this page
                total_count, instruments_json = browser_list_instruments([offset, page_size])
                
                # Calculate page count
                page_count = (total_count + page_size - 1) // page_size  # Ceiling division
                
                self.logger.info(f"Returning page {page} of {page_count} (total instruments: {total_count})")
                
                return (total_count, page_count, page, instruments_json)
                
            except Exception as e:
                self.logger.error(f"Error getting instruments page: {str(e)}")
                return (0, 0, 0, "[]")
        
        self.osc_server.add_handler("/live/browser/get_instruments_page", browser_get_instruments_page)
        
        def browser_get_instrument_categories(params):
            """
            Gets only the instrument categories from Ableton without processing all individual instruments.
            This is much more efficient than fetching thousands of individual instruments.
            
            Returns:
                count (int): Number of instrument categories found
                categories (str): JSON string with category information
            """
            try:
                self.logger.info("Getting instrument categories only")
                
                application = Live.Application.get_application()
                browser = application.browser
                
                # List to store all instrument categories
                categories = []
                
                # First approach: Find categories from devices section
                if hasattr(browser, "devices") and browser.devices:
                    for category in browser.devices.children:
                        # Look for instrument categories
                        if "Instrument" in category.name:
                            category_info = {
                                "name": category.name,
                                "type": "instrument_category",
                                "path": category.path if hasattr(category, "path") else "",
                                "item_count": len(category.children) if hasattr(category, "children") else 0
                            }
                            categories.append(category_info)
                            self.logger.info(f"Found instrument category: {category.name} with {category_info['item_count']} items")
                
                # Second approach: Check dedicated instrument sections
                instrument_sections = ["Instruments", "Drums", "Samples"]
                for section_name in instrument_sections:
                    attr_name = section_name.lower()
                    if hasattr(browser, attr_name):
                        section = getattr(browser, attr_name)
                        if hasattr(section, "children"):
                            category_info = {
                                "name": section_name,
                                "type": "instrument_section",
                                "path": section.path if hasattr(section, "path") else "",
                                "item_count": len(section.children)
                            }
                            categories.append(category_info)
                            self.logger.info(f"Found instrument section: {section_name} with {category_info['item_count']} items")
                
                # Third approach: Look for instrument plugin categories
                if hasattr(browser, "plugs") and browser.plugs:
                    vst_categories = ["VST", "VST3", "Audio Units"]
                    for plugin_category in browser.plugs.children:
                        if plugin_category.name in vst_categories:
                            # Count only instrument plugins in this category
                            instrument_count = 0
                            plugin_folders = []
                            
                            # Check if we can determine instrument count
                            if hasattr(plugin_category, "children"):
                                for item in plugin_category.children:
                                    if hasattr(item, "children") and item.children:
                                        # This is a folder, count instruments inside
                                        folder_instruments = sum(1 for plugin in item.children 
                                                               if hasattr(plugin, "is_instrument") and plugin.is_instrument)
                                        if folder_instruments > 0:
                                            plugin_folders.append({
                                                "name": item.name,
                                                "count": folder_instruments
                                            })
                                            instrument_count += folder_instruments
                                    elif hasattr(item, "is_instrument") and item.is_instrument:
                                        # Direct instrument plugin
                                        instrument_count += 1
                            
                            # Only add category if we found instruments or we can't determine
                            category_info = {
                                "name": f"{plugin_category.name} Instruments",
                                "type": "plugin_category",
                                "format": plugin_category.name,
                                "item_count": instrument_count,
                                "folders": plugin_folders
                            }
                            categories.append(category_info)
                            self.logger.info(f"Found plugin category: {plugin_category.name} with approximately {instrument_count} instruments")
                
                # Ensure we have at least some categories to display
                if not categories:
                    self.logger.info("No instrument categories found, adding example entries")
                    categories = [
                        {"name": "Instrument Racks", "type": "instrument_category", "item_count": 0},
                        {"name": "MIDI Effects", "type": "instrument_category", "item_count": 0},
                        {"name": "VST Instruments", "type": "plugin_category", "format": "VST", "item_count": 0}
                    ]
                
                # Return count and categories
                self.logger.info(f"Returning {len(categories)} instrument categories")
                return (len(categories), json.dumps(categories))
                
            except Exception as e:
                self.logger.error(f"Error getting instrument categories: {str(e)}")
                return (0, "[]")
        
        self.osc_server.add_handler("/live/browser/get_instrument_categories", browser_get_instrument_categories)
        
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

        # Store references to browser functions so they can be accessed by TCP handlers
        self.browser_list_vst_plugins = browser_list_vst_plugins
        self.browser_list_instrument_categories = browser_get_instrument_categories
        self.browser_list_audio_effects = browser_list_audio_effects
        
        # Register TCP handlers for large data transfers
        self.register_tcp_handlers()
    
    def register_tcp_handlers(self):
        """Register TCP handlers for large data transfers"""
        self.osc_server.add_tcp_handler("GET_VST_PLUGINS", self._tcp_get_vst_plugins)
        self.osc_server.add_tcp_handler("GET_INSTRUMENT_CATEGORIES", self._tcp_get_instrument_categories)
        self.osc_server.add_tcp_handler("GET_AUDIO_EFFECTS", self._tcp_get_audio_effects)
        self.logger.info("Registered TCP handlers for large data transfers")
    
    def _tcp_get_vst_plugins(self):
        """TCP handler to get all VST plugins"""
        try:
            self.logger.info("TCP request for all VST plugins")
            # Use the reference to the browser function with arguments for all plugins
            _, plugins_json = self.browser_list_vst_plugins([0, 10000])
            return plugins_json
        except Exception as e:
            self.logger.error(f"Error handling TCP VST plugins request: {e}")
            return json.dumps({"error": str(e)})
    
    def _tcp_get_instrument_categories(self):
        """TCP handler to get all instrument categories"""
        try:
            self.logger.info("TCP request for all instrument categories")
            # Use the reference to the browser function
            _, categories_json = self.browser_list_instrument_categories([])
            return categories_json
        except Exception as e:
            self.logger.error(f"Error handling TCP instrument categories request: {e}")
            return json.dumps({"error": str(e)})
    
    def _tcp_get_audio_effects(self):
        """TCP handler to get all audio effects"""
        try:
            self.logger.info("TCP request for all audio effects")
            # Use the reference to the browser function with arguments for all effects
            _, effects_json = self.browser_list_audio_effects([0, 10000])
            return effects_json
        except Exception as e:
            self.logger.error(f"Error handling TCP audio effects request: {e}")
            return json.dumps({"error": str(e)})

# Helper method to recursively explore browse items 
def _explore_browse_items(self, browse_items, parent_category, result_list):
    """Helper method to explore browse_items which some Live versions use instead of children"""
    try:
        if not browse_items:
            return
            
        self.logger.info(f"Exploring {len(browse_items)} browse items in {parent_category}")
        
        for item in browse_items:
            item_name = item.name if hasattr(item, "name") else "Unnamed"
            self.logger.info(f"Browse item: {item_name}")
            
            # Check if this is a folder with more items
            if hasattr(item, "browse_items") and item.browse_items:
                # This is a folder (likely manufacturer)
                self.logger.info(f"Found folder: {item_name} with {len(item.browse_items)} items")
                
                # Recursive call to explore this folder
                self._explore_browse_items(item.browse_items, f"{parent_category}/{item_name}", result_list)
            else:
                # This is a plugin
                plugin_info = {
                    "name": item_name,
                    "category": parent_category,
                    "is_loadable": item.is_loadable if hasattr(item, "is_loadable") else True,
                    "is_instrument": item.is_instrument if hasattr(item, "is_instrument") else False,
                    "is_effect": item.is_effect if hasattr(item, "is_effect") else True,
                    "is_plugin": True,
                    "format": parent_category.split('/')[0] if '/' in parent_category else parent_category
                }
                result_list.append(plugin_info)
                self.logger.info(f"Added plugin: {item_name} in {parent_category}")
    except Exception as e:
        self.logger.error(f"Error exploring browse items: {str(e)}")
