# robot.py

## About
A small configurable web spider to archive web sites statically.

First written in 1998, it was refactored several times. The current version uses Python3, YAML configuration and [curio](https://github.com/dabeaz/curio) for asynchronous I/O.

## Usage

See `robot -h` for command line arguments. Typical usage:

    ./robot.py -f wp.yaml -b http://example.org/path/to/wordpress/

## Configuration

Default settings are listed in [robot.yaml](robot.yaml). You can override them with site-specific settings; see e.g. [wp.yaml](wp.yaml) for [Wordpress](https://wordpress.org) rules.

### URL processing:

- `disable`: List of regexes for links that should be disabled (`href="#"`).
- `remove`: List of regexes for links that should be completely removed.
- `replace`: Replacement regexes for relative links, useful to add page names for directory indexes.
- `rewrite`: Replacement regexes for all links, useful to change the site layout on disk.
