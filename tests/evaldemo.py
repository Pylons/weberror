from weberror.evalexception import EvalException

def error_application(environ, start_response):
    a = 1
    b = 'x'*1000
    return sub_application(environ, start_response)

def sub_application(environ, start_response):
    test = 10
    raise Exception('The expected <error>')

if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('--port', default='8080',
                      help='The port to serve on (default 8080)',
                      dest='port')
    parser.add_option('--no-eval',
                      action='store_true',
                      dest='no_eval',
                      help='Don\'t use the eval catcher, just the static catcher')
    parser.add_option('--email',
                      metavar='EMAIL',
                      help='Use the emailer instead of evalexception',
                      dest='email')
    parser.add_option('--smtp-server',
                      default='localhost',
                      metavar='HOST[:PORT]',
                      dest='smtp_server',
                      help='SMTP server to use')
    options, args = parser.parse_args()
    from paste.httpserver import serve
    if options.no_eval or options.email:
        from weberror.errormiddleware import ErrorMiddleware
        app = ErrorMiddleware(
            error_application, debug=True, error_email=options.email,
            smtp_server=options.smtp_server)
    else:
        app = EvalException(error_application)
    serve(app, port=int(options.port))

