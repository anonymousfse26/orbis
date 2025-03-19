from setuptools import find_packages
from setuptools import setup

from scope import __version__

# with open('./README.md') as f:
#     LONG_DESCRIPTION = f.read()

setup(
    name='scope',
    version=__version__,
    description='SCOPE: Enhancing Symbolic Execution through Optimized Option-Related Branch Exploration',
    # long_description=LONG_DESCRIPTION,
    python_version='>=3.6',
    packages=find_packages(include=('scope', 'scope.*')),
    include_package_data=True,
    setup_requires=[],
    install_requires=[
        'numpy',
        'tree-sitter<=0.21.3',
        'clang<=6.0.0',
        'scikit-learn',
    ],
    dependency_links=[],
    entry_points={
        'console_scripts': [
            'scope=scope.bin:main',
        ]
    }
)
