import mock
import pytest

import pandas as pd
import synapseclient

from genie.maf import maf
from genie.mafSP import mafSP

syn = mock.create_autospec(synapseclient.Synapse)

maf_class = maf(syn, "SAGE")
mafsp_class = mafSP(syn, "SAGE")


def test_processing():
    keep_maf_columns = [
        'Hugo_Symbol', 'Entrez_Gene_Id', 'Center',
        'NCBI_Build', 'Chromosome', 'Start_Position',
        'End_Position', 'Strand', 'Variant_Classification',
        'Variant_Type', 'Reference_Allele', 'Tumor_Seq_Allele1',
        'Tumor_Seq_Allele2', 'dbSNP_RS', 'dbSNP_Val_Status',
        'Tumor_Sample_Barcode', 'Matched_Norm_Sample_Barcode',
        'Match_Norm_Seq_Allele1', 'Match_Norm_Seq_Allele2',
        'Tumor_Validation_Allele1', 'Tumor_Validation_Allele2',
        'Match_Norm_Validation_Allele1', 'Match_Norm_Validation_Allele2',
        'Verification_Status', 'Validation_Status', 'Mutation_Status',
        'Sequencing_Phase', 'Sequence_Source', 'Validation_Method', 'Score',
        'BAM_File', 'Sequencer', 'HGVSp_Short', 't_ref_count', 't_alt_count',
        'n_ref_count', 'n_alt_count', 'Protein_position', 'Codons',
        'SWISSPROT', 'RefSeq', 't_depth', 'n_depth', 'FILTER',
        'gnomAD_AF', 'gnomAD_AFR_AF', 'gnomAD_AMR_AF', 'gnomAD_ASJ_AF',
        'gnomAD_EAS_AF', 'gnomAD_FIN_AF', 'gnomAD_NFE_AF', 'gnomAD_OTH_AF',
        'gnomAD_SAS_AF']
    maf_dict = {key: ['', '', ''] for key in keep_maf_columns}
    maf_dict['Center'] = ["foo", "dsdf", "sdf"]
    maf_dict['Tumor_Sample_Barcode'] = ["GENIE-SAGE-1-3", "1-2", "3-2"]
    maf_dict['Sequence_Source'] = ["3", "e", "sd"]
    maf_dict['Sequencer'] = ["dsf", "sdf", "d"]
    maf_dict['Validation_Status'] = ["Unknown", "unknown", "f"]
    maf_dict['not_there'] = ['', '', '']
    mafdf = pd.DataFrame(maf_dict)

    formatted_mafdf = maf_class.formatMAF(mafdf)

    expected_maf_dict = {key: ['', '', ''] for key in keep_maf_columns}
    expected_maf_dict['Center'] = ["SAGE", "SAGE", "SAGE"]
    expected_maf_dict['Tumor_Sample_Barcode'] = [
        "GENIE-SAGE-1-3", "GENIE-SAGE-1-2", "GENIE-SAGE-3-2"]
    expected_maf_dict['Sequence_Source'] = [float('nan'), float('nan'),
                                            float('nan')]
    expected_maf_dict['Sequencer'] = [float('nan'), float('nan'),
                                      float('nan')]
    expected_maf_dict['Validation_Status'] = ['', '', "f"]
    expected_mafdf = pd.DataFrame(expected_maf_dict)
    assert expected_mafdf.equals(formatted_mafdf[expected_mafdf.columns])


def test_invalidname_validateFilename():
    with pytest.raises(AssertionError):
        maf_class.validateFilename(['foo'])


def test_valid_validateFilename():
    assert maf_class.validateFilename([
        "data_mutations_extended_SAGE.txt"]) == "maf"


def test_perfect_validation():
    mafDf = pd.DataFrame(dict(
        CHROMOSOME=[1, 2, 3, 4, 5],
        START_POSITION=[1, 2, 3, 4, 2],
        REFERENCE_ALLELE=["A", "A", "A", "A", "A"],
        TUMOR_SAMPLE_BARCODE=["ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1"],
        T_ALT_COUNT=[1, 2, 3, 4, 3],
        T_DEPTH=[1, 2, 3, 4, 3],
        T_REF_COUNT=[1, 2, 3, 4, 3],
        N_DEPTH=[1, 2, 3, 4, 3],
        N_REF_COUNT=[1, 2, 3, 4, 3],
        N_ALT_COUNT=[1, 2, 3, 4, 3],
        TUMOR_SEQ_ALLELE2=["A", "A", "A", "A", "A"]))

    error, warning = maf_class._validate(mafDf)
    assert error == ""
    assert warning == ""
    error, warning = mafsp_class._validate(mafDf)
    assert error == ""
    assert warning == ""


def test_firstcolumn_validation():
    """Tests if first column isn't correct"""
    mafDf = pd.DataFrame({
        'REFERENCE_ALLELE': ["A", "B", "C", "D", "E"],
        "START_POSITION": [1, 2, 3, 4, 2],
        "CHROMOSOME": ["A", "A", "A", "A", "A"],
        "TUMOR_SAMPLE_BARCODE": ["ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1"],
        "T_ALT_COUNT": [1, 2, 3, 4, 3],
        "T_DEPTH": [1, 2, 3, 4, 3],
        "T_REF_COUNT": [1, 2, 3, 4, 3],
        "N_DEPTH": [1, 2, 3, 4, 3],
        "N_REF_COUNT": [1, 2, 3, 4, 3],
        "N_ALT_COUNT": [1, 2, 3, 4, 3],
        "TUMOR_SEQ_ALLELE2": ["A", "A", "A", "A", "A"]})
    order = ['REFERENCE_ALLELE', 'START_POSITION', 'CHROMOSOME',
             'TUMOR_SAMPLE_BARCODE', 'T_ALT_COUNT', 'T_DEPTH',
             'T_REF_COUNT', 'N_DEPTH', 'N_REF_COUNT', 'N_ALT_COUNT',
             'TUMOR_SEQ_ALLELE2']
    error, warning = maf_class._validate(mafDf[order])
    expectedErrors = ("Mutation File: First column header must be "
                      "one of these: CHROMOSOME, HUGO_SYMBOL, "
                      "TUMOR_SAMPLE_BARCODE.\n")
    assert error == expectedErrors
    assert warning == ""


def test_missingcols_validation():
    """Tests missing columns"""
    emptydf = pd.DataFrame()
    error, warning = maf_class._validate(emptydf)
    expected_errors = ("Mutation File: Must at least have these headers: "
                       "CHROMOSOME,START_POSITION,REFERENCE_ALLELE,"
                       "TUMOR_SAMPLE_BARCODE,T_ALT_COUNT,"
                       "TUMOR_SEQ_ALLELE2. "
                       "If you are writing your maf file with R, please make"
                       "sure to specify the 'quote=FALSE' parameter.\n"
                       "Mutation File: If you are missing T_DEPTH, "
                       "you must have T_REF_COUNT!\n")
    expected_warnings = ("Mutation File: Does not have the column headers "
                         "that can give extra information to the processed "
                         "mutation file: T_REF_COUNT, N_DEPTH, N_REF_COUNT, "
                         "N_ALT_COUNT.\n")
    assert error == expected_errors
    assert warning == expected_warnings


def test_errors_validation():
    mafDf = pd.DataFrame(dict(
        CHROMOSOME=[1, "chr2", "WT", 4, 5],
        START_POSITION=[1, 2, 3, 4, 2],
        REFERENCE_ALLELE=["NA", float('nan'), "A", "A", "A"],
        TUMOR_SAMPLE_BARCODE=["ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1"],
        TUMOR_SEQ_ALLELE2=["B", "B", "B", "B", "B"],
        T_ALT_COUNT=[1, 2, 3, 4, 3],
        T_DEPTH=[1, 2, 3, 4, 3],
        N_REF_COUNT=[1, 2, 3, 4, 3],
        N_ALT_COUNT=[1, 2, 3, 4, 3]))

    error, warning = maf_class._validate(mafDf)

    expectedErrors = ("Mutation File: "
                      "Cannot have any empty REFERENCE_ALLELE values.\n"
                      "Mutation File: "
                      "CHROMOSOME column cannot have any values that start "
                      "with 'chr' or any 'WT' values.\n")
    expectedWarnings = ("Mutation File: "
                        "Does not have the column headers that can give "
                        "extra information to the processed mutation file: "
                        "T_REF_COUNT, N_DEPTH.\n"
                        "Mutation File: "
                        "Your REFERENCE_ALLELE column contains NA values, "
                        "which cannot be placeholders for blank values.  "
                        "Please put in empty strings for blank values.\n")

    assert error == expectedErrors
    assert warning == expectedWarnings


def test_invalid_validation():
    mafDf = pd.DataFrame(dict(
        CHROMOSOME=[1, 2, 3, 4, 2, 4],
        T_ALT_COUNT=[1, 2, 3, 4, 3, 4],
        START_POSITION=[1, 2, 3, 4, 2, 4],
        REFERENCE_ALLELE=["A", "A", "A", "A", "A", "A"],
        TUMOR_SAMPLE_BARCODE=["ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1"],
        N_DEPTH=[1, 2, 3, 4, 3, 4],
        N_REF_COUNT=[1, 2, 3, 4, 3, 4],
        N_ALT_COUNT=[1, 2, 3, 4, 3, 4],
        TUMOR_SEQ_ALLELE2=["NA", float('nan'), "A", "A", "A", "A"]))

    error, warning = maf_class._validate(mafDf)

    expectedErrors = (
        "Mutation File: Should not have duplicate rows\n"
        "Mutation File: "
        "If you are missing T_DEPTH, you must have T_REF_COUNT!\n"
        "Mutation File: TUMOR_SEQ_ALLELE2 can't have any null values.\n")
    expectedWarnings = (
        "Mutation File: TUMOR_SEQ_ALLELE2 column contains 'NA' values, "
        "which cannot be placeholders for blank values.  "
        "Please put in empty strings for blank values.\n"
        "Mutation File: Does not have the column headers that can give "
        "extra information to the processed mutation file: T_REF_COUNT.\n")
    assert error == expectedErrors
    assert warning == expectedWarnings
