"""SaleaeSocketSourceHLA

Implements a high level analyzer for Saleae Logic 2 which accepts Analyzer frame data and redirects it to 
a network port for external processing.
"""
import socket
import json

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, StringSetting, ChoicesSetting
from collections import OrderedDict


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "50626"
CHECK_FOR_RESPONSE_OPTIONS = OrderedDict((
    ("No Check", False),
    ("Check", True),
))


def saleae_time_to_str(saleae_time):
    """Convert the SaleaeTime object to ISO formatted string"""
    return saleae_time.as_datetime().isoformat()


def rx_data_until_newline(conn, current_accumulator=None):
    if current_accumulator is not None:
        accumulator = [current_accumulator]
    else:
        accumulator = [""]

    while True:
        data = conn.recv(2048).decode('utf-8')

        if '\n' not in data:
            # no newline in this dataset, just keep appending to our current string
            accumulator[0] += data
        else:
            # found at least one newline in this string, split it on newlines (if newline is the last
            # character split() will return an empty string in the last entry)
            split_data = data.split('\n')
            accumulator[0] += split_data[0]
            accumulator.extend(split_data[1:])
            break
    
    # accumulator now contains an initial entry which is all the data we got up to the point of the first 
    # newline, as there could be multiple newlines in any given data packet, we will return a tuple here:
    # - the first entry is a list containing all of the 'valid' data packets
    # - the second entry is the last entry which we will start our next rx sequence with
    return accumulator[0:-1], accumulator[-1]


class SocketSource(HighLevelAnalyzer):
    # BEGIN: User Settings
    socket_host = StringSetting(label='Host (optional, default=127.0.0.1)')
    socket_port = StringSetting(label="Port (optional, default=50626)")
    check_for_response = ChoicesSetting(CHECK_FOR_RESPONSE_OPTIONS.keys())

    socket = None

    def __init__(self):
        """Called anytime the Analyzer is initialized which happens when it is first added and on every re-run"""
        self.missed_packets = 0
        self.data_accumulator = ""

        # check to see if we have a connection, try to talk to it and see if it throws an error
        try:
            self.socket_send_json({
                "type": "client-notification",
                "data": "Ping: checking connection",
            }, unsafe=True)
        except (AttributeError, ConnectionResetError):
            self.socket_connect()
        else:
            if self.socket is None:
                self.socket_connect()

        # at this point we think we have a socket, try to talk to it and see if it throws an error
        self.socket_send_json({
            "type": "client-notification",
            "data": "Connected to socket",
        })

        # indicate to the client whether we expect to receive responses or not
        self.socket_send_json({
            "type": "client-control",
            "server-expects-response": self.should_check_for_response(),
        })


    def should_check_for_response(self):
        return CHECK_FOR_RESPONSE_OPTIONS[self.check_for_response]

    def socket_connect(self):
        """Attempt to connect to the socket defined by user settings (or use default)"""
        host = self.socket_host or DEFAULT_HOST
        port = int(self.socket_port or DEFAULT_PORT)

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.connect((host, port))
            print("Info: Socket connected")
        except ConnectionRefusedError:
            print("Warning: Socket connection Refused")
            self.socket = None

    def socket_send_json(self, message, unsafe=False):
        # check for lack of socket connection first so we don't waste time processing 
        # data and raising errors
        if not unsafe and self.socket is None:
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

        # if the check for response option is not enabled, we can simply return here 
        # as we aren't going to generate any frames, also check for whether we have an 
        # active connection or not since we don't want to waste time waiting for a 
        # response that will never come
        if not self.should_check_for_response() or self.socket is None:
            return

        # if we're here, we are expecting a response from the connected client
        response, self.data_accumulator = rx_data_until_newline(
            self.socket,
            current_accumulator=self.data_accumulator)

        if len(response) == 1:
            # in this case we just got the one packet we were looking for, reduce it to the 
            # contained type
            response = response[0]
        else:
            # in this case, we got too much data for one read and ended up with multiple 
            # newlines in a single block, we need to just grab the most recent data and
            # indicate that we missed a packet
            self.missed_packets += len(response) - 1
            print(f"Warning: missed_packets={self.missed_packets}")
            response = response[-1]

        # attempt to decode the data as JSON as an integrity check
        _ = json.loads(response)
        print(f"resp: {response}")
