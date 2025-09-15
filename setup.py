from setuptools import find_packages
from setuptools import setup

from orbis import __version__

# with open('./README.md') as f:
#     LONG_DESCRIPTION = f.read()

setup(
    name='orbis',
    version=__version__,
    description='ORBiS: Enhancing Symbolic Execution through Optimized Option-Related Branch Exploration',
    python_version='>=3.6',
    packages=find_packages(include=('orbis', 'orbis.*')),
    include_package_data=True,
    setup_requires=[],
    install_requires=[
        'numpy'
    ],
    dependency_links=[],
    entry_points={
        'console_scripts': [
            'orbis=orbis.bin:main',
        ]
    }
)
