from MQInitializer import MQInitializer
from MQPlots import MQPlots
import argparse
import tkinter as tk
from tkinter import filedialog
import logging


def main():
    # create arg parser to handle different options
    parser = argparse.ArgumentParser(description="A pipeline to analyze result files from a MaxQuant report. "
                                                 "The required result files are in the txt directory.")
    parser.add_argument(
        '--dir',
        dest='dir',
        action='store',
        help="Path to directory of analysis which should be analyzed."
             "If not set the program will open a prompt and ask to select one."
    )
    parser.add_argument(
        '--yml-file',
        dest='yml_file',
        action='store',
        help="Path to yml file which should be used for analysis, or 'default'. "
             "If not set the program will open a prompt and ask to select one, "
             "but if canceled the default yml file will be used."
    )
    parser.add_argument(
        "--loglevel",
        dest="loglevel",
        action="store",
        default=logging.WARNING,
        help="Logging level of analysis. Should be from options (lowest to highest): DEBUG < INFO < WARNING < ERROR. "
             "The higher the logging level the fewer messages are shown. Default: WARNING"
    )
    args = parser.parse_args()
    args_dict = vars(args)
    # print(args)
    # disable most ui things
    root = tk.Tk()
    root.withdraw()
    # if no dir was specified ask for one
    if args.dir is None:
        start_dir = filedialog.askdirectory(title='Please select a directory with MaxQuant result files')
        if not start_dir:
            raise ValueError("Please select a directory")
    else:
        start_dir = args.dir
    # determine logging level
    try:
        loglevel = getattr(logging, args.loglevel.upper())
    except AttributeError:
        try:
            loglevel = int(args.loglevel)
        except ValueError:
            loglevel = logging.DEBUG
    # create initializer which reads all required files
    mqinit = MQInitializer(start_dir, args.yml_file, loglevel=loglevel)
    # create plotter from initializer
    mqplots = MQPlots.from_MQInitializer(mqinit, loglevel=loglevel)
    # create all plots and other results
    mqplots.create_results()


if __name__ == "__main__":
    main()