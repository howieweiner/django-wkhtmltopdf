from __future__ import absolute_import

from copy import copy
from functools import wraps
from itertools import chain
import os
import re
import sys
import urllib
from urlparse import urljoin

from django.conf import settings

from .subprocess import check_output


def _options_to_args(**options):
    """Converts ``options`` into a list of command-line arguments."""
    flags = []

    # If we have an TOC or cover options, store and remove from original options, as they need re-applying positionally
    toc_options = {}
    cover_options = {}

    if 'cover' in options:
        cover_options['cover'] = options['cover']
        options.pop('cover', None)

    if 'toc' in options:
        toc_options['toc'] = True
        options.pop('toc', None)

        for toc_name in ('disable-dotted-lines', 'toc-header-text', 'toc-level-indentation', 'disable-toc-links',
                         'toc-text-size-shrink', 'xsl_style_sheet'):
            if toc_name in options:
                toc_value = options[toc_name]
                options.pop(toc_name, None)
                toc_options[toc_name] = toc_value

    for name in sorted(options):
        value = options[name]
        if value is None:
            continue
        else:
            flags.append('--' + name.replace('_', '-'))
        if value is not True:
            flags.append(unicode(value))

     # if we have cover options, then these must be applied positionally
    if cover_options:
        flags.append('cover')
        flags.append(cover_options['cover'])

    # if we have TOC options, then these must be applied positionally
    if toc_options:
        for toc_name in toc_options:
            toc_value = toc_options[toc_name]
            if  'toc' == toc_name:
                flags.append(toc_name)
            else:
                flags.append('--' + toc_name.replace('_', '-'))
            if toc_value is not True:
                flags.append(unicode(toc_value))
    return flags


def wkhtmltopdf(pages, output=None, **kwargs):
    """
    Converts html to PDF using http://code.google.com/p/wkhtmltopdf/.

    pages: List of file paths or URLs of the html to be converted.
    output: Optional output file path. If None, the output is returned.
    **kwargs: Passed to wkhtmltopdf via _extra_args() (See
              https://github.com/antialize/wkhtmltopdf/blob/master/README_WKHTMLTOPDF
              for acceptable args.)
              Kwargs is passed through as arguments. e.g.:
                  {'footer_html': 'http://example.com/foot.html'}
              becomes
                  '--footer-html http://example.com/foot.html'

              Where there is no value passed, use True. e.g.:
                  {'disable_javascript': True}
              becomes:
                  '--disable-javascript'

              To disable a default option, use None. e.g:
                  {'quiet': None'}
              becomes:
                  ''

    example usage:
        wkhtmltopdf(pages=['/tmp/example.html'],
                    dpi=300,
                    orientation='Landscape',
                    disable_javascript=True)
    """
    if isinstance(pages, basestring):
        # Support a single page.
        pages = [pages]

    if output is None:
        # Standard output.
        output = '-'

    # Default options:
    options = getattr(settings, 'WKHTMLTOPDF_CMD_OPTIONS', None)
    if options is None:
        options = {'quiet': True}
    else:
        options = copy(options)
    options.update(kwargs)

    # Force --encoding utf8 unless the user has explicitly overridden this.
    options.setdefault('encoding', 'utf8')

    env = getattr(settings, 'WKHTMLTOPDF_ENV', None)
    if env is not None:
        env = dict(os.environ, **env)

    cmd = getattr(settings, 'WKHTMLTOPDF_CMD', 'wkhtmltopdf')
    args = list(chain(cmd.split(),
                      _options_to_args(**options),
                      list(pages),
                      [output]))
    return check_output(args, stderr=sys.stderr, env=env)


def content_disposition_filename(filename):
    """
    Sanitize a file name to be used in the Content-Disposition HTTP
    header.

    Even if the standard is quite permissive in terms of
    characters, there are a lot of edge cases that are not supported by
    different browsers.

    See http://greenbytes.de/tech/tc2231/#attmultinstances for more details.
    """
    filename = filename.replace(';', '').replace('"', '')
    return http_quote(filename)


def http_quote(string):
    """
    Given a unicode string, will do its dandiest to give you back a
    valid ascii charset string you can use in, say, http headers and the
    like.
    """
    if isinstance(string, unicode):
        try:
            import unidecode
            string = unidecode.unidecode(string)
        except ImportError:
            string = string.encode('ascii', 'replace')
    # Wrap in double-quotes for ; , and the like
    return '"{0!s}"'.format(string.replace('\\', '\\\\').replace('"', '\\"'))


def pathname2fileurl(pathname):
    """Returns a file:// URL for pathname. Handles OS-specific conversions."""
    return urljoin('file:', urllib.pathname2url(pathname))


def make_absolute_paths(content):
    """Convert all MEDIA files into a file://URL paths in order to
    correctly get it displayed in PDFs."""

    overrides = [
        {
            'root': settings.MEDIA_ROOT,
            'url': settings.MEDIA_URL,
        },
        {
            'root': settings.STATIC_ROOT,
            'url': settings.STATIC_URL,
        }
    ]
    has_scheme = re.compile(r'^[^:/]+://')

    for x in overrides:
        if has_scheme.match(x['url']):
            continue

        if not x['root'].endswith('/'):
            x['root'] += '/'

        occur_pattern = '''["|']({0}.*?)["|']'''
        occurences = re.findall(occur_pattern.format(x['url']), content)
        occurences = list(set(occurences))  # Remove dups
        for occur in occurences:
            content = content.replace(occur,
                                      pathname2fileurl(x['root']) +
                                      occur[len(x['url']):])

    return content
