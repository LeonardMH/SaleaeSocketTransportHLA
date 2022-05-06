import json

from dataclasses import dataclass
from typing import Union


@dataclass
class TransportData:
    as_bytes: bytes
    as_dict: dict
    as_str: str

    @staticmethod
    def from_any(data: Union[bytes, dict, str]):
        """Create TransportData from any of the common data types"""
        if isinstance(data, bytes):
            return TransportData.from_bytes(data)
        elif isinstance(data, dict):
            return TransportData.from_dict(data)
        elif isinstance(data, str):
            return TransportData.from_str(data)

        raise TypeError(f"Got unexpected input type for data: {type(data)}")

    @staticmethod
    def from_bytes(data: bytes):
        as_str = data.decode('utf-8')
        return TransportData(
            as_bytes=data,
            as_str=as_str,
            as_dict=json.loads(as_str))

    @staticmethod
    def from_dict(data: dict):
        as_str = json.dumps(data)
        return TransportData(
            as_bytes=as_str.encode('utf-8'),
            as_str=as_str,
            as_dict=data)

    @staticmethod
    def from_str(data: str):
        return TransportData(
            as_bytes=data.encode('utf-8'),
            as_str=data,
            as_dict=json.loads(data))


class ResponseHandler:
    """Implement this class to handle decoding over multiple frames of data"""

    def __init__(self):
        # as you build frame information, store it here, when done with the frame set this back to None
        self.tracking_frame = None

        # while analyzing multiple frames you may need to refer to information from previous frames, store
        # that data here and set this back to an empty list when consumed
        self.previous_data = []

        # tracks most recent incoming and outgoing messages as TransportData types
        self.current_incoming = None
        self.current_outgoing = None

    def handle_incoming_response(self, recv: str) -> bytes:
        raise NotImplementedError("Must be implemented by subclass")

    def prepare_json_incoming(self, data: Union[bytes, dict, str]) -> dict:
        if not isinstance(data, TransportData):
            data = TransportData.from_any(data)

        self.current_incoming = data
        return data.as_dict

    def prepare_json_outgoing(self, data: Union[bytes, dict, str]) -> bytes:
        if not isinstance(data, TransportData):
            data = TransportData.from_any(data)

        self.current_outgoing = data
        return (data.as_str + '\n').encode('utf-8')


class DefaultResponder(ResponseHandler):
    def __init__(self):
        super().__init__()
        self.analyzer_type = None
        self.decode_map = {
            'async-serial': self.decode_async_serial,
        }

    def decode_async_serial(self, decoded):
        decoded['frame-type'] = 'text'
        decoded['data']['text'] = "0x{:02X}".format(decoded['data']['data'][0])

        return decoded

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

    def handle_incoming_response(self, recv):
        decoded = self.prepare_json_incoming(recv)

        # if we don't know what kind of data we are analyzing yet, figure it out
        determined_analyzer = self.determine_analyzer_type(decoded)

        if determined_analyzer is None:
            return self.prepare_json_outgoing(decoded)

        if self.analyzer_type is None:
            self.analyzer_type = determined_analyzer

        # look up the correct decoder for this analyzer_type, for anything we don't understand,
        # just respond back with the same data we got
        json_response = self.decode_map.get(self.analyzer_type, self.prepare_json_outgoing)(decoded)
        return self.prepare_json_outgoing(json_response)


class NullResponder(ResponseHandler):
    """A response handler that doesn't respond"""
    def handle_incoming_response(self, recv: str) -> bytes:
        return None


class AckResponder(ResponseHandler):
    """A response handler that just ACKs message receipt"""
    def handle_incoming_response(self, recv: str) -> bytes:
        return self.prepare_json_outgoing({'type': 'ACK'})