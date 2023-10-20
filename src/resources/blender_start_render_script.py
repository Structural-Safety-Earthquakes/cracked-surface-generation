import argparse

import bpy
import os
import sys


SCRIPT_NAME = 'generate_dataset.py'

# Parse arguments -- from the background_job.py template
argv = sys.argv
if "--" not in argv:
    argv = []  # as if no args are passed
else:
    argv = argv[argv.index("--") + 1:]  # get all args after "--"

# When --help or no args are given, print this help
usage_text = (
    "Run blender in background mode with this script:"
    "  blender --background --python " + __file__ + " -- [options]"
)
parser = argparse.ArgumentParser(description=usage_text)

parser.add_argument(
    "-c", "--count", dest="count", type=int, required=False, default=1,
    help="The data set size.",
)
args = parser.parse_args(argv)  # In this example we won't use the args

# Add to path
base_dir = os.path.join(os.path.dirname(bpy.data.filepath), '..')
if base_dir not in sys.path:
    sys.path.append(base_dir)

# Reload all submodules
import generate_dataset
import importlib
modules = [key for key in sys.modules.keys() if 'dataset_generation' in key or 'crack_generation' in key]
for key in modules:
    importlib.reload(sys.modules[key])

importlib.reload(generate_dataset)
generate_dataset.main(args.count)
