import socket
import threading
import logging


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 50626


def response_handler(recv):
    """Implement socket responder here"""
    # for now, just respond back with the same data we got
    if isinstance(recv, str):
        recv = (recv + '\n').encode('utf-8')

    return recv


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
                resp = response_handler(packet)

                if resp is not None:
                    conn.sendall(resp)

                # attempt to decode the data as JSON as an integrity check
                _ = json.loads(packet)
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
