import os

from setuptools import setup


def get_version() -> str:
    # https://packaging.python.org/guides/single-sourcing-package-version/
    init = open(os.path.join("src", "AutoWSGR", "__init__.py"), "r").read().split()
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
    install_requires=[
        "opencv-python==4.5.4.60",
        "opencv-contrib-python==4.5.4.60",
        "opencv-python-headless==4.5.4.60",
        "airtest",
        "keyboard",
        "easyocr",
        "streamlit",
    ],
)
