from setuptools import setup, find_packages
import sys

version = '0.13'

install_requires = [
    'WebOb',
    'Tempita',
    'Pygments',
    'Paste>=1.7.1',
    ]


if sys.version_info[:2] < (2, 6):
    install_requires.append('simplejson')

README = open('README.rst').read()
CHANGELOG = open('CHANGELOG').read()


setup(name='WebError',
      version=version,
      description="Web Error handling and exception catching",
      long_description=README + '\n\n' + CHANGELOG,
      classifiers=[
          "Development Status :: 5 - Production/Stable",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: MIT License",
          "Programming Language :: Python",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
          "Topic :: Software Development :: Libraries :: Python Modules",
          "Topic :: Internet :: WWW/HTTP :: WSGI",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware",
      ],
      keywords='wsgi',
      author='Ben Bangert, Ian Bicking, Mark Ramm',
      author_email='invalid@invalid.com',
      url='https://bitbucket.org/bbangert/weberror',
      license='MIT',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      package_data={'weberror.evalexception': ["*.html.tmpl", "media/*"]},
      zip_safe=False,
      install_requires=install_requires,
      test_suite='nose.collector',
      tests_require=['nose', 'webtest', 'Paste'],
      entry_points="""
      [paste.filter_app_factory]
      main = weberror.evalexception:make_general_exception
      error_catcher = weberror.errormiddleware:make_error_middleware
      evalerror = weberror.evalexception:make_eval_exception
      """,
      )
