"""Tests database to staging functions"""
import os

import mock
from mock import patch
import pandas as pd
import synapseclient

from genie import database_to_staging

SYN = synapseclient.Synapse()
FILEVIEW_SYNID = "syn12345"
GENIE_VERSION = "vTEST"
CONSORTIUM_SYNID = "syn2222"


class Tablequerydf():
    """tableQuery.asDataFrame() class"""
    def __init__(self, df):
        self.df = df

    def asDataFrame(self):
        return self.df


def test_store_gene_panel_files():
    current_release_staging = False

    data_gene_panel = pd.DataFrame({'mutations': ['PANEL1']})
    gene_paneldf = pd.DataFrame({'id': ['syn3333']})

    with mock.patch.object(
            SYN, "tableQuery",
            return_value=Tablequerydf(gene_paneldf)) as patch_syn_table_query,\
         mock.patch.object(
             database_to_staging, "store_file",
             return_value=synapseclient.Entity()) as patch_storefile,\
         mock.patch.object(
             SYN, "get",
             return_value=synapseclient.Entity(
                 path="/foo/bar/PANEL1.txt")) as patch_syn_get,\
         mock.patch.object(os, "rename") as patch_os_rename:

        database_to_staging.store_gene_panel_files(SYN,
                                                   FILEVIEW_SYNID,
                                                   GENIE_VERSION,
                                                   data_gene_panel,
                                                   CONSORTIUM_SYNID,
                                                   ["TEST"])

        patch_syn_table_query.assert_called_once_with(
            "select id from %s where cBioFileFormat = 'genePanel' "
            "and fileStage = 'staging' and "
            "name not in ('data_gene_panel_TEST.txt')" % FILEVIEW_SYNID)

        patch_storefile.assert_called_once_with(
            SYN,
            os.path.join(database_to_staging.GENIE_RELEASE_DIR,
                         "PANEL1_vTEST.txt"),
            parent=CONSORTIUM_SYNID,
            genieVersion=GENIE_VERSION,
            name="PANEL1.txt",
            cBioFileFormat="genePanel")

        patch_syn_get.assert_called_once_with('syn3333')
        patch_os_rename.assert_called_once_with(
            "/foo/bar/PANEL1.txt",
            os.path.join(database_to_staging.GENIE_RELEASE_DIR,
                         "PANEL1_vTEST.txt"))


def test_store_assay_info_files():
    """Tests storing of assay information file"""
    assay_infodf = pd.DataFrame({'library_strategy': ['WXS'],
                                 'SEQ_ASSAY_ID': ['A']})
    clinicaldf = pd.DataFrame({'SEQ_ASSAY_ID': ['A']})
    database_to_staging.GENIE_RELEASE_DIR = "./"
    path = os.path.join(database_to_staging.GENIE_RELEASE_DIR,
                        "assay_information_vTEST.txt")
    with patch.object(SYN, "tableQuery",
                      return_value=Tablequerydf(assay_infodf)) as patch_table_query,\
         patch.object(database_to_staging, "store_file",
                      return_value=synapseclient.Entity()) as patch_storefile:
        wes_ids = database_to_staging.store_assay_info_files(SYN,
                                                             GENIE_VERSION,
                                                             FILEVIEW_SYNID,
                                                             clinicaldf,
                                                             CONSORTIUM_SYNID)
        patch_table_query.assert_called_once_with(
            "select * from {} where SEQ_ASSAY_ID "
            "in ('{}')".format(FILEVIEW_SYNID, 'A'))
        patch_storefile.assert_called_once_with(SYN, path,
                                                parent=CONSORTIUM_SYNID,
                                                genieVersion=GENIE_VERSION,
                                                name="assay_information.txt")
        assert wes_ids == ['A']
