"""Process mutation files"""
import os
import shutil
import subprocess
import tempfile

import pandas as pd
import synapseclient
try:
    from synapesclient.exceptions import SynapseTimeoutError
except ModuleNotFoundError:
    from synapseclient.core.exceptions import SynapseTimeoutError

from . import process_functions

WORKDIR = os.path.expanduser("~/.synapseCache")
# Some columns are already capitalized, so they aren't included here
MAF_COL_MAPPING = {
    'HUGO_SYMBOL': 'Hugo_Symbol',
    'ENTREZ_GENE_ID': 'Entrez_Gene_Id',
    'CENTER': 'Center',
    'NCBI_BUILD': 'NCBI_Build',
    'CHROMOSOME': 'Chromosome',
    'START_POSITION': 'Start_Position',
    'END_POSITION': 'End_Position',
    'STRAND': 'Strand',
    'VARIANT_CLASSIFICATION': 'Variant_Classification',
    'VARIANT_TYPE': 'Variant_Type',
    'REFERENCE_ALLELE': 'Reference_Allele',
    'TUMOR_SEQ_ALLELE1': 'Tumor_Seq_Allele1',
    'TUMOR_SEQ_ALLELE2': 'Tumor_Seq_Allele2',
    'DBSNP_RS': 'dbSNP_RS',
    'DBSNP_VAL_STATUS': 'dbSNP_Val_Status',
    'TUMOR_SAMPLE_BARCODE': 'Tumor_Sample_Barcode',
    'MATCHED_NORM_SAMPLE_BARCODE': 'Matched_Norm_Sample_Barcode',
    'MATCH_NORM_SEQ_ALLELE1': 'Match_Norm_Seq_Allele1',
    'MATCH_NORM_SEQ_ALLELE2': 'Match_Norm_Seq_Allele2',
    'TUMOR_VALIDATION_ALLELE1': 'Tumor_Validation_Allele1',
    'TUMOR_VALIDATION_ALLELE2': 'Tumor_Validation_Allele2',
    'MATCH_NORM_VALIDATION_ALLELE1': 'Match_Norm_Validation_Allele1',
    'MATCH_NORM_VALIDATION_ALLELE2': 'Match_Norm_Validation_Allele2',
    'VERIFICATION_STATUS': 'Verification_Status',
    'VALIDATION_STATUS': 'Validation_Status',
    'MUTATION_STATUS': 'Mutation_Status',
    'SEQUENCING_PHASE': 'Sequencing_Phase',
    'SEQUENCE_SOURCE': 'Sequence_Source',
    'VALIDATION_METHOD': 'Validation_Method',
    'SCORE': 'Score',
    'BAM_FILE': 'BAM_File',
    'SEQUENCER': 'Sequencer',
    'T_REF_COUNT': 't_ref_count',
    'T_ALT_COUNT': 't_alt_count',
    'N_REF_COUNT': 'n_ref_count',
    'N_ALT_COUNT': 'n_alt_count',
    'COMMENTS': 'comments',
    'ALLELE': 'Allele',
    'AMINO_ACID_CHANGE': 'amino_acid_change',
    'AMINO_ACIDS': 'Amino_acids',
    'CDS_POSITION': 'CDS_position',
    'CODONS': 'Codons',
    'CONSEQUENCE': 'Consequence',
    'EXISTING_VARIATION': 'Existing_variation',
    'EXON_NUMBER': 'Exon_Number',
    'FEATURE': 'Feature',
    'FEATURE_TYPE': 'Feature_type',
    'GENE': 'Gene',
    'HGVSC': 'HGVSc',
    'HGVSP': 'HGVSp',
    'HGVSP_SHORT': 'HGVSp_Short',
    'HOTSPOT': 'Hotspot',
    'MA:FIMPACT': 'MA:FImpact',
    'MA:LINK.MSA': 'MA:link.MSA',
    'MA:LINK.PDB': 'MA:link.PDB',
    'MA:LINK.VAR': 'MA:link.var',
    'MA:PROTEIN.CHANGE': 'MA:protein.change',
    'POLYPHEN': 'PolyPhen',
    'PROTEIN_POSITION': 'Protein_position',
    'REFSEQ': 'RefSeq',
    'TRANSCRIPT': 'transcript',
    'TRANSCRIPT_ID': 'Transcript_ID',
    'ALL_EFFECTS': 'all_effects',
    'CDNA_CHANGE': 'cdna_change',
    'CDNA_POSITION': 'cDNA_position',
    'N_DEPTH': 'n_depth',
    'T_DEPTH': 't_depth'
}


def rename_column_headers(dataframe):
    """Rename dataframe column headers"""
    dataframe = dataframe.rename(columns=MAF_COL_MAPPING)
    return dataframe


def process_mutation_workflow(syn, center, mutation_files,
                              genie_annotation_pkg,
                              maf_tableid, flatfiles_synid):
    """Process vcf/maf workflow"""
    annotated_maf_path = annotate_mutation(
        center=center,
        mutation_files=mutation_files,
        genie_annotation_pkg=genie_annotation_pkg)

    # Split into narrow maf and store into db / flat file
    split_and_store_maf(syn=syn,
                        center=center,
                        maf_tableid=maf_tableid,
                        annotated_maf_path=annotated_maf_path,
                        flatfiles_synid=flatfiles_synid)

    return annotated_maf_path


def annotate_mutation(center: str, mutation_files: list,
                      genie_annotation_pkg: str) -> str:
    """Process vcf/maf files

    Args:
        center: Center name
        mutation_files: list of mutation files
        genie_annotation_pkg: Path to GENIE annotation package

    Returns:
        Path to final maf
    """
    input_files_dir = tempfile.mkdtemp(dir=WORKDIR)
    output_files_dir = tempfile.mkdtemp(dir=WORKDIR)

    for mutation_file in mutation_files:
        shutil.copyfile(mutation_file, input_files_dir)

    annotater_cmd = ['bash', os.path.join(genie_annotation_pkg,
                                          'annotation_suite_wrapper.sh'),
                     f'-i={input_files_dir}',
                     f'-o={output_files_dir}',
                     f'-m=data_mutations_extended_{center}.txt',
                     f'-c={center}',
                     '-s=WXS',
                     f'-p={genie_annotation_pkg}']

    subprocess.check_call(annotater_cmd)

    return os.path.join(output_files_dir,
                        "annotated", f"data_mutations_extended_{center}.txt")


def append_or_createdf(dataframe: 'DataFrame', filepath: str):
    """Creates a file with the dataframe or appends to a existing file.

    Args:
        df: pandas.dataframe to write out
        filepath: Filepath to append or create

    """
    if os.stat(filepath).st_size == 0:
        dataframe.to_csv(filepath, sep="\t", index=False)
    else:
        dataframe.to_csv(filepath, sep="\t", mode='a', index=False,
                         header=None)
    # write_or_append = "wb" if maf else "ab"
    # with open(filepath, write_or_append) as maf_file:
    #     maf_text = process_functions.removeStringFloat(maf_text)
    #     maf_file.write(maf_text.encode("utf-8"))


def store_full_maf(syn: 'Synapse', filepath: str, parentid: str):
    """Stores full maf file"""
    syn.store(synapseclient.File(filepath, parentId=parentid))


def store_narrow_maf(syn: 'Synapse', filepath: str, maf_tableid: str):
    '''
    Stores the processed maf
    There is a isNarrow option, but note that the number of rows
    of the maf file DOES NOT change in this function

    Args:
        filePath: Path to maf file
        mafSynId: database synid
        centerMafSynid: center flat file folder synid
        isNarrow: Is the file a narrow maf. Defaul to False.
    '''
    logger.info('STORING %s' % filepath)
    database = syn.get(maf_tableid)
    try:
        update_table = synapseclient.Table(database.id, filepath,
                                           separator="\t")
        syn.store(update_table)
    except SynapseTimeoutError:
        # This error occurs because of waiting for table to index.
        # Don't worry about this.
        pass


def format_maf(mafdf: 'DataFrame', center: str) -> 'DataFrame':
    """Format maf file, shortens the maf file length"""
    mafdf['Center'] = center
    mafdf['Tumor_Sample_Barcode'] = [
        process_functions.checkGenieId(i, center)
        for i in mafdf['Tumor_Sample_Barcode']
    ]

    mafdf['Sequence_Source'] = float('nan')
    mafdf['Sequencer'] = float('nan')
    mafdf['Validation_Status'][
        mafdf['Validation_Status'].isin(["Unknown", "unknown"])
    ] = ''

    return mafdf


def split_and_store_maf(syn: 'Synapse', center: str, maf_tableid: str,
                        annotated_maf_path: str, flatfiles_synid: str):
    """Separates annotated maf file into narrow and full maf and stores them

    Args:
        syn: Synapse connection
        center: Center
        maf_tableid: Mutation table synapse id
        annotated_maf_path: Annotated maf
        flatfiles_synid: GENIE flat files folder

    """
    narrow_maf_cols = [col['name']
                       for col in syn.getTableColumns(maf_tableid)
                       if col['name'] != 'inBED']
    full_maf_path = os.path.join(
        WORKDIR, center, "staging",
        f"data_mutations_extended_{center}_MAF.txt"
    )
    narrow_maf_path = os.path.join(
        WORKDIR, center, "staging",
        f"data_mutations_extended_{center}_MAF_narrow.txt"
    )
    maf_chunks = pd.read_csv(annotated_maf_path, chunksize=100000)

    for maf_chunk in maf_chunks:
        maf_chunk = format_maf(maf_chunk, center)
        append_or_createdf(maf_chunk, full_maf_path)
        narrow_maf_chunk = maf_chunk[narrow_maf_cols]
        append_or_createdf(narrow_maf_chunk, narrow_maf_path)

    store_narrow_maf(syn, narrow_maf_path, maf_tableid)
    # Store MAF flat file into synapse
    store_full_maf(syn, full_maf_path, flatfiles_synid)
