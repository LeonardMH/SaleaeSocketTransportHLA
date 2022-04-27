"""SaleaeSocketSourceHLA

Implements a high level analyzer for Saleae Logic 2 which accepts Analyzer frame data and redirects it to 
a network port for external processing.
"""
import socket
import json

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, StringSetting, NumberSetting, ChoicesSetting


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "50626"


def saleae_time_to_str(saleae_time):
    """Convert the SaleaeTime object to ISO formatted string"""
    return saleae_time.as_datetime().isoformat()


class SocketSource(HighLevelAnalyzer):
    # BEGIN: User Settings
    socket_host = StringSetting(label='Host (optional, default=127.0.0.1)')
    socket_port = StringSetting(label="Port (optional, default=50626)")

    socket = None

    def __init__(self):
        """Called anytime the Analyzer is initialized which happens when it is first added and on every re-run"""
        self.socket_send_json({
            "type": "message",
            "data": "Starting Analysis",
        })

        # if we haven't initialized a socket connection yet, do so
        if self.socket is None:
            self.socket_connect()

        # at this point we think we have a socket, try to talk to it and see if it throws an error
        try:
            self.socket_send_json({
                "type": "message",
                "data": "Connected to socket",
            })
        except ConnectionResetError:
            # the socket connection was reset, reconnect it
            self.socket_connect()

    def socket_connect(self):
        """Attempt to connect to the socket defined by user settings (or use default)"""
        host = self.socket_host or DEFAULT_HOST
        port = int(self.socket_port or DEFAULT_PORT)

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
        except ConnectionRefusedError:
            self.socket = None

    def socket_send_json(self, message):
        # check for lack of socket connection first so we don't waste time processing 
        # data and raising errors
        if self.socket is None:
            return

        string = (json.dumps(message) + '\n')

        try:
            self.socket.sendall(string.encode('utf-8'))
        except (ConnectionResetError, ConnectionAbortedError):
            # if we lost the connection while writing data, just indicate that we are disconnected 
            # so we don't keep trying to write data
            self.socket = None
    
    def decode(self, frame: AnalyzerFrame):
        '''This method is called once for each frame of data generated.

        This analyzer produces no corresponding AnalyzerFrames, it only sends 
        data to the specified socket.
        '''
        # scrub the frame data for bytes objects, which are not JSON serializable, convert 
        # to list of integers, not sure whether I am free to modify this or not so explicitly 
        # requesting a copy
        frame_data = frame.data.copy()
        for (k, v) in frame_data.items():
            if isinstance(v, bytes): frame_data[k] = list(v)

        # send the raw frame data (sanitized for JSON) to the socket, formatted as JSON
        self.socket_send_json({
            "type": "frame",
            "frame-type": frame.type,
            "start": saleae_time_to_str(frame.start_time),
            "end": saleae_time_to_str(frame.end_time),
            "data": frame_data,
        })