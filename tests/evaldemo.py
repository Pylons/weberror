from weberror.evalmiddleware import EvalException

def error_application(environ, start_response):
    a = 1
    b = 'x'*1000
    return sub_application(environ, start_response)

def sub_application(environ, start_response):
    test = 10
    raise Exception('The expected error')

if __name__ == '__main__':
    from paste.httpserver import serve
    serve(EvalException(error_application))
    
