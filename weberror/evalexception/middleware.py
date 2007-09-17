"""Exception-catching middleware that allows interactive debugging.

This middleware catches all unexpected exceptions.  A normal
traceback, like produced by
``weberror.exceptions.errormiddleware.ErrorMiddleware`` is given, plus
controls to see local variables and evaluate expressions in a local
context.

This can only be used in single-process environments, because
subsequent requests must go back to the same process that the
exception originally occurred in.  Threaded or non-concurrent
environments both work.

This shouldn't be used in production in any way.  That would just be
silly.

If calling from an XMLHttpRequest call, if the GET variable ``_`` is
given then it will make the response more compact (and less
Javascripty), since if you use innerHTML it'll kill your browser.  You
can look for the header X-Debug-URL in your 500 responses if you want
to see the full debuggable traceback.  Also, this URL is printed to
``wsgi.errors``, so you can open it up in another browser window.

"""
import sys
import os
import cgi
import traceback
from cStringIO import StringIO
import pprint
import itertools
import time
import re

from paste import urlparser
from paste import registry
from paste import request

import evalcontext
from weberror.exceptions import errormiddleware, formatter, collector

limit = 200

FORBIDDEN_MSG = """\
403 Forbidden
Access was denied to this resource.
%r not allowed

"""

NOT_FOUND_MSG = """\
404 Not Found
The resource could not be found.
%r not fond when parsing %r

"""

def html_quote(v):
    """
    Escape HTML characters, plus translate None to ''
    """
    if v is None:
        return ''
    return cgi.escape(str(v), 1)


def preserve_whitespace(v, quote=True):
    """
    Quote a value for HTML, preserving whitespace (translating
    newlines to ``<br>`` and multiple spaces to use ``&nbsp;``).

    If ``quote`` is true, then the value will be HTML quoted first.
    """
    if quote:
        v = html_quote(v)
    v = v.replace('\n', '<br>\n')
    v = re.sub(r'()(  +)', _repl_nbsp, v)
    v = re.sub(r'(\n)( +)', _repl_nbsp, v)
    v = re.sub(r'^()( +)', _repl_nbsp, v)
    return '<code>%s</code>' % v


def _repl_nbsp(match):
    if len(match.group(2)) == 1:
        return '&nbsp;'
    return match.group(1) + '&nbsp;' * (len(match.group(2))-1) + ' '


def simplecatcher(application):
    """
    A simple middleware that catches errors and turns them into simple
    tracebacks.
    """
    def simplecatcher_app(environ, start_response):
        try:
            return application(environ, start_response)
        except:
            out = StringIO()
            traceback.print_exc(file=out)
            start_response('500 Server Error',
                           [('content-type', 'text/html')],
                           sys.exc_info())
            res = out.getvalue()
            return ['<h3>Error</h3><pre>%s</pre>'
                    % html_quote(res)]
    return simplecatcher_app


def wsgiapp():
    """
    Turns a function or method into a WSGI application.
    """
    def decorator(func):
        def wsgiapp_wrapper(*args):
            # we get 3 args when this is a method, two when it is
            # a function :(
            if len(args) == 3:
                environ = args[1]
                start_response = args[2]
                args = [args[0]]
            else:
                environ, start_response = args
                args = []
            def application(environ, start_response):
                form = request.parse_formvars(environ,
                                              include_get_vars=True)
                status = '200 OK'
                form['environ'] = environ
                try:
                    res = func(*args, **form.mixed())
                except ValueError, ve:
                    status = '500 Server Error'
                    res = '<html>There was an error: %s</html>' % \
                        html_quote(ve)
                start_response(status, [('content-type', 'text/html')])
                return [res]
            app = simplecatcher(application)
            return app(environ, start_response)
        wsgiapp_wrapper.exposed = True
        return wsgiapp_wrapper
    return decorator


def get_debug_info(func):
    """
    A decorator (meant to be used under ``wsgiapp()``) that resolves
    the ``debugcount`` variable to a ``DebugInfo`` object (or gives an
    error if it can't be found).
    """
    def debug_info_replacement(self, **form):
        if 'debugcount' not in form:
            raise ValueError('You must provide a debugcount parameter')
        debugcount = form.pop('debugcount')
        try:
            debugcount = int(debugcount)
        except ValueError:
            raise ValueError('Bad value for debugcount')
        if debugcount not in self.debug_infos:
            raise ValueError(
                'Debug %s no longer found (maybe it has expired?)'
                % debugcount)
        debug_info = self.debug_infos[debugcount]
        return func(self, debug_info=debug_info, **form)
    return debug_info_replacement


debug_counter = itertools.count(int(time.time()))
def get_debug_count(environ):
    """
    Return the unique debug count for the current request
    """
    if 'weberror.evalexception.debug_count' in environ:
        return environ['weberror.evalexception.debug_count']
    else:
        environ['weberror.evalexception.debug_count'] = next = debug_counter.next()
        return next


class InvalidTemplate(Exception):
    pass


class EvalException(object):
    """Handles capturing an exception and turning it into an interactive
    exception explorer"""
    def __init__(self, application, global_conf=None, error_template=None,
                 xmlhttp_key=None, media_paths=None, 
                 templating_formatters=None, **params):
        self.application = application
        self.error_template = error_template
        self.debug_infos = {}
        self.templating_formatters = templating_formatters or []
        if xmlhttp_key is None:
            if global_conf is None:
                xmlhttp_key = '_'
            else:
                xmlhttp_key = global_conf.get('xmlhttp_key', '_')
        self.xmlhttp_key = xmlhttp_key
        self.media_paths = media_paths or {}
        
        for s in ['head', 'traceback_data', 'extra_data', 'template_data']:
            if "%("+s+")s" not in self.error_template:
                raise InvalidTemplate("Could not find %s in template"%("%("+s+")s"))
        try:
            error_template % {'head': '', 'traceback_data': '', 
                              'extra_data':'', 'template_data':'', 
                              'set_tab':'', 'prefix':''}
        except:
            raise Exception('Invalid template. Please ensure all % signs are properly '
                            'quoted as %% and no extra substitution strings are present.')
    
    def __call__(self, environ, start_response):
        assert not environ['wsgi.multiprocess'], (
            "The EvalException middleware is not usable in a "
            "multi-process environment")
        environ['weberror.evalexception'] = self
        if environ.get('PATH_INFO', '').startswith('/_debug/'):
            return self.debug(environ, start_response)
        else:
            return self.respond(environ, start_response)

    def debug(self, environ, start_response):
        assert request.path_info_pop(environ) == '_debug'
        next_part = request.path_info_pop(environ)
        method = getattr(self, next_part, None)
        if not method:
            start_response('404 Not Found', [('content-type', 'text/plain')])
            return NOT_FOUND_MSG % (next_part, request.construct_url(environ))
        if not getattr(method, 'exposed', False):
            start_response('403 Forbidden', [('content-type', 'text/plain')])
            return FORBIDDEN_MSG % next_part
            
        return method(environ, start_response)

    def media(self, environ, start_response):
        """Static path where images and other files live"""
        first_part = request.path_info_split(environ['PATH_INFO'])[0]
        if first_part in self.media_paths:
            request.path_info_pop(environ)
            app = urlparser.StaticURLParser(self.media_paths[first_part])
            return app(environ, start_response)
        else:
            app = urlparser.StaticURLParser(
                os.path.join(os.path.dirname(__file__), 'media'))
            return app(environ, start_response)
    media.exposed = True

    def mochikit(self, environ, start_response):
        """
        Static path where MochiKit lives
        """
        app = urlparser.StaticURLParser(
            os.path.join(os.path.dirname(__file__), 'mochikit'))
        return app(environ, start_response)
    mochikit.exposed = True

    def summary(self, environ, start_response):
        """
        Returns a JSON-format summary of all the cached
        exception reports
        """
        start_response('200 OK', [('Content-type', 'text/x-json')])
        data = [];
        items = self.debug_infos.values()
        items.sort(lambda a, b: cmp(a.created, b.created))
        data = [item.json() for item in items]
        return [repr(data)]
    summary.exposed = True

    def view(self, environ, start_response):
        """
        View old exception reports
        """
        id = int(request.path_info_pop(environ))
        if id not in self.debug_infos:
            start_response(
                '500 Server Error',
                [('Content-type', 'text/html')])
            return [
                "Traceback by id %s does not exist (maybe "
                "the server has been restarted?)"
                % id]
        debug_info = self.debug_infos[id]
        return debug_info.wsgi_application(environ, start_response)
    view.exposed = True

    def make_view_url(self, environ, base_path, count):
        return base_path + '/_debug/view/%s' % count

    #@wsgiapp()
    #@get_debug_info
    def show_frame(self, tbid, debug_info, **kw):
        frame = debug_info.frame(int(tbid))
        vars = frame.tb_frame.f_locals
        if vars:
            registry.restorer.restoration_begin(debug_info.counter)
            local_vars = make_table(vars)
            registry.restorer.restoration_end()
        else:
            local_vars = 'No local vars'
        return input_form(tbid, debug_info) + local_vars

    show_frame = wsgiapp()(get_debug_info(show_frame))

    #@wsgiapp()
    #@get_debug_info
    def exec_input(self, tbid, debug_info, input, **kw):
        if not input.strip():
            return ''
        input = input.rstrip() + '\n'
        frame = debug_info.frame(int(tbid))
        vars = frame.tb_frame.f_locals
        glob_vars = frame.tb_frame.f_globals
        context = evalcontext.EvalContext(vars, glob_vars)
        registry.restorer.restoration_begin(debug_info.counter)
        output = context.exec_expr(input)
        registry.restorer.restoration_end()
        input_html = formatter.str2html(input)
        return ('<code style="color: #060">&gt;&gt;&gt;</code> '
                '<code>%s</code><br>\n%s'
                % (preserve_whitespace(input_html, quote=False),
                   preserve_whitespace(output)))

    exec_input = wsgiapp()(get_debug_info(exec_input))

    def respond(self, environ, start_response):
        if environ.get('paste.throw_errors'):
            return self.application(environ, start_response)
        base_path = request.construct_url(environ, with_path_info=False,
                                          with_query_string=False)
        environ['paste.throw_errors'] = True
        started = []
        def detect_start_response(status, headers, exc_info=None):
            try:
                return start_response(status, headers, exc_info)
            except:
                raise
            else:
                started.append(True)
        try:
            __traceback_supplement__ = errormiddleware.Supplement, self, environ
            app_iter = self.application(environ, detect_start_response)
            try:
                return_iter = list(app_iter)
                return return_iter
            finally:
                if hasattr(app_iter, 'close'):
                    app_iter.close()
        except:
            exc_info = sys.exc_info()
            for expected in environ.get('paste.expected_exceptions', []):
                if isinstance(exc_info[1], expected):
                    raise

            # Tell the Registry to save its StackedObjectProxies current state
            # for later restoration
            registry.restorer.save_registry_state(environ)

            count = get_debug_count(environ)
            view_uri = self.make_view_url(environ, base_path, count)
            if not started:
                headers = [('content-type', 'text/html')]
                headers.append(('X-Debug-URL', view_uri))
                start_response('500 Internal Server Error',
                               headers,
                               exc_info)
            environ['wsgi.errors'].write('Debug at: %s\n' % view_uri)

            exc_data = collector.collect_exception(*exc_info)
            debug_info = DebugInfo(count, exc_info, exc_data, base_path,
                                   environ, view_uri, self.error_template,
                                   self.templating_formatters)
            assert count not in self.debug_infos
            self.debug_infos[count] = debug_info

            if self.xmlhttp_key:
                get_vars = request.parse_querystring(environ)
                if dict(get_vars).get(self.xmlhttp_key):
                    exc_data = collector.collect_exception(*exc_info)
                    html = formatter.format_html(
                        exc_data, include_hidden_frames=False,
                        include_reusable=False, show_extra_data=False)
                    return [html]

            # @@: it would be nice to deal with bad content types here
            return debug_info.content()

    def exception_handler(self, exc_info, environ):
        simple_html_error = False
        if self.xmlhttp_key:
            get_vars = request.parse_querystring(environ)
            if dict(get_vars).get(self.xmlhttp_key):
                simple_html_error = True
        return errormiddleware.handle_exception(
            exc_info, environ['wsgi.errors'],
            html=True,
            debug_mode=True,
            simple_html_error=simple_html_error)


class DebugInfo(object):

    def __init__(self, counter, exc_info, exc_data, base_path,
                 environ, view_uri, error_template, templating_formatters):
        self.counter = counter
        self.exc_data = exc_data
        self.base_path = base_path
        self.environ = environ
        self.view_uri = view_uri
        self.error_template = error_template
        self.created = time.time()
        self.templating_formatters = templating_formatters
        self.exc_type, self.exc_value, self.tb = exc_info
        __exception_formatter__ = 1
        self.frames = []
        n = 0
        tb = self.tb
        while tb is not None and (limit is None or n < limit):
            if tb.tb_frame.f_locals.get('__exception_formatter__'):
                # Stop recursion. @@: should make a fake ExceptionFrame
                break
            self.frames.append(tb)
            tb = tb.tb_next
            n += 1
    
    def json(self):
        """Return the JSON-able representation of this object"""
        return {
            'uri': self.view_uri,
            'created': time.strftime('%c', time.gmtime(self.created)),
            'created_timestamp': self.created,
            'exception_type': str(self.exc_type),
            'exception': str(self.exc_value),
            }

    def frame(self, tbid):
        for frame in self.frames:
            if id(frame) == tbid:
                return frame
        else:
            raise ValueError, (
                "No frame by id %s found from %r" % (tbid, self.frames))

    def wsgi_application(self, environ, start_response):
        start_response('200 OK', [('content-type', 'text/html')])
        return self.content()

    def content(self):
        html, extra_data = format_eval_html(self.exc_data, self.base_path, self.counter)
        head_html = (formatter.error_css + formatter.hide_display_js)
        head_html += self.eval_javascript()
        repost_button = make_repost_button(self.environ)
        template_data = '<p>No Template information available.</p>'
        tab = 'traceback_data'
        
        for formatter_ in self.templating_formatters:
            result = formatter_(self.exc_value)
            if result:
                tab = 'template_data'
                template_data = result
                break

        head_html = (error_head_template % {'prefix':self.base_path}) + head_html

        traceback_data = error_traceback_template % {
            'prefix':self.base_path,
            'body':html,
            'repost_button': repost_button or '',
        }

        extra_data = """<h1 class="first"><a name="content"></a>Extra Data</h1>""" + \
            '\n'.join(extra_data)
        page = self.error_template % {
            'head': head_html,
            'traceback_data': traceback_data,
            'extra_data':extra_data,
            'template_data':template_data.replace('<h2>',
                                              '<h1 class="first">').replace('</h2>',
                                                                            '</h1>'),
            'set_tab':tab,
            'prefix':self.base_path,
            }
        return [page]

    def eval_javascript(self):
        base_path = self.base_path + '/_debug'
        return (
            '<script type="text/javascript" src="%s/mochikit/MochiKit.js">'
            '</script>\n'
            '<script type="text/javascript" src="%s/media/debug.js">'
            '</script>\n'
            '<script type="text/javascript">\n'
            'debug_base = %r;\n'
            'debug_count = %r;\n'
            '</script>\n'
            % (base_path, base_path, base_path, self.counter))


class EvalHTMLFormatter(formatter.HTMLFormatter):

    def __init__(self, base_path, counter, **kw):
        super(EvalHTMLFormatter, self).__init__(**kw)
        self.base_path = base_path
        self.counter = counter
    
    def format_source_line(self, filename, frame):
        line = formatter.HTMLFormatter.format_source_line(
            self, filename, frame)
        return (line +
                '  <a href="#" class="switch_source" '
                'tbid="%s" onClick="return showFrame(this)">&nbsp; &nbsp; '
                '<img src="%s/_debug/media/plus.jpg" border=0 width=9 '
                'height=9> &nbsp; &nbsp;</a>'
                % (frame.tbid, self.base_path))


def make_table(items):
    if isinstance(items, dict):
        items = items.items()
        items.sort()
    rows = []
    i = 0
    for name, value in items:
        i += 1
        out = StringIO()
        try:
            pprint.pprint(value, out)
        except Exception, e:
            print >> out, 'Error: %s' % e
        value = html_quote(out.getvalue())
        if len(value) > 100:
            # @@: This can actually break the HTML :(
            # should I truncate before quoting?
            orig_value = value
            value = value[:100]
            value += '<a class="switch_source" style="background-color: #999" href="#" onclick="return expandLong(this)">...</a>'
            value += '<span style="display: none">%s</span>' % orig_value[100:]
        value = formatter.make_wrappable(value)
        if i % 2:
            attr = ' class="even"'
        else:
            attr = ' class="odd"'
        rows.append('<tr%s style="vertical-align: top;"><td>'
                    '<b>%s</b></td><td style="overflow: auto">%s<td></tr>'
                    % (attr, html_quote(name),
                       preserve_whitespace(value, quote=False)))
    return '<table>%s</table>' % (
        '\n'.join(rows))


def format_eval_html(exc_data, base_path, counter):
    short_formatter = EvalHTMLFormatter(
        base_path=base_path,
        counter=counter,
        include_reusable=False)
    short_er, extra_data = short_formatter.format_collected_data(exc_data)
    short_text_er = formatter.format_text(exc_data, show_extra_data=False)
    long_formatter = EvalHTMLFormatter(
        base_path=base_path,
        counter=counter,
        show_hidden_frames=True,
        show_extra_data=False,
        include_reusable=False)
    long_er, extra_data_none = long_formatter.format_collected_data(exc_data)
    long_text_er = formatter.format_text(exc_data, show_hidden_frames=True,
                                         show_extra_data=False)
    extra_data_text = format_extra_data_text(exc_data)
    if extra_data_text:
        extra_data.append("""
        <br />
        <div id="util-link">
            <script type="text/javascript">
            show_button('extra_data_text', 'text version')
            </script>
        </div>
        <div id="extra_data_text" class="hidden-data">
        <textarea style="width: 100%%" rows=%s cols=60>%s</textarea>
        </div>
        """ % (len(extra_data_text.splitlines()), extra_data_text))
    
    if short_formatter.filter_frames(exc_data.frames) != \
        long_formatter.filter_frames(exc_data.frames):
        # Only display the full traceback when it differs from the
        # short version
        long_text_er = cgi.escape(long_text_er)
        full_traceback_html = """
        <br />
        <div id="util-link">
            <script type="text/javascript">
            show_button('full_traceback', 'full traceback')
            </script>
        </div>
        <div id="full_traceback" class="hidden-data">
        %s
            <br />
            <div id="util-link">
                <script type="text/javascript">
                show_button('long_text_version', 'full traceback text version')
                </script>
            </div>
            <div id="long_text_version" class="hidden-data">
            <textarea style="width: 100%%" rows=%s cols=60>%s</textarea>
            </div>
        </div>
        """ % (long_er, len(long_text_er.splitlines()), long_text_er)
    else:
        full_traceback_html = ''

    short_text_er = cgi.escape(short_text_er)
    return """
    <style type="text/css">
            #util-link a, #util-link a:link, #util-link a:visited,
            #util-link a:active {
                border-bottom: 2px outset #aaa
            }
    </style>
    %s
    <br />
    <br />
    <div id="util-link">
        <script type="text/javascript">
        show_button('short_text_version', 'text version')
        </script>
    </div>
    <div id="short_text_version" class="hidden-data">
    <textarea style="width: 100%%" rows=%s cols=60>%s</textarea>
    </div>
    %s
    """ % (short_er, len(short_text_er.splitlines()), short_text_er,
           full_traceback_html), extra_data

def format_extra_data_text(exc_data):
    """ Return a text representation of the 'extra_data' dict when one exists """
    extra_data_text = ''
    if not exc_data.extra_data:
        return extra_data_text

    text_formatter = formatter.TextFormatter()
    by_title = {}
    for name, value_list in exc_data.extra_data.items():
        if isinstance(name, tuple):
            importance, title = name
        else:
            importance, title = 'normal', name
        if importance != 'extra':
            continue
        for value in value_list:
            by_title[title] = text_formatter.format_extra_data(importance, title, value)

    titles = by_title.keys()
    titles.sort()
    for title in titles:
        extra_data_text += by_title[title]
    return extra_data_text


def make_repost_button(environ):
    url = request.construct_url(environ)
    if environ['REQUEST_METHOD'] == 'GET':
        return ('<button onclick="window.location.href=%r">'
                'Re-GET Page</button><br>' % url)
    else:
        # @@: I'd like to reconstruct this, but I can't because
        # the POST body is probably lost at this point, and
        # I can't get it back :(
        return None
    # @@: Use or lose the following code block
    """
    fields = []
    for name, value in request.parse_formvars(
        environ, include_get_vars=False).items():
        if hasattr(value, 'filename'):
            # @@: Arg, we'll just submit the body, and leave out
            # the filename :(
            value = value.value
        fields.append(
            '<input type="hidden" name="%s" value="%s">'
            % (html_quote(name), html_quote(value)))
    return '''
<form action="%s" method="POST">
%s
<input type="submit" value="Re-POST Page">
</form>''' % (url, '\n'.join(fields))
"""


def input_form(tbid, debug_info):
    return '''
<form action="#" method="POST"
 onsubmit="return submitInput($(\'submit_%(tbid)s\'), %(tbid)s)">
<div id="exec-output-%(tbid)s" style="width: 95%%;
 padding: 5px; margin: 5px; border: 2px solid #000;
 display: none"></div>
<input type="text" name="input" id="debug_input_%(tbid)s"
 style="width: 100%%"
 autocomplete="off" onkeypress="upArrow(this, event)"><br>
<input type="submit" value="Execute" name="submitbutton"
 onclick="return submitInput(this, %(tbid)s)"
 id="submit_%(tbid)s"
 input-from="debug_input_%(tbid)s"
 output-to="exec-output-%(tbid)s">
<input type="submit" value="Expand"
 onclick="return expandInput(this)">
</form>
 ''' % {'tbid': tbid}


error_template = '''
<html>
<head>
 <title>Server Error</title>
 %(head_html)s
</head>
<body>

<div id="error-area" style="display: none; background-color: #600; color: #fff; border: 2px solid black">
<div id="error-container"></div>
<button onclick="return clearError()">clear this</button>
</div>

%(repost_button)s

%(body)s

</body>
</html>
'''

error_head_template = """
<style type="text/css">
        .red {
            color:#FF0000;
        }
        .bold {
            font-weight: bold;
        }
</style>
<script type="text/javascript">

if (document.images)
{
  pic1= new Image(100,25); 
  pic1.src="%(prefix)s/_debug/media/pylons/img/tab-yellow.png"; 
}

function switch_display(id) {
    ids = ['extra_data', 'template_data', 'traceback_data']
    for (i in ids){
        part = ids[i] 
        var el = document.getElementById(part);
        el.className = "hidden-data";
        var el = document.getElementById(part+'_tab');
        el.className = "not-active";
        var el = document.getElementById(part+'_link');
        el.className = "not-active";
    }
    var el = document.getElementById(id);
    el.className = "active";
    var el = document.getElementById(id+'_link');
    el.className = "active";
    var el = document.getElementById(id+'_tab');
    el.className = "active";
}   
</script>
"""


error_traceback_template = """\
<div style="float: left; width: 100%%; padding-bottom: 20px;">
<h1 class="first"><a name="content"></a>Error Traceback</h1>
<div id="error-area" style="display: none; background-color: #600; color: #fff; border: 2px solid black">
<button onclick="return clearError()">clear this</button>
<div id="error-container"></div>
<button onclick="return clearError()">clear this</button>
</div>
%(body)s
<br />
<div class="highlight" style="padding: 20px;">
<b>Extra Features</b>
<table border="0">
<tr><td>&gt;&gt;</td><td>Display the lines of code near each part of the traceback</td></tr>
<tr><td><img src="%(prefix)s/_debug/media/plus.jpg" /></td><td>Show a debug prompt to allow you to directly debug the code at the traceback</td></tr>
</table>
</div>%(repost_button)s"""


def make_eval_exception(app, global_conf, xmlhttp_key=None):
    """
    Wraps the application in an interactive debugger.

    This debugger is a major security hole, and should only be
    used during development.

    xmlhttp_key is a string that, if present in QUERY_STRING,
    indicates that the request is an XMLHttp request, and the
    Javascript/interactive debugger should not be returned.  (If you
    try to put the debugger somewhere with innerHTML, you will often
    crash the browser)
    """
    if xmlhttp_key is None:
        xmlhttp_key = global_conf.get('xmlhttp_key', '_')
    return EvalException(app, xmlhttp_key=xmlhttp_key)
