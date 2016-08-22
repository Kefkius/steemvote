#!/usr/bin/env python3
import os
from setuptools import setup, find_packages

# The current version of steemvote.
STEEMVOTE_VERSION = '0.2.0'

# http://stackoverflow.com/questions/4060221/how-to-reliably-open-a-file-in-the-same-directory-as-a-python-script
def readme():
    current_dir = os.path.realpath(os.path.join(os.getcwd(),
            os.path.dirname(__file__)))
    with open(os.path.join(current_dir, 'README.md')) as f:
        return f.read()

setup(
    name = 'Steemvote',
    version = STEEMVOTE_VERSION,
    description = 'Automated Steem voting.',
    long_description = readme(),
    url = 'https://github.com/kefkius/steemvote',
    keywords = [
        'steem',
        'steemit',
    ],
    license = 'AGPLv3+',
    classifiers = [
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Utilities',
    ],
    install_requires = [
        'humanfriendly',
        'plyvel',
        'steem-piston',
    ],
    packages = find_packages(),
    author = 'Tyler Willis',
    author_email = 'kefkius@mail.com',
    scripts = ['steemvoter']
)
