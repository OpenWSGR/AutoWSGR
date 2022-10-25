import os

from setuptools import setup


def get_version() -> str:
    # https://packaging.python.org/guides/single-sourcing-package-version/
    init = open(os.path.join("AutoWSGR", "__init__.py"), "r").read().split()
    return init[init.index("__version__") + 2][1:-1]


setup(
    name='AutoWSGR',
    version=get_version(),
    description="All in one Warship Girls python package",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/huan-yp/Auto-WSGR",
    setup_requires=['setuptools_scm'],
    use_scm_version=False,
    include_package_data=True,
    packages=['AutoWSGR'],
    install_requires=[
        "opencv-python==4.5.1.48",
        "airtest",
        "keyboard",
        "easyocr",
    ],
)
