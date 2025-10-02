import os
import sys

import pyinstaller_versionfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import constants

with open(os.path.join(os.path.dirname(__file__), "VERSION"), "w") as file:
    content = file.write(constants.VERSION)

pyinstaller_versionfile.create_versionfile(
    output_file=os.path.join(os.path.dirname(__file__), "pyinstaller_version.txt"),
    version=constants.VERSION,
    company_name=constants.APPLICATION_AUTHOR,
    file_description=constants.APPLICATION_NAME,
    internal_name=constants.APPLICATION_NAME,
    legal_copyright=constants.APPLICATION_COPYRIGHT,
    original_filename=f"{constants.APPLICATION_NAME}.exe",
    product_name=constants.APPLICATION_NAME,
    translations=[0x0409, 1200],
)
