"""
setup.py for WaveRNN package.
"""
import setuptools  # type: ignore
from torch.utils.cpp_extension import BuildExtension, CppExtension

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="wavernn",
    version="1.0.0",
    author="Andrew Gibiansky",
    author_email="andrew.gibiansky@gmail.com",
    description="A small example package",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gibiansky/wavernn",
    project_urls={
        "Bug Tracker": "https://github.com/gibiansky/wavernn/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    python_requires=">=3.6",
    install_requires=[
        "click==8.2.0",
        "omegaconf==2.3.0",
        "torch==2.6.0",
        "pytorch-lightning==2.5.1.post0",
        "librosa==0.11.0",
    ],
    scripts=["scripts/wavernn"],
    ext_modules=[
        CppExtension(
            "wavernn_kernel",
            [
                "src/kernel/kernel.cpp",
                "src/kernel/gemv.cpp",
                "src/kernel/ops.cpp",
                "src/kernel/timer.cpp",
            ],
            extra_compile_args=[
                "-Ofast",
                "-march=native",
                "-fopenmp",
            ],
        )
    ],
    cmdclass={"build_ext": BuildExtension.with_options(no_python_abi_suffix=True)},
)
