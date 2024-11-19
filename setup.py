import re

from setuptools import find_namespace_packages, setup


def _fetch_requirements(path: str) -> list:
    requirements = []
    with open(path) as f:
        for r in f:
            r = r.strip()
            if r.startswith('-r'):
                assert len(r.split()) == 2
                requirements.extend(_fetch_requirements(r.split()[-1]))
            else:
                requirements.append(r)
    return requirements


def _fetch_readme():
    with open('README.md', encoding='utf-8') as f:
        return f.read()


def find_version(filepath: str) -> str:
    """Extract version information from the given filepath.

    Adapted from https://github.com/ray-project/ray/blob/0b190ee1160eeca9796bc091e07eaebf4c85b511/python/setup.py
    """
    with open(filepath) as fp:
        version_match = re.search(
            r"^__version__ = ['\"]([^'\"]*)['\"]",
            fp.read(),
            re.MULTILINE,
        )
        if version_match:
            return version_match.group(1)
        raise RuntimeError('Unable to find version string.')


# Setup configuration
setup(
    name='autowsgr',
    version=find_version('autowsgr/__init__.py'),
    packages=find_namespace_packages(
        include=['autowsgr*', 'awsg*'],
        exclude=(
            'docs',
            'examples',
        ),
    ),
    include_package_data=True,
    description='Auto Warship Girls Framework.',
    long_description=_fetch_readme(),
    long_description_content_type='text/markdown',
    install_requires=_fetch_requirements('requirements.txt'),
    python_requires='>=3.10,<3.13',
    package_data={
        '': [
            'data/**',
            'requirements.txt',
            'bin/**',
            'c_src/**',
        ],  # 希望被打包的文件
    },
    classifiers=[
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Environment :: GPU :: NVIDIA CUDA',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: System :: Distributed Computing',
    ],
)
