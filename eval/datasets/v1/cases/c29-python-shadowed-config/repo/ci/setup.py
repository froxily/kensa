from setuptools import Extension, setup

# This probe is built only when qualifying a native toolchain.
# It is not part of the service distribution.
setup(
    ext_modules=[
        Extension(
            "quartz_probe",
            sources=["probe.c"],
        ),
    ],
)
