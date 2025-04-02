from ableton.v2.control_surface.component import Component
from typing import Optional, Tuple, Any, Dict, Callable
import logging
from .osc_server import OSCServer
import socket
import threading
import json

# TCP port for large data transfers
TCP_DATA_PORT = 11002  

class AbletonOSCHandler(Component):
    def __init__(self, manager):
        super().__init__()

        self.logger = logging.getLogger("abletonosc")
        self.manager = manager
        self.osc_server: OSCServer = self.manager.osc_server
        self.init_api()
        self.listener_functions = {}
        self.listener_objects = {}
        self.class_identifier = None
        
        # TCP server for large data transfers
        self.tcp_server = None
        self.tcp_handlers: Dict[str, Callable] = {}
        self._initialize_tcp_server()

    def _initialize_tcp_server(self):
        """Initialize the TCP server for handling large data transfers"""
        try:
            self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_server.bind(('0.0.0.0', TCP_DATA_PORT))
            self.tcp_server.listen(5)
            
            self.logger.info(f"Starting TCP server for large data transfers on port {TCP_DATA_PORT}")
            
            # Start TCP server in a background thread
            tcp_thread = threading.Thread(target=self._handle_tcp_connections, daemon=True)
            tcp_thread.start()
        except Exception as e:
            self.logger.error(f"Failed to initialize TCP server: {e}")
            self.tcp_server = None

    def _handle_tcp_connections(self):
        """Handle incoming TCP connections in a background thread"""
        if not self.tcp_server:
            return
            
        while True:
            try:
                client, addr = self.tcp_server.accept()
                self.logger.info(f"TCP client connected from {addr}")
                client_thread = threading.Thread(
                    target=self._handle_tcp_client,
                    args=(client, addr),
                    daemon=True
                )
                client_thread.start()
            except Exception as e:
                self.logger.error(f"Error accepting TCP connection: {e}")
                if not self.tcp_server:
                    break

    def _handle_tcp_client(self, client, addr):
        """Handle a connected TCP client"""
        try:
            # Configure timeout for client operations
            client.settimeout(30)  # 30 seconds timeout
            
            # Receive request command (should be small)
            data = client.recv(1024)
            if not data:
                return
                
            request = data.decode('utf-8').strip()
            self.logger.info(f"TCP request from {addr}: {request}")
            
            # Process the request
            if request in self.tcp_handlers:
                handler = self.tcp_handlers[request]
                try:
                    # Get data from handler
                    result = handler()
                    if isinstance(result, str):
                        response_data = result
                    else:
                        response_data = json.dumps(result)
                        
                    # Send response length first (4 bytes)
                    data_len = len(response_data)
                    client.sendall(data_len.to_bytes(4, byteorder='big'))
                    
                    # Then send actual data
                    client.sendall(response_data.encode('utf-8'))
                    self.logger.info(f"TCP response sent: {data_len} bytes")
                except Exception as e:
                    self.logger.error(f"Error processing TCP request '{request}': {e}")
                    error_response = json.dumps({"error": str(e)})
                    client.sendall(len(error_response).to_bytes(4, byteorder='big'))
                    client.sendall(error_response.encode('utf-8'))
            else:
                self.logger.warning(f"Unknown TCP request: {request}")
                error_response = json.dumps({"error": f"Unknown request: {request}"})
                client.sendall(len(error_response).to_bytes(4, byteorder='big'))
                client.sendall(error_response.encode('utf-8'))
        except socket.timeout:
            self.logger.warning(f"TCP client {addr} timed out")
        except ConnectionResetError:
            self.logger.warning(f"TCP client {addr} disconnected")
        except Exception as e:
            self.logger.error(f"Error handling TCP client {addr}: {e}")
        finally:
            client.close()
            self.logger.info(f"TCP client {addr} connection closed")
    
    def add_tcp_handler(self, command: str, handler: Callable):
        """
        Register a handler for TCP data requests
        
        Args:
            command: The command string that clients will send to request this data
            handler: A function that returns the data to send (will be JSON-encoded)
        """
        self.tcp_handlers[command] = handler
        self.logger.info(f"Registered TCP handler for command: {command}")

    def init_api(self):
        pass

    def clear_api(self):
        self._clear_listeners()
        # Close TCP server if it exists
        if self.tcp_server:
            try:
                self.tcp_server.close()
                self.tcp_server = None
            except Exception as e:
                self.logger.error(f"Error closing TCP server: {e}")

    #--------------------------------------------------------------------------------
    # Generic callbacks
    #--------------------------------------------------------------------------------
    def _call_method(self, target, method, params: Optional[Tuple] = ()):
        self.logger.info("Calling method for %s: %s (params %s)" % (self.class_identifier, method, str(params)))
        getattr(target, method)(*params)

    def _set_property(self, target, prop, params: Tuple) -> None:
        self.logger.info("Setting property for %s: %s (new value %s)" % (self.class_identifier, prop, params[0]))
        setattr(target, prop, params[0])

    def _get_property(self, target, prop, params: Optional[Tuple] = ()) -> Tuple[Any]:
        try:
            value = getattr(target, prop)
        except RuntimeError:
            #--------------------------------------------------------------------------------
            # Gracefully handle errors, which may occur when querying parameters that don't apply
            # to a particular object (e.g. track.fold_state for a non-group track)
            #--------------------------------------------------------------------------------
            value = None
        self.logger.info("Getting property for %s: %s = %s" % (self.class_identifier, prop, value))
        return (value, *params)

    def _start_listen(self, target, prop, params: Optional[Tuple] = (), getter = None) -> None:
        """
        Start listening for the property named `prop` on the Live object `target`.
        `params` is typically a tuple containing the track/clip index.

        getter can be used for a customer getter when we're accessing native objects
        e.g. in view.py we don't return the selected_scene, but the selected_scene index.

        Args:
            target: 
            prop:
            params:
            getter:
        """
        def property_changed_callback():
            if getter is None:
                value = getattr(target, prop)
            else:
                value = getter(params)
            if type(value) is not tuple:
                value = (value,)
            self.logger.info("Property %s changed of %s %s: %s" % (prop, self.class_identifier, str(params), value))
            osc_address = "/live/%s/get/%s" % (self.class_identifier, prop)
            self.osc_server.send(osc_address, (*params, *value,))

        listener_key = (prop, tuple(params))
        if listener_key in self.listener_functions:
            self._stop_listen(target, prop, params)

        self.logger.info("Adding listener for %s %s, property: %s" % (self.class_identifier, str(params), prop))
        add_listener_function_name = "add_%s_listener" % prop
        add_listener_function = getattr(target, add_listener_function_name)
        add_listener_function(property_changed_callback)
        self.listener_functions[listener_key] = property_changed_callback
        self.listener_objects[listener_key] = target
        #--------------------------------------------------------------------------------
        # Immediately send the current value
        #--------------------------------------------------------------------------------
        property_changed_callback()

    def _stop_listen(self, target, prop, params: Optional[Tuple[Any]] = ()) -> None:
        listener_key = (prop, tuple(params))
        if listener_key in self.listener_functions:
            self.logger.info("Removing listener for %s %s, property %s" % (self.class_identifier, str(params), prop))
            listener_function = self.listener_functions[listener_key]
            remove_listener_function_name = "remove_%s_listener" % prop
            remove_listener_function = getattr(target, remove_listener_function_name)
            try:
                remove_listener_function(listener_function)
            except Exception as e:
                #--------------------------------------------------------------------------------
                # This exception may be thrown when an observer is no longer connected --
                # e.g., when trying to stop listening for a clip property of a clip that has been deleted.
                # Ignore as it is benign.
                #--------------------------------------------------------------------------------
                self.logger.info("Exception whilst removing listener (likely benign): %s" % e)

            del self.listener_functions[listener_key]
            del self.listener_objects[listener_key]
        else:
            self.logger.warning("No listener function found for property: %s (%s)" % (prop, str(params)))

    def _clear_listeners(self):
        """
        Clears all listener functions, to prevent listeners continuing to report after a reload.
        """
        for listener_key in list(self.listener_functions.keys())[:]:
            target = self.listener_objects[listener_key]
            prop, params = listener_key
            self._stop_listen(target, prop, params)
