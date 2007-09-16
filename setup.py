from setuptools import setup, find_packages
import sys, os

version = '0.1'

setup(name='WebError',
      version=version,
      description="Web Error handling and exception catching",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='wsgi',
      author='Ben Bangert, Ian Bicking, Mark Ramm',
      author_email='',
      url='',
      license='',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
