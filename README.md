# robot.py

A configurable web spider written in Python. Started in 1998, it was rewritten several times. The current version uses Python3, YAML configuration and asynchronous I/O.

## Configuration

All settings are listed in [robot.yaml](robot.yaml). You can override them with site-specific settings, see [wp.yaml](wp.yaml) for an example with rules for [Wordpress](https://wordpress.org) sites.

URL / link processing:

- `disable`: List of regexes for links that should be disabled (`href="#"`).
- `remove`: List of regexes for links that should be completely removed.
- `replace`: Replacement regexes for relative links, useful to add page names for directory indexes.
- `rewrite`: Replacement regexes for all links, useful to change the site layout on disk.

## Usage

See `robot -h` for command line arguments. Typical usage:

    ./robot.py -c 4 -f wp.yaml http://example.org/path/to/wordpress/

