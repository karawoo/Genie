#!/usr/bin/env python3
from collections import defaultdict
import datetime
import logging
import os
import time
from typing import List

import synapseclient
try:
    from synapseclient.core.utils import to_unix_epoch_time
except ModuleNotFoundError:
    from synapseclient.utils import to_unix_epoch_time
import synapseutils
import pandas as pd

from .config import PROCESS_FILES
from . import process_functions
from . import validate
from . import toRetract

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DUPLICATED_FILE_ERROR = (
    "Duplicated filename! Files should be uploaded as new versions "
    "and the entire dataset should be uploaded."
)

'''
TODO:
Could potentially get all the inforamation of the file entity right here
To avoid the syn.get rest call later which doesn't actually download the file
'''

# def rename_file(ent):
#     '''
#     Gets file from synapse and renames the file if necessary.

#     Adds the expected name as an annotation to a Synapse File object.

#     Args:
#         synid : Synapse id or entity

#     Returns:
#         entity with annotation set for path of corrected file
#     '''
#     dirpath = os.path.dirname(ent.path)
#     expectedpath = os.path.join(dirpath, ent.name)

#     ent.annotations.expectedPath = expectedpath
#     return ent


def entity_date_to_timestamp(entity_date_time):
    """Convert Synapse object date/time string (from modifiedOn or createdOn properties) to a timestamp.
    """

    date_and_time = entity_date_time.split(".")[0]
    date_time_obj = datetime.datetime.strptime(date_and_time, "%Y-%m-%dT%H:%M:%S")
    return to_unix_epoch_time(date_time_obj)


def get_center_input_files(syn, synid, center, process="main", downloadFile=True):
    '''
    This function walks through each center's input directory
    to get a list of tuples of center files

    Args:
        syn: Synapse object
        synid: Center input folder synid
        center: Center name
        process: Process type includes, main, vcf, maf and mafSP.
                 Defaults to main such that the vcf

    Returns:
        List of entities with the correct format to pass into validation
    '''
    logger.info("GETTING {center} INPUT FILES".format(center=center))
    clinical_pair_name = [
        "data_clinical_supp_sample_{center}.txt".format(center=center),
        "data_clinical_supp_patient_{center}.txt".format(center=center)]

    center_files = synapseutils.walk(syn, synid)
    clinicalpair_entities = []
    prepared_center_file_list = []

    for _, _, entities in center_files:
        for name, ent_synid in entities:
            # This is to remove vcfs from being validated during main
            # processing. Often there are too many vcf files, and it is
            # not necessary for them to be run everytime.
            if name.endswith(".vcf") and process != "vcf":
                continue

            ent = syn.get(ent_synid, downloadFile=downloadFile)

            # Clinical file can come as two files.
            # The two files need to be merged together which is
            # why there is this format

            if name in clinical_pair_name:
                clinicalpair_entities.append(ent)
                continue

            prepared_center_file_list.append([ent])

    if clinicalpair_entities:
        # clinicalpair_entities = [x for x in clinicalpair]
        prepared_center_file_list.append(clinicalpair_entities)

    return prepared_center_file_list


def check_existing_file_status(validation_status_table, error_tracker_table, entities):
    '''
    This function checks input files against the existing validation and error
    tracking dataframe

    Args:
        validation_status_table: Validation status Synapse Table query result
        error_tracker_table: Error tracking Synapse Table query result
        entities: list of center input entites

    Returns:
        dict: Input file status
            status_list: file validation status
            error_list: Errors of the files if they exist,
            to_validate: Boolean value for whether of not an input
                         file needs to be validated
    '''
    if len(entities) > 2:
        raise ValueError(
            "There should never be more than 2 files being validated.")

    statuses = []
    errors = []

    validation_statusdf = validation_status_table.asDataFrame()
    error_trackerdf = error_tracker_table.asDataFrame()
    # This should be outside fo the forloop so that it doesn't
    # get reset
    to_validate = False
    for ent in entities:
        # Get the current status and errors from the tables.
        current_status = validation_statusdf[validation_statusdf['id'] == ent.id]
        current_error = error_trackerdf[error_trackerdf['id'] == ent.id]

        if current_status.empty:
            to_validate = True
        else:
            # This to_validate is here, because the following is a
            # sequential check of whether files need to be validated
            statuses.append(current_status['status'].values[0])
            if current_error.empty:
                to_validate = \
                    current_status['status'].values[0] == "INVALID"
            else:
                errors.append(current_error['errors'].values[0])
            # Add Name check here (must add name of the entity as a column)
            if current_status['md5'].values[0] != ent.md5 or \
               current_status['name'].values[0] != ent.name:
                to_validate = True
            else:
                status_str = "{filename} ({id}) FILE STATUS IS: {filestatus}"
                logger.info(status_str.format(filename=ent.name, id=ent.id,
                                              filestatus=current_status['status'].values[0]))

    return({'status_list': statuses,
            'error_list': errors,
            'to_validate': to_validate})


def _send_validation_error_email(syn, user, message_objs):
    '''
    Sends validation error email

    Args:
        syn: Synapse object
        user: username to send message to
        message_objs: list of dicts with 'filenames' and 'messages' to send
    '''

    username = syn.getUserProfile(user)['userName']

    errors = ""
    for message_obj in message_objs:
        file_names = ", ".join(message_obj['filenames'])
        error_message = message_obj['messages']
        errors += f"Filenames: {file_names}, Errors:\n {error_message}\n\n"

    email_message = (f"Dear {username},\n\n"
                     "You have invalid files! "
                     f"Here are the reasons why:\n\n{errors}")

    date_now = datetime.datetime.today().strftime("%Y-%m-%d %H:%M:%S")

    syn.sendMessage(userIds=[user],
                    messageSubject=f"GENIE Validation Error - {date_now}",
                    messageBody=email_message)


def _get_status_and_error_list(valid, message, entities):
    '''
    Helper function to return the status and error list of the
    files based on validation result.

    Args:
        valid: Boolean value of results of validation
        message: Validation message
        entities: List of Synapse Entities

    Returns:
        tuple: input_status_list - status of input files list,
               invalid_errors_list - error list
    '''
    if valid:
        input_status_list = [{'entity': ent, 'status': "VALIDATED"}
                             for ent in entities]
        invalid_errors_list = []
    else:
        input_status_list = [{'entity': ent, 'status': "INVALID"}
                             for ent in entities]
        invalid_errors_list = [{'entity': ent, 'errors': message}
                               for ent in entities]
    return input_status_list, invalid_errors_list


def validatefile(syn, project_id, entities, validation_status_table, error_tracker_table,
                 center, threads, oncotree_link,
                 format_registry=PROCESS_FILES):
    '''Validate a list of entities.

    If a file has not changed, then it doesn't need to be validated.

    Args:
        syn: Synapse object
        entities: A list of entities for a single file 'type' (usually a single file, but clinical can have two)
        validation_statusdf: Validation status dataframe
        error_trackerdf: Invalid files error tracking dataframe
        center: Center of interest
        oncotree_link: Oncotree url

    Returns:
        tuple: input_status_list - status of input files,
               invalid_errors_list - error list
               messages_to_send - list of tuples with (filenames, message, file_users)

    '''

    filepaths = [entity.path for entity in entities]
    filenames = [entity.name for entity in entities]

    logger.info("VALIDATING {filenames}".format(filenames=", ".join(filenames)))

    file_users = [entities[0].modifiedBy, entities[0].createdBy]

    check_file_status = check_existing_file_status(
        validation_status_table, error_tracker_table, entities)

    status_list = check_file_status['status_list']
    error_list = check_file_status['error_list']

    messages_to_send = []

    # Need to figure out to how to remove this
    # This must pass in filenames, because filetype is determined by entity
    # name Not by actual path of file
    validator = validate.GenieValidationHelper(syn=syn, project_id=project_id,
                                               center=center,
                                               entitylist=entities,
                                               format_registry=format_registry)
    filetype = validator.file_type
    if check_file_status['to_validate']:
        valid, message = validator.validate_single_file(
            oncotree_link=oncotree_link, nosymbol_check=False)
        logger.info("VALIDATION COMPLETE")
        input_status_list, invalid_errors_list = _get_status_and_error_list(
            valid, message, entities)
        # Send email the first time the file is invalid
        if invalid_errors_list:
            messages_to_send.append((filenames, message, file_users))
    else:
        input_status_list = [{'entity': entity, 'status': status}
                             for entity, status in zip(entities, status_list)]
        invalid_errors_list = [{'entity': entity, 'errors': errors}
                               for entity, errors in zip(entities, error_list)]
    # add in static filetype and center information
    for input_status in input_status_list:
        input_status.update({'fileType': filetype, 'center': center})
    # An empty list is returned if there are no errors,
    # so nothing will be appended
    for invalid_errors in invalid_errors_list:
        invalid_errors.update({'fileType': filetype, 'center': center})
    return input_status_list, invalid_errors_list, messages_to_send


def processfiles(syn, validfiles, center, path_to_genie,
                 center_mapping_df, oncotree_link, databaseToSynIdMappingDf,
                 validVCF=None, vcf2mafPath=None,
                 veppath=None, vepdata=None,
                 processing="main", reference=None):
    '''
    Processing validated files

    Args:
        syn: Synapse object
        validfiles: pandas dataframe containing validated files
                    has 'id', 'path', and 'fileType' column
        center: GENIE center name
        path_to_genie: Path to GENIE workdir
        center_mapping_df: Center mapping dataframe
        oncotree_link: Link to oncotree
        databaseToSynIdMappingDf: Database to synapse id mapping dataframe
        validVCF: Valid vcf files
        vcf2mafPath: Path to vcf2maf
        veppath: Path to vep
        vepdata: Path to vep index files
        processing: Processing type. Defaults to main
        reference: Reference file for vcf2maf
    '''
    logger.info("PROCESSING {} FILES: {}".format(center, len(validfiles)))
    center_staging_folder = os.path.join(path_to_genie, center)
    center_staging_synid = center_mapping_df.query(
        "center == '{}'".format(center)).stagingSynId.iloc[0]

    if not os.path.exists(center_staging_folder):
        os.makedirs(center_staging_folder)

    if processing != 'vcf':
        for fileSynId, filePath, name, fileType in zip(validfiles['id'],
                                                       validfiles['path'],
                                                       validfiles['name'],
                                                       validfiles['fileType']):
            # filename = os.path.basename(filePath)
            newPath = os.path.join(center_staging_folder, name)
            # store = True
            synId = databaseToSynIdMappingDf.Id[
                databaseToSynIdMappingDf['Database'] == fileType]
            if len(synId) == 0:
                synId = None
            else:
                synId = synId[0]
            if fileType is not None and (processing == "main" or processing == fileType):
                processor = PROCESS_FILES[fileType](syn, center)
                processor.process(
                    filePath=filePath, newPath=newPath,
                    parentId=center_staging_synid, databaseSynId=synId,
                    oncotree_link=oncotree_link,
                    fileSynId=fileSynId, validVCF=validVCF,
                    path_to_GENIE=path_to_genie, vcf2mafPath=vcf2mafPath,
                    veppath=veppath, vepdata=vepdata,
                    processing=processing,
                    databaseToSynIdMappingDf=databaseToSynIdMappingDf,
                    reference=reference)

    else:
        filePath = None
        newPath = None
        fileType = None
        synId = databaseToSynIdMappingDf.Id[
            databaseToSynIdMappingDf['Database'] == processing][0]
        fileSynId = None
        processor = PROCESS_FILES[processing](syn, center)
        processor.process(
            filePath=filePath, newPath=newPath,
            parentId=center_staging_synid, databaseSynId=synId,
            oncotree_link=oncotree_link,
            fileSynId=fileSynId, validVCF=validVCF,
            path_to_GENIE=path_to_genie, vcf2mafPath=vcf2mafPath,
            veppath=veppath, vepdata=vepdata,
            processing=processing,
            databaseToSynIdMappingDf=databaseToSynIdMappingDf,
            reference=reference)

    logger.info("ALL DATA STORED IN DATABASE")

# def _create_maf_db(syn, foo):
#     maf_database_ent = syn.get(maf_database_synid)
#     print(maf_database_ent)
#     maf_columns = list(syn.getTableColumns(maf_database_synid))
#     schema = synapseclient.Schema(
#         name='Narrow MAF {current_time} Database'.format(
#             current_time=time.time()),
#         columns=maf_columns,
#         parent=process_functions.getDatabaseSynId(
#             syn, "main",
#             databaseToSynIdMappingDf=database_synid_mappingdf))
#     schema.primaryKey = maf_database_ent.primaryKey
#     new_maf_database = syn.store(schema)

# TODO: Should split this into 3 funcitons
# so that unit tests are easier to write


def create_and_archive_maf_database(syn, database_synid_mappingdf):
    '''
    Creates new MAF database and archives the old database in the staging site

    Args:
        syn: Synapse object
        databaseToSynIdMappingDf: Database to synapse id mapping dataframe

    Return:
        Editted database to synapse id mapping dataframe
    '''
    maf_database_synid = process_functions.getDatabaseSynId(
        syn, "vcf2maf", project_id=None, databaseToSynIdMappingDf=database_synid_mappingdf)
    maf_database_ent = syn.get(maf_database_synid)
    maf_columns = list(syn.getTableColumns(maf_database_synid))
    schema = synapseclient.Schema(
        name='Narrow MAF {current_time} Database'.format(
            current_time=time.time()),
        columns=maf_columns,
        parent=process_functions.getDatabaseSynId(
            syn, "main", databaseToSynIdMappingDf=database_synid_mappingdf))
    schema.primaryKey = maf_database_ent.primaryKey
    new_maf_database = syn.store(schema)
    # Store in the new database synid
    database_synid_mappingdf['Id'][
        database_synid_mappingdf[
            'Database'] == 'vcf2maf'] = new_maf_database.id

    vcf2maf_mappingdf = database_synid_mappingdf[
        database_synid_mappingdf['Database'] == 'vcf2maf']
    # vcf2maf_mappingdf['Id'][0] = newMafDb.id
    syn.store(synapseclient.Table("syn10967259", vcf2maf_mappingdf))
    # Move and archive old mafdatabase (This is the staging synid)
    maf_database_ent.parentId = "syn7208886"
    maf_database_ent.name = "ARCHIVED " + maf_database_ent.name
    syn.store(maf_database_ent)
    # maf_database_synid = new_maf_database.id
    # Remove can download permissions from project GENIE team
    syn.setPermissions(new_maf_database.id, 3326313, [])
    return(database_synid_mappingdf)


def append_duplication_errors(duplicated_filesdf, user_message_dict):
    """Duplicated files can occur because centers can upload files with the
    same filename in different folders.  This is to append duplication
    errors to the list of errors to email

    Args:
        duplicated_filesdf: Dataframe of duplciated files
        user_message_dict: Dictionary containing list of error messages to
                           send to each user.

    Returns:
        Dictionary containing list of error messages to send to each user.
    """
    duplication_error = (
        "Duplicated filename! Files should be uploaded as new versions "
        "and the entire dataset should be uploaded."
    )
    if not duplicated_filesdf.empty:
        filenames = []
        users = []
        for entity in duplicated_filesdf['entity']:
            users.append(entity.modifiedBy)
            users.append(entity.createdBy)
            filenames.append(entity.name)
        file_messages = dict(filenames=filenames,
                             messages=duplication_error)
        # Must get unique set of users or there
        # will be duplicated error messages sent in the email
        for user in set(users):
            user_message_dict[user].append(file_messages)
    return user_message_dict


def get_duplicated_files(validation_statusdf):
    '''
    Check for duplicated files.  There should be no duplication,
    files should be uploaded as new versions and the entire dataset
    should be uploaded everytime

    #TODO: This is a custom GENIE function

    Args:
        validation_statusdf: dataframe with 'name' and 'id' column
        duplicated_error_message: Error message for duplicated files

    Returns:
        dataframe with 'id', 'name', 'errors', 'center', 'fileType'
        and 'entity' of duplicated files
    '''
    # This is special
    logger.info("CHECK FOR DUPLICATED FILES")
    duplicated_filesdf = validation_statusdf[
        validation_statusdf['name'].duplicated(keep=False)]
    # Define filename str vector
    filename_str = validation_statusdf.name.str
    # cbs/seg files should not be duplicated.
    cbs_seg_index = filename_str.endswith(("cbs", "seg"))
    cbs_seg_files = validation_statusdf[cbs_seg_index]
    if len(cbs_seg_files) > 1:
        duplicated_filesdf = duplicated_filesdf.append(cbs_seg_files)
    # clinical files should not be duplicated.
    clinical_index = filename_str.startswith("data_clinical_supp")
    clinical_files = validation_statusdf[clinical_index]
    if len(clinical_files) > 2:
        duplicated_filesdf = duplicated_filesdf.append(clinical_files)
    duplicated_filesdf.drop_duplicates("id", inplace=True)
    logger.info("THERE ARE {} DUPLICATED FILES".format(
        len(duplicated_filesdf)))
    duplicated_filesdf['errors'] = DUPLICATED_FILE_ERROR
    return duplicated_filesdf


def build_validation_status_table(input_valid_statuses: List[dict]):
    """Build validation status dataframe

    Args:
        input_valid_statuses: list of file validation status

    Returns:
        Validation status dataframe

    """
    status_table_columns = ["id", 'path', 'md5', 'status', 'name',
                            'modifiedOn', 'fileType', 'center',
                            'entity']
    input_status_rows = []
    for input_status in input_valid_statuses:
        entity = input_status['entity']
        row = {'id': entity.id,
               'path': entity.path,
               'md5': entity.md5,
               'status': input_status['status'],
               'name': entity.name,
               'modifiedOn': entity_date_to_timestamp(entity.properties.modifiedOn),
               'fileType': input_status['fileType'],
               'center': input_status['center'],
               'entity': entity}
        input_status_rows.append(row)
    if input_status_rows:
        input_valid_statusdf = pd.DataFrame(input_status_rows)
    else:
        input_valid_statusdf = pd.DataFrame(input_status_rows,
                                            columns=status_table_columns)
    return input_valid_statusdf


def build_error_tracking_table(invalid_errors: List[dict]):
    """Build error tracking dataframe

    Args:
        invalid_errors: list of file invalid errors

    Returns:
        Error tracking dataframe

    """
    error_table_columns = ["id", 'errors', 'name', 'fileType', 'center',
                           'entity']
    invalid_error_rows = []
    for invalid_error in invalid_errors:
        entity = invalid_error['entity']
        row = {'id': entity.id,
               'errors': invalid_error['errors'],
               'name': entity.name,
               'fileType': invalid_error['fileType'],
               'center': invalid_error['center'],
               'entity': entity}
        invalid_error_rows.append(row)
    if invalid_error_rows:
        invalid_errorsdf = pd.DataFrame(invalid_error_rows)
    else:
        invalid_errorsdf = pd.DataFrame(invalid_error_rows,
                                        columns=error_table_columns)
    return invalid_errorsdf


def update_status_and_error_tables(syn,
                                   input_valid_statusdf,
                                   invalid_errorsdf,
                                   validation_status_table,
                                   error_tracker_table):
    '''
    Update validation status and error tracking table

    Args:
        syn: Synapse object
        center: Center
        input_valid_status: list of lists of validation status
        invalid_errors: List of lists of invalid errors
        validation_status_table: Synapse table query of validation status
        error_tracker_table: Synapse table query of error tracker

    '''
    logger.info("UPDATE VALIDATION STATUS DATABASE")

    process_functions.updateDatabase(syn, error_tracker_table.asDataFrame(),
                                     invalid_errorsdf,
                                     error_tracker_table.tableId,
                                     ["id"], to_delete=True)

    process_functions.updateDatabase(syn,
                                     validation_status_table.asDataFrame(),
                                     input_valid_statusdf,
                                     validation_status_table.tableId,
                                     ["id"],
                                     to_delete=True)


def _update_tables_content(validation_statusdf, error_trackingdf):
    """Update validation status and error tracking dataframes with duplicated
    files.  Also update the error table to only contain errors - centers
    may have fixed their files so will want to remove old errors.

    Args:
        validation_statusdf: Validation status dataframe
        error_trackingdf: Error tracking dataframe

    Returns:
        dict: validation_statusdf: Updated validation status dataframe
              error_trackingdf: Updated error tracking dataframe
              duplicated_filesdf:  Duplicated files dataframe

    """
    # Get duplicated files
    duplicated_filesdf = get_duplicated_files(validation_statusdf)
    # index of all duplicated files
    duplicated_idx = validation_statusdf['id'].isin(duplicated_filesdf['id'])
    validation_statusdf['status'][duplicated_idx] = "INVALID"
    duplicated_idx = error_trackingdf['id'].isin(duplicated_filesdf['id'])
    error_trackingdf['errors'][duplicated_idx] = DUPLICATED_FILE_ERROR

    # Old errors are pulled down in validation, so obtain list of
    # files with duplicated file errors
    dup_ids = error_trackingdf['id'][
        error_trackingdf['errors'] == DUPLICATED_FILE_ERROR
    ]
    # Checks to see if the old duplicated files are still duplicated
    remove_ids = dup_ids[~dup_ids.isin(duplicated_filesdf['id'])]

    # Remove fixed duplicated files
    error_trackingdf = error_trackingdf[
        ~error_trackingdf['id'].isin(remove_ids)
    ]
    validation_statusdf = validation_statusdf[
        ~validation_statusdf['id'].isin(remove_ids)
    ]

    # Append duplicated file errors
    duplicated_filesdf['id'].isin(error_trackingdf['id'][duplicated_idx])
    error_trackingdf = error_trackingdf.append(
        duplicated_filesdf[error_trackingdf.columns]
    )
    # Remove duplicates if theres already an error that exists for the file
    error_trackingdf.drop_duplicates("id", inplace=True)

    # Since old errors are retained, make sure to only update
    # files that are actually invalid
    invalid_ids = validation_statusdf['id'][
        validation_statusdf['status'] == "INVALID"
    ]
    error_trackingdf = error_trackingdf[
        error_trackingdf['id'].isin(invalid_ids)
    ]

    return {'validation_statusdf': validation_statusdf,
            'error_trackingdf': error_trackingdf,
            'duplicated_filesdf': duplicated_filesdf}


def validation(syn, project_id, center, process,
               center_files, database_synid_mappingdf,
               oncotree_link, format_registry):
    '''
    Validation of all center files

    Args:
        syn: Synapse object
        center: Center name
        process: main, vcf, maf
        center_mapping_df: center mapping dataframe
        thread: Unused parameter for now
        oncotree_link: Link to oncotree

    Returns:
        dataframe: Valid files
    '''
    logger.info(f"{center} has uploaded {len(center_files)} files.")
    validation_status_synid = process_functions.getDatabaseSynId(
        syn, "validationStatus",
        databaseToSynIdMappingDf=database_synid_mappingdf)
    error_tracker_synid = process_functions.getDatabaseSynId(
        syn, "errorTracker",
        databaseToSynIdMappingDf=database_synid_mappingdf)

    # Make sure the vcf validation statuses don't get wiped away
    # If process is not vcf, the vcf files are not downloaded
    add_query_str = "and name not like '%.vcf'" if process != "vcf" else ''
    # id, md5, status, name, center, modifiedOn, fileType
    validation_status_table = syn.tableQuery(
        "SELECT * FROM {synid} "
        "where center = '{center}' {add}".format(
            synid=validation_status_synid,
            center=center,
            add=add_query_str))
    # id, center, errors, name, fileType
    error_tracker_table = syn.tableQuery(
        "SELECT * FROM {synid} "
        "where center = '{center}' {add}".format(
            synid=error_tracker_synid,
            center=center,
            add=add_query_str))

    input_valid_statuses = []
    invalid_errors = []

    # This default dict will capture all the error messages to send to
    # particular users
    user_message_dict = defaultdict(list)

    for ents in center_files:
        status, errors, messages_to_send = validatefile(
            syn, project_id, ents,
            validation_status_table,
            error_tracker_table,
            center=center, threads=1,
            oncotree_link=oncotree_link,
            format_registry=format_registry)

        input_valid_statuses.extend(status)
        if errors is not None:
            invalid_errors.extend(errors)

        if messages_to_send:
            logger.debug("Collating messages to send to users.")
            for filenames, messages, users in messages_to_send:
                file_messages = dict(filenames=filenames, messages=messages)
                # Must get unique set of users or there
                # will be duplicated error messages sent in the email
                for user in set(users):
                    user_message_dict[user].append(file_messages)

    validation_statusdf = build_validation_status_table(input_valid_statuses)
    error_trackingdf = build_error_tracking_table(invalid_errors)

    new_tables = _update_tables_content(validation_statusdf,
                                        error_trackingdf)
    validation_statusdf = new_tables['validation_statusdf']
    error_trackingdf = new_tables['error_trackingdf']
    duplicated_filesdf = new_tables['duplicated_filesdf']

    # In GENIE, we not only want to send out file format errors, but
    # also when there are duplicated errors.  The function below will
    # append duplication errors as an email to send to users (if applicable)
    user_message_dict = append_duplication_errors(duplicated_filesdf,
                                                  user_message_dict)

    for user, message_objs in user_message_dict.items():
        logger.debug("Sending messages to user {user}.".format(user=user))

        _send_validation_error_email(syn=syn, user=user,
                                     message_objs=message_objs)

    update_status_and_error_tables(
        syn=syn,
        input_valid_statusdf=validation_statusdf,
        invalid_errorsdf=error_trackingdf,
        validation_status_table=validation_status_table,
        error_tracker_table=error_tracker_table
    )

    valid_filesdf = validation_statusdf.query('status == "VALIDATED"')
    return(valid_filesdf[['id', 'path', 'fileType', 'name']])


def center_input_to_database(
        syn, project_id, center, process,
        only_validate, vcf2maf_path, vep_path,
        vep_data, database_to_synid_mappingdf,
        center_mapping_df, reference=None,
        delete_old=False, oncotree_link=None):
    if only_validate:
        log_path = os.path.join(
            process_functions.SCRIPT_DIR,
            "{}_validation_log.txt".format(center))
    else:
        log_path = os.path.join(
            process_functions.SCRIPT_DIR,
            "{}_{}_log.txt".format(center, process))

    logFormatter = logging.Formatter(
        "%(asctime)s [%(name)s][%(levelname)s] %(message)s")
    fileHandler = logging.FileHandler(log_path, mode='w')
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)

    # ----------------------------------------
    # Start input to staging process
    # ----------------------------------------
    '''
    # path_to_genie = os.path.realpath(os.path.join(
    #    process_functions.SCRIPT_DIR, "../"))
    Make the synapsecache dir the genie input folder for now
    The main reason for this is because the .synaspecache dir
    is mounted by batch
    '''
    path_to_genie = os.path.expanduser("~/.synapseCache")
    # Create input and staging folders
    if not os.path.exists(os.path.join(path_to_genie, center, "input")):
        os.makedirs(os.path.join(path_to_genie, center, "input"))
    if not os.path.exists(os.path.join(path_to_genie, center, "staging")):
        os.makedirs(os.path.join(path_to_genie, center, "staging"))

    if delete_old:
        process_functions.rmFiles(os.path.join(path_to_genie, center))

    center_input_synid = center_mapping_df['inputSynId'][
        center_mapping_df['center'] == center][0]
    logger.info("Center: " + center)
    center_files = get_center_input_files(syn, center_input_synid, center,
                                          process)

    # only validate if there are center files
    if center_files:
        validFiles = validation(syn, project_id, center, process, center_files,
                                database_to_synid_mappingdf,
                                oncotree_link, PROCESS_FILES)
    else:
        logger.info("{} has not uploaded any files".format(center))
        return

    if len(validFiles) > 0 and not only_validate:
        # Reorganize so BED file are always validated and processed first
        bed_files = validFiles['fileType'] == "bed"
        beds = validFiles[bed_files]
        validFiles = beds.append(validFiles)
        validFiles.drop_duplicates(inplace=True)
        # Valid vcf files
        vcf_files = validFiles['fileType'] == "vcf"
        validVCF = validFiles['path'][vcf_files].tolist()

        # merge clinical files into one row
        clinical_ind = validFiles['fileType'] == "clinical"
        if clinical_ind.any():
            clinical_files = validFiles[clinical_ind].to_dict(orient='list')
            # The [] implies the values in the dict as a list
            merged_clinical = pd.DataFrame([clinical_files])
            merged_clinical['fileType'] = 'clinical'
            merged_clinical['name'] = f"data_clinical_supp_{center}.txt"
            validFiles = validFiles[~clinical_ind].append(merged_clinical)

        processTrackerSynId = process_functions.getDatabaseSynId(
            syn, "processTracker",
            databaseToSynIdMappingDf=database_to_synid_mappingdf)
        # Add process tracker for time start
        processTracker = syn.tableQuery(
            "SELECT timeStartProcessing FROM {} "
            "where center = '{}' and "
            "processingType = '{}'".format(
                processTrackerSynId, center, process))
        processTrackerDf = processTracker.asDataFrame()
        if len(processTrackerDf) == 0:
            new_rows = [[
                center,
                str(int(time.time()*1000)),
                str(int(time.time()*1000)),
                process]]

            syn.store(synapseclient.Table(
                processTrackerSynId, new_rows))
        else:
            processTrackerDf['timeStartProcessing'][0] = \
                str(int(time.time()*1000))
            syn.store(synapseclient.Table(
                processTrackerSynId, processTrackerDf))

        processfiles(syn, validFiles, center, path_to_genie,
                     center_mapping_df, oncotree_link,
                     database_to_synid_mappingdf,
                     validVCF=validVCF,
                     vcf2mafPath=vcf2maf_path,
                     veppath=vep_path, vepdata=vep_data,
                     processing=process, reference=reference)

        # Should add in this process end tracking
        # before the deletion of samples
        processTracker = syn.tableQuery(
            "SELECT timeEndProcessing FROM {synid} where center = '{center}' "
            "and processingType = '{processtype}'".format(
                synid=processTrackerSynId,
                center=center,
                processtype=process))
        processTrackerDf = processTracker.asDataFrame()
        processTrackerDf['timeEndProcessing'][0] = str(int(time.time()*1000))
        syn.store(synapseclient.Table(processTrackerSynId, processTrackerDf))

        logger.info("SAMPLE/PATIENT RETRACTION")
        toRetract.retract(syn, project_id=project_id)

    else:
        messageOut = \
            "{} does not have any valid files" if not only_validate \
            else "ONLY VALIDATION OCCURED FOR {}"
        logger.info(messageOut.format(center))

    # Store log file
    log_folder_synid = process_functions.getDatabaseSynId(
        syn, "logs", databaseToSynIdMappingDf=database_to_synid_mappingdf)
    syn.store(synapseclient.File(log_path, parentId=log_folder_synid))
    os.remove(log_path)
    logger.info("ALL PROCESSES COMPLETE")
