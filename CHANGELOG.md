# Changelog

All notable changes to SaleaeSocketTransportHLA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2022-05-06

### Changed
- Changed apiVersion from 1.1.0 to 1.0.0 for compatibility (16a9dbe)
  - Saleae's default template uses 1.1.0 which is not yet supported
  - All major features verified to work with apiVersion 1.0.0
- Code cleanup for integration with TI tools (3c3238c)
  - Improved responsehandler.py structure
  - Refined socketclient.py implementation

## [1.0.0] - 2022-04-30

### Added
- Dynamic loading of response handlers via `-r/--responder` command line option (cc52c30)
  - Users can now specify custom responders as `<filepath>:<classname>`
  - Added `responders/` folder for user-created responders
  - Implemented `load_responder_classtype()` function for dynamic imports
  - Added FishResponder example to documentation
- Comprehensive ResponseHandler API documentation in README.md (cc52c30)
- Direct to file streaming functionality (31abfff)
  - Three file stream modes: Overwrite/Append, Sequence, Timestamp
  - Optional file streaming with or without socket connection
  - `fs_control`, `fs_options`, and `fs_path` settings in HLA
- `ResponseHandler` base class with helper methods (cc52c30)
  - `prepare_json_incoming()` for data reception
  - `prepare_json_outgoing()` for data transmission
  - Instance variables for stateful processing
- `TransportData` dataclass for format conversions (cc52c30)
- Built-in responders:
  - `DefaultResponder`: Auto-detects analyzer type and formats data
  - `NullResponder`: Receives data without responding
  - `AckResponder`: Simple acknowledgment responder
- Significantly expanded README.md documentation (d1d29f2, 02d4a87)
  - Comprehensive data format specifications
  - Multiple frame examples for different analyzer types
  - Usage instructions and command-line options

### Changed
- Improved timing handling and timestamp conversion (277149d)
  - Better `SaleaeTime` parsing with `sal_to_dt()` function
  - More accurate nanosecond precision handling
- Renamed project from "SaleaeSocketSourceHLA" to "SaleaeSocketTransportHLA" (b1a8c97)
  - Better reflects bidirectional nature of communication
- Analyzer version set to 1.0.0 (0218a11)

### Fixed
- Corrected STDIN/STDOUT terminology in README.md (62e23ce)

## [0.2.0] - 2022-04-29

### Added
- Bidirectional socket communication (b4db0ee)
  - Analyzer can now receive responses from clients
  - Client responses can generate new AnalyzerFrames in Saleae
  - `socket_check_response` setting to control response behavior
- Decode examples for multiple analyzer types (277149d)
  - Async Serial decoder examples
  - I2C decoder examples with full transactions
- Screenshot to repository and README (a54033c)

### Changed
- Cleanup and refinement of decode format handling (f05ee9e)

## [0.1.0] - 2022-04-27

### Added
- Initial implementation of SaleaeSocketSourceHLA (181ce3d)
  - High Level Analyzer for Saleae Logic 2
  - Unidirectional socket streaming of analyzer frames
  - JSON-based data transport format
- `socketclient.py` (originally `socketsink.py`) for receiving data (66b13b4)
  - Socket binding and connection handling
  - Daemon thread for non-blocking operation
  - Command-line interface with host/port configuration
- Initial README.md with project overview (70119b8)
- MIT License (46cd143)
- Project structure and configuration files (46cd143)

### Features in Initial Release
- Socket-based communication (localhost by default)
- Configurable host and port settings
- JSON serialization of AnalyzerFrame data
- Support for multiple low-level analyzer types
- Nanosecond-precision timestamps
- Error handling for connection issues

---

## Version History Summary

- **v1.0.1** (2022-05-06): API compatibility fix and TI tools integration cleanup
- **v1.0.0** (2022-04-30): Major release with dynamic responders, file streaming, and comprehensive docs
- **v0.2.0** (2022-04-29): Bidirectional communication added
- **v0.1.0** (2022-04-27): Initial unidirectional streaming implementation

## Links

[1.0.1]: https://github.com/LeonardMH/SaleaeSocketTransportHLA/compare/0218a11...16a9dbe
[1.0.0]: https://github.com/LeonardMH/SaleaeSocketTransportHLA/compare/b4db0ee...0218a11
[0.2.0]: https://github.com/LeonardMH/SaleaeSocketTransportHLA/compare/66b13b4...b4db0ee
[0.1.0]: https://github.com/LeonardMH/SaleaeSocketTransportHLA/commit/181ce3d
