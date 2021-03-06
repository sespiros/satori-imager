#!/usr/bin/env python3

import argparse
import imp
import itertools
import os
import sys
from multiprocessing.dummy import Pool

from hooker import EVENTS

from satoricore.logger import logger, set_quiet_logger, set_debug_logger
from satoricore.common import _STANDARD_EXT as SE
from satoricore.crawler import BaseCrawler
from satoricore.image import SatoriImage
from satoricore.common import load_extension_list
from satoricore.common import get_image_context_from_arg

from satoricore.file.json import SatoriJsoner
from satoricore.file.pickle import SatoriPickler

EVENTS.append([
    "imager.on_start", "imager.pre_open", "imager.with_open",
    "imager.post_close", "imager.on_end",
])
from satoricore.extensions import *  # noqa


PROCESSED_FILES = 0


def file_worker(image, file_desc, context=os):
    global PROCESSED_FILES
    PROCESSED_FILES += 1
    filename, filetype = file_desc
    image.add_file(filename)
    func = EVENTS["imager.pre_open"]
    func(
            satori_image=image, file_path=filename,
            file_type=filetype, os_context=context,
        )
    if filetype is not SE.DIRECTORY_T:
        if len(EVENTS["imager.with_open"]):
            try:
                fd = open(filename, 'rb')
                func = EVENTS["imager.with_open"]
                func(
                    satori_image=image, file_path=filename,
                    file_type=filetype, fd=fd,
                )
                fd.close()
                func = EVENTS["imager.post_close"]
                func(
                    satori_image=image, file_path=filename,
                    file_type=filetype, os_context=context,
                )
            except Exception as e:
                logger.info(
                    "%s . File '%s' could not be opened."
                    % (e, filename)
                )

def _clone(args, image, context=os):
    entrypoints = []
    for entrypoint in args.entrypoints:
        if context.path.isdir(entrypoint):
            entrypoints.append(entrypoint)
        else:
            logger.error(
                "Entrypoint '{}' is not a Directory".format(entrypoint)
            )
    if not entrypoints:
        logger.critical("No valid Entrypoints Found!")
        logger.critical("Exiting...")
        sys.exit(-1)

    crawler = BaseCrawler(entrypoints, args.excluded_dirs, image=context)

    load_extension_list(args.load_extensions)

    pool = Pool(args.threads)
    pool.starmap(  # image, (filename, filetype), context
        file_worker, zip(
                itertools.repeat(image),
                crawler(),
                itertools.repeat(context)
            )
    )
    pool.close()
    pool.join()

    logger.info("Processed {} files".format(PROCESSED_FILES))
    logger.info("Image Generated!")
    image_serializer = SatoriJsoner()
    # image_serializer = SatoriPickler()
    image_serializer.write(image, args.image_file)
    logger.warn("Stored to file '{}'".format(image_serializer.last_file))


def _setup_argument_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-e', '--excluded-dirs',
        help='Exclude files under specified locations.',
        action='append',
    )

    parser.add_argument(
        '-l', '--load-extensions',
        help='Load the following extensions',
        action='append',
        default=[],
    )

    parser.add_argument(
        '-q', '--quiet',
        help=("Does not show Errors"),
        default=False,
        action='store_true',
    )

    parser.add_argument(
        '-t', '--threads',
        help=("Number of threads to use (might cause dead-locks)"),
        default=1,
        type=int,
    )

    parser.add_argument(
        '-r', '--remote',
        help=("A connection string for remote connection"),
    )


    parser.add_argument(
        'entrypoints',
        help='Start iteration using these directories.',
        nargs='+',
    )

    parser.add_argument(
        'image_file',
        help='Store the created image in that file',
        # default="%s.str" % os.uname,
    )
    return parser


def main():
    parser = _setup_argument_parser()
    args = parser.parse_args()

    if args.quiet:
        set_quiet_logger()


    image = SatoriImage()
    EVENTS["imager.on_start"](parser=parser, args=args, satori_image=image)
    conn_context=None
    if args.remote:
        try:
            import satoriremote

            conn_context = get_image_context_from_arg(args.remote, allow_local=False)
            with conn_context as context:
                _clone(args, image, context=context)

        except ImportError:
            logger.critical("'--remote' parameter not available without 'satori-remote' package.")
            sys.exit(1)


    else:
        _clone(args, image, context=os)
    EVENTS["imager.on_end"]()


if __name__ == '__main__':
    main()
