import socket
import threading


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 50626


def bind(host=DEFAULT_HOST, port=DEFAULT_PORT):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    s.bind((host, port))
    s.listen()

    try:
        s.settimeout(0.1)
        return s.accept()
    except (socket.timeout, TimeoutError):
        return (None, None)


def listener(conn, addr, recv_bufsize=1024):
    with conn:
        while True:
            data = conn.recv(recv_bufsize)
            if data is None or data == b'':
                return

            # print the data as a string without any additional newlines,
            # they are all already encoded into the data
            print(data.decode('utf-8'), end='')


def event_loop(host, port):
    while True:
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
