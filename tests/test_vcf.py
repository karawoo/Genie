import mock
import pytest

import pandas as pd
import synapseclient

from genie.vcf import vcf

syn = mock.create_autospec(synapseclient.Synapse)

vcfClass = vcf(syn, "SAGE")


def test_processing():
    pass


@pytest.mark.parametrize("filepath_list", [["foo"], ["GENIE-SAGE-ID1.bed"]])
def test_incorrect_validatefilename(filepath_list):
    with pytest.raises(AssertionError):
        vcfClass.validateFilename(filepath_list)


def test_validation():
    assert vcfClass.validateFilename(["GENIE-SAGE-ID1.vcf"]) == "vcf"

    vcfDf = pd.DataFrame({
        "#CHROM": ['2', '9', '12'],
        "POS": [69688533, 99401860, 53701241],
        "ID": ['AAK1', 'AAED1', 'AAAS'],
        "REF": ['AAK1', 'AAED1', 'AAAS'],
        "ALT": ['AAK1', 'AAED1', 'AAAS'],
        "QUAL": ['AAK1', 'AAED1', 'AAAS'],
        "FILTER": ['AAK1', 'AAED1', 'AAAS'],
        "INFO": ['AAK1', 'AAED1', 'AAAS']})

    error, warning = vcfClass._validate(vcfDf)
    assert error == ""
    assert warning == ""

    vcfDf = pd.DataFrame({
        "POS": [69688533, 99401860, 53701241],
        "ID": ['AAK1', 'AAED1', 'AAAS'],
        "REF": ['AAK1', 'AAED1', 'AAAS'],
        "ALT": ['AAK1', 'AAED1', 'AAAS'],
        "QUAL": ['AAK1', 'AAED1', 'AAAS'],
        "FILTER": ['AAK1', 'AAED1', 'AAAS'],
        "INFO": ['AAK1', 'AAED1', 'AAAS'],
        "FOO": ['AAK1', 'AAED1', 'AAAS'],
        "DOO": ['AAK1', 'AA ED1', 'AAAS']})

    error, warning = vcfClass._validate(vcfDf)
    expectedError = (
        "Your vcf file must have these headers: CHROM, POS, ID, REF, "
        "ALT, QUAL, FILTER, INFO.\n"
        "Your vcf file must have FORMAT header if genotype columns exist.\n")
    expectedWarning = (
        "Your vcf file should not have any white spaces "
        "in any of the columns.\n")
    assert error == expectedError
    assert warning == expectedWarning

    vcfDf = pd.DataFrame({"#CHROM": ['chr2', 'chrM', float('nan'), 'chr2'],
                          "POS": [69688533, 99401860, 53701241, 69688533],
                          "ID": ['AAK1', 'AAED1', 'AAAS', 'AAK1'],
                          "REF": ['AAK1', 'AAED1', 'AAAS', 'AAK1'],
                          "ALT": ['AAK1', 'AAED1', 'AAAS', 'AAK1'],
                          "QUAL": ['AAK1', 'AAED1', 'AAAS', 'AAK1'],
                          "FILTER": ['AAK1', 'AAED1', 'AAAS', 'AAK1'],
                          "INFO": ['AAK1', 'AAED1', 'AAAS', 'AAK1']})

    error, warning = vcfClass._validate(vcfDf)
    expectedError = ("Your vcf file should not have duplicate rows\n"
                     "Your vcf file may contain rows that are "
                     "space delimited instead of tab delimited.\n"
                     "Your vcf file must not have variants on chrM.\n")
    expectedWarning = ("Your vcf file should not have the chr prefix "
                       "in front of chromosomes.\n")
    assert error == expectedError
    assert warning == expectedWarning
