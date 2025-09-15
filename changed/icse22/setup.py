from setuptools import find_packages
from setuptools import setup

from symtuner import __version__

# with open('./README.md') as f:
#     LONG_DESCRIPTION = f.read()

setup(
    name='symtuner',
    version=__version__,
    description='Symtuner with ORBiS',
    python_version='>=3.6',
    packages=find_packages(include=('symtuner', 'symtuner.*')),
    include_package_data=True,
    setup_requires=[],
    install_requires=[
        'numpy'
    ],
    dependency_links=[],
    entry_points={
        'console_scripts': [
            'symtuner=symtuner.bin:main',
        ]
    }
)
