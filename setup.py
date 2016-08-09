from setuptools import setup, find_packages

setup(
    name = 'Steemvote',
    version = '0.1.0',
    install_requires = [
        'humanfriendly',
        'plyvel',
        'steem-piston',
    ],
    packages = find_packages(),
    author = 'kefkius',
    scripts = ['steemvoter']
)
