from setuptools import setup, find_packages

setup(
    name="MySensorTools",
    version="0.1.0",
    description="Tools for robot sensor fault diagnosis, data analysis, log parsing, and visualization",
    author="YilunHuang1",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.7",
    install_requires=[
        "numpy>=1.21.0",
        "pandas>=1.3.0",
        "matplotlib>=3.4.0",
        "scipy>=1.7.0",
    ],
    extras_require={
        "dev": ["pytest>=6.0"],
    },
)
