# (c) 2005 Ian Bicking, Clark C. Evans and contributors
# This module is part of the Python Paste Project and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php
"""
WSGI Exception Middleware

Regression Test Suite
"""
from paste.httpexceptions import *
from paste.wsgilib import raw_interactive
from paste.response import header_value
import py


def test_HTTPMove():
    """ make sure that location is a mandatory attribute of Redirects """
    py.test.raises(AssertionError,HTTPFound)
    py.test.raises(AssertionError,HTTPTemporaryRedirect,
                   headers=[('l0cation','/bing')])
    assert isinstance(HTTPMovedPermanently("This is a message",
                          headers=[('Location','/bing')])
                     ,HTTPRedirection)
    assert isinstance(HTTPUseProxy(headers=[('LOCATION','/bing')])
                     ,HTTPRedirection)
    assert isinstance(HTTPFound('/foobar'),HTTPRedirection)

def test_badapp():
    """ verify that the middleware handles previously-started responses """
    def badapp(environ, start_response):
        start_response("200 OK",[])
        raise HTTPBadRequest("Do not do this at home.")
    newapp = HTTPExceptionHandler(badapp)
    assert 'Bad Request' in ''.join(newapp({'HTTP_ACCEPT': 'text/html'},
                                           (lambda a, b, c=None: None)))

def test_unicode():
    """ verify unicode output """
    tstr = u"\0xCAFE"
    def badapp(environ, start_response):
        start_response("200 OK",[])
        raise HTTPBadRequest(tstr)
    newapp = HTTPExceptionHandler(badapp)
    assert tstr.encode("utf-8") in ''.join(newapp({'HTTP_ACCEPT':
                                         'text/html'},
                                         (lambda a, b, c=None: None)))
    assert tstr.encode("utf-8") in ''.join(newapp({'HTTP_ACCEPT':
                                         'text/plain'},
                                         (lambda a, b, c=None: None)))

def test_template():
    """ verify that html() and plain() output methods work """
    e = HTTPInternalServerError()
    e.template = 'A %(ping)s and <b>%(pong)s</b> message.'
    assert str(e).startswith("500 Internal Server Error")
    assert e.plain({'ping': 'fun', 'pong': 'happy'}) == (
        '500 Internal Server Error\r\n'
        'A fun and happy message.\r\n')
    assert '<p>A fun and <b>happy</b> message.</p>' in \
           e.html({'ping': 'fun', 'pong': 'happy'})

def test_iterator_application():
    """
    This tests to see that an iterator's exceptions are caught by
    HTTPExceptionHandler
    """
    def basic_found(environ, start_response):
        raise HTTPFound("/bing/foo")
        return ['result']
    app = HTTPExceptionHandler(basic_found)
    (status, headers, content, errors) = raw_interactive(app)
    assert '302 Found' == status
    def make_iter(application):
        def iterapp(environ, start_response):
            result = application(environ, start_response)
            for chunk in result:
                yield chunk
        return iterapp
    app = HTTPExceptionHandler(make_iter(basic_found))
    (status, headers, content, errors) = raw_interactive(app)
    assert '302 Found' == status
    def iterate_found(environ, start_response):
        raise HTTPFound("/bing/foo")
        yield 'result'
    app = HTTPExceptionHandler(iterate_found)
    (status, headers, content, errors) = raw_interactive(app)
    assert '302 Found' == status

def test_redapp():
    """ check that redirect returns the correct, expected results """
    saved = []
    def saveit(status, headers, exc_info = None):
        saved.append((status,headers))
    def redapp(environ, start_response):
        raise HTTPFound("/bing/foo")
    app = HTTPExceptionHandler(redapp)
    result = list(app({'HTTP_ACCEPT': 'text/html'},saveit))
    assert '<a href="/bing/foo">' in result[0]
    assert "302 Found" == saved[0][0]
    assert "text/html" == header_value(saved[0][1], 'content-type')
    assert "/bing/foo" == header_value(saved[0][1],'location')
    result = list(app({'HTTP_ACCEPT': 'text/plain'},saveit))
    print result[0] == (
        '302 Found\n'
        'This resource was found at /bing/foo;\n'
        'you should be redirected automatically.\n')
    assert "text/plain" == header_value(saved[1][1],'content-type')
    assert "/bing/foo" == header_value(saved[1][1],'location')

def test_misc():
    assert get_exception(301) == HTTPMovedPermanently
    redirect = HTTPFound("/some/path")
    assert isinstance(redirect,HTTPException)
    assert isinstance(redirect,HTTPRedirection)
    assert not isinstance(redirect,HTTPError)
    notfound = HTTPNotFound()
    assert isinstance(notfound,HTTPException)
    assert isinstance(notfound,HTTPError)
    assert isinstance(notfound,HTTPClientError)
    assert not isinstance(notfound,HTTPServerError)
    notimpl = HTTPNotImplemented()
    assert isinstance(notimpl,HTTPException)
    assert isinstance(notimpl,HTTPError)
    assert isinstance(notimpl,HTTPServerError)
    assert not isinstance(notimpl,HTTPClientError)

