from typing import Tuple, Any, Callable, Dict
from .constants import OSC_LISTEN_PORT, OSC_RESPONSE_PORT, TCP_DATA_PORT
from ..pythonosc.osc_message import OscMessage, ParseError
from ..pythonosc.osc_bundle import OscBundle
from ..pythonosc.osc_message_builder import OscMessageBuilder, BuildError

import re
import errno
import socket
import logging
import traceback
import threading
import json
import time

class OSCServer:
    def __init__(self,
                 local_addr: Tuple[str, int] = ('0.0.0.0', OSC_LISTEN_PORT),
                 remote_addr: Tuple[str, int] = ('127.0.0.1', OSC_RESPONSE_PORT)):
        """
        Class that handles OSC server responsibilities, including support for sending
        reply messages.

        Implemented because pythonosc's OSC server causes a beachball when handling
        incoming messages. To investigate, as it would be ultimately better not to have
        to roll our own.

        Args:
            local_addr: Local address and port to listen on.
                        By default, binds to the wildcard address 0.0.0.0, which means listening on
                        every available local IPv4 interface (including 127.0.0.1).
            remote_addr: Remote address to send replies to, by default. Can be overridden in send().
        """

        self._local_addr = local_addr
        self._remote_addr = remote_addr
        self._response_port = remote_addr[1]

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(0)
        self._socket.bind(self._local_addr)
        self._callbacks = {}

        # Increase socket buffer sizes to handle larger UDP packets (fix for WinError 10040)
        try:
            send_buffer_size = 65535 
            recv_buffer_size = 65535 
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, send_buffer_size)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer_size)
            self.logger = logging.getLogger("abletonosc")
            self.logger.info(f"Socket buffer sizes increased to {send_buffer_size} bytes")
        except Exception as e:
            pass

        self.logger = logging.getLogger("abletonosc")
        self.logger.info("Starting OSC server (local %s, response port %d)",
                         str(self._local_addr), self._response_port)
        
        # Initialize TCP server for large data transfers after OSC server is ready
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

    def add_handler(self, address: str, handler: Callable) -> None:
        """
        Add an OSC handler.

        Args:
            address: The OSC address string
            handler: A handler function, with signature:
                     params: Tuple[Any, ...]
        """
        self._callbacks[address] = handler

    def clear_handlers(self) -> None:
        """
        Remove all existing OSC handlers.
        """
        self._callbacks = {}
        self.tcp_handlers = {}

    def send(self,
             address: str,
             params: Tuple = (),
             remote_addr: Tuple[str, int] = None) -> None:
        """
        Send an OSC message.

        Args:
            address: The OSC address (e.g. /frequency)
            params: A tuple of zero or more OSC params
            remote_addr: The remote address to send to, as a 2-tuple (hostname, port).
                         If None, uses the default remote address.
        """
        msg_builder = OscMessageBuilder(address)
        for param in params:
            msg_builder.add_arg(param)

        try:
            msg = msg_builder.build()
            if remote_addr is None:
                remote_addr = self._remote_addr
            self._socket.sendto(msg.dgram, remote_addr)
        except BuildError:
            self.logger.error("AbletonOSC: OSC build error: %s" % (traceback.format_exc()))

    def process_message(self, message, remote_addr):
        if message.address in self._callbacks:
            callback = self._callbacks[message.address]
            rv = callback(message.params)

            if rv is not None:
                assert isinstance(rv, tuple)
                remote_hostname, _ = remote_addr
                response_addr = (remote_hostname, self._response_port)
                self.send(address=message.address,
                          params=rv,
                          remote_addr=response_addr)
        elif "*" in message.address:
            regex = message.address.replace("*", "[^/]+")
            for callback_address, callback in self._callbacks.items():
                if re.match(regex, callback_address):
                    try:
                        rv = callback(message.params)
                    except ValueError:
                        #--------------------------------------------------------------------------------
                        # Don't throw errors for queries that require more arguments
                        # (e.g. /live/track/get/send with no args)
                        #--------------------------------------------------------------------------------
                        continue
                    except AttributeError:
                        #--------------------------------------------------------------------------------
                        # Don't throw errors when trying to create listeners for properties that can't
                        # be listened for (e.g. can_be_armed, is_foldable)
                        #--------------------------------------------------------------------------------
                        continue
                    if rv is not None:
                        assert isinstance(rv, tuple)
                        remote_hostname, _ = remote_addr
                        response_addr = (remote_hostname, self._response_port)
                        self.send(address=callback_address,
                                  params=rv,
                                  remote_addr=response_addr)
        else:
            self.logger.error("AbletonOSC: Unknown OSC address: %s" % message.address)

    def process_bundle(self, bundle, remote_addr):
        for i in bundle:
            if OscBundle.dgram_is_bundle(i.dgram):
                self.process_bundle(i, remote_addr)
            else:
                self.process_message(i, remote_addr)

    def parse_bundle(self, data, remote_addr):
        if OscBundle.dgram_is_bundle(data):
            try:
                bundle = OscBundle(data)
                self.process_bundle(bundle, remote_addr)
            except ParseError:
                self.logger.error("AbletonOSC: Error parsing OSC bundle: %s" % (traceback.format_exc()))
        else:
            try:
                message = OscMessage(data)
                self.process_message(message, remote_addr)
            except ParseError:
                self.logger.error("AbletonOSC: Error parsing OSC message: %s" % (traceback.format_exc()))

    def process(self) -> None:
        """
        Synchronously process all data queued on the OSC socket.
        """
        try:
            repeats = 0
            while True:
                #--------------------------------------------------------------------------------
                # Loop until no more data is available.
                #--------------------------------------------------------------------------------
                data, remote_addr = self._socket.recvfrom(65536)
                #--------------------------------------------------------------------------------
                # Update the default reply address to the most recent client. Used when
                # sending (e.g) /live/song/beat messages and listen updates.
                #
                # This is slightly ugly and prevents registering listeners from different IPs.
                #--------------------------------------------------------------------------------
                self._remote_addr = (remote_addr[0], OSC_RESPONSE_PORT)
                self.parse_bundle(data, remote_addr)

        except socket.error as e:
            if e.errno == errno.ECONNRESET:
                #--------------------------------------------------------------------------------
                # This benign error seems to occur on startup on Windows
                #--------------------------------------------------------------------------------
                self.logger.warning("AbletonOSC: Non-fatal socket error: %s" % (traceback.format_exc()))
            elif e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                #--------------------------------------------------------------------------------
                # Another benign networking error, throw when no data is received
                # on a call to recvfrom() on a non-blocking socket
                #--------------------------------------------------------------------------------
                pass
            else:
                #--------------------------------------------------------------------------------
                # Something more serious has happened
                #--------------------------------------------------------------------------------
                self.logger.error("AbletonOSC: Socket error: %s" % (traceback.format_exc()))

        except Exception as e:
            self.logger.error("AbletonOSC: Error handling OSC message: %s" % e)
            self.logger.warning("AbletonOSC: %s" % traceback.format_exc())

    def send_disconnect(self) -> None:
        """
        Send a disconnect signal to any connected clients before shutting down.
        This allows clients to properly handle server disconnection.
        """
        try:
            self.logger.info("Sending disconnect signal to clients")
            # Send to the most recent client that connected
            self.send("/live/connection/disconnected", (1,))
            # Allow a small delay for the message to be sent before socket closure
            time.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Error sending disconnect signal: {e}")

    def shutdown(self) -> None:
        """
        Shutdown the server network sockets.
        """
        # Send disconnect signal before closing sockets
        self.send_disconnect()
        
        # Close the UDP socket
        self._socket.close()
        
        # Close the TCP server if it exists
        if self.tcp_server:
            try:
                self.tcp_server.close()
                self.tcp_server = None
            except Exception as e:
                self.logger.error(f"Error closing TCP server: {e}")
