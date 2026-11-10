from setuptools import Extension, setup

setup(name='thistle-helper', version='0.1.0', ext_modules=[Extension('thistle_helper', ['helper.c'])])
