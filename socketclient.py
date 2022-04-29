import json
from multiprocessing import set_forkserver_preload
import socket
import threading
import logging


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 50626


class ResponseHandler:
    """Implement this class to handle decoding over multiple frames of data"""
    def __init__(self):
        self.analyzer_type = None
        self.decode_map = {
            'async-serial': self.decode_async_serial,
        }

        # as you build frame information, store it here, when done with the frame set this back to None
        self.tracking_frame = None

        # while analyzing multiple frames you may need to refer to information from previous frames, store
        # that data here and set this back to an empty list when consumed
        self.previous_data = []

    def determine_analyzer_type(self, decoded):
        """Determines the input type of the data we are decoding, Saleae provides no direct indication of this
        
        Returns None if type cannot be reliably determined or incoming data is not a frame.
        """
        if decoded['type'] != 'frame':
            return None

        ft = decoded['frame-type']
        data = decoded['data']

        # all known frame types contain data
        if data is None:
            return None

        if ft == 'data':
            # i2c and async-serial both contain a data field, i2c will always contain an 'ack' field in the data 
            # which serial does not
            if 'ack' not in data:
                return 'async-serial'
            else:
                return 'i2c'
        elif ft in ['address', 'start', 'stop']:
            # i2c frames do not always have a data key, but they'll always have one of these at least and no 
            # other analyzer uses these keys
            return 'i2c'
        elif ft in ['enable', 'disable', 'result', 'error']:
            # spi frame shave unique keys
            return 'spi'

        return None

    def parse_incoming_json(self, input):
        return json.loads(input)

    def prepare_json_for_response(self, output):
        if isinstance(output, bytes):
            return output
        
        return (json.dumps(output) + '\n').encode('utf-8')
    
    def decode_async_serial(self, decoded):
        decoded['frame-type'] = 'text'
        decoded['data']['text'] = "0x{:02X}".format(decoded['data']['data'][0])

        return decoded
    
    def handle_response(self, recv):
        decoded = self.parse_incoming_json(recv)

        # if we don't know what kind of data we are analyzing yet, figure it out
        determined_analyzer = self.determine_analyzer_type(decoded)

        if determined_analyzer is None:
            return self.prepare_json_for_response(decoded)

        if self.analyzer_type is None:
            self.analyzer_type = determined_analyzer

        # look up the correct decoder for this analyzer_type, for anything we don't understand, 
        # just respond back with the same data we got
        json_response = self.decode_map.get(self.analyzer_type, self.prepare_json_for_response)(decoded)
        return self.prepare_json_for_response(json_response)


def bind(host=DEFAULT_HOST, port=DEFAULT_PORT):
    logging.debug(f"bind({host}, {port})")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    s.bind((host, port))
    s.listen()

    try:
        s.settimeout(0.1)
        return s.accept()
    except (socket.timeout, TimeoutError):
        return (None, None)


def rx_data_until_newline(conn, current_accumulator=None, timeout=1.0):
    import time

    start_time = time.time()

    if current_accumulator is not None:
        accumulator = [current_accumulator]
    else:
        accumulator = [""]

    while True:
        logging.debug("rx_data_until_newline while loop")

        if time.time() - timeout > start_time:
            logging.debug("rx_data_until_newline timeout")
            return (None, None)

        data = conn.recv(2048).decode('utf-8')
        if '\n' not in data:
            # no newline in this dataset, just keep appending to our current string
            accumulator[0] += data
        else:
            # found at least one newline in this string, split it on newlines (if newline is the last
            # character split will return an empty string in the last entry)
            split_data = data.split('\n')
            accumulator[0] += split_data[0]
            accumulator.extend(split_data[1:])
            break
    
    # accumulator now contains an initial entry which is all the data we got up to the point of the first 
    # newline, as there could be multiple newlines in any given data packet, we will return a tuple here:
    # - the first entry is a list containing all of the 'valid' data packets
    # - the second entry is the last entry which we will start our next rx sequence with
    return accumulator[0:-1], accumulator[-1]


def listener(conn, addr):
    import json

    data_accumulator = ""

    with conn:
        while True:
            logging.debug("listener loop")

            # it's possible the connection can be reset by Saleae here on capture start, 
            # if so just go back and rebind the socket
            try:
                data, data_accumulator = rx_data_until_newline(conn, current_accumulator=data_accumulator)

                # if the rx_data function hits a timeout it will return (None, None), in this case go 
                # back to rebinding
                if any([x is None for x in (data, data_accumulator)]):
                    return
            except ConnectionResetError:
                return

            for packet in data:
                # if we get here, we got some data in the receive buffer, 
                # process it and respond back to Saleae
                resp = RESPONSE_HANDLER.handle_response(packet)

                if resp is not None:
                    conn.sendall(resp)

                print(packet)


def event_loop(host, port):
    while True:
        logging.debug(f"event_loop({host}, {port})")
        conn, addr = bind(host=args.host, port=args.port)

        # bind sets a timeout of 100ms to check for a connection, if it doesn't
        # hear anything back it will timeout and unblock the program so we can
        # exit with Ctrl-C, or we can just keep checking
        if (conn, addr) == (None, None):
            continue

        listener(conn, addr)


RESPONSE_HANDLER = ResponseHandler()


if __name__ == "__main__":
    import argparse
    import sys
    import time

    parser = argparse.ArgumentParser("socketsink.py: Read data from a streaming socket and print to STDIN")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host address to bind to")
    parser.add_argument("--port", default=DEFAULT_PORT, help="Port to bind to", type=int)

    args = parser.parse_args()

    # set this up as a deamon thread which allows us to run the event loop in
    # the background (the socket accept method is blocking) and still exit out
    # of the program with ctrl-c
    event_loop_thread = threading.Thread(
        target=event_loop,
        args=(args.host, args.port),
        daemon=True,
    )

    try:
        event_loop_thread.start()
        while True: time.sleep(0.1)
    except KeyboardInterrupt:
        sys.exit(0)
