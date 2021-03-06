"""Tests validate.py"""
import mock
from mock import patch
import pandas as pd
import pytest
import synapseclient
try:
    from synapseclient.exceptions import SynapseHTTPError
except ModuleNotFoundError:
    from synapseclient.core.exceptions import SynapseHTTPError

from genie import validate, clinical, process_functions

CENTER = "SAGE"
syn = mock.create_autospec(synapseclient.Synapse)

CNA_ENT = synapseclient.File(name="data_CNA_SAGE.txt",
                             path="data_CNA_SAGE.txt",
                             parentId="syn12345")
CLIN_ENT = synapseclient.File(name="data_clinical_supp_SAGE.txt",
                              path="data_clinical_supp_SAGE.txt",
                              parentId="syn12345")
SAMPLE_ENT = synapseclient.File(name="data_clinical_supp_sample_SAGE.txt",
                                path="data_clinical_supp_sample_SAGE.txt",
                                parentId="syn12345")
PATIENT_ENT = synapseclient.File(name="data_clinical_supp_patient_SAGE.txt",
                                 path="data_clinical_supp_patient_SAGE.txt",
                                 parentId="syn12345")
WRONG_NAME_ENT = synapseclient.File(name="wrong.txt",
                                    path="data_clinical_supp_SAGE.txt",
                                    parentId="syn12345")


@pytest.mark.parametrize("ent_list,fileformat",
                         # tuple with (input, expectedOutput)
                         [([CNA_ENT], "cna"),
                          ([CLIN_ENT], "clinical"),
                          ([SAMPLE_ENT, PATIENT_ENT], "clinical")])
def test_perfect_determine_filetype(ent_list, fileformat):
    """
    Tests determining of file type through filenames
    Parameters are passed in from filename_fileformat_map
    """
    validator = validate.GenieValidationHelper(syn, None, CENTER, ent_list)
    assert validator.determine_filetype() == fileformat


def test_wrongfilename_noerror_determine_filetype():
    '''
    Tests None is passed back when wrong filename is passed
    when raise_error flag is False
    '''
    ent_list = [WRONG_NAME_ENT]
    validator = validate.GenieValidationHelper(syn, project_id=None,
                                               center=CENTER,
                                               entitylist=ent_list)
    assert validator.file_type is None


def test_valid_collect_errors_and_warnings():
    '''
    Tests if no error and warning strings are passed that
    returned valid and message is correct
    '''
    message = validate.collect_errors_and_warnings('', '')
    assert message == "YOUR FILE IS VALIDATED!\n"


def test_invalid_collect_errors_and_warnings():
    """
    Tests if error and warnings strings are passed that
    returned valid and message is correct
    """
    message = validate.collect_errors_and_warnings("error\nnow",
                                                   'warning\nnow')
    assert message == (
        "----------------ERRORS----------------\n"
        "error\nnow"
        "-------------WARNINGS-------------\n"
        'warning\nnow')


def test_warning_collect_errors_and_warnings():
    """
    Tests if no error but warnings strings are passed that
    returned valid and message is correct
    """
    message = \
        validate.collect_errors_and_warnings('', 'warning\nnow')
    assert message == (
        "YOUR FILE IS VALIDATED!\n"
        "-------------WARNINGS-------------\n"
        'warning\nnow')


def test_valid_validate_single_file():
    """
    Tests that all the functions are run in validate single
    file workflow and all the right things are returned
    """
    entitylist = [CLIN_ENT]
    error_string = ''
    warning_string = ''
    expected_valid = True
    expected_message = "valid message here!"
    expected_filetype = "clinical"

    with patch.object(validate.GenieValidationHelper,
                      "determine_filetype",
                      return_value=expected_filetype) as mock_determine_ftype,\
         patch.object(clinical.clinical, "validate",
                      return_value=(expected_valid, error_string,
                                    warning_string)) as mock_genie_class,\
         patch.object(validate, "collect_errors_and_warnings",
                      return_value=expected_message) as mock_determine:
        validator = validate.GenieValidationHelper(syn, project_id=None,
                                                   center=CENTER,
                                                   entitylist=entitylist)
        valid, message = validator.validate_single_file(oncotree_link=None,
                                                        nosymbol_check=False)

        assert valid == expected_valid
        assert message == expected_message
        assert validator.file_type == expected_filetype

        mock_determine_ftype.assert_called_once_with()

        mock_genie_class.assert_called_once_with(filePathList=[CLIN_ENT.path],
                                                 oncotree_link=None,
                                                 nosymbol_check=False)

        mock_determine.assert_called_once_with(error_string, warning_string)


def test_filetype_validate_single_file():
    """
    Tests that if filetype is passed in that an error is thrown
    if it is an incorrect filetype
    """
    entitylist = [WRONG_NAME_ENT]
    expected_error = "----------------ERRORS----------------\nYour filename is incorrect! Please change your filename before you run the validator or specify --filetype if you are running the validator locally"
    validator = validate.GenieValidationHelper(syn, None, CENTER, entitylist)

    valid, message = validator.validate_single_file()
    assert message == expected_error
    assert not valid


def test_wrongfiletype_validate_single_file():
    """
    Tests that if there is no filetype for the filename passed
    in, an error is thrown
    """
    entitylist = [WRONG_NAME_ENT]
    expected_error = '----------------ERRORS----------------\nYour filename is incorrect! Please change your filename before you run the validator or specify --filetype if you are running the validator locally'

    with patch.object(validate.GenieValidationHelper,
                      "determine_filetype",
                      return_value=None) as mock_determine_filetype:
        validator = validate.GenieValidationHelper(syn=syn, project_id=None,
                                                   center=CENTER,
                                                   entitylist=entitylist)
        valid, message = validator.validate_single_file()

        assert message == expected_error
        assert not valid
        mock_determine_filetype.assert_called_once_with()


def test_nopermission__check_parentid_permission_container():
    """Throws error if no permissions to access"""
    parentid = "syn123"
    with patch.object(syn, "get", side_effect=SynapseHTTPError),\
         pytest.raises(ValueError,
                       match="Provided Synapse id must be your input folder "
                             "Synapse id or a Synapse Id of a folder inside "
                             "your input directory"):
        validate._check_parentid_permission_container(syn, parentid)


def test_notcontainer__check_parentid_permission_container():
    """Throws error if input if synid of file"""
    parentid = "syn123"
    file_ent = synapseclient.File("foo", parentId=parentid)
    with patch.object(syn, "get", return_value=file_ent),\
         pytest.raises(ValueError,
                       match="Provided Synapse id must be your input folder "
                             "Synapse id or a Synapse Id of a folder inside "
                             "your input directory"):
        validate._check_parentid_permission_container(syn, parentid)


def test_valid__check_parentid_permission_container():
    """
    Test that parentid specified is a container and have permissions to access
    """
    parentid = "syn123"
    folder_ent = synapseclient.Folder("foo", parentId=parentid)
    with patch.object(syn, "get", return_value=folder_ent):
        validate._check_parentid_permission_container(syn, parentid)


def test_valid__check_center_input():
    center = "FOO"
    center_list = ["FOO", "WOW"]
    validate._check_center_input(center, center_list)


def test_invalid__check_center_input():
    center = "BARFOO"
    center_list = ["FOO", "WOW"]
    with pytest.raises(ValueError,
                       match="Must specify one of these "
                             "centers: {}".format(", ".join(center_list))):
        validate._check_center_input(center, center_list)


ONCOTREE_ENT = 'syn222'


class argparser:
    oncotree_link = "link"
    parentid = None
    filetype = None
    project_id = None
    center = "try"
    filepath = "path.csv"
    nosymbol_check = False
    format_registry_packages = ["genie"]
    project_id = "syn1234"

    def asDataFrame(self):
        database_dict = {"Database": ["centerMapping", 'oncotreeLink'],
                         "Id": ["syn123", ONCOTREE_ENT],
                         "center": ["try", 'foo']}
        databasetosynid_mappingdf = pd.DataFrame(database_dict)
        return databasetosynid_mappingdf


def test_notnone_get_oncotree_link():
    """Test link passed in by user is used"""
    arg = argparser()
    url = "https://www.synapse.org"
    link = validate._get_oncotreelink(syn, arg.asDataFrame(),
                                      oncotree_link=url)
    assert link == url


def test_none__getoncotreelink():
    """Test oncotree link is gotten"""
    arg = argparser()
    url = "https://www.synapse.org"
    link = synapseclient.File("foo", parentId="foo", externalURL=url)
    with patch.object(syn, "get", return_value=link) as patch_synget:
        oncolink = validate._get_oncotreelink(syn, arg.asDataFrame())
        patch_synget.assert_called_once_with(ONCOTREE_ENT)
        assert oncolink == url


def test_valid__upload_to_synapse():
    """
    Test upload of file to synapse under right conditions
    """
    ent = synapseclient.File(id="syn123", parentId="syn222")
    with patch.object(syn, "store", return_value=ent) as patch_synstore:
        validate._upload_to_synapse(syn, ['foo'], True, parentid="syn123")
        patch_synstore.assert_called_once_with(
            synapseclient.File('foo', parent="syn123"))


def test_perform_validate():
    """Make sure all functions are called"""
    arg = argparser()
    valid = True
    with patch.object(validate,
                      "_check_parentid_permission_container",
                      return_value=None) as patch_check_parentid,\
         patch.object(process_functions, "get_synid_database_mappingdf",
                      return_value=arg.asDataFrame()) as patch_getdb,\
         patch.object(syn, "tableQuery",
                      return_value=arg) as patch_syn_tablequery,\
         patch.object(validate, "_check_center_input") as patch_check_center,\
         patch.object(validate, "_get_oncotreelink") as patch_get_onco,\
         patch.object(validate.GenieValidationHelper,
                      "validate_single_file",
                      return_value=(valid, 'foo')) as patch_validate,\
         patch.object(validate, "_upload_to_synapse") as patch_syn_upload:
        validate._perform_validate(syn, arg)
        patch_check_parentid.assert_called_once_with(syn, arg.parentid)
        patch_getdb.assert_called_once_with(syn, project_id=arg.project_id)
        patch_syn_tablequery.assert_called_once_with('select * from syn123')
        patch_check_center.assert_called_once_with(arg.center, ["try", "foo"])
        patch_get_onco.assert_called_once()
        patch_validate.assert_called_once_with(oncotree_link=arg.oncotree_link,
                                               nosymbol_check=arg.nosymbol_check,
                                               project_id=arg.project_id)
        patch_syn_upload.assert_called_once_with(
            syn, arg.filepath, valid, parentid=arg.parentid)
