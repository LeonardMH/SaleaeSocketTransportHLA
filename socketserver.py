"""SaleaeSocketTransportHLA

Implements a high level analyzer for Saleae Logic 2 which opens a bidirectional network socket for
sending data to an external program and accepts return data to generate analyzer frames.
"""
from datetime import datetime, timezone
import socket
import json
from statistics import mode

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, StringSetting, ChoicesSetting
from saleae.data.timing import SaleaeTime

from collections import OrderedDict
from enum import Enum

class FileStreamControl(Enum):
    OFF = 0
    ON_WITH_SOCKET = 1
    ON_WITHOUT_SOCKET = 2

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "50626"
CHECK_FOR_RESPONSE_OPTIONS = OrderedDict((
    ("NO", False),
    ("YES", True),
))
FILE_STREAM_CONTROL_OPTIONS = OrderedDict((
    ("OFF", FileStreamControl.OFF),
    ("ON, with socket", FileStreamControl.ON_WITH_SOCKET),
    ("ON, no socket", FileStreamControl.ON_WITHOUT_SOCKET),
))
FILE_STREAM_OPTIONS = OrderedDict((
    ("Overwrite/Append", ('a', 'append')),
    ("Sequence", ('a', 'sequence')),
    ("Timestamp", ('a', 'timestamp')),
))


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


class SocketTransport(HighLevelAnalyzer):
    # BEGIN: User Settings
    socket_host = StringSetting(label="Host (optional, default=127.0.0.1)")
    socket_port = StringSetting(label="Port (optional, default=50626)")
    socket_check_response = ChoicesSetting(CHECK_FOR_RESPONSE_OPTIONS.keys())

    fs_control = ChoicesSetting(FILE_STREAM_CONTROL_OPTIONS.keys(), label="Stream to File")
    fs_options = ChoicesSetting(FILE_STREAM_OPTIONS.keys(), label="File Stream Mode")
    fs_path = StringSetting(label="Output File")
    # END: User Settings

    socket = None
    result_types = {
        'text': { 'format': '{{data.text}}'}
    }

    def __init__(self):
        """Called anytime the Analyzer is initialized which happens when it is first added and on every re-run"""
        self.missed_packets = 0
        self.data_accumulator = ""

        self.fp_enabled = False
        self.fp_info = (None, None)

        # check to see if we have a connection, try to talk to it and see if it throws an error
        if self.socket_streaming_enabled():
            try:
                self.socket_send_json({
                    "type": "client-notification",
                    "data": "Ping: checking connection",
                    "level": "debug",
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
                "level": "info",
            })

            # indicate to the client whether we expect to receive responses or not
            self.socket_send_json({
                "type": "client-control",
                "server-expects-response": self.should_check_for_response(),
            })
        else:
            self.socket = None

        # check if the user has enabled file streaming and if so set up our fp
        fs_info = self.get_file_stream_info()
        if fs_info['enabled'] and fs_info['path'] is not None:
            self.fp_info = (fs_info['path'], fs_info['mode'])
            self.fp_enabled = True
        else:
            self.fp_info = (None, None)
            self.fp_enabled = False

    def socket_streaming_enabled(self):
        fs_control = FILE_STREAM_CONTROL_OPTIONS.get(self.fs_control, FileStreamControl.ON_WITH_SOCKET)
        return fs_control != FileStreamControl.ON_WITHOUT_SOCKET

    def get_file_stream_info(self):
        from glob import glob
        from os.path import basename, split, splitext

        fs_control = FILE_STREAM_CONTROL_OPTIONS.get(self.fs_control, FileStreamControl.ON_WITH_SOCKET)
        enabled = fs_control != FileStreamControl.OFF
        fmode, fmode_opt = FILE_STREAM_OPTIONS.get(self.fs_options, ('a', 'append'))

        ret = {
            'enabled': enabled,
            'mode': fmode,
            'path': None,
        } 

        # if file streaming isn't enabled, we have already determined all of the information needed
        if not enabled or self.fs_path == "":
            return ret
        
        # file streaming is enabled, perform validation of the path provided
        if fmode_opt == 'append':
            # append mode is simple, we can just use the file name provided,
            # if the file doesn't exist it will be created
            ret['path'] = self.fs_path
        elif fmode_opt == 'sequence':
            # sequence mode is a bit more complex...
            #  - We will use naming format <fname>-<seq_num>.<ext> based off of the user input
            #    of <fname>.ext
            user_fname, user_ext = splitext(self.fs_path)
            fname_template = "{fname}-{seq}{ext}"
            found_files = sorted(
                glob(fname_template.format(fname=user_fname, seq="*", ext=user_ext)),
                key=basename)

            # now, found_files should be a list of any files we found matching this sequence 
            # naming format
            if not found_files:
                # the base case in which the list is empty means we can just start at zero
                ret['path'] = fname_template.format(fname=user_fname, seq=0, ext=user_ext)
            else:
                # otherwise, the found_files list is sorted by filename, which should mean increasing seq 
                # values (as that should be the only difference in the names), therefore we can just take
                # the seq value from the last entry and increment it by one
                new_seq = int(splitext(basename(found_files[-1]).split('-')[1])[0]) + 1
                ret['path'] = fname_template.format(fname=user_fname, seq=new_seq, ext=user_ext)
        elif fmode_opt == 'timestamp':
            user_fname, user_ext = splitext(self.fs_path)
            ret['path'] = "{fname}-{timestamp}{ext}".format(
                fname=user_fname,
                timestamp=datetime.now().isoformat().split('.')[0].replace(':', '-'),
                ext=user_ext)

        return ret

    def should_check_for_response(self):
        return CHECK_FOR_RESPONSE_OPTIONS[self.socket_check_response]

    def socket_connect(self):
        """Attempt to connect to the socket defined by user settings (or use default)"""
        if not self.socket_streaming_enabled():
            self.socket = None
            return

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
        string = (json.dumps(message) + '\n')

        if (not unsafe and self.socket is None) or not self.socket_streaming_enabled():
            return string

        try:
            self.socket.sendall(string.encode('utf-8'))
        except (ConnectionResetError, ConnectionAbortedError):
            # if we lost the connection while writing data, just indicate that we are disconnected 
            # so we don't keep trying to write data
            self.socket = None
        
        return string
    
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
        sent_message = self.socket_send_json({
            "type": "frame",
            "frame-type": frame.type,
            "start": str(frame.start_time),
            "end": str(frame.end_time),
            "data": frame_data,
        })

        # if we have an fp, write the sent data to a file
        if self.fp_enabled:
            with open(*self.fp_info) as fp:
                fp.write(sent_message)

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

        def sal_to_dt(time_str):
            """
            input: time in a format `yyyy-mm-ddT0hh:mm:ss.up_to_12_digits`
            """
            broad, fine = time_str.split("T")
            Y, M, d = [int(x) for x in broad.split("-")]
            h, m, s = fine.split(":")
            int_s, ns = s.split(".")
            int_s = int(int_s)
            ns = int(ns[:-4 if ns.endswith("000Z") else 0])

            dt = datetime(Y, M, d, int(h), int(m), int_s, tzinfo=timezone.utc)
            ms = float(ns)/1000000.0

            return dt, ms

        # decode the data as JSON for further processing
        decoded = json.loads(response)

        # if the data doesn't say to make a frame, don't make a frame
        if decoded is None or decoded['type'] != 'frame':
            return

        # convert lists of integers in the data entry back to bytes
        for (k, v) in decoded['data'].items():
            if isinstance(v, list): 
                decoded['data'][k] = int.from_bytes(v, 'little')

        # create a new AnalyzerFrame based on the response data
        start_dt, start_ms = sal_to_dt(decoded['start'])
        end_dt, end_ms = sal_to_dt(decoded['end'])

        base_frame = AnalyzerFrame(
            decoded['frame-type'], 
            start_time=SaleaeTime(start_dt, millisecond=start_ms),
            end_time=SaleaeTime(end_dt, millisecond=end_ms),
            data=decoded['data'],
        )

        return base_frame