.. -*-rst-*-

Introduction
============

WebError provides WSGI middleware for the debugging and handling of errors
inside of WSGI applications.

Usage
=====

There are two primary WSGI middleware components:

weberror.errormiddleware.make_error_middleware 
----------------------------------------------

This middleware should be used for production
deployed applications and is used to track extra information regarding
errors that occur.  These error entries can additionally be emailed to
a given email address using the *error_email* option.  Example usage::

  from weberror.evalexception import make_eval_exception
  app = make_eval_exception(app, global_conf)


weberror.evalexception.make_eval_exception
------------------------------------------

This middleware is used to help debug errors in wsgi applications
during development and should not be used in production.  Example usage::

  from weberror.evalexception import make_eval_exception
  app = make_eval_exception(app, global_conf)
