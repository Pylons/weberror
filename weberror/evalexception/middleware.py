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
from tempita import HTMLTemplate
from webob import Request, Response
from webob import exc

limit = 200

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
    def debug_info_replacement(self, req):
        if 'debugcount' not in req.params:
            return exc.HTTPBadRequest(
                "You must provide a debugcount parameter")
        debugcount = req.params['debugcount']
        try:
            debugcount = int(debugcount)
        except ValueError, e:
            return exc.HTTPBadRequest(
                "Invalid value for debugcount (%r): %s"
                % (debugcount, e))
        if debugcount not in self.debug_infos:
            return exc.HTTPServerError(
                "Debug %s not found (maybe it has expired, or the server was restarted)"
                % debugcount)
        req.debug_info = self.debug_infos[debugcount]
        return func(self, req)
    debug_info_replacement.exposed = True
    return debug_info_replacement

debug_counter = itertools.count(int(time.time()))

def get_debug_count(req):
    """
    Return the unique debug count for the current request
    """
    if hasattr(req, 'environ'):
        environ = req.environ
    else:
        environ = req
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
    def __init__(self, application, global_conf=None,
                 error_template_filename=os.path.join(os.path.dirname(__file__), 'error_template.html.tmpl'),
                 xmlhttp_key=None, media_paths=None, 
                 templating_formatters=None, **params):
        self.application = application
        self.debug_infos = {}
        self.templating_formatters = templating_formatters or []
        if xmlhttp_key is None:
            if global_conf is None:
                xmlhttp_key = '_'
            else:
                xmlhttp_key = global_conf.get('xmlhttp_key', '_')
        self.xmlhttp_key = xmlhttp_key
        self.media_paths = media_paths or {}
        self.error_template = HTMLTemplate.from_filename(error_template_filename)
    
    def __call__(self, environ, start_response):
        ## FIXME: print better error message (maybe fall back on
        ## normal middleware, plus an error message)
        assert not environ['wsgi.multiprocess'], (
            "The EvalException middleware is not usable in a "
            "multi-process environment")
        environ['weberror.evalexception'] = self
        req = Request(environ)
        if req.path_info_peek() == '_debug':
            return self.debug(req)(environ, start_response)
        else:
            return self.respond(environ, start_response)

    def debug(self, req):
        assert req.path_info_pop() == '_debug'
        next_part = req.path_info_pop()
        method = getattr(self, next_part, None)
        if method is None:
            return exc.HTTPNotFound('Nothing could be found to match %r' % next_part)
        if not getattr(method, 'exposed', False):
            return exc.HTTPForbidden('Access to %r is forbidden' % next_part)
        return method(req)

    def media(self, req):
        """Static path where images and other files live"""
        first_part = req.path_info_peek()
        if first_part in self.media_paths:
            req.path_info_pop()
            path = self.media_paths[first_part]
        else:
            path = os.path.join(os.path.dirname(__file__), 'media')
        app = urlparser.StaticURLParser(path)
        return app
    media.exposed = True

    def mochikit(self, req):
        """
        Static path where MochiKit lives
        """
        app = urlparser.StaticURLParser(
            os.path.join(os.path.dirname(__file__), 'mochikit'))
        return app
    mochikit.exposed = True

    def summary(self, req):
        """
        Returns a JSON-format summary of all the cached
        exception reports
        """
        res = Response(content_type='text/x-json')
        data = [];
        items = self.debug_infos.values()
        items.sort(lambda a, b: cmp(a.created, b.created))
        data = [item.json() for item in items]
        res.body = repr(data)
        return res
    summary.exposed = True

    def view(self, req):
        """
        View old exception reports
        """
        id = int(req.path_info_pop())
        if id not in self.debug_infos:
            return exc.HTTPServerError(
                "Traceback by id %s does not exist (maybe "
                "the server has been restarted?)" % id)
        debug_info = self.debug_infos[id]
        return debug_info.wsgi_application
    view.exposed = True

    def make_view_url(self, environ, base_path, count):
        return base_path + '/view/%s' % count

    #@get_debug_info
    def show_frame(self, req):
        tbid = int(req.params['tbid'])
        frame = req.debug_info.frame(tbid)
        vars = frame.tb_frame.f_locals
        if vars:
            registry.restorer.restoration_begin(req.debug_info.counter)
            try:
                local_vars = make_table(vars)
            finally:
                registry.restorer.restoration_end()
        else:
            local_vars = 'No local vars'
        res = Response(content_type='text/html')
        res.body = input_form.substitute(tbid=tbid, debug_info=req.debug_info) + local_vars
        return res

    show_frame = get_debug_info(show_frame)

    #@get_debug_info
    def exec_input(self, req):
        input = req.params.get('input')
        if not input.strip():
            return ''
        input = input.rstrip() + '\n'
        frame = req.debug_info.frame(int(req.params['tbid']))
        vars = frame.tb_frame.f_locals
        glob_vars = frame.tb_frame.f_globals
        context = evalcontext.EvalContext(vars, glob_vars)
        registry.restorer.restoration_begin(req.debug_info.counter)
        try:
            output = context.exec_expr(input)
        finally:
            registry.restorer.restoration_end()
        input_html = formatter.str2html(input)
        res = Response(content_type='text/html')
        res.body = (
            '<code style="color: #060">&gt;&gt;&gt;</code> '
            '<code>%s</code><br>\n%s'
            % (preserve_whitespace(input_html, quote=False),
               preserve_whitespace(output)))
        return res

    exec_input = get_debug_info(exec_input)

    def respond(self, environ, start_response):
        req = Request(environ)
        if req.environ.get('paste.throw_errors'):
            return self.application(environ, start_response)
        base_path = req.application_url + '/_debug'
        req.environ['paste.throw_errors'] = True
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

            # Tell the Registry to save its StackedObjectProxies current state
            # for later restoration
            ## FIXME: needs to be more abstract (something in the environ)
            ## to remove the Paste dependency
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
                if self.xmlhttp_key in req.params:
                    exc_data = collector.collect_exception(*exc_info)
                    html = formatter.format_html(
                        exc_data, include_hidden_frames=False,
                        include_reusable=False, show_extra_data=False)
                    return [html]

            # @@: it would be nice to deal with bad content types here
            return debug_info.content()


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
        traceback_body, extra_data = format_eval_html(self.exc_data, self.base_path, self.counter)
        head_html = ''
        repost_button = make_repost_button(self.environ)
        template_data = '<p>No Template information available.</p>'
        tab = 'traceback_data'
        
        for tmpl_formatter in self.templating_formatters:
            result = tmpl_formatter(self.exc_value)
            if result:
                tab = 'template_data'
                template_data = result
                break

        template_data = template_data.replace('<h2>', '<h1 class="first">')
        template_data = template_data.replace('</h2>', '</h1>')
        page = self.error_template.substitute(
            head_html=head_html,
            repost_button=repost_button or '',
            traceback_body=traceback_body,
            extra_data=extra_data,
            template_data=template_data,
            set_tab=tab,
            prefix=self.base_path,
            counter=self.counter,
            )
        return [page]

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
                '<img src="%s/media/plus.jpg" border=0 width=9 '
                'height=9> &nbsp; &nbsp;</a>'
                % (frame.tbid, self.base_path))


def make_table(items):
    if isinstance(items, dict):
        items = items.items()
        items.sort()
    return table_template.substitute(
        html_quote=html_quote,
        items=items,
        preserve_whitespace=preserve_whitespace,
        make_wrappable=formatter.make_wrappable,
        pprint_format=pprint_format)

table_template = HTMLTemplate('''
{{py:i = 0}}
<table>
{{for name, value in items:}}
  {{py:i += 1}}
{{py:
value_html = html_quote(pprint_format(value, safe=True))
value_html = make_wrappable(value_html)
if len(value_html) > 100:
    ## FIXME: This can break HTML; truncate before quoting?
    value_html, expand_html = value_html[:100], value_html[100:]
else:
    expand_html = ''
}}
  <tr class="{{if i%2}}even{{else}}odd{{endif}}"
      style="vertical-align: top">
    <td><b>{{name}}</b></td>
    <td style="overflow: auto">{{preserve_whitespace(value_html, quote=False)|html}}{{if expand_html}}
      <a class="switch_source" style="background-color: #999" href="#" onclick="return expandLong(this)">...</a>
      <span style="display: none">{{expand_html|html}}</span>
    {{endif}}
    </td>
  </tr>
{{endfor}}
</table>
''', name='table_template')

def pprint_format(value, safe=False):
    out = StringIO()
    try:
        pprint.pprint(value, out)
    except Exception, e:
        if safe:
            out.write('Error: %s' % e)
        else:
            raise
    return out.getvalue()

def format_eval_html(exc_data, base_path, counter):
    short_formatter = EvalHTMLFormatter(
        base_path=base_path,
        counter=counter,
        include_reusable=False)
    short_er, extra_data = short_formatter.format_collected_data(exc_data)
    short_text_er, text_extra_data = formatter.format_text(exc_data, show_extra_data=False)
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


input_form = HTMLTemplate('''
<form action="#" method="POST"
 onsubmit="return submitInput($(\'submit_{{tbid}}\'), {{tbid}})">
<div id="exec-output-{{tbid}}" style="width: 95%;
 padding: 5px; margin: 5px; border: 2px solid #000;
 display: none"></div>
<input type="text" name="input" id="debug_input_{{tbid}}"
 style="width: 100%"
 autocomplete="off" onkeypress="upArrow(this, event)"><br>
<input type="submit" value="Execute" name="submitbutton"
 onclick="return submitInput(this, {{tbid}})"
 id="submit_{{tbid}}"
 input-from="debug_input_{{tbid}}"
 output-to="exec-output-{{tbid}}">
<input type="submit" value="Expand"
 onclick="return expandInput(this)">
</form>
 ''', name='input_form')


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
