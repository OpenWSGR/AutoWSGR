import os
import platform
import subprocess
import sys
from datetime import datetime

from setuptools import find_namespace_packages, find_packages, setup
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

_build_mode = os.getenv("AUTOWSGR_BUILD_MODE", "")


def _is_nightly():
    return _build_mode.lower() == "nightly"


def _fetch_requirements(path):
    with open(path, "r") as fd:
        return [r.strip() for r in fd.readlines()]


def _fetch_readme():
    with open("README.md", encoding="utf-8") as f:
        return f.read()


def _fetch_version():

    version_path = os.path.join(os.path.dirname(__file__), "version.txt")
    with open(version_path, "r") as f:
        version = f.read().strip()

    if _is_nightly():
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        version += f".dev{date_str}"

    return version


def _fetch_package_name():
    return "autowsgr-nightly" if _is_nightly() else "autowsgr"


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
    version=_fetch_version(),
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
    dependency_links=[
        "https://www.paddlepaddle.org.cn/packages/stable/cu123/",
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
        ],  # 包含 version.txt 文件
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
