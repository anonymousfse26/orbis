from setuptools import find_packages
from setuptools import setup

from scope import __version__

# with open('./README.md') as f:
#     LONG_DESCRIPTION = f.read()

setup(
    name='scope',
    version=__version__,
    description='scope: Maximizing the Power of Symbolic Execution by Adaptively Tuning External Parameters',
    # long_description=LONG_DESCRIPTION,
    python_version='>=3.6',
    packages=find_packages(include=('scope', 'scope.*')),
    include_package_data=True,
    setup_requires=[],
    install_requires=[
        'numpy',
    ],
    dependency_links=[],
    entry_points={
        'console_scripts': [
            'scope=scope.bin:main',
        ]
    }
)
