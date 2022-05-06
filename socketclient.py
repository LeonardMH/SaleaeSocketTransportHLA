import socket
import threading
import logging

from typing import Tuple


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 50626


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


def listener(conn, **kwargs):
    quiet_receive = kwargs.get('quiet_receive', False)
    quiet_response = kwargs.get('quiet_response', False)
    show_msg_dir = kwargs.get('show_msg_dir', False)
    response_handler = kwargs.get('response_handler', None)

    data_accumulator = ""

    with conn:
        while True:
            logging.debug("listener loop")

            try:
                data, data_accumulator = rx_data_until_newline(conn, current_accumulator=data_accumulator)

                # if the rx_data function hits a timeout it will return (None, None), in this case go
                # back to rebinding
                if any([x is None for x in (data, data_accumulator)]):
                    return
            except ConnectionResetError:
                # it's possible the connection can be reset by Saleae here on capture start,
                # if so just go back and rebind the socket
                return

            for packet in data:
                # if we get here, we got some data in the receive buffer,
                # process it and respond back to Saleae
                if not quiet_receive:
                    print(("-> " if show_msg_dir else "") + packet)

                if response_handler is not None:
                    resp = response_handler.handle_incoming_response(packet)
                else:
                    resp = None

                if resp is not None:
                    conn.sendall(resp)

                    if not quiet_response:
                        rsp_str = resp.decode('utf-8').rstrip()
                        print(("<- " if show_msg_dir else "") + rsp_str)


def event_loop(host, port, **kwargs):
    while True:
        logging.debug(f"event_loop({host}, {port})")
        conn, addr = bind(host=args.host, port=args.port)

        # bind sets a timeout of 100ms to check for a connection, if it doesn't
        # hear anything back it will timeout and unblock the program so we can
        # exit with Ctrl-C, or we can just keep checking
        if (conn, addr) == (None, None):
            continue

        listener(conn, **kwargs)


def parse_responder_spec_to_parts(responder_spec: str) -> Tuple[str, str]:
    from os.path import join

    # begin by splitting on the colon to extract the class name, there
    # could possibly be colons in the file name which would cause more
    # than two splits, so we can use the splat operator to collect all
    # of these into a list and then rejoin them later
    *fpath, class_name = responder_spec.split(':')
    fpath = join("".join(fpath))

    return fpath, class_name


def load_responder_classtype(fpath, class_name):
    from importlib import util as imputil
    from os.path import basename, splitext
    from responsehandler import DefaultResponder

    mod_name = splitext(basename(fpath))[0]
    spec = imputil.spec_from_file_location(mod_name, fpath)
    responder = imputil.module_from_spec(spec)

    spec.loader.exec_module(responder)
    return getattr(responder, class_name, DefaultResponder)


if __name__ == "__main__":
    import argparse
    import sys
    import time

    parser = argparse.ArgumentParser("socketsink.py: Read data from a streaming socket and print to STDOUT")
    parser.add_argument("-H", "--host", default=DEFAULT_HOST, help="host address to bind to")
    parser.add_argument("-P", "--port", default=DEFAULT_PORT, help="port to bind to", type=int)
    parser.add_argument('-q', '--quiet', action='store_true', help="do not print any message responses")
    parser.add_argument(
        '-r', '--responder',
        help="custom responder to process messages from server, provide a full path and class name as <fpath>:<class_name>")
    parser.add_argument('--quiet-receive', action='store_true', help="do not print the data received from the server")
    parser.add_argument('--quiet-response', action='store_true', help="do not print the data sent back to the server")
    parser.add_argument('--show-message-dir', action='store_true', help="when logging responses, show direction of message transmission")

    args = parser.parse_args()

    if args.quiet:
        quiet_receive = True
        quiet_response = True
        show_msg_dir = False
    else:
        quiet_receive = args.quiet_receive
        quiet_response = args.quiet_response
        show_msg_dir = args.show_message_dir

    if args.responder:
        responder = load_responder_classtype(*parse_responder_spec_to_parts(args.responder))()
    else:
        from responsehandler import DefaultResponder
        responder = DefaultResponder()

    # set this up as a deamon thread which allows us to run the event loop in
    # the background (the socket accept method is blocking) and still exit out
    # of the program with ctrl-c
    event_loop_thread = threading.Thread(
        target=event_loop,
        args=(args.host, args.port),
        kwargs={
            'quiet_receive': quiet_receive,
            'quiet_response': quiet_response,
            'show_msg_dir': show_msg_dir,
            'response_handler': responder,
        },
        daemon=True,
    )

    try:
        event_loop_thread.start()
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        sys.exit(0)
