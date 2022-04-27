# SaleaeSocketSourceHLA

A High Level Analyzer for Saleae which redirects analyzer frames to a network socket.

This HLA produces no Analyzer frames on its own so will not add any new frames to the GUI, it
only intercepts frames produced by other analyzers and copies them in JSON format to a socket for
another tool to listen and provide further data processing.

![Screenshot of Saleae Logic 2 w/ SaleaeSocketSourceHLA and serialsink.py running in a terminal window](assets/screenshot-1.png)

## Using socketsink.py

This repository includes a helper script `socketsink.py` which can be used to check that the
analyzer is functioning as expected. It implements a basic socket listener which waits for data from
Saleae and prints frames to STDOUT as they are received. There are some basic error recovery mechanisms
built in, but this implementation is far from robust.

Basic usage instructions can be found with `python socketsink.py --help`:

```
usage: socketsink.py: Read data from a streaming socket and print to STDIN [-h] [--host HOST] [--port PORT]

options:
  -h, --help   show this help message and exit
  --host HOST  Host address to bind to
  --port PORT  Port to bind to
```

You can exit this tool at any time with the `CTRL+C` key combination.

## Using SaleaeSocketSourceHLA and socketsink.py over network

While this HLA was designed primarily with the intent of routing data from within Saleae to another
data consumer on the same machine, the decision to use sockets as the underlying transport means we
get the ability to send Saleae data to a remote machine for free. Again, this solution is not necessarily
robust, so YMMV.
