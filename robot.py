#!/usr/bin/env python3

'''
Purpose: Beat relentlessly on an unsuspecting web server
Copyright (c) 1998-2018 Daniel Knauth
'''

from lxml import html
from urllib import parse as urlparse, robotparser
import asks, curio, os, re, time, yaml


# global settings are loaded from YAML files
CONFIG = {}


class Url:
    'A parsed URL'    

    def __init__( self, url, referer=None):
        self.referer = referer # For 404 errors
        
        if referer:
            url = urlparse.urljoin( str( referer), url)
            
        self.url = urlparse.urlsplit( url)
        self.type = None

        # Force HTTPS
        if referer and not self.is_special():
            if referer.url.scheme != self.url.scheme and referer.url.netloc == self.url.netloc:
                self.url = urlparse.urlsplit( url.replace( self.url.scheme, referer.url.scheme))
        
        # sanity check on netloc
        if not self.is_special():
            if not self.url.netloc: raise ValueError( url)
            
            if '.' in os.path.basename( self.url.path):
                _path, self.type = os.path.splitext( self.url.path.lower())
            
            
    def __str__( self):
        return urlparse.urlunsplit( self.url)
    
    
    def __eq__( self, other):
        left,  _frag = urlparse.urldefrag( str( self))
        right, _frag = urlparse.urldefrag( str( other))
        return left == right
        
        
    def __hash__( self):
        left,  _frag = urlparse.urldefrag( str( self))
        return hash( left)
        
        
    def is_static( self):
        return self.type in CONFIG['static']
    
    
    def is_special( self):
        return self.url.scheme in CONFIG['specials']


    def relativePath( self, base, fragment=None):
        'compute a relative URL'

        assert base.url.netloc and base.url.scheme
        
        # Check preconditions for relative URL
        if self.url.netloc and (
            self.url.netloc != base.url.netloc or
            self.url.scheme != base.url.scheme or
            self.url.port   != base.url.port):
                return str( self)

        path = self.url.path
        if self.url.query: path = self.url.path + '?' + self.url.query
        for pattern, sub in CONFIG['replace'].items():
            if pattern.search( path):
                path = pattern.sub( sub, path)
            
        if path != self.url.path:
            pass
        elif self.type in CONFIG['dynamic']:
            path, _ext = os.path.splitext( self.url.path)
            path = path + CONFIG['page_suffix']
        elif path.endswith('/'):
            path += CONFIG['index']
            
        # os.path.relpath assumes the a directory as second argument.
        basedir = base.url.path
        if not basedir.endswith('/'): basedir = os.path.dirname( basedir)
        path = os.path.relpath( path, basedir)
        
        return '%s#%s' % (path, fragment) if fragment else path


class Page:
    'Pages are queued by the robot and then loaded'
    
    def __init__( self, url, level):
        self.url = url
        self.level = level

        self.reply = None
        self.html = None

        self.headers = { 'User-Agent' : CONFIG['user_agent'] }
        self.headers.update( CONFIG['headers'])


    def __str__( self):
        return str( self.url)
    
        
    def __eq__( self, other):
        return str( self) == ( other)


    def is_html( self):
        return "text/html" in self.reply.headers['content-type']
        

    async def get( self):
        'Fetch the Page'
        
        self.reply = await self.session.get(
            str( self.url), headers=self.headers)
        if self.reply.status_code == 200 and self.is_html():
            self.html = html.fromstring( self.reply.text)
        return self.reply.status_code


    async def save( self, path, link_cb):
        'Write page contents to disk'
        
        # Create parent folders for a path if needed
        folder = os.path.dirname( path)
        if not os.path.isdir( folder):
            # print( '\tCreating folder:', folder)
            os.makedirs( folder)
        
        assert not os.path.isfile( path), "Attempt to overwrite %s" % path
        async with curio.file.aopen( path, 'wb') as f:
            if self.is_html():
                self.html.rewrite_links( link_cb)
                await f.write( html.tostring( self.html))
            else:
                await f.write( self.reply.content)


class Robot:
    ''' Runs through a queue of URLs to fetch,
        and keeps track of downloaded pages.
    '''
    
    def __init__( self, args):

        self.args = args
        self.hits = 0
        self.queue = []        # Items to fetch
        self.hitlist = set()   # Already visited
        self.blocklist = set() # Do not visit

        # HTTP target settings
        self.base  = Url( CONFIG['baseurl'])
        
        # Use host name as output folder name
        self.directory = os.path.join(
            self.base.url.netloc, self.base.url.path[1:])

        # Set up robots.txt
        self.robots_txt = robotparser.RobotFileParser(
            urlparse.urljoin( CONFIG['baseurl'], '/robots.txt'))
        
        # Set up a shared HTTP session
        Page.session = asks.Session( connections=CONFIG['connections'])
            

    async def go( self):
        'Crawler main entry'

        start = time.time()
        print( 'Fetching %s, max. depth is %d' % (self.base, self.args.depth))

        self.robots_txt.read()
        
        startpage = Page( self.base, 0)
        if not self.can_fetch( startpage):
            print( 'URL "%s" is blocked by robots.txt' % startpage.url)
            return
        
        # Start crawling
        self.queue.append( startpage)

        try:
            async with curio.TaskGroup() as tasks:
                self.tasks = tasks
                await tasks.spawn( self.do_page())
            
        except KeyboardInterrupt:
            print( 'Aborted')
            
        print( "Finished after %.1f seconds" % (time.time() - start))


    async def do_page( self):
        'Load a single page'

        page = self.queue.pop()
        if page.url in self.hitlist: return
        self.hitlist.add( page.url)
        
        code = await page.get()
        print( '%.2d/%d\t%s' % (
            self.hits, page.level, page.url))
        self.hits += 1

        if code == 200:
            def link_cb( url):
                'Callback to replace URLs with page-relative paths'
                
                url = self.rewrite( url)
                
                try:
                    link = Url( url, page.url)
                    if link.is_special(): return url
            
                    # Completely erase selected links 
                    for pat in CONFIG['remove']:
                        if pat.search( url): return

                    # Disable blocked links
                    if link in self.blocklist: return '#'
            
                    path = link.relativePath(
                        page.url, link.url.fragment)
                        
                    if self.args.strip:
                        pos = path.rfind( CONFIG['index'])
                        if pos >= 0: path = path[:pos]
                    return path
                    
                except ValueError:
                    return url
        
            if page.is_html():
                for nextpage in self.harvest( page):
                    self.queue.append( nextpage)
                    await self.tasks.spawn( self.do_page())
                    
            elif self.args.html_only: return
                    
            if not self.args.dryrun:
                await page.save( self.path( page.url), link_cb)
            
        elif code in (301, 302): # Follow HTTP redirects
            url = Url( page.reply.headers['Location'])
            nextpage = Page( url, page.level)
            if self.can_fetch( nextpage):
                print( "\tR  ", url)
                self.queue.insert( 0, nextpage)
                await self.tasks.spawn( self.do_page())
            
        else: 
            print( "\tOops! ", code, 'Referer:', page.url.referer)
                        

    def harvest( self, page):
        'Extract URLs from HTML'

        for (_element, _attribute, url, _pos) in page.html.iterlinks():
            url = self.rewrite( url)

            try:
                link = Url( url, page.url)
            except ValueError:
                if self.args.verbosity > 1: print( "\tERR", url)
                continue

            # Which links look interesting?
            if (link.url.scheme not in CONFIG['protocols']
                or link.url.netloc != self.base.url.netloc): 
                    if self.args.verbosity > 2: print( "\tEXT", link)
                    continue

            # Bail out if link is blocked
            if any( stop.search( url)
                for stop in list( CONFIG['disable']) + list( CONFIG['remove'])):
                    if self.args.verbosity > 1: print( "\t!  ", link)
                    self.blocklist.add( link)
                    continue
            
            if link.is_static():
                # Skip static data in test runs
                if self.args.dryrun or self.args.html_only: continue
                
                # Leave already downloaded files alone
                if os.path.isfile( self.path( link)): continue

            nextpage = Page( link, page.level + 1)
            if not self.can_fetch( nextpage):
                self.blocklist.add( link)
                continue

            if self.args.verbosity > 2: print( '\t=  ', url)
            if link in self.hitlist:
                if self.args.verbosity > 1: print( "\t✓  ", link)
                continue
    
            if nextpage in self.queue:
                if self.args.verbosity > 2: print( '\t-  ', link)
            elif nextpage.level > self.args.depth and not link.is_static():
                if self.args.verbosity > 1: print( '\tEND', link)
                self.blocklist.add( link)
            else:
                if self.args.verbosity > 0: print( "\t+  ", link)
                yield nextpage


    def can_fetch( self, page):
        'Is a page fetch allowed by robots.txt?'
        
        if self.robots_txt.can_fetch( CONFIG['user_agent'], str( page.url)):
            return True
            
        if self.args.verbosity > 1: print( "\t!  ", page.url)
        return False
        

    def path( self, link):
        'Get the storage path for an URL in the output directory'
        return os.path.join( self.directory,
            urlparse.unquote( link.relativePath( self.base)))
            
            
    def rewrite( self, url):
        'Apply global rewrite rules, i.e. to follow redirects'
        for pattern, sub in CONFIG['rewrite'].items():
            url = pattern.sub( sub, url)
        return url
        
        
if __name__ == '__main__':
    
    asks.init('curio')

    # Read basic config
    CONFIG.update( yaml.load( open( __file__.replace ( '.py', '.yaml')).read()))
    
    # Handle command line arguments
    from argparse import ArgumentParser, FileType
    parser = ArgumentParser( description='Crawl a web site.')
    parser.add_argument( '-b', '--baseurl', help="base URL")
    parser.add_argument( '-f', '--config', type=FileType('r'), help='YAML config')
    parser.add_argument( '-d', '--depth', type=int, default=CONFIG['depth'],
        help='search depth (default: %d)' % CONFIG['depth'])

    parser.add_argument( '-n', '--dryrun', action='store_const',
        const=True, default=False, help='dry run, do not store')
    parser.add_argument( '-v', '--verbosity', type=int, default=0,
        help='log level (0-3, default: 0)')
    parser.add_argument( '-c', '--connections', type=int, default=4,
        help='number of concurrent connections (default: 4)')        
    parser.add_argument( '-H', '--html-only', action='store_const',
        const=True, default=False, help='retrieve only HTML pages')
    parser.add_argument( '-s', '--strip', action='store_const',
        const=True, default=False, help='strip "%s" from links' % CONFIG['index'])
    
    # Update default settings with site configuration 
    args = parser.parse_args()
    if args.config:
        CONFIG.update( yaml.load( args.config.read()))
        
    # Handle command line overrides
    if args.baseurl: CONFIG['baseurl'] = args.baseurl
    if args.connections: CONFIG['connections'] = args.connections
    
    # Compile URL patterns
    CONFIG['disable'] = map( re.compile, CONFIG['disable'])
    CONFIG['remove']  = map( re.compile, CONFIG['remove'])
    
    # Compile replacement patterns
    CONFIG['replace'] = { re.compile (pat) : sub 
        for pat, sub in CONFIG['replace'].items() }
    CONFIG['rewrite'] = { re.compile (pat) : sub  
        for pat, sub in CONFIG['rewrite'].items() }

    # Ready, steady, ...
    curio.run( Robot( args).go())
