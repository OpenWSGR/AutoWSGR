import os
import platform
import re
import subprocess
import sys


def _fetch_requirements(path):
    with open(path, "r") as fd:
        return [r.strip() for r in fd.readlines()]


def _fetch_readme():
    with open("README.md", encoding="utf-8") as f:
        return f.read()


def find_version(filepath: str) -> str:
    """Extract version information from the given filepath.

    Adapted from https://github.com/ray-project/ray/blob/0b190ee1160eeca9796bc091e07eaebf4c85b511/python/setup.py
    """
    with open(filepath) as fp:
        version_match = re.search(
            r"^__version__ = ['\"]([^'\"]*)['\"]", fp.read(), re.M
        )
        if version_match:
            return version_match.group(1)
        raise RuntimeError("Unable to find version string.")


def install_wheel():
    try:
        import wheel
    except ImportError:
        subprocess.run(["pip", "install", "wheel"])


install_wheel()


def _fetch_package_name():
    return "autowsgr"


from setuptools import find_namespace_packages, find_packages, setup
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel


# Custom wheel class to modify the wheel name
class bdist_wheel(_bdist_wheel):
    def finalize_options(self):
        _bdist_wheel.finalize_options(self)
        self.root_is_pure = False

    def get_tag(self):
        python_version = f"cp{sys.version_info.major}{sys.version_info.minor}"
        abi_tag = f"{python_version}"

        if platform.system() == "Linux":
            platform_tag = "manylinux1_x86_64"
        else:
            platform_tag = platform.system().lower()

        return python_version, abi_tag, platform_tag


# Setup configuration
setup(
    name=_fetch_package_name(),
    version=find_version("autowsgr/__init__.py"),
    packages=find_namespace_packages(
        include=["autowsgr*", "awsg*"],
        exclude=(
            "docs",
            "examples",
        ),
    ),
    include_package_data=True,
    description="Auto Warship Girls Framework.",
    long_description=_fetch_readme(),
    long_description_content_type="text/markdown",
    install_requires=_fetch_requirements("requirements.txt"),
    setup_requires=["wheel"],
    dependency_links=[
        "https://download.pytorch.org/whl/cu123",
    ],
    python_requires=">=3.9",
    package_data={
        "": [
            "version.txt",
            "data/**",
            "requirements.txt",
            "bin/**",
            "c_src/**",
        ],  # 希望被打包的文件
    },
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Environment :: GPU :: NVIDIA CUDA",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: System :: Distributed Computing",
    ],
    cmdclass={"bdist_wheel": bdist_wheel},
)
