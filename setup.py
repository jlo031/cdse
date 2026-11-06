import os

from setuptools import find_packages, setup

def read(filename):
    path = os.path.join(os.path.dirname(__file__), filename)
    with open(path, encoding="utf-8") as file:
        return file.read()

setup(
    name="cdse",
    version="0.0.1",
    author="Johannes Lohse",
    author_email="johannes.lohse@utas.edu.au",
    description="Search and download data from CDSE.",
    license="The Ask Johannes Before You Do Anything License",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "loguru",
        "requests",
        "geojson",
        "geomet",
        "python-dotenv",
    ],
    python_requires=">=3.9",
)
