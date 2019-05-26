#!/usr/bin/env python
import genie
import synapseclient
import logging
logger = logging.getLogger('genie')


def synapse_login(username=None, password=None):
    """
    This function logs into synapse for you if credentials are saved.
    If not saved, then user is prompted username and password.

    :returns:     Synapseclient object
    """
    try:
        syn = synapseclient.login(silent=True)
    except Exception:
        if username is None and password is None:
            raise ValueError(
                "Please specify --syn_user, --syn_pass the first time "
                "you run this script.")
        else:
            syn = synapseclient.login(
                email=username,
                password=password,
                rememberMe=True,
                silent=True)
    return(syn)


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(description='GENIE processing')

    parser.add_argument(
        "--syn_user",
        type=str,
        help='Synapse username')

    parser.add_argument(
        "--syn_pass",
        type=str,
        help='Synapse password')

    subparsers = parser.add_subparsers(
        title='commands',
        description='The following commands are available:',
        help='For additional help: "genie <COMMAND> -h"')

    parser_validate = subparsers.add_parser(
        'validate',
        help='Validates GENIE file formats')

    parser_validate.add_argument(
        "filepath",
        type=str,
        nargs="+",
        help='File(s) that you are validating.  \
        If you validation your clinical files and you have both sample and \
        patient files, you must provide both')

    parser_validate.add_argument(
        "center",
        type=str,
        help='Contributing Centers')

    parser_validate.add_argument(
        "--filetype",
        type=str,
        choices=genie.PROCESS_FILES.keys(),
        help='By default, the validator uses the filename to match '
             'the file format.  If your filename is incorrectly named, '
             'it will be invalid.  If you know the file format you are '
             'validating, you can ignore the filename validation and skip '
             'to file content validation. '
             'Note, the filetypes with SP at '
             'the end are for special sponsored projects')

    parser_validate.add_argument(
        "--oncotreelink",
        type=str,
        help="Link to oncotree code")

    parser_validate.add_argument(
        "--parentid",
        type=str,
        default=None,
        help='Synapse id of center input folder. '
             'If specified, your valid files will be uploaded '
             'to this directory.')

    parser_validate.add_argument(
        "--testing",
        action='store_true',
        help='Put in testing mode')

    parser_validate.add_argument(
        "--nosymbol-check",
        action='store_true',
        help='Do not check hugo symbols of fusion and cna file')

    parser_validate.set_defaults(func=genie.validate.perform_validate)
    return(parser)


def main():
    args = build_parser().parse_args()
    syn = synapse_login(args.syn_user, args.syn_pass)
    if 'func' in args:
        try:
            args.func(syn, args)
        except Exception:
            raise


if __name__ == "__main__":
    main()
