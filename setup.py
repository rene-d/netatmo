import sys
from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))


# Get the long description from the README file
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="netatmo",
    version="0.0.1",
    description="Python3 API for the Netatmo Weather Station",
    long_description=long_description,
    long_description_content_type='text/markdown',  # Optional (see note above)
    url='https://github.com/rene-d/netatmo',  # Optional
    author="Rene Devichi",
    author_email="rene.github@gmail.com",
    classifiers=[
        "License :: OSI Approved :: The Unlicense",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    keywords="development domotics netatmo",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.5, <4",
    install_requires=["requests"],
    entry_points={"console_scripts": ["netatmo=netatmo.netatmo:main"]},
    project_urls={
        "Source": "https://github.com/rene-d/netatmo",
        "Bug Reports": "https://github.com/rene-d/netatmo/issues",
    },
)
